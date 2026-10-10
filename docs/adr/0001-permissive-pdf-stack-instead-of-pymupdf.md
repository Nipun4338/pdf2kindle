# Permissive PDF stack instead of PyMuPDF

The project is MIT-licensed so it can be open-sourced without constraining forks. PyMuPDF is AGPL and would force the whole project to AGPL, so we use `pdfminer.six` (MIT) for text extraction and `pypdfium2` (Apache/BSD) for page rendering, accepting somewhat slower extraction and more glue code. `pdfminer.six` also exposes per-character font names, which Legacy-Encoded Page detection relies on.

## Consequences

Every new dependency must be MIT/Apache/BSD/OFL-compatible; this also rules out Surya OCR (non-OSI model-weight license).
