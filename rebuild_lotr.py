#!/usr/bin/env python3
"""Extract text and images from a PDF into structured objects."""
import fitz
import os
from dataclasses import dataclass
from typing import List, Union

SRC = os.path.join(os.path.dirname(__file__), "risk-lord-of-the-rings-edition.pdf")
OUT = os.path.join(os.path.dirname(__file__), "rebuilt_lotr.pdf")


@dataclass
class TextObject:
    text: str
    bbox: tuple  # (x0, y0, x1, y1)
    fontsize: float
    fontname: str


@dataclass
class ImageObject:
    image_bytes: bytes
    bbox: tuple  # (x0, y0, x1, y1)
    xref: int


def extract_objects(src_path: str) -> dict:
    """Extract all objects from PDF, organized by page."""
    src = fitz.open(src_path)
    pages_data = {}
    extracted_xrefs = set()  # Track which images we've already extracted

    for pno in range(src.page_count):
        page = src.load_page(pno)
        page_objects: List[Union[TextObject, ImageObject]] = []
        
        rect = page.rect
        pd = page.get_text("dict")
        
        if not isinstance(pd, dict):
            # Still extract images even if no text dict
            try:
                for img_index in page.get_images():
                    xref = img_index[0]
                    if xref not in extracted_xrefs:
                        try:
                            img_info = src.extract_image(xref)
                            if img_info and img_info.get("image"):
                                page_objects.append(ImageObject(
                                    image_bytes=img_info.get("image"),
                                    bbox=(0, 0, rect.width, rect.height),
                                    xref=xref
                                ))
                                extracted_xrefs.add(xref)
                        except Exception:
                            pass
            except Exception:
                pass
            pages_data[pno] = page_objects
            continue

        bbox = (0, 0, rect.width, rect.height)  # Default bbox
        for b in pd.get("blocks", []):
            btype = b.get("type")
            bbox = tuple(b.get("bbox", [0, 0, rect.width, rect.height]))
            
            if btype == 0:
                # Text block
                lines = []
                for line in b.get("lines", []):
                    spans = [span.get("text", "") for span in line.get("spans", [])]
                    lines.append("".join(spans))
                text = "\n".join(lines).strip()
                
                if text:
                    page_objects.append(TextObject(
                        text=text,
                        bbox=bbox,
                        fontsize=11,
                        fontname="Times-Roman"
                    ))
            
            elif btype == 1:
                # Image block
                img_block = b.get("image")
                try:
                    xref = None
                    img_bytes = None
                    
                    if isinstance(img_block, dict):
                        xref = img_block.get("xref")
                        if xref and xref not in extracted_xrefs:
                            img_info = src.extract_image(xref)
                            img_bytes = img_info.get("image")
                    elif isinstance(img_block, int):
                        xref = img_block
                        if xref not in extracted_xrefs:
                            img_info = src.extract_image(img_block)
                            img_bytes = img_info.get("image")
                    elif isinstance(img_block, (bytes, bytearray)):
                        img_bytes = bytes(img_block)
                        xref = hash(img_bytes)
                    
                    if img_bytes and xref and xref not in extracted_xrefs:
                        page_objects.append(ImageObject(
                            image_bytes=img_bytes,
                            bbox=bbox,
                            xref=xref
                        ))
                        extracted_xrefs.add(xref)
                except Exception:
                    pass
        
        # Extract all remaining images from page that weren't in text blocks
        try:
            for img_index in page.get_images():
                xref = img_index[0]
                if xref not in extracted_xrefs:
                    try:
                        img_info = src.extract_image(xref)
                        if img_info and img_info.get("image"):
                            page_objects.append(ImageObject(
                                image_bytes=img_info.get("image"),
                                bbox=bbox,
                                xref=xref
                            ))
                            extracted_xrefs.add(xref)
                    except Exception:
                        pass
        except Exception:
            pass
        
        pages_data[pno] = page_objects

    src.close()
    return pages_data


