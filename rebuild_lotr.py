#!/usr/bin/env python3
"""Extract text and images from a PDF into structured objects."""
import fitz
import os
import shutil
import logging
import sys
from dataclasses import dataclass
from typing import List, Union, Optional, Dict

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

SRC = os.path.join(os.path.dirname(__file__), "risk-lord-of-the-rings-edition.pdf")
OUT = os.path.join(os.path.dirname(__file__), "rebuilt_lotr.pdf")


@dataclass
class TextObject:
    text: str
    bbox: tuple  # (x0, y0, x1, y1)
    fontsize: float
    fontname: str
    page_num: int  # Add page number for reference


@dataclass
class ImageObject:
    image_bytes: bytes
    bbox: tuple  # (x0, y0, x1, y1)
    xref: int
    page_num: int  # Add page number for reference
    width: Optional[int] = None
    height: Optional[int] = None
    ext: Optional[str] = None  # Image format extension


def extract_text_from_block(block: dict) -> Optional[str]:
    """Extract text from a text block."""
    lines = []
    for line in block.get("lines", []):
        spans = [span.get("text", "") for span in line.get("spans", [])]
        line_text = "".join(spans)
        if line_text.strip():
            lines.append(line_text)
    return "\n".join(lines).strip() if lines else None


def get_font_info_from_block(block: dict) -> tuple:
    """Extract font size and name from block spans."""
    fontsize = 11.0  # Default
    fontname = "Times-Roman"  # Default
    
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            if "size" in span:
                fontsize = span["size"]
            if "font" in span:
                fontname = span["font"]
            if fontsize != 11.0 and fontname != "Times-Roman":
                break
        if fontsize != 11.0 and fontname != "Times-Roman":
            break
    
    return fontsize, fontname


def extract_objects(src_path: str, extract_page_images: bool = False) -> dict:
    """
    Extract all objects from PDF, organized by page.
    
    Args:
        src_path: Path to source PDF
        extract_page_images: If True, also extract full page images
    
    Returns:
        Dictionary mapping page numbers to lists of TextObject and ImageObject
    """
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"PDF file not found: {src_path}")
    
    src = fitz.open(src_path)
    pages_data = {}
    seen_xrefs = set()  # Track extracted images to avoid duplicates

    logger.info(f"Extracting objects from {src.page_count} pages...")
    
    for pno in range(src.page_count):
        page = src.load_page(pno)
        page_objects: List[Union[TextObject, ImageObject]] = []
        rect = page.rect
        
        try:
            pd = page.get_text("dict")
        except Exception as e:
            logger.warning(f"Page {pno + 1}: Failed to extract text dict: {e}")
            pd = {}
        
        if not isinstance(pd, dict):
            pages_data[pno] = page_objects
            continue

        # Extract text blocks
        for b in pd.get("blocks", []):
            btype = b.get("type")
            bbox = tuple(b.get("bbox", [0, 0, rect.width, rect.height]))
            
            if btype == 0:  # Text block
                text = extract_text_from_block(b)
                if text:
                    fontsize, fontname = get_font_info_from_block(b)
                    page_objects.append(TextObject(
                        text=text,
                        bbox=bbox,
                        fontsize=fontsize,
                        fontname=fontname,
                        page_num=pno
                    ))
            
            elif btype == 1:  # Image block
                img_block = b.get("image")
                xref = None
                
                try:
                    if isinstance(img_block, dict):
                        xref = img_block.get("xref")
                    elif isinstance(img_block, int):
                        xref = img_block
                    
                    if xref and xref not in seen_xrefs:
                        img_info = src.extract_image(xref)
                        img_bytes = img_info.get("image")
                        
                        if img_bytes:
                            seen_xrefs.add(xref)
                            page_objects.append(ImageObject(
                                image_bytes=img_bytes,
                                bbox=bbox,
                                xref=xref,
                                page_num=pno,
                                width=img_info.get("width"),
                                height=img_info.get("height"),
                                ext=img_info.get("ext", "jpg")
                            ))
                except Exception as e:
                    logger.warning(f"Page {pno + 1}: Failed to extract image block: {e}")
        
        # Extract images directly from page (fallback for images not in blocks)
        try:
            for img_index in page.get_images():
                xref = img_index[0]
                
                if xref in seen_xrefs:
                    continue
                
                try:
                    img_info = src.extract_image(xref)
                    if img_info and img_info.get("image"):
                        img_bytes = img_info.get("image")
                        
                        # Try to find bbox from text dict if available
                        found_bbox = None
                        for b in pd.get("blocks", []):
                            if b.get("type") == 1:
                                img_block = b.get("image")
                                if isinstance(img_block, dict) and img_block.get("xref") == xref:
                                    found_bbox = tuple(b.get("bbox", [0, 0, rect.width, rect.height]))
                                    break
                                elif isinstance(img_block, int) and img_block == xref:
                                    found_bbox = tuple(b.get("bbox", [0, 0, rect.width, rect.height]))
                                    break
                        
                        # Use page dimensions if bbox not found
                        if found_bbox is None:
                            found_bbox = (0, 0, rect.width, rect.height)
                        
                        seen_xrefs.add(xref)
                        page_objects.append(ImageObject(
                            image_bytes=img_bytes,
                            bbox=found_bbox,
                            xref=xref,
                            page_num=pno,
                            width=img_info.get("width"),
                            height=img_info.get("height"),
                            ext=img_info.get("ext", "jpg")
                        ))
                except Exception as e:
                    logger.warning(f"Page {pno + 1}: Failed to extract image xref {xref}: {e}")
        except Exception as e:
            logger.warning(f"Page {pno + 1}: Failed to get page images: {e}")
        
        # Optionally extract full page image
        if extract_page_images:
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
                page_img_bytes = pix.tobytes("png")
                page_objects.append(ImageObject(
                    image_bytes=page_img_bytes,
                    bbox=(0, 0, rect.width, rect.height),
                    xref=-1,  # Special marker for page images
                    page_num=pno,
                    width=pix.width,
                    height=pix.height,
                    ext="png"
                ))
            except Exception as e:
                logger.warning(f"Page {pno + 1}: Failed to extract page image: {e}")
        
        pages_data[pno] = page_objects
        img_count = sum(1 for obj in page_objects if isinstance(obj, ImageObject))
        text_count = sum(1 for obj in page_objects if isinstance(obj, TextObject))
        logger.info(f"Page {pno + 1}: {text_count} text blocks, {img_count} images")

    src.close()
    return pages_data


