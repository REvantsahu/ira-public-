# PDF
description: Reading, creating, merging, splitting, and editing PDF files
when_to_use: User mentions .pdf, PDF, wants to extract text from, merge, split, create, or fill PDF forms

## Instructions
### Reading Text
Use `pypdf` (PdfReader) or `pdfplumber` (better for layout + tables):
```python
from pypdf import PdfReader
reader = PdfReader("file.pdf")
text = "".join(page.extract_text() for page in reader.pages)
```

For tables: use pdfplumber's `page.extract_tables()`

### Scanned PDFs (OCR)
```python
from pdf2image import convert_from_path
import pytesseract
images = convert_from_path("scanned.pdf")
text = "".join(pytesseract.image_to_string(img) for img in images)
```

### Creating PDFs
Use `reportlab`:
- Letter size: 12240 x 15840 DXA
- Never use Unicode subscripts/superscripts (render as black boxes in built-in fonts) — use reportlab XML tags `<sub>` and `<super>` instead
- For simple text: canvas.drawString()
- For multi-page: SimpleDocTemplate + Platypus

### Merging PDFs
```python
from pypdf import PdfWriter, PdfReader
writer = PdfWriter()
for pdf in ["a.pdf", "b.pdf"]:
    for page in PdfReader(pdf).pages:
        writer.add_page(page)
writer.write("merged.pdf")
```

### Other Operations
- Split: one page per file using PdfWriter
- Rotate: `page.rotate(90)`
- Watermark: `page.merge_page(watermark)`
- Encrypt: `writer.encrypt("password")`
- CLI: qpdf for fast merge/split/rotate

## Examples
- User: "extract text from this PDF" → pdfplumber or pypdf
- User: "merge these PDFs" → pypdf PdfWriter
- User: "create a PDF report" → reportlab
