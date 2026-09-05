# DSOLNEX QR Code Generator

A password-protected Streamlit web app that converts CSV values into print-ready QR PDF files.

## Features

- Unicode/Bangla text support
- Proper quoted CSV and multiline-cell support
- Select the column that contains the QR value
- Use a serial-number column for reference
- QR size, gaps, and margins in mm, cm, or inches
- A3, A4, A5, A6, Letter, Legal, Tabloid, and custom sheet sizes
- Multi-page PDF and continuous roll PDF layouts
- High QR error correction

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a new GitHub repository and upload these three files.
2. In Streamlit Community Cloud choose the repository and set the main file path to `app.py`.
3. Click Deploy.

No `packages.txt` is required for this app.