def categorize_image(image_obj: ImageObject, page_text: str = "") -> str:
    """
    Categorize images based on context.
    Returns: 'map', 'card', 'piece', 'diagram', 'other'
    """
    # Use bbox size and position as hints
    bbox = image_obj.bbox
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    
    # Large images are likely maps or full-page content
    if width > 2000 or height > 2000:
        return "map"
    
    # Small, square-ish images might be game pieces or cards
    if 200 < width < 500 and 200 < height < 500:
        aspect_ratio = width / height if height > 0 else 1
        if 0.6 < aspect_ratio < 1.4:
            return "card"
        return "piece"
    
    # Medium images might be diagrams
    if 500 < width < 1500 or 500 < height < 1500:
        return "diagram"
    
    return "other"


def is_image_empty(image_bytes: bytes, filter_empty: bool = True) -> bool:
    """
    Check if an image is mostly empty/background using OpenCV.
    
    Args:
        image_bytes: Raw image bytes
        filter_empty: Whether to actually perform the check (if False, returns False)
    
    Returns:
        True if image appears to be empty/background only
    """
    if not filter_empty:
        return False
    
    try:
        import cv2
        import numpy as np
        
        # Convert bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        
        if img is None:
            return True
        
        # Convert to grayscale if needed
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        
        # Check variance - low variance means mostly uniform (likely background)
        variance = np.var(gray)
        if variance < 10.0:
            return True
        
        # Check for mostly white/light pixels (> 240)
        light_pixels = np.sum(gray > 240)
        light_ratio = light_pixels / gray.size
        if light_ratio > 0.95:
            return True
        
        # Check for mostly dark pixels (< 15)
        dark_pixels = np.sum(gray < 15)
        dark_ratio = dark_pixels / gray.size
        if dark_ratio > 0.95:
            return True
        
        # Use edge detection to check for content
        edges = cv2.Canny(gray, 50, 100)
        edge_pixels = np.sum(edges > 0)
        edge_ratio = edge_pixels / edges.size
        
        # If very few edges, likely just background
        if edge_ratio < 0.05:
            return True
        
        return False
    except ImportError:
        # OpenCV not available, skip filtering
        logger.debug("OpenCV not available, skipping empty image detection")
        return False
    except Exception as e:
        logger.debug(f"Error checking if image is empty: {e}")
        return False  # Don't filter on error


