#!/bin/bash
# Double-click in Finder to start. Run `chmod +x pdf2epub.command` once first.
python3 "$(dirname "$0")/pdf2epub.py" "$@"
read -n 1 -s -r -p "Press any key to close"
echo
