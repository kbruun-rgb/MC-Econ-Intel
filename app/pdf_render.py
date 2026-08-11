"""Renders PDF pages as JPEG images so a report can be embedded as a plain
vertical stack of <img> tags -- scrolls with the page itself, instead of a
native PDF viewer with its own toolbar/thumbnails/internal scrollbar.
Rendered pages are cached on disk, keyed by the source file's mtime, so a
new monthly edition invalidates the cache automatically.
"""
import hashlib
import os

CACHE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "content_cache", "pdf_pages")
ZOOM = 2.0
JPEG_QUALITY = 82


def pdf_page_count(pdf_path):
    import fitz

    with fitz.open(pdf_path) as doc:
        return doc.page_count


def render_pdf_page(pdf_path, page_number, cache_root=CACHE_ROOT):
    """Returns the path to a cached JPEG of the given 1-indexed page,
    rendering it first if there's no cache entry for this exact file
    version yet.
    """
    import fitz

    mtime = int(os.path.getmtime(pdf_path))
    basename = os.path.splitext(os.path.basename(pdf_path))[0]
    # Two reports from different folders can share a filename (e.g. a
    # differently-shaped naming clash) -- key on the full resolved path,
    # not just the filename, so their caches can never collide or clobber
    # each other's "previous edition" cleanup below.
    path_hash = hashlib.sha1(os.path.realpath(pdf_path).encode("utf-8")).hexdigest()[:10]
    cache_key = f"{basename}-{path_hash}"
    cache_path = os.path.join(cache_root, f"{cache_key}__{mtime}__p{page_number}.jpg")

    if os.path.isfile(cache_path):
        return cache_path

    os.makedirs(cache_root, exist_ok=True)

    # Clear any renders from a previous edition of this same report before
    # adding this one -- otherwise every monthly refresh leaves its old
    # pages behind forever since each mtime gets its own cache filename.
    prefix = f"{cache_key}__"
    for f in os.scandir(cache_root):
        if f.name.startswith(prefix) and not f.name.startswith(f"{cache_key}__{mtime}__"):
            try:
                os.remove(f.path)
            except OSError:
                pass

    with fitz.open(pdf_path) as doc:
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
        pixmap.save(cache_path, jpg_quality=JPEG_QUALITY)

    return cache_path