def extract_images(objects: dict, output_dir: str = "cheatsheet_images", 
                   categorize: bool = False, min_size: int = 50,
                   filter_empty: bool = True, clear_output: bool = True) -> Dict[tuple, str]:
    """
    Extract and save images from PDF to directory.
    
    Args:
        objects: Dictionary of page objects
        output_dir: Output directory for images
        categorize: If True, organize images into subdirectories
        min_size: Minimum width or height in pixels to extract (filters tiny icons)
        filter_empty: If True, filter out empty/background-only images
        clear_output: If True, clear output directory before extracting
    
    Returns:
        Dictionary mapping (page_num, idx) to filepath
    """
    # Clear output directory if requested
    if clear_output and os.path.exists(output_dir):
        logger.info(f"Clearing output directory: {output_dir}")
        shutil.rmtree(output_dir)
    
    os.makedirs(output_dir, exist_ok=True)
    
    if categorize:
        for cat in ["maps", "cards", "pieces", "diagrams", "other"]:
            os.makedirs(os.path.join(output_dir, cat), exist_ok=True)
    
    image_paths = {}
    page_text_cache = {}  # Cache page text for categorization
    
    for page_num in sorted(objects.keys()):
        # Get page text for categorization
        if categorize:
            page_text = " ".join([
                obj.text for obj in objects[page_num] 
                if isinstance(obj, TextObject)
            ])
            page_text_cache[page_num] = page_text
        
        for idx, obj in enumerate(objects[page_num]):
            if isinstance(obj, ImageObject):
                # Filter out tiny images (likely decorative icons)
                bbox = obj.bbox
                img_width = bbox[2] - bbox[0]
                img_height = bbox[3] - bbox[1]
                
                if img_width < min_size and img_height < min_size:
                    logger.debug(f"Skipping tiny image on page {page_num + 1}: {img_width}x{img_height}")
                    continue
                
                # Filter out empty/background-only images
                if filter_empty and is_image_empty(obj.image_bytes, filter_empty=True):
                    logger.debug(f"Skipping empty/background image on page {page_num + 1}: {img_width}x{img_height}")
                    continue
                
                # Determine file extension
                ext = obj.ext or "jpg"
                if not obj.image_bytes.startswith(b'\x89PNG'):
                    if obj.image_bytes.startswith(b'GIF'):
                        ext = "gif"
                    elif obj.image_bytes.startswith(b'\xff\xd8'):
                        ext = "jpg"
                    else:
                        # Try to detect from first bytes
                        ext = "png" if obj.ext == "png" else "jpg"
                
                # Generate filename
                if obj.xref == -1:  # Page image
                    filename = f"page{page_num + 1}_full.{ext}"
                else:
                    filename = f"page{page_num + 1}_img{idx}_{obj.xref}.{ext}"
                
                # Add category to path if categorizing
                if categorize:
                    category = categorize_image(obj, page_text_cache.get(page_num, ""))
                    filepath = os.path.join(output_dir, category, filename)
                else:
                    filepath = os.path.join(output_dir, filename)
                
                try:
                    with open(filepath, 'wb') as f:
                        f.write(obj.image_bytes)
                    
                    image_paths[(page_num, idx)] = filepath
                    size_kb = len(obj.image_bytes) / 1024
                    logger.info(f"  Extracted: {filename} ({size_kb:.1f} KB)")
                except Exception as e:
                    logger.error(f"  Failed to save {filename}: {e}")
    
    return image_paths


