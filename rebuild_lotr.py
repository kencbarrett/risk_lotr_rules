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

    for pno in range(src.page_count):
        page = src.load_page(pno)
        page_objects: List[Union[TextObject, ImageObject]] = []
        
        rect = page.rect
        pd = page.get_text("dict")
        
        if not isinstance(pd, dict):
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
                        if xref:
                            img_info = src.extract_image(xref)
                            img_bytes = img_info.get("image")
                    elif isinstance(img_block, int):
                        xref = img_block
                        img_info = src.extract_image(img_block)
                        img_bytes = img_info.get("image")
                    elif isinstance(img_block, (bytes, bytearray)):
                        img_bytes = bytes(img_block)
                    
                    if img_bytes and xref:
                        page_objects.append(ImageObject(
                            image_bytes=img_bytes,
                            bbox=bbox,
                            xref=xref
                        ))
                except Exception:
                    pass
        
        # Also extract images directly from page xrefs
        # Get all image xrefs from the page
        try:
            for img_index in page.get_images():
                xref = img_index[0]
                try:
                    img_info = src.extract_image(xref)
                    if img_info and img_info.get("image"):
                        # Try to find bbox from text dict if available
                        found_bbox = bbox
                        for b in pd.get("blocks", []):
                            if b.get("type") == 1:
                                img_block = b.get("image")
                                if isinstance(img_block, dict) and img_block.get("xref") == xref:
                                    found_bbox = tuple(b.get("bbox", bbox))
                                elif isinstance(img_block, int) and img_block == xref:
                                    found_bbox = tuple(b.get("bbox", bbox))
                        
                        # Check if we haven't already added this image
                        img_bytes = img_info.get("image")
                        if img_bytes and not any(isinstance(obj, ImageObject) and obj.xref == xref for obj in page_objects):
                            page_objects.append(ImageObject(
                                image_bytes=img_bytes,
                                bbox=found_bbox,
                                xref=xref
                            ))
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
                
                filename = f"page{page_num + 1}_img{idx}.{ext}"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(img_bytes)
                
                image_paths[(page_num, idx)] = filepath
                print(f"  Extracted: {filename}")
    
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


if __name__ == "__main__":
    print(f"Source: {SRC}")
    objects = extract_objects(SRC)
    create_cheat_sheet(objects)
    create_html_cheatsheet(objects)