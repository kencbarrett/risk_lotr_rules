#!/usr/bin/env python3
"""
Image segmentation module for extracting individual pieces from composite images.

Uses OpenCV to detect and extract individual game pieces/icons from composite images
that contain multiple pieces arranged together.
"""
import json
import os
import shutil
import cv2
import numpy as np
import logging
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def is_empty_image(image: np.ndarray, background_threshold: float = 0.95,
                   variance_threshold: float = 10.0) -> bool:
    """
    Check if an image is mostly empty (background only or very little content).
    
    Args:
        image: Input image as numpy array (BGR format)
        background_threshold: Percentage of pixels that can be background (0-1)
        variance_threshold: Minimum variance in pixel values to consider non-empty
    
    Returns:
        True if image appears to be empty/background only
    """
    if image is None or image.size == 0:
        return True
    
    # Convert to grayscale for analysis
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # Check variance - low variance means mostly uniform (likely background)
    variance = np.var(gray.astype(np.float64))
    if variance < variance_threshold:
        return True
    
    # Check if image is mostly white/light background
    # For images with alpha channel, check alpha channel
    if len(image.shape) == 4 or (len(image.shape) == 3 and image.shape[2] == 4):
        # Has alpha channel
        if len(image.shape) == 4:
            alpha = image[:, :, 3]
        else:
            alpha = image[:, :, 3]
        
        # If mostly transparent, consider empty
        transparent_ratio = np.sum(alpha < 10) / alpha.size
        if transparent_ratio > background_threshold:
            return True
    
    # Check for mostly white/light pixels (common background)
    # Consider pixels > 240 (very light) as background
    light_pixels = np.sum(gray > 240)
    light_ratio = light_pixels / gray.size
    
    if light_ratio > background_threshold:
        return True
    
    # Check for mostly dark pixels (could be empty dark background)
    dark_pixels = np.sum(gray < 15)
    dark_ratio = dark_pixels / gray.size
    
    if dark_ratio > background_threshold:
        return True
    
    return False


def has_meaningful_content(image: np.ndarray, min_content_ratio: float = 0.05,
                           edge_threshold: int = 50) -> bool:
    """
    Check if image has meaningful content (not just background).
    
    Uses edge detection to find content areas.
    
    Args:
        image: Input image as numpy array
        min_content_ratio: Minimum ratio of image that should have edges/content
        edge_threshold: Threshold for edge detection
    
    Returns:
        True if image has meaningful content
    """
    if image is None or image.size == 0:
        return False
    
    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # Use Canny edge detection to find content
    edges = cv2.Canny(gray, edge_threshold, edge_threshold * 2)
    
    # Count pixels with edges
    edge_pixels = np.sum(edges > 0)
    edge_ratio = edge_pixels / edges.size
    
    # If very few edges, likely just background
    return bool(edge_ratio >= min_content_ratio)


def is_background_only(image_path: str, background_threshold: float = 0.95) -> bool:
    """
    Check if an image file is mostly background with no meaningful content.
    
    Args:
        image_path: Path to image file
        background_threshold: Percentage threshold for background detection
    
    Returns:
        True if image is mostly background
    """
    try:
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return True
        
        # Check if empty
        if is_empty_image(img, background_threshold=background_threshold):
            return True
        
        # Check if has meaningful content
        if not has_meaningful_content(img):
            return True
        
        return False
    except Exception as e:
        logger.warning(f"Error checking background for {image_path}: {e}")
        return True  # Assume empty on error to be safe


