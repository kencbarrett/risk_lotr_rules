#!/usr/bin/env python3
"""Extract text and images from a PDF into structured objects."""
import fitz
import os
import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Union, Dict

SRC = os.path.join(os.path.dirname(__file__), "risk-lord-of-the-rings-edition.pdf")
OUT = os.path.join(os.path.dirname(__file__), "rebuilt_lotr.pdf")


@dataclass
class TextObject:
    text: str
    bbox: tuple  # (x0, y0, x1, y1)
    fontsize: float
    fontname: str
    color: int  # Add color field


@dataclass
class ImageObject:
    image_bytes: bytes
    bbox: tuple  # (x0, y0, x1, y1)
    xref: int


def extract_objects(src_path: str) -> tuple:
    """Extract all objects from PDF, organized by page."""
    src = fitz.open(src_path)
    pages_data = {}
    extracted_xrefs = set()  # Track which images we've already extracted
    blue_text = []  # Collect blue text across all pages

    for pno in range(src.page_count):
        page = src.load_page(pno)
        page_objects: List[Union[TextObject, ImageObject]] = []
        
        rect = page.rect
        pd = page.get_text("dict")
        
        bbox = (0, 0, rect.width, rect.height)  # Default bbox
        for b in pd.get("blocks", []):
            btype = b.get("type")
            bbox = tuple(b.get("bbox", [0, 0, rect.width, rect.height]))
            
            if btype == 0:
                # Text block
                lines = []
                for line in b.get("lines", []):
                    spans = []
                    for span in line.get("spans", []):
                        color = span.get("color", 0)
                        text = span.get("text", "")
                        if color == 2301728:  # Blue color
                            blue_text.append(text)
                        spans.append(text)
                    lines.append("".join(spans))
                text = "\n".join(lines).strip()
                
                if text:
                    page_objects.append(TextObject(
                        text=text,
                        bbox=bbox,
                        fontsize=11,
                        fontname="Times-Roman",
                        color=0  # Default, or compute from spans if needed
                    ))
        
        # Extract images using page.get_images() - more reliable method
        image_list = page.get_images()
        if image_list:
            print(f"  Page {pno + 1}: Found {len(image_list)} images")
            for img_info in image_list:
                xref = img_info[0]  # First element is xref
                if xref and xref not in extracted_xrefs:
                    try:
                        pix = fitz.Pixmap(src, xref)
                        # Use proper PNG encoding
                        if pix.n - pix.alpha < 4:  # GRAY or RGB
                            image_bytes = pix.tobytes("png")
                        else:  # CMYK
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                            image_bytes = pix.tobytes("png")
                        
                        if image_bytes and len(image_bytes) > 0:
                            page_objects.append(ImageObject(
                                image_bytes=image_bytes,
                                bbox=bbox,
                                xref=xref
                            ))
                            extracted_xrefs.add(xref)
                            print(f"    Extracted image xref {xref}")
                        else:
                            print(f"    Warning: Could not encode image xref {xref}: empty bytes")
                    except Exception as e:
                        print(f"    Warning: Could not extract image xref {xref}: {e}")
        
        pages_data[pno] = page_objects

    src.close()
    return pages_data, blue_text

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
                
                try:
                    with open(filepath, 'wb') as f:
                        bytes_written = f.write(img_bytes)
                    
                    if bytes_written > 0:
                        image_paths[(page_num, idx)] = filepath
                        print(f"  Extracted: {filename} ({bytes_written} bytes)")
                    else:
                        print(f"  Warning: {filename} has 0 bytes")
                except Exception as e:
                    print(f"  Error writing {filename}: {e}")
                
                global_counter += 1
    
    print(f"✓ Total images extracted: {len(image_paths)}")
    return image_paths


