#!/usr/bin/env python3
"""
Image segmentation module for extracting individual pieces from composite images.

Uses OpenCV to detect and extract individual game pieces/icons from composite images
that contain multiple pieces arranged together.
"""
import os
import shutil
import cv2
import numpy as np
import logging
from typing import List, Tuple, Optional
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
    variance = np.var(gray)
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
    return edge_ratio >= min_content_ratio


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
                         max_area: Optional[int] = None) -> List[Tuple[int, int, int, int]]:
    """
    Detect individual pieces using contour detection.
    
    Args:
        image: Input image as numpy array (BGR format)
        min_area: Minimum contour area to consider as a piece
        max_area: Maximum contour area (None for no limit)
    
    Returns:
        List of bounding boxes as (x, y, width, height)
    """
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Apply threshold to create binary image
    # Use adaptive threshold for better results with varying lighting
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, 11, 2
    )
    
    # Alternative: Use Otsu's threshold if adaptive doesn't work well
    # _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Morphological operations to clean up the image
    kernel = np.ones((3, 3), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    bounding_boxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        if max_area and area > max_area:
            continue
        
        # Get bounding box
        x, y, w, h = cv2.boundingRect(contour)
        
        # Filter out very thin or very wide boxes (likely not pieces)
        aspect_ratio = w / h if h > 0 else 0
        if aspect_ratio < 0.1 or aspect_ratio > 10:
            continue
        
        bounding_boxes.append((x, y, w, h))
    
    return bounding_boxes


def detect_pieces_color_based(image: np.ndarray, min_area: int = 500) -> List[Tuple[int, int, int, int]]:
    """
    Detect pieces using color-based segmentation.
    Useful for images with distinct colored pieces (e.g., gold vs red pieces).
    
    Args:
        image: Input image as numpy array (BGR format)
        min_area: Minimum area to consider as a piece
    
    Returns:
        List of bounding boxes as (x, y, width, height)
    """
    # Convert to HSV for better color segmentation
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # Create mask for non-white/transparent areas
    # Assuming pieces are on white/light background
    lower_white = np.array([0, 0, 200])
    upper_white = np.array([180, 30, 255])
    mask = cv2.inRange(hsv, lower_white, upper_white)
    mask = cv2.bitwise_not(mask)  # Invert to get non-white areas
    
    # Clean up mask
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    bounding_boxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        
        x, y, w, h = cv2.boundingRect(contour)
        
        # Filter by aspect ratio
        aspect_ratio = w / h if h > 0 else 0
        if aspect_ratio < 0.2 or aspect_ratio > 5:
            continue
        
        bounding_boxes.append((x, y, w, h))
    
    return bounding_boxes


def detect_pieces_grid(image: np.ndarray, expected_rows: Optional[int] = None,
                       expected_cols: Optional[int] = None) -> List[Tuple[int, int, int, int]]:
    """
    Detect pieces arranged in a regular grid pattern.
    
    Args:
        image: Input image as numpy array
        expected_rows: Expected number of rows (None for auto-detect)
        expected_cols: Expected number of columns (None for auto-detect)
    
    Returns:
        List of bounding boxes as (x, y, width, height)
    """
    height, width = image.shape[:2]
    
    # Use contour detection first to find approximate grid
    boxes = detect_pieces_contour(image, min_area=1000)
    
    if len(boxes) < 2:
        return boxes
    
    # Group boxes by approximate row/column positions
    # Simple approach: sort by y-coordinate for rows, then x for columns
    boxes_sorted = sorted(boxes, key=lambda b: (b[1], b[0]))
    
    # If we have expected dimensions, try to fit them
    if expected_rows and expected_cols:
        if len(boxes_sorted) >= expected_rows * expected_cols:
            # Take the first N boxes that fit the grid
            boxes_sorted = boxes_sorted[:expected_rows * expected_cols]
    
    return boxes_sorted


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


def segment_composite_image(image_path: str, output_dir: str,
                           method: str = "auto",
                           min_area: int = 500,
                           padding: int = 5,
                           filter_empty: bool = True,
                           clear_output: bool = True) -> List[str]:
    """
    Segment a composite image into individual pieces.
    
    Args:
        image_path: Path to the composite image
        output_dir: Directory to save extracted pieces
        method: Segmentation method ("contour", "color", "grid", or "auto")
        min_area: Minimum area for a detected piece
        padding: Padding around each extracted piece
        filter_empty: If True, filter out empty/background-only pieces
        clear_output: If True, clear output directory before extracting
    
    Returns:
        List of paths to extracted piece images
    """
    # Load image
    image = cv2.imread(image_path)
    if image is None:
        logger.error(f"Failed to load image: {image_path}")
        return []
    
    height, width = image.shape[:2]
    logger.info(f"Processing {os.path.basename(image_path)} ({width}x{height})")
    
    # Clear output directory if requested
    if clear_output and os.path.exists(output_dir):
        logger.debug(f"Clearing output directory: {output_dir}")
        shutil.rmtree(output_dir)
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Detect pieces based on method
    if method == "auto":
        # Try contour detection first
        boxes = detect_pieces_contour(image, min_area=min_area)
        if len(boxes) < 2:
            # Fall back to color-based if contour doesn't find much
            logger.info("Contour detection found few pieces, trying color-based...")
            boxes = detect_pieces_color_based(image, min_area=min_area)
    elif method == "contour":
        boxes = detect_pieces_contour(image, min_area=min_area)
    elif method == "color":
        boxes = detect_pieces_color_based(image, min_area=min_area)
    elif method == "grid":
        boxes = detect_pieces_grid(image)
    else:
        logger.warning(f"Unknown method '{method}', using contour detection")
        boxes = detect_pieces_contour(image, min_area=min_area)
    
    if len(boxes) == 0:
        logger.warning(f"No pieces detected in {image_path}")
        return []
    
    logger.info(f"Detected {len(boxes)} potential pieces")
    
    # Extract base filename
    base_name = Path(image_path).stem
    
    # Extract and save each piece
    extracted_paths = []
    skipped_count = 0
    for idx, bbox in enumerate(boxes):
        piece = extract_piece(image, bbox, padding=padding)
        
        # Filter out empty/background-only pieces
        if filter_empty and not is_valid_piece(piece):
            skipped_count += 1
            x, y, w, h = bbox
            logger.debug(f"  Skipped empty piece {idx + 1}: {w}x{h} at ({x}, {y})")
            continue
        
        # Generate output filename
        output_filename = f"{base_name}_piece_{idx + 1:03d}.png"
        output_path = os.path.join(output_dir, output_filename)
        
        # Save piece
        cv2.imwrite(output_path, piece)
        extracted_paths.append(output_path)
        
        x, y, w, h = bbox
        logger.debug(f"  Extracted piece {idx + 1}: {w}x{h} at ({x}, {y})")
    
    if skipped_count > 0:
        logger.info(f"Skipped {skipped_count} empty/background pieces")
    logger.info(f"✓ Extracted {len(extracted_paths)} valid pieces to {output_dir}")
    return extracted_paths


def segment_all_composites(input_dir: str, output_dir: str,
                          min_size: int = 1000,
                          method: str = "auto",
                          min_area: int = 500,
                          filter_empty: bool = True) -> dict:
    """
    Segment all composite images in a directory.
    
    Args:
        input_dir: Directory containing composite images
        output_dir: Directory to save extracted pieces
        min_size: Minimum dimension to consider as composite
        method: Segmentation method to use
        min_area: Minimum area for detected pieces
        filter_empty: If True, filter out empty/background-only pieces
    
    Returns:
        Dictionary mapping input image paths to lists of extracted piece paths
    """
    results = {}
    
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
        extracted = segment_composite_image(
            image_path,
            composite_output_dir,
            method=method,
            min_area=min_area,
            filter_empty=filter_empty,
            clear_output=clear_output  # Clear each composite's subdirectory
        )
        
        if extracted:
            results[image_path] = extracted
    
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
        choices=["auto", "contour", "color", "grid"],
        default="auto",
        help="Segmentation method (default: auto)"
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
        "--single",
        help="Process a single image file instead of directory"
    )
    
    args = parser.parse_args()
    
    filter_empty = not args.no_filter_empty
    clear_output = not args.no_clear
    
    if args.single:
        # Process single image
        output_dir = os.path.join(args.output, Path(args.single).stem)
        segment_composite_image(
            args.single,
            output_dir,
            method=args.method,
            min_area=args.min_area,
            filter_empty=filter_empty,
            clear_output=clear_output
        )
    else:
        # Process directory
        segment_all_composites(
            args.input_dir,
            args.output,
            min_size=args.min_size,
            method=args.method,
            min_area=args.min_area,
            filter_empty=filter_empty,
            clear_output=clear_output
        )