def create_cheat_sheet(objects: dict, output_path: str = "lotr_risk_cheatsheet.txt"):
    """Extract important rules and create an organized cheat sheet."""
    with open(output_path, 'w', encoding='utf-8') as f:
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
    
    logger.info(f"✓ Cheat sheet created: {output_path}")


def create_html_cheatsheet(objects: dict, output_path: str = "lotr_risk_cheatsheet.html",
                          include_all_images: bool = True, filter_empty: bool = True):
    """Create an HTML version of the cheat sheet with embedded images."""
    image_paths = extract_images(objects, filter_empty=filter_empty)
    
    # Collect images by page for better organization
    images_by_page = {}
    for (page_num, idx), path in image_paths.items():
        if page_num not in images_by_page:
            images_by_page[page_num] = []
        images_by_page[page_num].append((idx, path))
    
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RISK: Lord of the Rings - Quick Reference</title>
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background: #f5f5f5; 
            line-height: 1.6;
        }
        .container { 
            max-width: 1000px; 
            margin: 0 auto; 
            background: white; 
            padding: 30px; 
            border-radius: 8px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 { 
            text-align: center; 
            border-bottom: 3px solid #333; 
            padding-bottom: 10px; 
            color: #2c3e50;
        }
        h2 { 
            border-left: 4px solid #007bff; 
            padding-left: 10px; 
            margin-top: 30px; 
            color: #34495e;
        }
        h3 {
            color: #555;
            margin-top: 20px;
        }
        table { 
            border-collapse: collapse; 
            margin: 15px 0; 
            width: 100%; 
        }
        th, td { 
            border: 1px solid #ddd; 
            padding: 10px 12px; 
            text-align: left; 
        }
        th { 
            background-color: #007bff; 
            color: white; 
        }
        tr:nth-child(even) { 
            background-color: #f9f9f9; 
        }
        .image-section { 
            margin: 20px 0; 
            text-align: center; 
        }
        .image-section img { 
            max-width: 100%; 
            height: auto; 
            border: 1px solid #ddd; 
            margin: 10px 0; 
            border-radius: 4px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .image-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        ul { 
            margin: 10px 0; 
            padding-left: 25px; 
        }
        li { 
            margin: 8px 0; 
        }
        .info-box { 
            background: #e7f3ff; 
            padding: 15px; 
            border-left: 4px solid #2196F3; 
            margin: 15px 0; 
            border-radius: 4px;
        }
        .warning-box {
            background: #fff3cd;
            padding: 15px;
            border-left: 4px solid #ffc107;
            margin: 15px 0;
            border-radius: 4px;
        }
        .critical-box {
            background: #f8d7da;
            padding: 15px;
            border-left: 4px solid #dc3545;
            margin: 15px 0;
            border-radius: 4px;
            font-weight: bold;
        }
        ol ol {
            margin: 10px 0;
            padding-left: 30px;
        }
        ol ol li {
            margin: 5px 0;
        }
        .page-images {
            margin: 30px 0;
            padding: 20px;
            background: #f9f9f9;
            border-radius: 4px;
        }
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
        <div class="critical-box">
            <p>⚠️ STEP 1 MUST BE DONE FIRST: Reinforce Strongholds (often missed!)</p>
        </div>
        <ol>
            <li><strong>Receive and place reinforcements</strong> (always)
                <ol type="a">
                    <li><strong>1a. Reinforce Strongholds</strong> - Place 1 battalion into EACH territory with a stronghold you control (THIS IS FIRST!)</li>
                    <li><strong>1b. Count Territories</strong> - Divide by 3 (ignore remainder), minimum 3 reinforcements</li>
                    <li><strong>1c. Add Region Bonuses</strong> - Check gameboard chart for each complete region you control</li>
                    <li><strong>1d. Turn In Card Sets</strong> - If you have 5+ cards, you MUST turn in a set (see Card Sets table below)</li>
                    <li><strong>1e. Place ALL Reinforcements</strong> - Place everything gathered above into your territories</li>
                </ol>
            </li>
            <li><strong>Combat</strong> (invade other territories - optional)</li>
            <li><strong>Fortify your position</strong> (optional - ONE fortification move allowed)</li>
            <li><strong>Collect a territory card</strong> (if you conquered at least 1 territory)</li>
            <li><strong>Collect an adventure card</strong> (if your Leader conquered a territory with a Site of Power)</li>
            <li><strong>Replace a leader</strong> (if you have no Leaders on the board)</li>
            <li><strong>Try to find the Ring</strong> (EVIL only - see Finding the Ring section below)</li>
            <li><strong>Move the Fellowship</strong> (see Fellowship Movement section below)</li>
        </ol>
        
        <h2>Reinforcements</h2>
        
        <h3>Territories Reinforcement Table</h3>
        <table>
            <tr>
                <th>Territories Controlled</th>
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
                <td>21-23</td>
                <td>7</td>
            </tr>
            <tr>
                <td>24-26</td>
                <td>8</td>
            </tr>
            <tr>
                <td>27-29</td>
                <td>9</td>
            </tr>
            <tr>
                <td>30-32</td>
                <td>10</td>
            </tr>
            <tr>
                <td>33-35</td>
                <td>11</td>
            </tr>
            <tr>
                <td>36-38</td>
                <td>12</td>
            </tr>
            <tr>
                <td>39-41</td>
                <td>13</td>
            </tr>
            <tr>
                <td>42-44</td>
                <td>14</td>
            </tr>
            <tr>
                <td>45-47</td>
                <td>15</td>
            </tr>
            <tr>
                <td>48-50</td>
                <td>16</td>
            </tr>
            <tr>
                <td>51-53</td>
                <td>17</td>
            </tr>
            <tr>
                <td>54-56</td>
                <td>18</td>
            </tr>
            <tr>
                <td>57-59</td>
                <td>19</td>
            </tr>
            <tr>
                <td>60-62</td>
                <td>20</td>
            </tr>
            <tr>
                <td>63</td>
                <td>21</td>
            </tr>
            <tr>
                <td>64+</td>
                <td>÷3, round up</td>
            </tr>
        </table>
        
        <div class="warning-box">
            <p><strong>Remember:</strong> Region bonuses are shown on the gameboard chart. Different regions give different bonuses (typically 2-11 reinforcements per complete region).</p>
        </div>
        
        <h3>Card Set Bonuses</h3>
        <div class="critical-box">
            <p>⚠️ MANDATORY: If you have 5 or more Territory cards, you MUST turn in a set!</p>
        </div>
        <table>
            <tr>
                <th>Card Set</th>
                <th>Bonus Battalions</th>
            </tr>
            <tr>
                <td>3 Elven Archers</td>
                <td>4</td>
            </tr>
            <tr>
                <td>3 Dark Riders</td>
                <td>6</td>
            </tr>
            <tr>
                <td>3 Eagles</td>
                <td>8</td>
            </tr>
            <tr>
                <td>1 Elven Archer + 1 Dark Rider + 1 Eagle</td>
                <td>10</td>
            </tr>
        </table>
        <p><strong>Wild Cards:</strong> Can substitute for any card type in a set.</p>
        
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
            <li><strong>Attacking Requirements:</strong> Need at least 2 battalions in territory to attack (1 must stay behind to protect territory)</li>
            <li><strong>Attacking:</strong> Send 1-3 battalions per battle (attacker rolls 1, 2, or 3 dice)</li>
            <li><strong>Defending:</strong> Defend with 1-2 battalions per battle (defender rolls 1 or 2 dice)</li>
            <li><strong>Resolving:</strong> Compare highest die to highest die, then next-highest to next-highest</li>
            <li><strong>Tie Breaker:</strong> Defender wins ties</li>
            <li><strong>Continue:</strong> Repeat battles until territory is conquered or invasion is called off</li>
        </ul>
        
        <h3>Combat Bonuses</h3>
        <table>
            <tr>
                <th>Condition</th>
                <th>Bonus</th>
            </tr>
            <tr>
                <td>Leader attacking</td>
                <td>+1 to highest attack die</td>
            </tr>
            <tr>
                <td>Leader defending</td>
                <td>+1 to higher defense die</td>
            </tr>
            <tr>
                <td>Stronghold defending</td>
                <td>+1 to higher defense die</td>
            </tr>
            <tr>
                <td>Leader + Stronghold defending</td>
                <td>+2 to higher defense die</td>
            </tr>
        </table>
        <div class="info-box">
            <p><strong>Important:</strong> Bonuses are only added to the highest/higher die roll, not to all dice. Leader bonuses apply only when the Leader is in combat.</p>
        </div>
        
        <h2>Strongholds & Sites of Power</h2>
        <div class="info-box">
            <p><strong>Strongholds:</strong></p>
            <ul>
                <li>Place 1 battalion into each stronghold territory at the START of your turn (Step 1a)</li>
                <li>Provide +1 to higher defense die when defending</li>
                <li>Worth 2 points at game end (scoring)</li>
            </ul>
            <p><strong>Sites of Power:</strong></p>
            <ul>
                <li>Worth 2 points at game end, but only if you control the entire region</li>
                <li>Conquering a Site of Power with a Leader allows you to draw an Adventure card</li>
            </ul>
        </div>
"""
    
    # Add images from relevant pages
    if include_all_images:
        for page_num in sorted(images_by_page.keys()):
            if page_num in [2, 3, 4, 6, 7]:  # Pages with important visual references
                html += f"""
        <div class="page-images">
            <h3>Visual Reference from Page {page_num + 1}</h3>
            <div class="image-grid">
"""
                for idx, path in sorted(images_by_page[page_num]):
                    html += f'                <img src="{path}" alt="Page {page_num + 1} image {idx}">\n'
                html += """            </div>
        </div>
"""
    
    html += """
        <h2>Leaders</h2>
        <div class="info-box">
            <ul>
                <li><strong>Movement:</strong> Leaders move WITH battalions (cannot move alone)</li>
                <li><strong>Combat:</strong> Add +1 to highest attack die or higher defense die (only when in combat)</li>
                <li><strong>After Conquering:</strong> If Leader was used to conquer a territory, the Leader must move into that territory</li>
                <li><strong>Leader Elimination:</strong> If the last battalion in a territory with a Leader is defeated, the Leader is removed</li>
                <li><strong>Passing Through:</strong> A Leader can pass through a territory containing your other Leader, but cannot end in the same territory</li>
                <li><strong>Replacement:</strong> If you have no Leaders on the board, place one in any of your territories (Step 6)</li>
            </ul>
        </div>
        
        <h2>Adventure Cards</h2>
        <ul>
            <li><strong>Mission Cards:</strong> Complete by getting your Leader to the Site of Power listed on the card. Keep completed cards for scoring.</li>
            <li><strong>Event Cards:</strong> Say "Play Immediately" - must be played when drawn. See Event Card Handling below.</li>
            <li><strong>Power Cards:</strong> Play during combat (or sometimes during other players' turns) for advantages. Keep played cards for scoring.</li>
        </ul>
        
        <h3>Event Card Handling (Step 5)</h3>
        <div class="warning-box">
            <p>When you draw an Adventure card after conquering a Site of Power:</p>
            <ol>
                <li>If it's an Event card (says "Play Immediately"), play it immediately</li>
                <li>Draw another Adventure card</li>
                <li>Continue playing Event cards and drawing until you get a Mission or Power card</li>
                <li>Add the Mission or Power card to your hand</li>
                <li>If you now have more than 4 Adventure cards, discard one (your choice)</li>
            </ol>
            <p><strong>Important:</strong> After a Mission or Power card is drawn, no more Adventure cards can be played that turn.</p>
        </div>
        
        <h2>Scoring Points</h2>
        <table>
            <tr>
                <th>Item</th>
                <th>Points</th>
            </tr>
            <tr>
                <td>Each territory controlled</td>
                <td>1 point</td>
            </tr>
            <tr>
                <td>Each stronghold controlled</td>
                <td>2 points</td>
            </tr>
            <tr>
                <td>Each complete region controlled</td>
                <td>Equal to that region's battalion bonus (check gameboard chart)</td>
            </tr>
            <tr>
                <td>Each Site of Power controlled</td>
                <td>2 points (only if you control the entire region)</td>
            </tr>
            <tr>
                <td>Adventure cards played</td>
                <td>Points indicated on the card (cards in hand don't count)</td>
            </tr>
        </table>
        <div class="info-box">
            <p><strong>Note:</strong> Only Adventure cards that have been played (Mission cards completed, Power cards used) count for scoring. Cards still in your hand do not count.</p>
        </div>
        
        <h2>Finding the Ring (Step 7 - EVIL Only)</h2>
        <div class="critical-box">
            <p><strong>When:</strong> Just before moving the Fellowship (Step 8), if The One Ring is in a territory controlled by an evil player.</p>
        </div>
        <ul>
            <li><strong>Roll:</strong> The evil player who controls the territory rolls 2 dice (any color)</li>
            <li><strong>Bonuses:</strong>
                <ul>
                    <li>+1 if controlling the entire region where the Ring is located</li>
                    <li>+1 if your Leader is in the territory with the Ring</li>
                    <li>+2 if both conditions (control entire region AND Leader present)</li>
                </ul>
            </li>
            <li><strong>Success:</strong> If the total (dice roll + bonuses) is 12 or higher, The One Ring is found and evil instantly wins!</li>
        </ul>
        
        <h2>Moving the Fellowship (Step 8)</h2>
        <div class="info-box">
            <p><strong>Normal Movement:</strong> Move The One Ring (Fellowship) 1 territory along the dotted path.</p>
            <p><strong>DIE Symbol Territories:</strong> If the Ring is currently on a territory with a DIE symbol:</p>
            <ul>
                <li>You MUST roll 1 die before moving</li>
                <li><strong>Roll > 3:</strong> Move to the next territory on the path</li>
                <li><strong>Roll ≤ 3:</strong> The Fellowship stays in the current territory (try again next turn)</li>
                <li>The Fellowship will remain in this territory until a successful roll is made</li>
            </ul>
        </div>
        
        <h2>Winning the Game</h2>
        <p><strong>When the Fellowship reaches Mount Doom:</strong></p>
        <ul>
            <li>Make a final die roll to destroy The One Ring</li>
            <li><strong>Roll > 3:</strong> The One Ring is destroyed - game ends, calculate final scores</li>
            <li><strong>Roll ≤ 3:</strong> The Fellowship has not destroyed The One Ring - game continues</li>
            <li>Each player, at the end of their turn, rolls to destroy The One Ring until successful</li>
            <li><strong>Alternative Win:</strong> Evil can win by finding The One Ring (see Finding the Ring above)</li>
        </ul>
        <p><strong>Winner:</strong> Player with the highest score wins!</p>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    logger.info(f"✓ HTML cheat sheet created: {output_path}")


def segment_extracted_images(images_dir: str = "cheatsheet_images",
                            output_dir: str = "segmented_pieces",
                            min_size: int = 1000,
                            method: str = "auto",
                            min_area: int = 500):
    """
    Segment composite images into individual pieces.
    
    Args:
        images_dir: Directory containing extracted images
        output_dir: Directory to save segmented pieces
        min_size: Minimum dimension to consider as composite
        method: Segmentation method ("auto", "contour", "color", "grid")
        min_area: Minimum area for detected pieces
        filter_empty: If True, filter out empty/background-only images and pieces
        clear_output: If True, clear output directory before processing
    """
    try:
        from segment_images import segment_all_composites
        logger.info(f"Segmenting composite images from {images_dir}...")
        results = segment_all_composites(
            images_dir,
            output_dir,
            min_size=min_size,
            method=method,
            min_area=min_area,
            filter_empty=filter_empty,
            clear_output=clear_output
        )
        logger.info(f"✓ Segmentation complete. Extracted pieces from {len(results)} composites.")
        return results
    except ImportError:
        logger.error("segment_images module not found. Install OpenCV: pip install opencv-python")
        return {}
    except Exception as e:
        logger.error(f"Error during segmentation: {e}")
        return {}


if __name__ == "__main__":
    extract_page_imgs = "--page-images" in sys.argv
    segment_imgs = "--segment" in sys.argv
    
    logger.info(f"Source: {SRC}")
    objects = extract_objects(SRC, extract_page_images=extract_page_imgs)
    create_cheat_sheet(objects)
    create_html_cheatsheet(objects, include_all_images=True)
    
    if segment_imgs:
        segment_extracted_images()