def is_composite_image(image_path: str, min_size: int = 1000) -> bool:
    """
    Determine if an image is likely a composite containing multiple pieces.
    
    Args:
        image_path: Path to the image file
        min_size: Minimum dimension (width or height) to consider as composite
    
    Returns:
        True if image appears to be a composite
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return False
        
        # Skip if it's just background
        if is_background_only(image_path):
            return False
        
        height, width = img.shape[:2]
        # Large images are more likely to be composites
        return width >= min_size or height >= min_size
    except Exception as e:
        logger.warning(f"Error checking composite status for {image_path}: {e}")
        return False

def detect_pieces_contour(image: np.ndarray, min_area: int = 500, 
                         max_area: Optional[int] = None,
                         debug_dir: Optional[str] = None) -> List[Tuple[int, int, int, int]]:
    """
    Improved contour detection:
      - CLAHE contrast boost
      - bilateral filter to preserve edges
      - adaptive threshold with block size proportional to image size
      - Canny edges merged with threshold contours
      - area filtering relative to image area
      - optional debug output (gray, thresh, edges, merged)
    """
    h, w = image.shape[:2]
    img_area = float(max(1, h * w))

    # Grayscale + contrast
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Denoise but keep edges
    denoised = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

    # Adaptive threshold with block size proportional to image
    block = max(11, (min(h, w) // 40) | 1)  # odd block size
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, block, 7
    )

    # Morphology sized for image
    ksize = max(3, (min(h, w) // 300) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # Canny edges -> dilate to join small gaps
    edges = cv2.Canny(denoised, 50, 150)
    ed_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, ed_k, iterations=1)

    # Merge masks (threshold + edges) to catch both filled and outline-only pieces
    merged = cv2.bitwise_or(thresh, edges)

    # Find contours on merged mask
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bounding_boxes = []
    # min_area relative to image area if not huge absolute
    rel_min_area = max(min_area, int(img_area * 0.0004))  # tune this fraction if needed

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < rel_min_area:
            continue
        if max_area and area > max_area:
            continue

        x, y, wbox, hbox = cv2.boundingRect(contour)
        aspect_ratio = wbox / hbox if hbox > 0 else 0
        if aspect_ratio < 0.08 or aspect_ratio > 12:
            continue

        # pad box a bit
        pad = max(4, int(min(h, w) * 0.01))
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(image.shape[1], x + wbox + pad)
        y1 = min(image.shape[0], y + hbox + pad)
        bounding_boxes.append((x0, y0, x1 - x0, y1 - y0))

    # Optionally write debug images
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        cv2.imwrite(os.path.join(debug_dir, "gray.png"), gray)
        cv2.imwrite(os.path.join(debug_dir, "thresh.png"), thresh)
        cv2.imwrite(os.path.join(debug_dir, "edges.png"), edges)
        cv2.imwrite(os.path.join(debug_dir, "merged.png"), merged)

    # Sort left->right, top->down for deterministic output
    bounding_boxes = sorted(bounding_boxes, key=lambda b: (b[1], b[0]))
    return bounding_boxes

def detect_pieces_color_based(image: np.ndarray, min_area: int = 500) -> List[Tuple[int, int, int, int]]:
    """
    Detect pieces that sit on a mostly-uniform colored background (e.g. the blue columns).
    - Auto-detects dominant hue from page borders
    - Masks the background hue, inverts to get foreground icons
    - Morphological cleaning and contour filtering by area/aspect
    """
    h, w = image.shape[:2]
    img_area = float(max(1, h * w))

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    s = hsv[:, :, 1]
    hue = hsv[:, :, 0]

    # sample left/right border strips to find dominant background hue
    strip_w = max(10, w // 12)
    samples = np.concatenate([
        hsv[:, :strip_w, :].reshape(-1, 3),
        hsv[:, -strip_w:, :].reshape(-1, 3)
    ], axis=0)
    # filter low-saturation/value pixels
    sat_val_mask = (samples[:, 1] > 30) & (samples[:, 2] > 30)
    if np.any(sat_val_mask):
        dominant_hue = int(np.median(samples[sat_val_mask, 0].astype(np.float64)))
    else:
        dominant_hue = int(np.median(samples[:, 0].astype(np.float64)))

    delta = 12  # hue tolerance
    lower = np.array([max(0, dominant_hue - delta), 30, 20], dtype=np.uint8)
    upper = np.array([min(179, dominant_hue + delta), 255, 255], dtype=np.uint8)

    bg_mask = cv2.inRange(hsv, lower, upper)
    fg_mask = cv2.bitwise_not(bg_mask)

    # remove very dark/very light noise: require some brightness
    bright_mask = (v > 25).astype(np.uint8) * 255
    mask = cv2.bitwise_and(fg_mask, bright_mask)

    # morphological cleanup (sizes proportional to image)
    ksize = max(3, (min(h, w) // 300) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: List[Tuple[int, int, int, int]] = []

    rel_min_area = max(min_area, int(img_area * 0.00015))
    for c in contours:
        area = cv2.contourArea(c)
        if area < rel_min_area:
            continue
        x, y, ww, hh = cv2.boundingRect(c)
        ar = ww / float(hh + 1e-6)
        if ar < 0.06 or ar > 15:
            continue
        pad = max(4, int(min(h, w) * 0.008))
        x0 = max(0, x - pad); y0 = max(0, y - pad)
        x1 = min(image.shape[1], x + ww + pad); y1 = min(image.shape[0], y + hh + pad)
        boxes.append((x0, y0, x1 - x0, y1 - y0))

    # sort top->down then left->right (good for vertical icon columns)
    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    return boxes


def detect_pieces_grid(image: np.ndarray, expected_rows: Optional[int] = None,
                       expected_cols: Optional[int] = None) -> List[Tuple[int, int, int, int]]:
    """
    Fallback grid detector: use color-based mask first, then try to detect
    regularly spaced items by analyzing vertical projections if a column is detected.
    """
    # try color-based first
    boxes = detect_pieces_color_based(image, min_area=200)
    if boxes:
        return boxes

    # fallback: projection-based grid detection
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    th = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, 31, 10)

    # vertical projection
    vert_proj = np.sum(th, axis=1)
    # normalize and find peaks
    norm = (vert_proj - vert_proj.min()) / (vert_proj.ptp() + 1e-6)
    peaks = np.where(norm > 0.25)[0]

    boxes_out: List[Tuple[int, int, int, int]] = []
    if peaks.size > 0:
        # group consecutive rows into bands
        groups = np.split(peaks, np.where(np.diff(peaks) != 1)[0] + 1)
        for g in groups:
            y0 = max(0, int(g[0] - 6))
            y1 = min(image.shape[0], int(g[-1] + 6))
            # horizontal crop and find contours to localize item
            crop = th[y0:y1, :]
            cnts, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                x, y, ww, hh = cv2.boundingRect(c)
                area = ww * hh
                if area < 200:
                    continue
                pad = 4
                boxes_out.append((x - pad, y0 + y - pad, ww + 2 * pad, hh + 2 * pad))
        boxes_out = [(max(0, x), max(0, y), min(image.shape[1] - x, w), min(image.shape[0] - y, h))
                     for (x, y, w, h) in boxes_out]

    # final sort and return
    boxes_final = sorted(boxes_out, key=lambda b: (b[1], b[0]))
    return boxes_final

def extract_piece(image: np.ndarray, bbox: Tuple[int, int, int, int], 
                 padding: int = 5) -> np.ndarray:
    """
    Extract a single piece from the image using its bounding box.
    
    Args:
        image: Source image
        bbox: Bounding box as (x, y, width, height)
        padding: Extra pixels to add around the piece
    
    Returns:
        Cropped image of the piece
    """
    x, y, w, h = bbox
    height, width = image.shape[:2]
    
    # Add padding, ensuring we don't go outside image bounds
    x_start = max(0, x - padding)
    y_start = max(0, y - padding)
    x_end = min(width, x + w + padding)
    y_end = min(height, y + h + padding)
    
    return image[y_start:y_end, x_start:x_end]


def is_valid_piece(piece: np.ndarray, min_content_ratio: float = 0.05) -> bool:
    """
    Check if an extracted piece has meaningful content (not just background).
    
    Args:
        piece: Extracted piece image
        min_content_ratio: Minimum ratio of piece that should have content
    
    Returns:
        True if piece is valid (has content)
    """
    if piece is None or piece.size == 0:
        return False
    
    # Check if piece is too small
    if piece.shape[0] < 10 or piece.shape[1] < 10:
        return False
    
    # Check if it's mostly empty
    if is_empty_image(piece, background_threshold=0.90):
        return False
    
    # Check if it has meaningful content
    return has_meaningful_content(piece, min_content_ratio=min_content_ratio)


def _detect_special_composite_type(image: np.ndarray, image_path: str) -> Optional[str]:
    """Detect if the image looks like a known composite type requiring special rules."""
    name = os.path.basename(image_path).lower()

    # Filename hints (most reliable)
    if "battalion" in name or "battalions" in name:
        return "battalion_sheet"
    if "shield" in name or "leader" in name:
        return "leader_shields"
    if "site" in name or "sites" in name:
        return "site_icons"

    # Size/shape heuristics (fallback)
    h, w = image.shape[:2]
    aspect = w / (h + 1e-9)
    # Some battalion sheets are wide and short; allow tuning later
    if aspect > 2.0 and w > 800 and h > 200:
        return "battalion_sheet"
    # A roughly square block of icons could be sites grid
    if 0.8 < aspect < 1.3 and w > 400 and h > 400:
        return "site_icons"

    return None


def _fixed_grid_boxes(image: np.ndarray, rows: int, cols: int,
                      min_area: int = 0, padding: int = 0) -> List[Tuple[int, int, int, int]]:
    """Return grid-aligned bounding boxes covering the image."""
    h, w = image.shape[:2]
    cell_w = w // cols
    cell_h = h // rows

    boxes: List[Tuple[int, int, int, int]] = []
    for r in range(rows):
        for c in range(cols):
            x = c * cell_w
            y = r * cell_h
            # Ensure last cell reaches the edge (avoid losing pixels)
            w_box = cell_w if c < cols - 1 else w - x
            h_box = cell_h if r < rows - 1 else h - y
            boxes.append((x, y, w_box, h_box))

    # Optionally filter boxes that are too small
    if min_area > 0:
        boxes = [b for b in boxes if b[2] * b[3] >= min_area]

    # Apply padding (keeping within bounds)
    if padding > 0:
        padded = []
        for (x, y, bw, bh) in boxes:
            x0 = max(0, x - padding)
            y0 = max(0, y - padding)
            x1 = min(w, x + bw + padding)
            y1 = min(h, y + bh + padding)
            padded.append((x0, y0, x1 - x0, y1 - y0))
        boxes = padded

    return boxes


def _segment_special_composite(image: np.ndarray, composite_type: str,
                               min_area: int, padding: int) -> List[Tuple[int, int, int, int]]:
    """Special-case segmentation strategies for known composite types."""
    if composite_type == "battalion_sheet":
        # Typical battalion sheets are 2 rows x 3 columns
        return _fixed_grid_boxes(image, rows=2, cols=3, min_area=min_area, padding=padding)
    if composite_type == "leader_shields":
        # Leaders typically appear as 2 items side-by-side (approx)
        return _fixed_grid_boxes(image, rows=1, cols=2, min_area=min_area, padding=padding)
    if composite_type == "site_icons":
        # Sites of Power are often arranged in a grid
        # Default to a 3x3 grid, but allow downstream filtering by validity
        return _fixed_grid_boxes(image, rows=3, cols=3, min_area=min_area, padding=padding)

    # Unknown composite type
    return []


# Helper functions for merging boxes found by multiple detectors
def _offset_boxes(boxes: List[Tuple[int,int,int,int]], dx: int, dy: int = 0) -> List[Tuple[int,int,int,int]]:
    return [(x + dx, y + dy, w, h) for (x, y, w, h) in boxes]


def _box_iou(a: Tuple[int,int,int,int], b: Tuple[int,int,int,int]) -> float:
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ax1, ay1, ax2, ay2 = ax, ay, ax + aw, ay + ah
    bx1, by1, bx2, by2 = bx, by, bx + bw, by + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _add_unique_boxes(existing: List[Tuple[int,int,int,int]],
                      new: List[Tuple[int,int,int,int]],
                      iou_thresh: float = 0.25) -> List[Tuple[int,int,int,int]]:
    out = list(existing)
    for nb in new:
        skip = False
        for eb in out:
            if _box_iou(nb, eb) > iou_thresh:
                skip = True
                break
        if not skip:
            out.append(nb)
    return out


def segment_composite_image(image_path: str, output_dir: str,
                           method: str = "auto",
                           min_area: int = 500,
                           padding: int = 5,
                           filter_empty: bool = True,
                           clear_output: bool = True,
                           emit_manifest: bool = True,
                           manifest_root: Optional[str] = None) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Segment a composite image into individual pieces.

    NOTE: in "auto" mode this now:
      - runs contour detection
      - always runs color-based detection on left/right page border strips
        (useful for blue columns containing Strongholds / Sites of Power)
      - merges unique boxes (avoids duplicates) before extraction
    """
    # Load image
    image = cv2.imread(image_path)
    if image is None:
        logger.error(f"Failed to load image: {image_path}")
        return ([], [])
    
    height, width = image.shape[:2]
    logger.info(f"Processing {os.path.basename(image_path)} ({width}x{height})")
    
    # Clear output directory if requested
    if clear_output and os.path.exists(output_dir):
        logger.debug(f"Clearing output directory: {output_dir}")
        shutil.rmtree(output_dir)
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Detect pieces based on method or known composite patterns
    boxes: List[Tuple[int,int,int,int]] = []
    used_method = method

    # Special-case handlers for known composites (when using auto or special)
    if method in ("auto", "special"):
        composite_type = _detect_special_composite_type(image, image_path)
        if composite_type:
            logger.info(f"Detected special composite type: {composite_type}")
            boxes = _segment_special_composite(image, composite_type, min_area=min_area, padding=padding)
            used_method = f"special:{composite_type}"

    # Fall back to requested/common methods if no special rules applied
    if not boxes:
        if method == "auto":
            # Try contour detection first (good for center artwork / pieces)
            boxes = detect_pieces_contour(image, min_area=min_area)
            # Always also try color-based detection on left/right strips to catch column icons
            strip_w = max(40, width // 10)
            left_strip = image[:, :strip_w]
            right_strip = image[:, -strip_w:]
            # use a smaller min_area for strip detection (icons are smaller)
            strip_min_area = max(100, int(min_area * 0.3))
            left_boxes = detect_pieces_color_based(left_strip, min_area=strip_min_area)
            right_boxes = detect_pieces_color_based(right_strip, min_area=strip_min_area)
            # offset right boxes to page coords
            right_boxes = _offset_boxes(right_boxes, dx=width - strip_w)
            # left boxes already in page coords (dx=0)
            # merge without duplicating existing boxes
            boxes = _add_unique_boxes(boxes, left_boxes)
            boxes = _add_unique_boxes(boxes, right_boxes)
            if len(boxes) < 2:
                # If nothing found, try whole-image color-based fallback
                logger.info("Few pieces found; trying full-image color-based detection...")
                boxes = detect_pieces_color_based(image, min_area=min_area)
        elif method == "contour":
            boxes = detect_pieces_contour(image, min_area=min_area)
        elif method == "color":
            boxes = detect_pieces_color_based(image, min_area=min_area)
        elif method == "grid":
            boxes = detect_pieces_grid(image)
        elif method == "special":
            # attempted special already; fall back to contour
            boxes = detect_pieces_contour(image, min_area=min_area)
        else:
            logger.warning(f"Unknown method '{method}', using contour detection")
            boxes = detect_pieces_contour(image, min_area=min_area)

    if len(boxes) == 0:
        logger.warning(f"No pieces detected in {image_path}")
        return ([], [])

    logger.info(f"Detected {len(boxes)} potential pieces")
    
    if len(boxes) == 0:
        logger.warning(f"No pieces detected in {image_path}")
        return ([], [])
    
    logger.info(f"Detected {len(boxes)} potential pieces")
    
    # Extract base filename
    base_name = Path(image_path).stem
    composite_id = base_name

    # Extract and save each piece
    extracted_paths = []
    manifest_entries = []
    skipped_count = 0
    piece_index = 0
    for idx, bbox in enumerate(boxes):
        piece = extract_piece(image, bbox, padding=padding)
        
        # Filter out empty/background-only pieces
        if filter_empty and not is_valid_piece(piece):
            skipped_count += 1
            x, y, w, h = bbox
            logger.debug(f"  Skipped empty piece {idx + 1}: {w}x{h} at ({x}, {y})")
            continue
        
        piece_index += 1
        # Generate output filename
        output_filename = f"{base_name}_piece_{piece_index:03d}.png"
        output_path = os.path.join(output_dir, output_filename)
        
        # Save piece
        cv2.imwrite(output_path, piece)
        extracted_paths.append(output_path)

        if emit_manifest:
            try:
                # Make piece paths consistently relative to the manifest location
                # If caller provided a manifest_root (the directory where manifest.json will be written),
                # compute paths relative to that; otherwise fall back to default relpath behavior.
                if manifest_root:
                    path_rel = os.path.relpath(output_path, start=os.path.abspath(manifest_root))
                else:
                    path_rel = os.path.relpath(output_path)
            except ValueError:
                path_rel = output_path
            x, y, w, h = bbox
            manifest_entries.append({
                "composite_id": composite_id,
                "source_image": os.path.basename(image_path),
                "piece_index": piece_index,
                "piece_path": path_rel,
                "path": path_rel,  # kept for backwards compatibility
                "bounding_box": {"x": x, "y": y, "w": w, "h": h},
                "segmentation_method": used_method,
            })
        else:
            x, y, w, h = bbox
        logger.debug(f"  Extracted piece {piece_index}: {w}x{h} at ({x}, {y})")
    
    if skipped_count > 0:
        logger.info(f"Skipped {skipped_count} empty/background pieces")
    logger.info(f"✓ Extracted {len(extracted_paths)} valid pieces to {output_dir}")
    return (extracted_paths, manifest_entries)


def segment_composite_images(input_dir: str, output_dir: str,
                              min_size: int = 1000,
                              method: str = "auto",
                              min_area: int = 500,
                              filter_empty: bool = True,
                              clear_output: bool = True,
                              emit_manifest: bool = True) -> dict:
    """Segment a directory of extracted composite images.

    This is the preferred public API for downstream scripts.

    It scans `input_dir` for image files, checks whether each appears to be a composite,
    then delegates to :func:`segment_composite_image` for the actual segmentation.

    Args:
        input_dir: Directory containing extracted composite images
        output_dir: Directory to save segmented pieces
        min_size: Minimum dimension to consider as a composite image
        method: Segmentation method to use (auto/contour/color/grid)
        min_area: Minimum area for detected pieces
        filter_empty: If True, filter out empty/background-only pieces
        clear_output: If True, clear output directory before processing
        emit_manifest: If True, write a combined manifest.json to output_dir

    Returns:
        Dictionary mapping input image paths to lists of extracted piece paths
    """
    # Delegate to the existing implementation that already performs per-image segmentation
    return segment_all_composites(
        input_dir=input_dir,
        output_dir=output_dir,
        min_size=min_size,
        method=method,
        min_area=min_area,
        filter_empty=filter_empty,
        clear_output=clear_output,
        emit_manifest=emit_manifest,
    )


def segment_all_composites(input_dir: str, output_dir: str,
                          min_size: int = 1000,
                          method: str = "auto",
                          min_area: int = 500,
                          filter_empty: bool = True,
                          clear_output: bool = True,
                          emit_manifest: bool = True) -> dict:
    """
    Segment all composite images in a directory.
    
    Args:
        input_dir: Directory containing composite images
        output_dir: Directory to save extracted pieces
        min_size: Minimum dimension to consider as composite
        method: Segmentation method to use
        min_area: Minimum area for detected pieces
        filter_empty: If True, filter out empty/background-only pieces
        clear_output: If True, clear output directory before processing
        emit_manifest: If True, write manifest.json to output_dir
    
    Returns:
        Dictionary mapping input image paths to lists of extracted piece paths
    """
    if clear_output and os.path.exists(output_dir):
        logger.info(f"Clearing output directory: {output_dir}")
        shutil.rmtree(output_dir)

    results = {}
    all_manifest_entries = []

    # Find all image files
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
    image_files = [
        f for f in os.listdir(input_dir)
        if Path(f).suffix.lower() in image_extensions
    ]

    logger.info(f"Found {len(image_files)} images in {input_dir}")

    for filename in sorted(image_files):
        image_path = os.path.join(input_dir, filename)

        # Check if it's likely a composite
        if not is_composite_image(image_path, min_size=min_size):
            logger.debug(f"Skipping {filename} (not a composite)")
            continue

        # Create subdirectory for this composite's pieces
        base_name = Path(filename).stem
        composite_output_dir = os.path.join(output_dir, base_name)

        # Segment the composite
        extracted_paths, manifest_entries = segment_composite_image(
            image_path,
            composite_output_dir,
            method=method,
            min_area=min_area,
            filter_empty=filter_empty,
            clear_output=clear_output,
            emit_manifest=emit_manifest,
        )

        if extracted_paths:
            results[image_path] = extracted_paths
            if emit_manifest and manifest_entries:
                all_manifest_entries.extend(manifest_entries)

    if emit_manifest and all_manifest_entries:
        manifest_path = os.path.join(output_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(all_manifest_entries, f, indent=2)
        logger.info(f"Wrote manifest: {manifest_path}")

    logger.info(f"✓ Processed {len(results)} composite images")
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Segment composite images into individual pieces"
    )
    parser.add_argument(
        "input_dir",
        help="Directory containing composite images"
    )
    parser.add_argument(
        "-o", "--output",
        default="segmented_pieces",
        help="Output directory for extracted pieces (default: segmented_pieces)"
    )
    parser.add_argument(
        "-m", "--method",
        choices=["auto", "contour", "color", "grid", "special"],
        default="auto",
        help="Segmentation method (default: auto). Use 'special' to apply known composite heuristics."
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=1000,
        help="Minimum dimension to consider as composite (default: 1000)"
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=500,
        help="Minimum area for detected pieces (default: 500)"
    )
    parser.add_argument(
        "--no-filter-empty",
        action="store_true",
        help="Do not filter out empty/background-only pieces"
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear output directory before processing"
    )
    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="Do not write manifest.json (default: write manifest)"
    )
    parser.add_argument(
        "--single",
        help="Process a single image file instead of directory"
    )

    args = parser.parse_args()

    filter_empty = not args.no_filter_empty
    clear_output = not args.no_clear
    emit_manifest = not args.no_manifest

    if args.single:
        # Process single image
        output_dir = os.path.join(args.output, Path(args.single).stem)
        extracted_paths, manifest_entries = segment_composite_image(
            args.single,
            output_dir,
            method=args.method,
            min_area=args.min_area,
            filter_empty=filter_empty,
            clear_output=clear_output,
            emit_manifest=emit_manifest,
            manifest_root=output_dir,
        )
        if emit_manifest and manifest_entries:
            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_entries, f, indent=2)
            logger.info(f"Wrote manifest: {manifest_path}")
    else:
        # Process directory
        segment_composite_images(
            args.input_dir,
            args.output,
            min_size=args.min_size,
            method=args.method,
            min_area=args.min_area,
            filter_empty=filter_empty,
            clear_output=clear_output,
            emit_manifest=emit_manifest,
        )
