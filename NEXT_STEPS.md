## ✅ Goal: Generate a **PDF cheatsheet** directly (instead of HTML) using `fitz` (PyMuPDF)

Since you already have `fitz` in use for extraction, the cleanest path is to **create a new PDF file from scratch** with `fitz.Document()` and use its drawing/texture APIs to lay out the cheatsheet content. This lets you design a readable “handout” format (paged, styled, possibly with images) without being constrained by HTML/CSS.

---

## 1) Decide what content the PDF should contain (layout + sections)

A good cheatsheet PDF can be structured like:

1. **Cover / Title page**
   - Big title (“RISK: LORD OF THE RINGS — Quick Reference”)
   - Optional subtitle (players, age, etc.)

2. **Quick Rules / Overview**
   - Players, age, goal (brief)
   - Key “Game Components” block (strongholds, sites, leaders, cards, etc.)

3. **Turn sequence (8 steps)** — embed the relevant details inline  
   - Reinforcement rules + table reference  
   - Card set rules + how Adventure cards work  
   - Finding the Ring rules  
   - Fellowship movement rules  
   - Note any “common gotchas” (stronghold placement, mandatory card turn-in)

4. **Reference tables**
   - Reinforcement table (territory count → reinforcements)
   - Battalion values table
   - Combat bonus table
   - Optional: “Scoring” / “Winning” summary

5. **Optional: Visual reference pages**
   - Insert extracted images (maps, piece layouts) on later pages, if helpful

---

## 2) Technical plan: build the PDF with `fitz` (PyMuPDF)

### ✅ 2.1 Create the PDF skeleton
- `pdf = fitz.Document()`
- `page = pdf.new_page(width=…, height=…)` (e.g., A4 or letter)

### ✅ 2.2 Define typography + layout utilities
- Set base fonts: `font = "helv"` or `pdf.insert_font(...)`  
- Define common sizes: `title_size`, `h2_size`, `body_size`
- Define a “text box” helper that:
  - Takes a rectangle (x0, y0, x1, y1)
  - Uses `page.insert_textbox(rect, text, fontname=..., fontsize=..., align=...)`
  - Returns the bottom Y coordinate so you can flow text vertically

### ✅ 2.3 Add structured sections
- Add title block (centered)
- Add “Quick Rules Overview” and “Game Components” as separate text boxes
- For the “8 steps” section:
  - Use nested indentation by using line prefixes like `•`, `  -`, etc.
  - Use `insert_textbox` to wrap automatically within a fixed width

### ✅ 2.4 Add tables and boxed callouts
- Use `page.draw_rect(...)` and `page.draw_line(...)` to draw simple tables
- Use `insert_textbox` inside each table cell
- Alternatively: render a text-based ASCII table using a monospace font (easier if you want minimal drawing code)

### ✅ 2.5 Add images (optional but powerful)
- Use `page.insert_image(rect, stream=img_bytes)` where `img_bytes` comes from your extracted images
- Layout: reserve one or more pages with a simple grid (e.g., 2–3 images per row)

### ✅ 2.6 Save output
- `pdf.save("lotr_risk_cheatsheet.pdf")`

---

## 3) Where you can reuse existing code/data
- You already have `create_cheat_sheet()` producing the text content—**reuse its string blocks** as the source for the PDF text, instead of rewriting everything (or generate the PDF content from the same data structures).
- You already extract/comment on objects and images, so you can:
  - Grab `objects` from `extract_objects()`
  - Use `extract_images()` to generate images (or directly use extracted image bytes)
  - Place those images into the PDF

---

## 4) Example implementation outline (pseudocode)

```python
import fitz

def create_pdf_cheatsheet(objects, output_path="lotr_risk_cheatsheet.pdf"):
    pdf = fitz.Document()
    page = pdf.new_page()

    # helper
    def add_text(page, rect, text, font="helv", size=11, align=0):
        page.insert_textbox(rect, text, fontname=font, fontsize=size, align=align)

    # Title
    add_text(page, fitz.Rect(30, 30, 560, 90), "RISK: LORD OF THE RINGS", size=24, align=1)

    # Game Components (use your existing “Game Components” text)
    add_text(page, fitz.Rect(30, 110, 560, 260), game_components_text, size=10)

    # Steps (with inline reinforcement/card/ring notes)
    add_text(page, fitz.Rect(30, 270, 560, 520), turn_steps_text, size=10)

    # ... etc ...

    pdf.save(output_path)
```

---

## 5) Next decision: presentation style
To make the PDF feel like a polished “cheatsheet”, you can choose one of these formats:

- **Simple “text-first” layout**: mostly text + small boxes / bold headers (fastest to implement)
- **“Card-style” layout**: each major section on a separate page, with side panels for tables (more work but cleaner)
- **“Board-style” layout**: simulate a “cheat sheet card” with a specific page aspect ratio (e.g., 5x7 or 8.5x11) and use columns

---

## ✅ What I need from you next (pick one)
1. **Do you want the PDF to follow the same *exact* content/order as the current text cheatsheet** (just rendered as PDF), or  
2. **Do you want a redesigned layout** (e.g., one page per major section, more visuals, clearer table formatting)?