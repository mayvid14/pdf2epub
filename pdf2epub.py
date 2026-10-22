#!/usr/bin/env python3
"""pdf2epub - convert PDFs to EPUB by answering a few y/n questions.

Usage:
    python pdf2epub.py                  # asks for a file or folder
    python pdf2epub.py "My Book.pdf"    # or pass it (drag-and-drop works)
    python pdf2epub.py Books/ --yes     # accept every default, no questions

Prose books go through Calibre; technical books (tables, math, code) go
through Marker + Pandoc. Everything runs locally on Windows and macOS.
"""

import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# Default install locations, used when a tool is not on PATH.
FALLBACKS = {
    "ebook-convert": [
        r"C:\Program Files\Calibre2\ebook-convert.exe",
        r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
        "/Applications/calibre.app/Contents/MacOS/ebook-convert",
    ],
    "pandoc": [
        os.path.expandvars(r"%LOCALAPPDATA%\Pandoc\pandoc.exe"),
        r"C:\Program Files\Pandoc\pandoc.exe",
        "/opt/homebrew/bin/pandoc",
        "/usr/local/bin/pandoc",
    ],
    "epubcheck": ["/opt/homebrew/bin/epubcheck", "/usr/local/bin/epubcheck"],
}

INSTALL_HINTS = {
    "ebook-convert": ("winget install calibre.calibre", "brew install --cask calibre"),
    "pandoc": ("winget install JohnMacFarlane.Pandoc", "brew install pandoc"),
    "marker_single": (
        "py install 3.12; py -V:3.12 -m venv .venv-marker; "
        ".venv-marker\\Scripts\\pip install \"marker-pdf<2\"   (run in the pdf2epub folder)",
        "python3.12 -m venv .venv-marker && .venv-marker/bin/pip install 'marker-pdf<2'"
        "   (run in the pdf2epub folder)",
    ),
}

# Calibre treats short paragraphs like "Chapter 3", "PART ONE" or the spaced-out
# "C H A P T E R - 1" as chapter starts, and builds the table of contents from them.
CHAPTER_XPATH = (
    "//*[(name()='h1' or name()='h2' or name()='p') and string-length(.) < 60 and "
    "re:test(., '^\\s*(c\\s?h\\s?a\\s?p\\s?t\\s?e\\s?r|part|book|prologue|epilogue)\\b', 'i')]"
)
# A paragraph that contains nothing but a page number ("12", "Page 12", "12 of 300").
PAGE_NUMBER_REGEX = (
    r"(?i)<p[^>]*>\s*(?:<[^>]+>\s*)*(?:page\s+)?\d{1,4}(?:\s+of\s+\d{1,4})?"
    r"\s*(?:</[^>]+>\s*)*</p>"
)


class ConversionError(Exception):
    pass


# --- prompts --------------------------------------------------------------

ASSUME_DEFAULTS = False


def ask_yn(question, default):
    """Ask a y/n question; Enter picks the default (shown in capitals)."""
    if ASSUME_DEFAULTS:
        return default
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"{question} {hint}: ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please type y or n (or press Enter for the default).")


def ask_text(question):
    while True:
        answer = input(f"{question}: ").strip()
        if answer:
            return answer


