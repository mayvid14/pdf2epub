# pdf2epub

Convert PDFs to EPUB by answering a few y/n questions. It works on Windows and macOS, and everything runs on your computer.

- **Novels / prose** are converted with [Calibre](https://calibre-ebook.com).
- **Technical books** (tables, math, code) are converted with [Marker](https://github.com/datalab-to/marker) and [Pandoc](https://pandoc.org).

## One-time setup

You need Python 3.10 or newer. Install only what you need.

| | Windows (PowerShell) | macOS (Terminal, with [Homebrew](https://brew.sh)) |
|---|---|---|
| Prose books | `winget install calibre.calibre` | `brew install --cask calibre` |
| Technical books | `winget install JohnMacFarlane.Pandoc`, then `pip install marker-pdf` | `brew install pandoc`, then `pip3 install marker-pdf` |
| Validation (optional) | `winget install EclipseAdoptium.Temurin.21.JRE`, then put `epubcheck.jar` from [epubcheck releases](https://github.com/w3c/epubcheck/releases) in an `epubcheck` folder next to `pdf2epub.py` | `brew install epubcheck` |

The first technical conversion downloads Marker's models (a few GB). Marker uses an NVIDIA GPU or Apple Silicon if
one is available. Otherwise it runs on the CPU, which is slower.

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
