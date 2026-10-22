# pdf2epub

Convert PDFs to EPUB by answering a few y/n questions. It works on Windows and macOS, and everything runs on your computer.

- **Novels / prose** are converted with [Calibre](https://calibre-ebook.com).
- **Technical books** (tables, math, code) are converted with [Marker](https://github.com/datalab-to/marker) and [Pandoc](https://pandoc.org).

## One-time setup

You need Python 3.10 or newer. Install only what you need.

| | Windows (PowerShell) | macOS (Terminal, with [Homebrew](https://brew.sh)) |
|---|---|---|
| Prose books | `winget install calibre.calibre` | `brew install --cask calibre` |
| Technical books | `winget install JohnMacFarlane.Pandoc`, then install Marker (below) | `brew install pandoc python@3.12`, then install Marker (below) |
| Validation (optional) | `winget install EclipseAdoptium.Temurin.21.JRE`, then put `epubcheck.jar` from [epubcheck releases](https://github.com/w3c/epubcheck/releases) in an `epubcheck` folder next to `pdf2epub.py` | `brew install epubcheck` |

### Installing Marker

**The easy way:** convert a technical book and answer **y** to *"Marker is not set up. Set it up now?"*. pdf2epub
creates a `.venv-marker` folder next to `pdf2epub.py` and installs Marker into it.

Marker needs Python 3.10–3.13; it does not install on 3.14 yet. If you have neither, install Python 3.12 first with
`winget install Python.Python.3.12` (Windows) or `brew install python@3.12` (macOS). Marker also pulls in PyTorch,
which is several GB; keeping it in its own folder keeps it out of your main Python. pdf2epub always uses this copy
of Marker, even if another one is installed elsewhere.

pdf2epub installs Marker 1.x (`marker-pdf<2`). Marker 2.0 needs Docker or a separate llama.cpp server to run its
models, while 1.x runs them directly in Python.

To set it up by hand instead, run these one at a time inside the `pdf2epub` folder.

Windows (PowerShell or Command Prompt):

```
py -3.12 -m venv .venv-marker
.venv-marker\Scripts\python -m pip install "marker-pdf<2"
```

macOS:

```
python3.12 -m venv .venv-marker
.venv-marker/bin/python -m pip install 'marker-pdf<2'
```

> **Technical conversions are slow.** Marker runs AI models on your computer. On Windows, the standard setup runs on
> the CPU, even if you have an NVIDIA GPU. A long book can take **an hour or more** (a 110-page programming book took
> about an hour on a 14th-gen Core i7), and pdf2epub shows no progress while Marker runs, so leave the window open.
> The first run also downloads about 3 GB of models. On a Mac, Marker uses the Apple Silicon GPU when it can.
> Prose books through Calibre take seconds.
>
> When you convert a folder, Marker processes all the books in one run, so it loads its models only once.

On macOS, run `chmod +x pdf2epub.command` once so you can double-click the launcher.

## Use

Double-click `pdf2epub.bat` (Windows) or `pdf2epub.command` (macOS), or drag PDFs onto the launcher. You can also run:

```
python pdf2epub.py
```

```
PDF file or folder: ~/Books/My Book.pdf
Is this a technical book (tables, math, code)? [y/N]:
Remove stray page numbers? [Y/n]:
Save as "My Book.epub" next to the PDF? [Y/n]:
Validate the result with epubcheck? [Y/n]:
Converting My Book.pdf...
  done -> ~/Books/My Book.epub
  epubcheck: OK
Convert another file? [y/N]:
```

Press **Enter** to accept the default, which is the capital letter. By default the EPUB gets the same name as the
PDF and is saved in the same folder.

- **Whole folder:** give a folder instead of a file. The questions are asked once and applied to every PDF in it.
- **No questions:** `python pdf2epub.py "My Book.pdf" --yes` accepts every default (prose, same name, no overwrite).

## Tips

- If a prose book comes out messy, such as tables turned into word soup, convert it again as a technical book, and vice versa.
- Scanned PDFs (page images with no text) need OCR first. Marker does OCR automatically, so use the technical option.
- Pages packed with equations or diagrams may never reflow well. For those books, your reader's built-in PDF reflow mode may work better.
