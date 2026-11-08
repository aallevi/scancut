# Add-ons

Optional parts, installed from **Add-ons** with a progress bar:

- **Tools**: the Apple Vision helpers, SANE (scanner), ExifTool (text in cut files), JPEG XL.
- **SAM 3**: Ultralytics and the model (about 3.4 GB; needs a free Hugging Face access request).
- **Remove background**: BiRefNet lite (recommended, ~180 MB) and other BiRefNet models.
- **Text (OCR)**: Ollama runs the readers on this Mac; GLM-OCR and Qwen3-VL download from here.
  Unlimited-OCR installs its own small Python (once per Mac) and runs on the Apple GPU; a model already
  on the Mac is not downloaded again.

Models are stored once on this Mac and load only when used.
