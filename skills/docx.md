# DOCX
description: Creating, reading, and editing Word documents (.docx files)
when_to_use: User mentions Word doc, .docx, report, memo, letter, or wants a formatted document

## Instructions
### Reading
Use `python-docx`:
```python
from docx import Document
doc = Document("file.docx")
text = "\n".join(p.text for p in doc.paragraphs)
```

### Creating New Documents
Use `python-docx`. Key rules:
- Always set page size explicitly — default is A4, set to Letter (12240 x 15840 DXA) for US docs
- Never use `\n` — use separate paragraphs
- NEVER use Unicode bullets (•) — use python-docx numbering API
- Always use WidthType.DXA for table widths (percentages break in Google Docs)
- Table width = sum of columnWidths
- Always set cell margins for readability
- Use ShadingType.CLEAR not SOLID for table shading
- PageBreak must be inside a Paragraph

### Editing Existing Documents
1. Unpack the .docx (it's a ZIP)
2. Edit XML in `word/document.xml`
3. Repack

### Tracked Changes
Use `<w:ins>` for insertions, `<w:del>` for deletions with `<w:delText>`.
For rejecting another author's changes: nest `<w:del>` inside their `<w:ins>`.

### Converting .doc to .docx
Use LibreOffice: `soffice --headless --convert-to docx document.doc`

### Headers/Footers/Page Numbers
```python
from docx import Document
from docx.enum.section import WD_ORIENT
section = doc.sections[0]
header = section.header
footer = section.footer
```

## Examples
- User: "write a report" → python-docx with proper formatting
- User: "edit this Word doc" → python-docx or unpack-edit-repack
