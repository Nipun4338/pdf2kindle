# Free, local Engines only

Every Engine must be free and run locally — no paid or cloud OCR/LLM services, even as opt-ins — so anyone can run the open-source project without accounts or keys and no book ever leaves the user's machine. We accept lower Bengali OCR quality (Tesseract with preprocessing) and heuristic structure detection; low-confidence pages become Image Fallbacks and the TOC is user-editable to compensate.

## Considered Options

- Claude vision / Google Vision Engines with the user's own key: better Bengali OCR and structure cleanup, rejected for cost and privacy.
- Local Ollama Engine: free, but too heavy for a default; may arrive later as an opt-in.
