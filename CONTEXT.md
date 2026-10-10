# PDF to Kindle

Turns a Source PDF (Bengali, English, or mixed) into a Reflowable EPUB that reads well on a Kindle.

## Language

### Input

**Source PDF**:
The PDF a user hands in for conversion.
_Avoid_: Input file, document

**Text Page**:
A page whose text layer extracts as correct Unicode.

**Legacy-Encoded Page**:
A page whose text layer uses a pre-Unicode Bengali font (e.g. Bijoy/SutonnyMJ), so extracted text is garbled until remapped.
_Avoid_: Bijoy page, ANSI page

**Scanned Page**:
A page with no usable text layer; its text exists only as pixels.
_Avoid_: Image page

**Complex Page**:
A page whose layout (tables, math, multi-column art, comics) can't be faithfully reflowed.

### Output

**Reflowable EPUB**:
The output book: resizable, wrapping text rather than fixed page images.
_Avoid_: Kindle book, ebook

**Image Fallback**:
A Source PDF page included in the Reflowable EPUB as a rendered image, used when its text can't be reconstructed with confidence.
_Avoid_: Fixed page, snapshot

**TOC**:
The ordered list of chapter entries that becomes the EPUB's navigation; derived from bookmarks, then typography, and editable by the user.
_Avoid_: Outline, index

### Processing

**Conversion**:
One run of a Source PDF through the pipeline, tracked with page-level progress; its per-page results are reused when re-exporting.
_Avoid_: Job, task

**Engine**:
A swappable, free, locally-run provider for a step such as OCR.
_Avoid_: Backend, provider

**Page Noise**:
Running headers, footers and page numbers that repeat across pages and are stripped before reflow.
_Avoid_: Furniture, boilerplate

**Conversion Report**:
The per-page summary shown before export: Page kind, whether it became an Image Fallback, and OCR confidence.
_Avoid_: Log, preview