def create_cheat_sheet(objects: dict, output_path: str = "lotr_risk_cheatsheet.txt"):
    """Extract important rules and create an organized cheat sheet."""
    with open(output_path, 'w') as f:
        f.write("=" * 70 + "\n")
        f.write("RISK: LORD OF THE RINGS - QUICK REFERENCE CHEAT SHEET\n")
        f.write("=" * 70 + "\n\n")
        
        # Collect all text by page
        all_text = {}
        for page_num in sorted(objects.keys()):
            page_text = []
            for obj in objects[page_num]:
                if isinstance(obj, TextObject):
                    page_text.append(obj.text.strip())
            if page_text:
                all_text[page_num] = "\n".join(page_text)
        
        # Write organized sections
        f.write("QUICK RULES OVERVIEW\n")
        f.write("-" * 70 + "\n")
        f.write("Players: 2-4 | Age: 10+\n\n")
        
        f.write("OBJECTIVE:\n")
        f.write("  Score points by controlling territories, regions, and completing missions\n")
        f.write("  Don't let the Fellowship reach Mount Doom!\n\n")
        
        f.write("THE 8 STEPS OF YOUR TURN:\n")
        f.write("  1. Receive and place reinforcements\n")
        f.write("  2. Combat (invade other territories)\n")
        f.write("  3. Fortify your position\n")
        f.write("  4. Collect a territory card (if you conquered)\n")
        f.write("  5. Collect an adventure card (if leader conquered)\n")
        f.write("  6. Replace a leader\n")
        f.write("  7. Try to find the Ring (EVIL only - if you control Ring's region, roll to find it)\n")
        f.write("  8. Move the Fellowship\n\n")
        
        f.write("REINFORCEMENTS TABLE:\n")
        f.write("  ┌─────────────────┬───────────────┐\n")
        f.write("  │ Territories     │ Reinforcements│\n")
        f.write("  ├─────────────────┼───────────────┤\n")
        f.write("  │ 1-11            │ 3             │\n")
        f.write("  │ 12-14           │ 4             │\n")
        f.write("  │ 15-17           │ 5             │\n")
        f.write("  │ 18-20           │ 6             │\n")
        f.write("  │ 21+             │ ÷3, round up  │\n")
        f.write("  └─────────────────┴───────────────┘\n")
        f.write("  Region Control: +7-11 pts per region\n")
        f.write("  Card Sets: 3 same type→bonus pts; Wild card can substitute\n\n")
        
        f.write("BATTALION VALUES:\n")
        f.write("  ┌────────────────┬─────────────┬────────────────┬─────────────┐\n")
        f.write("  │ Good Armies    │ Value       │ Evil Armies    │ Value       │\n")
        f.write("  ├────────────────┼─────────────┼────────────────┼─────────────┤\n")
        f.write("  │ Elven Archer   │ 1 battalion │ Orc            │ 1 battalion │\n")
        f.write("  │ Rider of Rohan │ 3 battalions│ Dark Rider     │ 3 battalions│\n")
        f.write("  │ Eagle          │ 5 battalions│ Cave Troll     │ 5 battalions│\n")
        f.write("  └────────────────┴─────────────┴────────────────┴─────────────┘\n\n")
        
        f.write("COMBAT RULES:\n")
        f.write("  - Need at least 2 battalions in territory to attack\n")
        f.write("  - Each side rolls 1 die per attacking/defending battalion\n")
        f.write("  - Compare highest die rolls (attacker needs tie to win)\n")
        f.write("  - Winner removes loser's battalion\n")
        f.write("  - Leaders add +1 to combat rolls\n")
        f.write("  - Continue until one side is eliminated\n\n")
        
        f.write("STRONGHOLDS & SITES OF POWER:\n")
        f.write("  Strongholds: +1 reinforcement (counted as part of region, not added)\n")
        f.write("  Sites of Power: +2 pts, but only if you control entire region\n\n")
        
        f.write("ADVENTURE CARDS:\n")
        f.write("  Mission: Complete by getting Leader to specified location\n")
        f.write("  Event: Play immediately for effect\n")
        f.write("  Power: Play during combat for advantage\n\n")
        
        f.write("SCORING:\n")
        f.write("  1 point per territory controlled\n")
        f.write("  2-4 pts per region controlled\n")
        f.write("  Card bonuses vary by card type\n")
        f.write("  Leaders completing missions earn points\n\n")
        
        f.write("WINNING:\n")
        f.write("  When Fellowship reaches Mount Doom, roll 1 die:\n")
        f.write("    - 3 or less: Fellowship fails, game continues\n")
        f.write("    - 4+: Fellowship succeeds, game ends, calculate final scores\n\n")
        
        f.write("=" * 70 + "\n")
        f.write("COMPLETE TEXT FOR REFERENCE:\n")
        f.write("=" * 70 + "\n\n")
        
        # Write full text for reference
        for page_num in sorted(all_text.keys()):
            f.write(f"\n--- PAGE {page_num + 1} ---\n\n")
            f.write(all_text[page_num])
            f.write("\n")
    
    print(f"✓ Cheat sheet created: {output_path}")


