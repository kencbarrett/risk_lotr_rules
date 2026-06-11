import pymupdf

doc = pymupdf.open("risk-lord-of-the-rings-edition.pdf")
full_text = []

for page in doc:
    # "blocks" mode preserves paragraph structure better than raw text
    blocks = page.get_text("blocks")
    for b in blocks:
        # b[4] is the actual text content of the block
        full_text.append(b[4].strip())

# Write to a file to see if ANYTHING came out
with open("debug_rules.txt", "w", encoding="utf-8") as f:
    f.write("\n\n".join(full_text))

print(f"Extraction complete. Found {len(full_text)} blocks of text.")
