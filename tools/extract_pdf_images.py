"""Extract question diagrams from an exam-paper PDF.

Pulls out both embedded raster images and vector-drawn figures, saves them as
PNGs into a working directory, and writes an images_report.json describing
where each image came from (page, position, nearby question text) so the
images can be matched to questions during JSON conversion.

Usage:
    python tools/extract_pdf_images.py paper.pdf [-o out_dir]
                                       [--min-dim 50] [--zoom 3.0]

Output:
    out_dir/
        p03_img1.png        extracted images, named by page + index
        ...
        images_report.json  [{file, page, kind, bbox, width, height,
                              nearby_text}]

Heuristics:
    - Images smaller than --min-dim px in either direction are skipped
      (bullets, logos, rules).
    - An identical image appearing on 3+ pages is treated as a decoration
      (header/watermark) and skipped.
    - Vector figures are found via drawing clusters and rendered at --zoom.
    - nearby_text is the text immediately above the image on the page,
      which usually contains the question number.
"""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF is required: pip install pymupdf")

DECORATION_PAGE_THRESHOLD = 3
NEARBY_TEXT_HEIGHT = 90  # points above the image to scan for question text
NEARBY_TEXT_MAX_CHARS = 160


def nearby_text(page, rect):
    """Text just above (or overlapping the top of) the image bounds."""
    # Full page width: question text is often left-aligned while the
    # figure sits indented or in a second column.
    zone = fitz.Rect(
        0,
        max(0, rect.y0 - NEARBY_TEXT_HEIGHT),
        page.rect.x1,
        rect.y0 + 10,
    )
    text = " ".join(page.get_text("text", clip=zone).split())
    return text[-NEARBY_TEXT_MAX_CHARS:]


def extract_embedded(doc, min_dim):
    """Yield (page_index, rect, pixmap) for embedded raster images."""
    # First pass: find images repeated across many pages (decorations).
    pages_by_digest = defaultdict(set)
    for page_index in range(len(doc)):
        for img in doc[page_index].get_images(full=True):
            xref = img[0]
            digest = hashlib.sha1(doc.extract_image(xref)["image"]).hexdigest()
            pages_by_digest[digest].add(page_index)
    decorations = {
        d for d, pages in pages_by_digest.items()
        if len(pages) >= DECORATION_PAGE_THRESHOLD
    }

    for page_index in range(len(doc)):
        page = doc[page_index]
        for img in page.get_images(full=True):
            xref = img[0]
            extracted = doc.extract_image(xref)
            digest = hashlib.sha1(extracted["image"]).hexdigest()
            if digest in decorations:
                continue
            if extracted["width"] < min_dim or extracted["height"] < min_dim:
                continue
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.colorspace and pix.colorspace.n > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
            except Exception as e:
                print(f"  warning: could not decode image xref {xref} "
                      f"on page {page_index + 1}: {e}")
                continue
            yield page_index, rects[0], pix


def extract_vector(doc, min_dim, zoom):
    """Yield (page_index, rect, pixmap) for vector-drawn figures."""
    for page_index in range(len(doc)):
        page = doc[page_index]
        try:
            clusters = page.cluster_drawings()
        except Exception:
            continue
        for rect in clusters:
            if rect.width < min_dim or rect.height < min_dim:
                continue
            # Full-page-width boxes are usually tables/borders, not figures;
            # keep them anyway but flag via size in the report. Render clip.
            pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(zoom, zoom))
            yield page_index, rect, pix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="Path to the exam paper PDF")
    parser.add_argument("-o", "--out", default=None,
                        help="Output directory (default: <pdf name>_images)")
    parser.add_argument("--min-dim", type=int, default=50,
                        help="Skip images smaller than this in px/pt (default 50)")
    parser.add_argument("--zoom", type=float, default=3.0,
                        help="Render zoom for vector figures (default 3.0)")
    parser.add_argument("--no-vector", action="store_true",
                        help="Skip vector figure detection")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        sys.exit(f"PDF not found: {args.pdf}")

    out_dir = args.out or os.path.splitext(args.pdf)[0] + "_images"
    os.makedirs(out_dir, exist_ok=True)

    doc = fitz.open(args.pdf)
    report = []
    counters = defaultdict(int)

    def save(page_index, rect, pix, kind):
        counters[page_index] += 1
        name = f"p{page_index + 1:02d}_img{counters[page_index]}.png"
        path = os.path.join(out_dir, name)
        pix.save(path)
        page = doc[page_index]
        report.append({
            "file": name,
            "page": page_index + 1,
            "kind": kind,
            "bbox": [round(v, 1) for v in rect],
            "width": pix.width,
            "height": pix.height,
            "nearby_text": nearby_text(page, rect),
        })

    print(f"Scanning {len(doc)} pages of {os.path.basename(args.pdf)} ...")
    for page_index, rect, pix in extract_embedded(doc, args.min_dim):
        save(page_index, rect, pix, "embedded")
    if not args.no_vector:
        for page_index, rect, pix in extract_vector(doc, args.min_dim, args.zoom):
            save(page_index, rect, pix, "vector")

    report.sort(key=lambda r: (r["page"], r["bbox"][1]))
    report_path = os.path.join(out_dir, "images_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Extracted {len(report)} candidate images -> {out_dir}")
    print(f"Report: {report_path}")
    if not report:
        print("No images found — the paper may be text-only, or diagrams "
              "may be part of a scanned page (use page screenshots instead).")


if __name__ == "__main__":
    main()
