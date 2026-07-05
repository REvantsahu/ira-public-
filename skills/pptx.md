# PPTX
description: Creating, editing, and reading PowerPoint presentations (.pptx files)
when_to_use: User mentions .pptx, slides, deck, presentation, or wants to create/edit/read a PowerPoint file

## Instructions
### Reading
Use `python-pptx` to extract text from slides:
```python
from pptx import Presentation
prs = Presentation("file.pptx")
for i, slide in enumerate(prs.slides):
    for shape in slide.shapes:
        if shape.has_text_frame:
            print(slide.text_frame.text)
```

### Creating from Scratch
Use `python-pptx`. Never create boring slides:
- Pick a bold color palette (60-70% dominant color, accent)
- Every slide needs a visual element (image, icon, shape, chart)
- Vary layouts across slides — don't repeat same layout
- Title: 36-44pt bold, Body: 14-16pt
- Left-align body text, center only titles
- NEVER use accent lines under titles (hallmark of AI slides)
- NEVER default to cream/beige backgrounds — use white or brand palette
- Check text overflow — if text doesn't fit, reduce size or split

### Editing Existing
1. Unpack PPTX (it's a ZIP of XML files)
2. Edit the XML in `ppt/slides/`
3. Repack as .pptx

### Design Ideas
- Two-column (text left, illustration right)
- Icon + text rows (icon in colored circle)
- Large stat callouts (big numbers 60-72pt)
- Before/after comparison columns
- Timeline or process flow

### QA
Always verify: extract-text output.pptx → check for missing content, placeholder text
Visual: convert to images → inspect for overlaps, overflow, misalignment

## Examples
- User: "make a pitch deck for my startup" → create PPTX with python-pptx
- User: "read this presentation" → extract text from slides
