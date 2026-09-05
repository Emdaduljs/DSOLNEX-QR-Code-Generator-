# QR Code CSV Generator

A Streamlit web app that converts CSV values to individual high-resolution QR PNG files and delivers them in one ZIP file.

## Features

- Unicode/Bangla text support
- Proper quoted CSV and multiline-cell support
- Select the column that contains the QR value
- Use a serial-number column for PNG file names
- High-resolution print PNGs (512–2048 px)
- High QR error correction and configurable quiet zone

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
