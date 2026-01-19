#!/usr/bin/env python3
"""Extract text and images from a PDF into structured objects."""
import fitz
import os
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


def extract_images(objects: dict, output_dir: str = "cheatsheet_images", 
                   categorize: bool = False, min_size: int = 50) -> Dict[tuple, str]:
    """
    Extract and save images from PDF to directory.
    
    Args:
        objects: Dictionary of page objects
        output_dir: Output directory for images
        categorize: If True, organize images into subdirectories
        min_size: Minimum width or height in pixels to extract (filters tiny icons)
    
    Returns:
        Dictionary mapping (page_num, idx) to filepath
    """
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
                          include_all_images: bool = True):
    """Create an HTML version of the cheat sheet with embedded images."""
    image_paths = extract_images(objects)
    
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
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    logger.info(f"✓ HTML cheat sheet created: {output_path}")


if __name__ == "__main__":
    extract_page_imgs = "--page-images" in sys.argv
    
    logger.info(f"Source: {SRC}")
    objects = extract_objects(SRC, extract_page_images=extract_page_imgs)
    create_cheat_sheet(objects)
    create_html_cheatsheet(objects, include_all_images=True)