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

# Marker lives in its own venv next to this script (see README).
MARKER_VENV = HERE / ".venv-marker"
MARKER_BIN = MARKER_VENV / ("Scripts" if IS_WIN else "bin")
# Marker 1.x needs Python 3.10-3.13 (it pins pillow<11); 2.x needs Docker or llama.cpp.
MARKER_PYTHONS = ("3.12", "3.13", "3.11", "3.10")
MARKER_PACKAGE = "marker-pdf<2"

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
    "marker_single": ('run pdf2epub again and answer y to "Set up Marker now?"',) * 2,
}

# Calibre treats short paragraphs like "Chapter 3", "PART ONE" or the spaced-out
# "C H A P T E R - 1" as chapter starts, and builds the table of contents from them.
CHAPTER_XPATH = (
    "//*[(name()='h1' or name()='h2' or name()='p') and string-length(.) < 60 and "
    "re:test(., '^\\s*(c\\s?h\\s?a\\s?p\\s?t\\s?e\\s?r|part|book|prologue|epilogue)\\b', 'i')]"
)
# A paragraph that contains nothing but a page number ("12", "Page 12", "12 of 300").
# Bare numbers are capped at 3 digits so a year on its own line ("1965") survives.
PAGE_NUMBER_REGEX = (
    r"(?i)<p[^>]*>\s*(?:<[^>]+>\s*)*(?:\d{1,3}|page\s+\d{1,4}|\d{1,4}\s+of\s+\d{1,4})"
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
    exe = name + (".exe" if IS_WIN else "")
    # Marker's venv comes first so an older global install (e.g. Marker 2.x) can't shadow it.
    local = MARKER_BIN / exe
    if local.is_file():
        return str(local)
    found = shutil.which(name)
    if found:
        return found
    candidates = list(FALLBACKS.get(name, []))
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


def find_marker_python():
    """Return a command that runs a Python Marker can install on, or None."""
    if (3, 10) <= sys.version_info[:2] <= (3, 13):
        return [sys.executable]
    for version in MARKER_PYTHONS:
        cmd = ["py", f"-{version}"] if IS_WIN else [f"python{version}"]
        if shutil.which(cmd[0]) and subprocess.run(
                cmd + ["--version"], capture_output=True).returncode == 0:
            return cmd
    return None


def setup_marker():
    """Create Marker's venv next to this script and install Marker into it."""
    python = find_marker_python()
    if not python:
        print("Marker needs Python 3.10-3.13. Install Python 3.12, then run pdf2epub again:")
        print("  " + ("winget install Python.Python.3.12" if IS_WIN else "brew install python@3.12"))
        return False
    try:
        print(f"  Creating {MARKER_VENV} ...")
        run(python + ["-m", "venv", str(MARKER_VENV)], "Creating the Marker environment")
        print("  Installing Marker (several GB; this can take 10+ minutes)...")
        run([str(MARKER_BIN / ("python.exe" if IS_WIN else "python")),
             "-m", "pip", "install", MARKER_PACKAGE], "Installing Marker")
    except ConversionError as e:
        print(f"  {e}")
        return False
    return True


def require(names):
    paths = {name: find_tool(name) for name in names}
    if "marker_single" in names and not paths["marker_single"] and \
            ask_yn("Marker is not set up. Set it up now (downloads several GB)?", False) and \
            setup_marker():
        paths["marker_single"] = find_tool("marker_single")
    missing = [name for name, path in paths.items() if not path]
    if missing:
        print("\nSome required tools are missing. Install them with:")
        for name in missing:
            hints = INSTALL_HINTS[name]
            print(f"  {name:14} {hints[1] if IS_MAC else hints[0]}")
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


def marker_models_cached():
    """True if Marker's models are already downloaded (platformdirs cache for "datalab")."""
    if IS_WIN:
        cache = Path(os.environ.get("LOCALAPPDATA", "")) / "datalab" / "datalab" / "Cache"
    elif IS_MAC:
        cache = Path.home() / "Library" / "Caches" / "datalab"
    else:
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "datalab"
    models = cache / "models"
    return models.is_dir() and any(models.iterdir())


def technical_warning():
    lines = ["  Note: technical books are converted by AI models running on this computer."]
    if IS_MAC:
        lines.append("  Marker uses the Apple Silicon GPU when it can, but a long book can still")
        lines.append("  take a long time, with no progress shown.")
    else:
        lines.append("  The standard Marker setup runs on the CPU (even if you have a GPU), so a")
        lines.append("  long book can take an hour or more, with no progress shown.")
    if not marker_models_cached():
        lines.append("  This first run also downloads about 3 GB of models.")
    print("\n".join(lines))


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


def run_marker(pdfs, tools, tmp):
    """Run Marker on all PDFs; return {pdf: markdown path or None}."""
    out_dir = Path(tmp) / "marker"
    batch = tools.get("marker") if len(pdfs) > 1 else None
    print(f"Running Marker on {len(pdfs)} book(s); this can take a long time. "
          "Leave this window open...")
    try:
        if batch:
            # One process for the whole batch, so the models are loaded only once.
            in_dir = Path(tmp) / "in"
            in_dir.mkdir()
            for pdf in pdfs:
                shutil.copy2(pdf, in_dir / pdf.name)
            run([batch, str(in_dir), "--output_dir", str(out_dir), "--workers", "1"], "Marker")
        else:
            for pdf in pdfs:
                run([tools["marker_single"], str(pdf), "--output_dir", str(out_dir)], "Marker")
    except ConversionError as e:
        print(f"  {e}")  # books Marker finished before the error are still converted
    return {pdf: next(iter(sorted((out_dir / pdf.stem).rglob("*.md"))), None) for pdf in pdfs}


def build_technical_epub(pdf, md, out, tools):
    if md is None:
        raise ConversionError("Marker produced no output.")
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
        tools["marker"] = find_tool("marker")
        technical_warning()
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
    with tempfile.TemporaryDirectory(prefix="pdf2epub-") as tmp:
        markdown = run_marker(list(outputs), tools, tmp) if technical else {}
        for i, (pdf, out) in enumerate(outputs.items(), 1):
            counter = "" if single else f"[{i}/{len(outputs)}] "
            print(f"{counter}Converting {pdf.name}...")
            try:
                if technical:
                    build_technical_epub(pdf, markdown[pdf], out, tools)
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
