#!/usr/bin/env python3
"""
Apply semantic labels to segmented pieces and produce resolved manifest and labeled/ output.

Reads manifest.json (from segment_images) and piece_labels.json; copies labeled pieces
into labeled/<label>/ and writes resolved_manifest.json with path, label, and category.
"""
import json
import os
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Battalion table piece labels (get category "battalion")
BATTALION_LABELS = {
    "elven_archer",
    "rider_of_rohan",
    "eagle",
    "orc",
    "dark_rider",
    "cave_troll",
}


def load_manifest(manifest_path: str) -> List[Dict[str, Any]]:
    """Load manifest.json; return list of {composite_id, piece_index, path}."""
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Manifest must be a list of entries: {manifest_path}")
    return data


def load_piece_labels(labels_path: str) -> Dict[str, Dict[str, str]]:
    """Load piece_labels.json; return composite_id -> { piece_index (str) -> label }."""
    with open(labels_path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            out[k] = {str(piece_idx): str(label) for piece_idx, label in v.items()}
    return out


def resolve_labels(
    manifest_entries: List[Dict[str, Any]],
    piece_labels: Dict[str, Dict[str, str]],
    base_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Merge manifest and labels into resolved entries with path, label, category.

    Args:
        manifest_entries: From manifest.json
        piece_labels: From piece_labels.json (composite_id -> { piece_index -> label })
        base_dir: If set, paths in resolved manifest are relative to this dir

    Returns:
        List of { path, label, category } for entries that have a label.
        category is "battalion" for the six battalion piece labels, else "other".
    """
    resolved = []
    for entry in manifest_entries:
        composite_id = entry.get("composite_id")
        piece_index = entry.get("piece_index")
        path = entry.get("path")
        if not composite_id or piece_index is None or not path:
            continue
        comp_labels = piece_labels.get(composite_id)
        if not comp_labels:
            continue
        label = comp_labels.get(str(piece_index))
        if not label:
            continue
        category = "battalion" if label in BATTALION_LABELS else "other"
        path_use = path
        if base_dir:
            path_use = os.path.relpath(path, base_dir) if os.path.isabs(path) else path
        resolved.append({
            "path": path_use,
            "label": label,
            "category": category,
        })
    return resolved


def build_labeled_dir(
    resolved_entries: List[Dict[str, Any]],
    labeled_dir: str,
    project_root: Optional[str] = None,
    use_symlinks: bool = False,
) -> None:
    """
    Copy or symlink each resolved piece into labeled/<label>/<composite>_<index>.png.

    Args:
        resolved_entries: From resolve_labels (must include "path" and "label")
        labeled_dir: Root directory for labeled output (e.g. labeled/)
        project_root: If set, path in entries is relative to this; otherwise cwd
        use_symlinks: If True, symlink; else copy.
    """
    root = project_root or os.getcwd()
    for i, entry in enumerate(resolved_entries):
        path = entry["path"]
        label = entry["label"]
        src = os.path.join(root, path) if not os.path.isabs(path) else path
        if not os.path.isfile(src):
            logger.warning("Missing piece file: %s", src)
            continue
        # Filename: use path basename so we get e.g. page1_img7_10_piece_001.png
        base = os.path.basename(path)
        dest_dir = os.path.join(labeled_dir, label)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, base)
        if use_symlinks:
            if os.path.lexists(dest):
                os.remove(dest)
            os.symlink(os.path.abspath(src), dest)
        else:
            shutil.copy2(src, dest)
        logger.debug("Labeled: %s -> %s", label, dest)


def run(
    manifest_path: str = "segmented_pieces/manifest.json",
    labels_path: str = "piece_labels.json",
    labeled_dir: str = "labeled",
    resolved_path: str = "resolved_manifest.json",
    project_root: Optional[str] = None,
    clear_labeled: bool = True,
    use_symlinks: bool = False,
) -> List[Dict[str, Any]]:
    """
    Load manifest and labels, write resolved manifest and labeled/ directory.

    Returns:
        Resolved entries (path, label, category).
    """
    root = project_root or os.getcwd()
    manifest_full = os.path.join(root, manifest_path) if not os.path.isabs(manifest_path) else manifest_path
    labels_full = os.path.join(root, labels_path) if not os.path.isabs(labels_path) else labels_path

    if not os.path.isfile(manifest_full):
        logger.error("Manifest not found: %s", manifest_full)
        return []
    if not os.path.isfile(labels_full):
        logger.error("Piece labels not found: %s", labels_full)
        return []

    manifest_entries = load_manifest(manifest_full)
    piece_labels = load_piece_labels(labels_full)
    resolved = resolve_labels(manifest_entries, piece_labels, base_dir=root)

    logger.info("Resolved %d labeled pieces (of %d in manifest)", len(resolved), len(manifest_entries))

    # Write resolved manifest
    resolved_full = os.path.join(root, resolved_path) if not os.path.isabs(resolved_path) else resolved_path
    resolved_dir = os.path.dirname(resolved_full)
    if resolved_dir:
        os.makedirs(resolved_dir, exist_ok=True)
    with open(resolved_full, "w", encoding="utf-8") as f:
        json.dump(resolved, f, indent=2)
    logger.info("Wrote resolved manifest: %s", resolved_full)

    # Build labeled/ directory
    labeled_full = os.path.join(root, labeled_dir) if not os.path.isabs(labeled_dir) else labeled_dir
    if clear_labeled and os.path.isdir(labeled_full):
        shutil.rmtree(labeled_full)
    build_labeled_dir(resolved, labeled_full, project_root=root, use_symlinks=use_symlinks)
    logger.info("Wrote labeled pieces to: %s", labeled_full)

    return resolved


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Apply semantic labels to segmented pieces")
    ap.add_argument("--manifest", default="segmented_pieces/manifest.json", help="Path to manifest.json")
    ap.add_argument("--labels", default="piece_labels.json", help="Path to piece_labels.json")
    ap.add_argument("--labeled-dir", default="labeled", help="Output directory for labeled pieces")
    ap.add_argument("--resolved", default="resolved_manifest.json", help="Output path for resolved manifest")
    ap.add_argument("--project-root", default=None, help="Project root (default: cwd)")
    ap.add_argument("--no-clear", action="store_true", help="Do not clear labeled dir before writing")
    ap.add_argument("--symlink", action="store_true", help="Use symlinks instead of copying")

    args = ap.parse_args()
    run(
        manifest_path=args.manifest,
        labels_path=args.labels,
        labeled_dir=args.labeled_dir,
        resolved_path=args.resolved,
        project_root=args.project_root,
        clear_labeled=not args.no_clear,
        use_symlinks=args.symlink,
    )
