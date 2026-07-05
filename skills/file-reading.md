# File Reading
description: How to read different file types correctly — PDF, DOCX, XLSX, CSV, JSON, images, archives, code files
when_to_use: User gives you a file path to read and you don't know the format yet, or the file type needs special handling

## Instructions
1. Look at the file extension first — that decides your approach
2. For **PDF**: use read_pdf tool (never read raw). If scanned, use pytesseract OCR.
3. For **DOCX**: use read_docx tool. Legacy .doc needs LibreOffice conversion first.
4. For **XLSX**: use pandas with nrows=5 to peek. Never load full file blindly.
5. For **CSV/TSV**: use pandas with nrows=5. Check shape before full load.
6. For **JSON/JSONL**: use ConvertFrom-Json or jq to see structure first.
7. For **images** (jpg/png/gif/webp): you can see them directly as vision input.
8. For **archives** (zip/tar/gz): list contents first, never extract unless asked.
9. For **code/text/log files**: check size first. Under 20KB = full read, over = head+tail.
10. Always stat the file before reading large files — check size and last modified.

## Examples
- User: "read this file" + path → check extension → dispatch to right tool
- User: "what's in that CSV" → pandas read with nrows=5 + shape
