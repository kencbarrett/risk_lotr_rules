# Next Steps: Image Segmentation

## Challenge
Some extracted PDF images are composites containing multiple game pieces/icons (e.g., the battalion pieces, leaders, and sites of power all in a single PNG file). These should be automatically segmented into individual image files for each piece.

## Example
The game pieces image contains:
- 3 gold battalion pieces (Elven Archer, Rider of Rohan, Eagle)
- 3 red battalion pieces (Orc, Dark Rider, Cave Troll)
- 2 leader shields
- Multiple sites of power icons (arranged in a grid)

Currently this is extracted as a single composite image, but ideally each piece should be its own file.

## Proposed Solution
Implement image segmentation using one of these approaches:

### Option 1: Color-Based Segmentation
- Detect distinct color regions (gold pieces, red pieces, black shields, etc.)
- Extract bounding boxes for each color group
- Crop and save individually

### Option 2: Contour Detection
- Use edge detection to find individual piece outlines
- Extract connected components/contours
- Crop and save each detected object

### Option 3: Targeted Composite Handling
- Identify known composite images by size/content
- Apply specialized segmentation rules per composite type
- Fallback to general approach for unknowns

## Implementation Approach
Add a new function `segment_composite_images()` that:
1. Loads each extracted image
2. Detects whether it's a composite
3. Segments into individual pieces
4. Saves each piece with a descriptive name or sequential numbering
5. Optionally generates a manifest mapping piece locations to source composite

## Dependencies
- OpenCV (`cv2`) or scikit-image for image processing
- NumPy for array manipulation
