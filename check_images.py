#!/usr/bin/env python3
from rebuild_lotr import extract_objects, ImageObject

objects = extract_objects('risk-lord-of-the-rings-edition.pdf')
for page_num in sorted(objects.keys()):
    img_count = sum(1 for obj in objects[page_num] if isinstance(obj, ImageObject))
    if img_count > 0:
        print(f'Page {page_num + 1}: {img_count} image(s)')
