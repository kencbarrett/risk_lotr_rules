#!/usr/bin/env python3
"""
Suggest semantic labels for segmented pieces by comparing to reference images.

Compares each piece in manifest to images/*_piece.png using histogram comparison;
outputs a suggested mapping or report for review and merge into piece_labels.json.
"""
import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Reference image filename stem -> semantic label (without _piece)
REFERENCE_LABELS = {
    "elven_archer_piece": "elven_archer",
    "rider_of_rohan_piece": "rider_of_rohan",
    "eagle_piece": "eagle",
    "orc_piece": "orc",
    "dark_rider_piece": "dark_rider",
    "cave_troll_piece": "cave_troll",
}


def load_manifest(manifest_path: str) -> List[Dict[str, Any]]:
    """Load manifest.json."""
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def load_reference_images(images_dir: str) -> Dict[str, Any]:
    """
    Load reference piece images from images_dir.
    Returns dict: label -> (image array or None). Uses OpenCV; returns empty dict if cv2 missing.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.warning("OpenCV not installed; cannot suggest labels.")
        return {}

    refs = {}
    for stem, label in REFERENCE_LABELS.items():
        for ext in (".png", ".jpg", ".jpeg"):
            path = os.path.join(images_dir, stem + ext)
            if os.path.isfile(path):
                img = cv2.imread(path)
                if img is not None:
                    refs[label] = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                break
    return refs


def compare_histograms(piece_gray, ref_gray) -> float:
    """Compare two grayscale images via histogram correlation; return 0..1."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return 0.0
    # Resize piece to ref size for fair comparison
    h, w = ref_gray.shape[:2]
    piece_resized = cv2.resize(piece_gray, (w, h), interpolation=cv2.INTER_AREA)
    hist_piece = cv2.calcHist([piece_resized], [0], None, [256], [0, 256])
    hist_ref = cv2.calcHist([ref_gray], [0], None, [256], [0, 256])
    cv2.normalize(hist_piece, hist_piece, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(hist_ref, hist_ref, 0, 1, cv2.NORM_MINMAX)
    # HISTCMP_CORREL returns -1..1; shift to 0..1
    score = cv2.compareHist(hist_piece, hist_ref, cv2.HISTCMP_CORREL)
    return max(0.0, (score + 1) / 2.0)


def suggest_for_piece(
    piece_path: str,
    project_root: str,
    references: Dict[str, Any],
    manifest_dir: Optional[str] = None,
) -> Tuple[Optional[str], float]:
    """
    Return (best_label, score) for a piece image, or (None, 0) if no refs or unreadable.
    """
    if not references:
        return None, 0.0
    try:
        import cv2
    except ImportError:
        return None, 0.0
    if os.path.isabs(piece_path):
        full_path = piece_path
    else:
        base_for_relative = manifest_dir or project_root or os.getcwd()
        full_path = os.path.join(base_for_relative, piece_path)
    if not os.path.isfile(full_path):
        return None, 0.0
    img = cv2.imread(full_path)
    if img is None:
        return None, 0.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    best_label = None
    best_score = 0.0
    for label, ref_gray in references.items():
        s = compare_histograms(gray, ref_gray)
        if s > best_score:
            best_score = s
            best_label = label
    return best_label, best_score


def suggest_labels(
    manifest_path: str = "segmented_pieces/manifest.json",
    images_dir: str = "images",
    project_root: Optional[str] = None,
    min_score: float = 0.5,
) -> Dict[str, Dict[str, str]]:
    """
    For each manifest entry, suggest a label from reference images.
    Returns structure compatible with piece_labels.json: composite_id -> { piece_index (str) -> label }.
    Only includes suggestions with score >= min_score.
    """
    root = project_root or os.getcwd()
    manifest_full = os.path.join(root, manifest_path) if not os.path.isabs(manifest_path) else manifest_path
    images_full = os.path.join(root, images_dir) if not os.path.isabs(images_dir) else images_dir

    if not os.path.isfile(manifest_full):
        logger.error("Manifest not found: %s", manifest_full)
        return {}
    manifest_entries = load_manifest(manifest_full)
    references = load_reference_images(images_full)
    if not references:
        logger.error("No reference images found in %s", images_full)
        return {}

    # composite_id -> { piece_index_str -> label }
    suggested: Dict[str, Dict[str, str]] = {}
    manifest_dir = os.path.dirname(manifest_full) or None
    for entry in manifest_entries:
        composite_id = entry.get("composite_id")
        piece_index = entry.get("piece_index")
        # Prefer the newer field name; fall back to legacy `path`
        path = entry.get("piece_path") or entry.get("path")
        if composite_id is None or piece_index is None or not path:
            continue
        label, score = suggest_for_piece(path, root, references, manifest_dir=manifest_dir)
        if label and score >= min_score:
            if composite_id not in suggested:
                suggested[composite_id] = {}
            suggested[composite_id][str(piece_index)] = label
            logger.info("  %s piece %s -> %s (%.2f)", composite_id, piece_index, label, score)
        else:
            logger.debug("  %s piece %s -> no match (best %.2f)", composite_id, piece_index, score or 0.0)

    return suggested


def run(
    manifest_path: str = "segmented_pieces/manifest.json",
    images_dir: str = "images",
    project_root: Optional[str] = None,
    min_score: float = 0.5,
    output_path: Optional[str] = "suggested_labels.json",
    report_only: bool = False,
) -> Dict[str, Dict[str, str]]:
    """
    Suggest labels and optionally write suggested_labels.json.
    If report_only, only log and return (do not write file).
    """
    suggested = suggest_labels(
        manifest_path=manifest_path,
        images_dir=images_dir,
        project_root=project_root,
        min_score=min_score,
    )
    logger.info("Suggested labels for %d composite(s)", len(suggested))
    if not report_only and suggested and output_path:
        root = project_root or os.getcwd()
        out_full = os.path.join(root, output_path) if not os.path.isabs(output_path) else output_path
        with open(out_full, "w", encoding="utf-8") as f:
            json.dump(suggested, f, indent=2)
        logger.info("Wrote suggested mapping: %s (review and merge into piece_labels.json)", out_full)
    return suggested


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Suggest semantic labels for segmented pieces")
    ap.add_argument("--manifest", default="segmented_pieces/manifest.json", help="Path to manifest.json")
    ap.add_argument("--images-dir", default="images", help="Directory with *_piece.png reference images")
    ap.add_argument("--project-root", default=None, help="Project root (default: cwd)")
    ap.add_argument("--min-score", type=float, default=0.5, help="Minimum match score to suggest (0-1)")
    ap.add_argument("--output", "-o", default="suggested_labels.json", help="Output path for suggested mapping")
    ap.add_argument("--report-only", action="store_true", help="Only print report, do not write file")

    args = ap.parse_args()
    run(
        manifest_path=args.manifest,
        images_dir=args.images_dir,
        project_root=args.project_root,
        min_score=args.min_score,
        output_path=args.output,
        report_only=args.report_only,
    )