def segment_composite_images(image_dir: str = "cheatsheet_images", output_dir: str = "cheatsheet_images/pieces"):
    """Segment composite images into individual pieces using contour detection."""
    # Delete existing pieces to force re-segmentation
    if os.path.exists(output_dir):
        import shutil
        shutil.rmtree(output_dir)
        print(f"  Deleted existing pieces folder")
    
    os.makedirs(output_dir, exist_ok=True)
    piece_paths = {}  # Maps piece identity to file path
    
    if not os.path.exists(image_dir):
        print(f"  Warning: {image_dir} does not exist")
        return piece_paths
    
    images = [f for f in sorted(os.listdir(image_dir)) if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not os.path.isdir(os.path.join(image_dir, f))]
    print(f"  Found {len(images)} images to segment")
    
    piece_counter = 1
    for filename in images:
        filepath = os.path.join(image_dir, filename)
        
        try:
            # Read image
            img = cv2.imread(filepath)
            if img is None:
                print(f"    ✗ {filename}: Could not read")
                continue
            
            print(f"    Processing: {filename} ({img.shape[1]}x{img.shape[0]})")
            
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Try different thresholds to find best segmentation
            thresholds_to_try = [
                ("Otsu", lambda: cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]),
                ("Fixed 200", lambda: cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]),
                ("Fixed 100", lambda: cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)[1]),
                ("Fixed 150", lambda: cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)[1]),
            ]
            
            thresh = None
            used_method = None
            
            for method_name, threshold_func in thresholds_to_try:
                try:
                    thresh = threshold_func()
                    used_method = method_name
                    break
                except Exception as e:
                    print(f"      Threshold {method_name} failed: {e}")
                    continue
            
            if thresh is None:
                print(f"    ✗ {filename}: All thresholds failed")
                continue
            
            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            print(f"      Found {len(contours)} contours with {used_method}")
            
            # Filter contours by size - dynamic threshold based on image size
            img_area = gray.shape[0] * gray.shape[1]
            min_area = max(200, img_area // 200)
            print(f"      Min area threshold: {min_area} (image area: {img_area})")
            
            valid_contours = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area >= min_area:
                    valid_contours.append(contour)
            
            print(f"      Valid contours after filtering: {len(valid_contours)}")
            
            if len(valid_contours) == 0:
                print(f"      → No pieces found (try adjusting min_area)")
                continue
            
            for contour in sorted(valid_contours, key=lambda c: cv2.boundingRect(c)[0]):  # Sort left to right
                x, y, w, h = cv2.boundingRect(contour)
                
                # Extract piece with some padding
                padding = 5
                x_start = max(0, x - padding)
                y_start = max(0, y - padding)
                x_end = min(img.shape[1], x + w + padding)
                y_end = min(img.shape[0], y + h + padding)
                
                piece = img[y_start:y_end, x_start:x_end]
                
                # Save piece
                piece_filename = f"piece_{piece_counter:04d}.png"
                piece_filepath = os.path.join(output_dir, piece_filename)
                cv2.imwrite(piece_filepath, piece)
                
                piece_paths[piece_counter] = piece_filepath
                piece_counter += 1
            
            print(f"    ✓ Extracted {len(valid_contours)} pieces from {filename}")
        
        except Exception as e:
            print(f"    ✗ {filename}: {e}")
    
    print(f"  Total pieces extracted: {len(piece_paths)}")
    return piece_paths


def create_html_cheatsheet(objects: dict, output_path: str = "lotr_risk_cheatsheet.html"):
    """Create an HTML version of the cheat sheet with embedded images."""
    piece_paths = segment_composite_images()
    
    # Map pieces to battalion types (adjust based on actual piece extraction order)
    # These are placeholder mappings - you may need to adjust based on actual piece order
    good_piece_map = {
        "Elven Archer": piece_paths.get(1, ""),
        "Rider of Rohan": piece_paths.get(2, ""),
        "Eagle": piece_paths.get(3, "")
    }
    evil_piece_map = {
        "Orc": piece_paths.get(4, ""),
        "Dark Rider": piece_paths.get(5, ""),
        "Cave Troll": piece_paths.get(6, "")
    }
    
    # Build battalion tables with images
    good_battalion_rows = ""
    for unit, image_path in good_piece_map.items():
        if unit == "Elven Archer":
            value = "1 battalion"
        elif unit == "Rider of Rohan":
            value = "3 battalions"
        else:
            value = "5 battalions"
        
        img_html = f'<img src="{image_path}" style="max-width: 60px; height: auto;">' if image_path else "N/A"
        good_battalion_rows += f"""            <tr>
                <td>{unit}</td>
                <td>{value}</td>
                <td>{img_html}</td>
            </tr>
"""
    
    evil_battalion_rows = ""
    for unit, image_path in evil_piece_map.items():
        if unit == "Orc":
            value = "1 battalion"
        elif unit == "Dark Rider":
            value = "3 battalions"
        else:
            value = "5 battalions"
        
        img_html = f'<img src="{image_path}" style="max-width: 60px; height: auto;">' if image_path else "N/A"
        evil_battalion_rows += f"""            <tr>
                <td>{unit}</td>
                <td>{value}</td>
                <td>{img_html}</td>
            </tr>
"""
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>RISK: Lord of the Rings - Quick Reference</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        h1 {{ text-align: center; border-bottom: 3px solid #333; padding-bottom: 10px; }}
        h2 {{ border-left: 4px solid #007bff; padding-left: 10px; margin-top: 20px; }}
        table {{ border-collapse: collapse; margin: 10px 0; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
        th {{ background-color: #007bff; color: white; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .image-section {{ margin: 20px 0; text-align: center; }}
        .image-section img {{ max-width: 100%; height: auto; border: 1px solid #ddd; margin: 10px 0; }}
        ul {{ margin: 10px 0; padding-left: 20px; }}
        li {{ margin: 5px 0; }}
        .info-box {{ background: #e7f3ff; padding: 10px; border-left: 4px solid #2196F3; margin: 10px 0; }}
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
                <th colspan="3">Good Armies</th>
                <th colspan="3">Evil Armies</th>
            </tr>
            <tr>
                <th>Unit</th>
                <th>Value</th>
                <th>Image</th>
                <th>Unit</th>
                <th>Value</th>
                <th>Image</th>
            </tr>
            <tr>
                <td>Elven Archer</td>
                <td>1 battalion</td>
                <td><img src="{good_piece_map.get('Elven Archer', '')}" style="max-width: 60px; height: auto;"></td>
                <td>Orc</td>
                <td>1 battalion</td>
                <td><img src="{evil_piece_map.get('Orc', '')}" style="max-width: 60px; height: auto;"></td>
            </tr>
            <tr>
                <td>Rider of Rohan</td>
                <td>3 battalions</td>
                <td><img src="{good_piece_map.get('Rider of Rohan', '')}" style="max-width: 60px; height: auto;"></td>
                <td>Dark Rider</td>
                <td>3 battalions</td>
                <td><img src="{evil_piece_map.get('Dark Rider', '')}" style="max-width: 60px; height: auto;"></td>
            </tr>
            <tr>
                <td>Eagle</td>
                <td>5 battalions</td>
                <td><img src="{good_piece_map.get('Eagle', '')}" style="max-width: 60px; height: auto;"></td>
                <td>Cave Troll</td>
                <td>5 battalions</td>
                <td><img src="{evil_piece_map.get('Cave Troll', '')}" style="max-width: 60px; height: auto;"></td>
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
</html>"""
    
    with open(output_path, 'w') as f:
        f.write(html)
    
    print(f"✓ HTML cheat sheet created: {output_path}")


def create_pdf_cheatsheet(output_path: str = "lotr_risk_cheatsheet.pdf"):
    """Create a PDF version of the cheat sheet - first two pages using PyMuPDF."""
    piece_paths = segment_composite_images()
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


def save_blue_text_as_txt(blue_text: list, output_path: str = "blue_text.txt"):
    """Save collected blue text to a text file."""
    with open(output_path, 'w') as f:
        f.write("Blue Text Extracted from PDF:\n\n")
        f.write("\n".join(blue_text))
    print(f"✓ Blue text saved as text: {output_path}")


def save_blue_text_as_html(blue_text: list, output_path: str = "blue_text.html"):
    """Save collected blue text to an HTML file."""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Blue Text from PDF</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .blue-text {{ color: blue; }}
    </style>
</head>
<body>
    <h1>Blue Text Extracted from PDF</h1>
    <div class="blue-text">
        {"<br>".join(blue_text)}
    </div>
</body>
</html>"""
    with open(output_path, 'w') as f:
        f.write(html)
    print(f"✓ Blue text saved as HTML: {output_path}")


if __name__ == "__main__":
    print(f"Source: {SRC}")
    objects, blue_text = extract_objects(SRC)
    create_cheat_sheet(objects)
    create_html_cheatsheet(objects)
    create_pdf_cheatsheet()
    save_blue_text_as_txt(blue_text)
    save_blue_text_as_html(blue_text)