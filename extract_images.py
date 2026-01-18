import os
import pymupdf

pdf_file_path = "risk-lord-of-the-rings-edition.pdf"

doc = pymupdf.open(pdf_file_path)

for page_index in range(len(doc)):
    page = doc[page_index]
    image_list = page.get_images()

    for img_index, img in enumerate(image_list):
        xref = img[0]  # Get the XREF
        
        # Alternative extraction: returns a dictionary
        extracted = doc.extract_image(xref)
        
        if extracted:
            img_bytes = extracted["image"]  # Raw image data
            ext = extracted["ext"]          # Original extension (e.g., 'jpeg', 'png')
            
            # Save using the original format
            dirname = os.path.abspath("extracted_impages")
            os.makedirs(dirname, exist_ok=True)

            filename = f"page{page_index}_img{img_index}.{ext}"
            filename = os.path.join(dirname, filename)
            with open(filename, "wb") as f:
                f.write(img_bytes)

 