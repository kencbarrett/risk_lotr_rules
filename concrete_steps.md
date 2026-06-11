## ✅ Goal

Turn the “NEXT_STEPS.md” intent into a concrete implementation plan by closing gaps in the current repo (segmentation wrapper, richer manifest & naming, and a clearer pipeline).

---

## 1) Add `segment_composite_images()` wrapper (doc-aligned API)

### Why
NEXT_STEPS.md explicitly calls out a function with this name, but the repo currently has only `segment_composite_image()`.

### What to do
1. Add a new function `segment_composite_images(input_dir, output_dir, ...)` in segment_images.py that:
   - Finds all extracted images in `input_dir`
   - Calls the existing `segment_composite_image()` for each file
   - Emits a combined manifest (`manifest.json`) listing all segmented pieces
2. Update any scripts (e.g., rebuild_lotr.py) to call `segment_composite_images()` instead of the low-level helper.

---

## 2) Improve segmentation output naming + manifest (descriptive & positional)

### Why
Current output uses sequential numbering (`piece_001.png`) and manifest lacks bounding boxes/locations.

### What to do
1. Change output naming logic in segment_images.py to include:
   - Source image name (e.g., `battalion_sheet`)
   - Piece index and optionally a hint (e.g., `battalion_sheet_piece_01.png`)
2. Expand manifest schema to include (while remaining backward compatible):
   - `source_image` (filename of the composite)
   - `piece_path` (preferred path to the extracted piece)
   - `path` (legacy field kept for compatibility)
   - `piece_index`
   - `bounding_box`: {x,y,w,h}
   - `segmentation_method` (e.g., `auto`, `contour`, `color`, `grid`)
3. Ensure label_pieces.py and suggest_labels.py consume the new manifest fields (especially `piece_path` and `bounding_box`) without breaking.

---

## 3) Add a “composite type / specialized segmentation” layer (Option 3)

### Why
Some composites are known (battalions, leaders, sites), and special rules produce better segmentation than generic contour logic.

### What to do
1. Add a mapping of known composite image patterns:
   - e.g., if (width,height) or filename matches “battalion”, apply a fixed grid-slice or known bounding boxes
2. Implement the special-case handlers in segment_images.py:
   - `segment_battalion_sheet()`, `segment_leader_shields()`, etc.
3. Fall back to the existing contour-based method when no known pattern matches.

---

## 4) Improve end-to-end pipeline orchestration (single “run everything” flow)

### Why
The current scripts are fragmented; user wants a clear extract → segment → label path.

### What to do
1. Modify rebuild_lotr.py (or add a new CLI/command) that:
   - Extracts images (if needed)
   - Runs `segment_composite_images()` to generate segmented pieces + manifest
   - Runs label assignment (using label_pieces.py / suggest_labels.py)
   - Emits final output (e.g., resolved_manifest.json / labeled assets)
2. Expose flags like `--segment`, `--label`, `--all`, so the pipeline is easy to run.

---

## 5) Optional: Add a “color-based segmentation” alternative (Option 1)

### Why
The document suggests a color-region approach; this can improve segmentation for pieces that are easily separable by dominant palette.

### What to do (optional / future)
1. Add a new segmentation mode under segment_images.py:
   - Use OpenCV k-means / color clustering on the composite
   - Extract bounding boxes per color region
   - Optionally allow mode selection via CLI (`--method contour|color|auto`)
2. Keep this as an alternative, so current contour-based logic remains the default.

---