def clean_path(text):
    """Turn typed or drag-and-dropped text into a Path."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1]
    elif not IS_WIN:
        text = re.sub(r"\\(.)", r"\1", text)  # macOS Terminal escapes spaces as "\ "
    return Path(text).expanduser()


# --- tools ----------------------------------------------------------------

def find_tool(name):
    found = shutil.which(name)
    if found:
        return found
    candidates = list(FALLBACKS.get(name, []))
    exe = name + (".exe" if IS_WIN else "")
    # Marker's own venv next to this script (see README), then this Python's scripts.
    candidates.append(str(HERE / ".venv-marker" / ("Scripts" if IS_WIN else "bin") / exe))
    scripts = sysconfig.get_path("scripts")
    if scripts:
        candidates.append(os.path.join(scripts, exe))
    return next((c for c in candidates if os.path.isfile(c)), None)


def find_epubcheck():
    """Return the command prefix that runs epubcheck, or None."""
    exe = find_tool("epubcheck")
    if exe:
        return [exe]
    jar = os.environ.get("EPUBCHECK_JAR") or HERE / "epubcheck" / "epubcheck.jar"
    java = shutil.which("java")
    if java and Path(jar).is_file():
        return [java, "-jar", str(jar)]
    return None


def require(names):
    paths = {name: find_tool(name) for name in names}
    missing = [name for name, path in paths.items() if not path]
    if missing:
        print("\nSome required tools are missing. Install them with:")
        for name in missing:
            win, mac = INSTALL_HINTS[name]
            print(f"  {name:14} {mac if IS_MAC else win}")
        print("Then open a new terminal and run pdf2epub again.")
        sys.exit(1)
    return paths


def run(cmd, what):
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-5:]
        raise ConversionError(f"{what} failed:\n    " + "\n    ".join(tail))
    return result


# --- converters -----------------------------------------------------------

def convert_prose(pdf, out, tools, strip_page_numbers):
    cmd = [
        tools["ebook-convert"], str(pdf), str(out),
        "--epub-version", "3",
        "--enable-heuristics",  # includes line unwrapping and dehyphenation
        "--html-unwrap-factor", "0.45",
        "--chapter", CHAPTER_XPATH,
        "--chapter-mark", "pagebreak",
        "--level1-toc", CHAPTER_XPATH,
        # PDF title fields are often junk ("Microsoft Word - draft3.doc"); the file name is better.
        "--title", pdf.stem,
    ]
    if strip_page_numbers:
        cmd += ["--sr1-search", PAGE_NUMBER_REGEX, "--sr1-replace", ""]
    run(cmd, "Calibre")


def convert_technical(pdf, out, tools):
    with tempfile.TemporaryDirectory(prefix="pdf2epub-") as tmp:
        print("  Running Marker; this can take a long time. Leave this window open...")
        run([tools["marker_single"], str(pdf), "--output_dir", tmp], "Marker")
        markdown = sorted(Path(tmp).rglob("*.md"))
        if not markdown:
            raise ConversionError("Marker produced no output.")
        md = markdown[0]
        # Newer Marker versions emit <math> tags; Pandoc wants $...$ to build MathML.
        text = md.read_text(encoding="utf-8")
        text = re.sub(r'<math display="block">(.*?)</math>', r"$$\1$$", text, flags=re.S)
        text = re.sub(r"<math[^>]*>(.*?)</math>", r"$\1$", text, flags=re.S)
        md.write_text(text, encoding="utf-8")
        run([
            tools["pandoc"], str(md), "-f", "markdown", "-o", str(out),
            "--mathml", "--toc",
            "--css", str(HERE / "technical.css"),
            "--resource-path", str(md.parent),
            "--metadata", f"title={pdf.stem}",
        ], "Pandoc")


def validate(out, epubcheck):
    result = subprocess.run(epubcheck + [str(out)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode == 0:
        return "epubcheck: OK"
    errors = [l for l in (result.stdout + result.stderr).splitlines()
              if l.startswith(("ERROR", "FATAL"))]
    shown = "\n    ".join(errors[:5]) or "see epubcheck output"
    return f"epubcheck: {len(errors)} problem(s)\n    {shown}"


# --- main flow ------------------------------------------------------------

def collect_pdfs(source):
    if source.is_dir():
        return sorted(p for p in source.iterdir()
                      if p.is_file() and p.suffix.lower() == ".pdf")
    if source.is_file() and source.suffix.lower() == ".pdf":
        return [source]
    return []


def choose_outputs(pdfs, single):
    """Return {pdf: epub path}. Default is the same name next to the PDF."""
    if single:
        default = pdfs[0].with_suffix(".epub")
        prompt = f'Save as "{default.name}" next to the PDF?'
    else:
        prompt = "Save each EPUB next to its PDF, with the same name?"
    if ask_yn(prompt, True):
        return {p: p.with_suffix(".epub") for p in pdfs}

    target = clean_path(ask_text("Output folder" + (" or .epub file" if single else "")))
    if single and target.suffix.lower() == ".epub":
        target.parent.mkdir(parents=True, exist_ok=True)
        return {pdfs[0]: target}
    target.mkdir(parents=True, exist_ok=True)
    return {p: target / (p.stem + ".epub") for p in pdfs}


def convert_batch(source):
    pdfs = collect_pdfs(source)
    if not pdfs:
        print(f"No PDF found at {source}")
        return
    single = len(pdfs) == 1
    if not single:
        print(f"Found {len(pdfs)} PDFs in {source}")

    technical = ask_yn("Is this a technical book (tables, math, code)?"
                       if single else "Are these technical books (tables, math, code)?",
                       False)
    tools = require(["marker_single", "pandoc"] if technical else ["ebook-convert"])
    if technical:
        print("  Note: technical books are converted by AI models running on this computer.\n"
              "  Without a supported GPU this is slow: a long book can take an hour or more,\n"
              "  with no progress shown. The first run also downloads about 3 GB of models.")
    strip_page_numbers = False if technical else ask_yn("Remove stray page numbers?", True)
    outputs = choose_outputs(pdfs, single)

    existing = [o for o in outputs.values() if o.exists()]
    if existing:
        what = f'"{existing[0].name}" already exists.' if len(existing) == 1 \
            else f"{len(existing)} EPUBs already exist."
        if not ask_yn(f"{what} Overwrite?", False):
            outputs = {p: o for p, o in outputs.items() if not o.exists()}
            if not outputs:
                print("Nothing to convert.")
                return

    epubcheck = find_epubcheck()
    check = bool(epubcheck) and ask_yn("Validate the result with epubcheck?", True)

    failed = []
    for i, (pdf, out) in enumerate(outputs.items(), 1):
        counter = "" if single else f"[{i}/{len(outputs)}] "
        print(f"{counter}Converting {pdf.name}...")
        try:
            if technical:
                convert_technical(pdf, out, tools)
            else:
                convert_prose(pdf, out, tools, strip_page_numbers)
        except ConversionError as e:
            failed.append(pdf)
            print(f"  {e}")
            continue
        print(f"  done -> {out}")
        if check:
            print(f"  {validate(out, epubcheck)}")

    if failed:
        print(f"\n{len(failed)} of {len(outputs)} failed: " + ", ".join(p.name for p in failed))
        print("Tip: if a book keeps failing, try the other book type, or read it with "
              "your e-reader's built-in PDF reflow mode.")
    elif not single:
        print(f"\nAll {len(outputs)} converted.")


def main():
    global ASSUME_DEFAULTS
    args = sys.argv[1:]
    if "--yes" in args or "-y" in args:
        ASSUME_DEFAULTS = True
        args = [a for a in args if a not in ("--yes", "-y")]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return
    if ASSUME_DEFAULTS and not args:
        print("--yes needs a PDF file or folder to convert.")
        sys.exit(2)

    sources = [clean_path(a) for a in args]
    while True:
        if not sources:
            sources = [clean_path(ask_text("PDF file or folder"))]
        for source in sources:
            convert_batch(source)
        sources = []
        if ASSUME_DEFAULTS or not ask_yn("\nConvert another file?", False):
            break


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(130)