def extract_images(objects: dict, output_dir: str = "cheatsheet_images"):
    """Extract and save images from PDF to directory."""
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    image_paths = {}
    global_counter = 1
    for page_num in sorted(objects.keys()):
        for idx, obj in enumerate(objects[page_num]):
            if isinstance(obj, ImageObject):
                # Determine file extension
                # Try to detect format from bytes
                img_bytes = obj.image_bytes
                ext = "jpg"
                if img_bytes.startswith(b'\x89PNG'):
                    ext = "png"
                elif img_bytes.startswith(b'GIF'):
                    ext = "gif"
                
                filename = f"image_{global_counter:03d}.{ext}"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(img_bytes)
                
                image_paths[(page_num, idx)] = filepath
                print(f"  Extracted: {filename}")
                global_counter += 1
    
    return image_paths


def create_html_cheatsheet(objects: dict, output_path: str = "lotr_risk_cheatsheet.html"):
    """Create an HTML version of the cheat sheet with embedded images."""
    image_paths = extract_images(objects)
    
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>RISK: Lord of the Rings - Quick Reference</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 900px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        h1 { text-align: center; border-bottom: 3px solid #333; padding-bottom: 10px; }
        h2 { border-left: 4px solid #007bff; padding-left: 10px; margin-top: 20px; }
        table { border-collapse: collapse; margin: 10px 0; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
        th { background-color: #007bff; color: white; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .image-section { margin: 20px 0; text-align: center; }
        .image-section img { max-width: 100%; height: auto; border: 1px solid #ddd; margin: 10px 0; }
        ul { margin: 10px 0; padding-left: 20px; }
        li { margin: 5px 0; }
        .info-box { background: #e7f3ff; padding: 10px; border-left: 4px solid #2196F3; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>RISK: LORD OF THE RINGS - QUICK REFERENCE</h1>
        
        <h2>Quick Rules Overview</h2>
        <p><strong>Players:</strong> 2-4 | <strong>Age:</strong> 10+</p>
        
        <h2>Objective</h2>
        <p>Score points by controlling territories, regions, and completing missions. Don't let the Fellowship reach Mount Doom!</p>
        
        <h2>The 8 Steps of Your Turn</h2>
        <ol>
            <li>Receive and place reinforcements</li>
            <li>Combat (invade other territories)</li>
            <li>Fortify your position</li>
            <li>Collect a territory card (if you conquered)</li>
            <li>Collect an adventure card (if leader conquered)</li>
            <li>Replace a leader</li>
            <li>Try to find the Ring (EVIL only - if you control Ring's region, roll to find it)</li>
            <li>Move the Fellowship</li>
        </ol>
        
        <h2>Reinforcements Table</h2>
        <table>
            <tr>
                <th>Territories</th>
                <th>Reinforcements</th>
            </tr>
            <tr>
                <td>1-11</td>
                <td>3</td>
            </tr>
            <tr>
                <td>12-14</td>
                <td>4</td>
            </tr>
            <tr>
                <td>15-17</td>
                <td>5</td>
            </tr>
            <tr>
                <td>18-20</td>
                <td>6</td>
            </tr>
            <tr>
                <td>21+</td>
                <td>÷3, round up</td>
            </tr>
        </table>
        <ul>
            <li><strong>Region Control:</strong> +7-11 pts per region</li>
            <li><strong>Card Sets:</strong> 3 same type→bonus pts; Wild card can substitute</li>
        </ul>
        
        <h2>Battalion Values</h2>
        <table>
            <tr>
                <th colspan="2">Good Armies</th>
                <th colspan="2">Evil Armies</th>
            </tr>
            <tr>
                <th>Unit</th>
                <th>Value</th>
                <th>Unit</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Elven Archer</td>
                <td>1 battalion</td>
                <td>Orc</td>
                <td>1 battalion</td>
            </tr>
            <tr>
                <td>Rider of Rohan</td>
                <td>3 battalions</td>
                <td>Dark Rider</td>
                <td>3 battalions</td>
            </tr>
            <tr>
                <td>Eagle</td>
                <td>5 battalions</td>
                <td>Cave Troll</td>
                <td>5 battalions</td>
            </tr>
        </table>
        
        <h2>Combat Rules</h2>
        <ul>
            <li>Need at least 2 battalions in territory to attack</li>
            <li>Each side rolls 1 die per attacking/defending battalion</li>
            <li>Compare highest die rolls (attacker needs tie to win)</li>
            <li>Winner removes loser's battalion</li>
            <li>Leaders add +1 to combat rolls</li>
            <li>Continue until one side is eliminated</li>
        </ul>
        
        <h2>Strongholds & Sites of Power</h2>
        <div class="info-box">
            <p><strong>Strongholds:</strong> +1 reinforcement (counted as part of region, not added)</p>
            <p><strong>Sites of Power:</strong> +2 pts, but only if you control entire region</p>
        </div>
"""
    
    # Add images from page 3 (where Strongholds/Sites are shown)
    if any(key[0] == 2 for key in image_paths.keys()):  # Page 3 is index 2
        html += """        <h3>Visual Reference from Rulebook</h3>
        <div class="image-section">
"""
        for (page_num, idx), path in sorted(image_paths.items()):
            if page_num == 2:  # Page 3
                html += f'            <img src="{path}" alt="Strongholds and Sites of Power">\n'
        html += """        </div>
"""
    
    html += """
        <h2>Adventure Cards</h2>
        <ul>
            <li><strong>Mission:</strong> Complete by getting Leader to specified location</li>
            <li><strong>Event:</strong> Play immediately for effect</li>
            <li><strong>Power:</strong> Play during combat for advantage</li>
        </ul>
        
        <h2>Scoring</h2>
        <ul>
            <li>1 point per territory controlled</li>
            <li>2-4 pts per region controlled</li>
            <li>Card bonuses vary by card type</li>
            <li>Leaders completing missions earn points</li>
        </ul>
        
        <h2>Winning</h2>
        <p>When Fellowship reaches Mount Doom, roll 1 die:</p>
        <ul>
            <li><strong>3 or less:</strong> Fellowship fails, game continues</li>
            <li><strong>4+:</strong> Fellowship succeeds, game ends, calculate final scores</li>
        </ul>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w') as f:
        f.write(html)
    
    print(f"✓ HTML cheat sheet created: {output_path}")


def create_pdf_cheatsheet(output_path: str = "lotr_risk_cheatsheet.pdf"):
    """Create a PDF version of the cheat sheet - first two pages using PyMuPDF."""
    doc = fitz.open()  # Create new PDF
    
    # Page 1
    page1 = doc.new_page()
    
    x, y = 36, 36  # Start position (0.5 inch margins)
    line_height = 12
    
    # Title
    page1.insert_text((x, y), "RISK: LORD OF THE RINGS", fontsize=16, fontname="helv")
    y += line_height + 4
    page1.insert_text((x, y), "QUICK REFERENCE CHEAT SHEET", fontsize=16, fontname="helv")
    y += line_height * 2
    
    # Quick Overview
    page1.insert_text((x, y), "Quick Rules Overview", fontsize=11, fontname="helv")
    y += line_height
    page1.insert_text((x, y), "Players: 2-4  |  Age: 10+", fontsize=9)
    y += line_height * 1.5
    
    # Objective
    page1.insert_text((x, y), "Objective", fontsize=11, fontname="helv")
    y += line_height
    page1.insert_text((x, y), "Score points by controlling territories, regions, and completing", fontsize=9)
    y += line_height
    page1.insert_text((x, y), "missions. Don't let the Fellowship reach Mount Doom!", fontsize=9)
    y += line_height * 1.5
    
    # The 8 Steps
    page1.insert_text((x, y), "The 8 Steps of Your Turn", fontsize=11, fontname="helv")
    y += line_height
    steps = [
        "1. Receive and place reinforcements",
        "2. Combat (invade other territories)",
        "3. Fortify your position",
        "4. Collect a territory card (if you conquered)",
        "5. Collect an adventure card (if leader conquered)",
        "6. Replace a leader",
        "7. Try to find the Ring (EVIL only - if you control Ring's region)",
        "8. Move the Fellowship"
    ]
    for step in steps:
        page1.insert_text((x + 10, y), step, fontsize=9)
        y += line_height
    y += line_height
    
    # Reinforcements Table
    page1.insert_text((x, y), "Reinforcements Table", fontsize=11, fontname="helv")
    y += line_height + 4
    
    table_x = x
    table_y = y
    col_width = 100
    row_height = 16
    
    # Header
    page1.insert_text((table_x, table_y), "Territories", fontsize=8, fontname="helv")
    page1.insert_text((table_x + col_width, table_y), "Reinforcements", fontsize=8, fontname="helv")
    
    # Draw table border
    page1.draw_rect(fitz.Rect(table_x - 2, table_y - 10, table_x + col_width * 2, table_y + row_height * 6), color=0)
    
    # Data rows
    data = [
        ("1-11", "3"),
        ("12-14", "4"),
        ("15-17", "5"),
        ("18-20", "6"),
        ("21+", "÷3, round up")
    ]
    
    for i, (terr, rein) in enumerate(data):
        row_y = table_y + row_height * (i + 1)
        page1.insert_text((table_x + 5, row_y), terr, fontsize=8)
        page1.insert_text((table_x + col_width + 5, row_y), rein, fontsize=8)
        page1.draw_line(fitz.Point(table_x - 2, row_y + 8), fitz.Point(table_x + col_width * 2, row_y + 8), color=0)
    
    y = table_y + row_height * 6 + line_height
    page1.insert_text((x, y), "Region Control: +7-11 pts per region", fontsize=9)
    y += line_height
    page1.insert_text((x, y), "Card Sets: 3 same type→bonus pts; Wild card can substitute", fontsize=9)
    y += line_height * 1.5
    
    # Battalion Values
    page1.insert_text((x, y), "Battalion Values", fontsize=11, fontname="helv")
    y += line_height + 4
    
    battalion_data = [
        ("Good Armies", "Value", "Evil Armies", "Value"),
        ("Elven Archer", "1 battalion", "Orc", "1 battalion"),
        ("Rider of Rohan", "3 battalions", "Dark Rider", "3 battalions"),
        ("Eagle", "5 battalions", "Cave Troll", "5 battalions")
    ]
    
    col_width = 70
    table_y = y
    
    for i, row in enumerate(battalion_data):
        if i == 0:
            for j, text in enumerate(row):
                page1.insert_text((x + j * col_width, table_y), text, fontsize=8, fontname="helv")
        else:
            for j, text in enumerate(row):
                page1.insert_text((x + j * col_width, table_y), text, fontsize=8)
        table_y += row_height
    
    # PAGE 2
    page2 = doc.new_page()
    
    x, y = 36, 36
    
    # Combat Rules
    page2.insert_text((x, y), "Combat Rules", fontsize=11, fontname="helv")
    y += line_height
    
    combat_rules = [
        "Need at least 2 battalions in territory to attack",
        "Each side rolls 1 die per attacking/defending battalion",
        "Compare highest die rolls (attacker needs tie to win)",
        "Winner removes loser's battalion",
        "Leaders add +1 to combat rolls",
        "Continue until one side is eliminated"
    ]
    
    for rule in combat_rules:
        page2.insert_text((x + 10, y), rule, fontsize=9)
        y += line_height
    
    y += line_height
    
    # Strongholds & Sites
    page2.insert_text((x, y), "Strongholds & Sites of Power", fontsize=11, fontname="helv")
    y += line_height
    page2.insert_text((x + 10, y), "Strongholds: +1 reinforcement (counted as part of region)", fontsize=9)
    y += line_height
    page2.insert_text((x + 10, y), "Sites of Power: +2 pts, only if you control entire region", fontsize=9)
    y += line_height * 1.5
    
    # Adventure Cards
    page2.insert_text((x, y), "Adventure Cards", fontsize=11, fontname="helv")
    y += line_height
    page2.insert_text((x + 10, y), "Mission: Complete by getting Leader to specified location", fontsize=9)
    y += line_height
    page2.insert_text((x + 10, y), "Event: Play immediately for effect", fontsize=9)
    y += line_height
    page2.insert_text((x + 10, y), "Power: Play during combat for advantage", fontsize=9)
    y += line_height * 1.5
    
    # Scoring
    page2.insert_text((x, y), "Scoring", fontsize=11, fontname="helv")
    y += line_height
    
    scoring = [
        "1 point per territory controlled",
        "2-4 pts per region controlled",
        "Card bonuses vary by card type",
        "Leaders completing missions earn points"
    ]
    
    for score in scoring:
        page2.insert_text((x + 10, y), score, fontsize=9)
        y += line_height
    
    y += line_height
    
    # Winning
    page2.insert_text((x, y), "Winning", fontsize=11, fontname="helv")
    y += line_height
    page2.insert_text((x, y), "When Fellowship reaches Mount Doom, roll 1 die:", fontsize=9)
    y += line_height
    page2.insert_text((x + 10, y), "3 or less: Fellowship fails, game continues", fontsize=9)
    y += line_height
    page2.insert_text((x + 10, y), "4+: Fellowship succeeds, game ends, calculate final scores", fontsize=9)
    
    # Save PDF
    doc.save(output_path)
    doc.close()
    print(f"✓ PDF cheat sheet created: {output_path}")


if __name__ == "__main__":
    print(f"Source: {SRC}")
    objects = extract_objects(SRC)
    create_cheat_sheet(objects)
    create_html_cheatsheet(objects)
    create_pdf_cheatsheet()