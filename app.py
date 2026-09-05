from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass

import qrcode
import streamlit as st
from PIL import Image


st.set_page_config(page_title="QR CSV Generator", page_icon="▣", layout="wide")


@dataclass
class QRItem:
    label: str
    value: str


ERROR_LEVELS = {
    "Low (7%)": qrcode.constants.ERROR_CORRECT_L,
    "Medium (15%)": qrcode.constants.ERROR_CORRECT_M,
    "Quartile (25%)": qrcode.constants.ERROR_CORRECT_Q,
    "High (30%) – recommended": qrcode.constants.ERROR_CORRECT_H,
}


def decode_csv(raw: bytes) -> str:
    """Open CSVs exported by Excel, Illustrator workflows, or UTF-8 editors."""
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("The CSV could not be decoded. Please export it as UTF-8 CSV.")


def read_rows(text: str, delimiter: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))


def make_safe_name(label: str, index: int) -> str:
    label = re.sub(r"[<>:/\\|?*\x00-\x1f]", "_", label).strip().strip(".")
    label = re.sub(r"\s+", " ", label)
    return (label[:70] or f"QR_{index:04d}")


def make_qr_png(value: str, pixels: int, border: int, error_level: int) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=error_level,
        box_size=10,
        border=border,
    )
    # qrcode uses UTF-8 byte mode automatically for Bangla and other Unicode text.
    qr.add_data(value, optimize=0)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    image = image.resize((pixels, pixels), Image.Resampling.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def build_zip(items: list[QRItem], pixels: int, border: int, error_level: int) -> bytes:
    output = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, item in enumerate(items, start=1):
            name = make_safe_name(item.label, index)
            candidate = name
            suffix = 2
            while candidate.lower() in used_names:
                candidate = f"{name}_{suffix}"
                suffix += 1
            used_names.add(candidate.lower())
            archive.writestr(
                f"{index:04d}_{candidate}.png",
                make_qr_png(item.value, pixels, border, error_level),
            )
    return output.getvalue()


def nonempty(value: str) -> bool:
    # Preserve spaces and blank lines in the final QR value; only use strip to skip empty cells.
    return bool(value.strip())


st.title("QR Code CSV Generator")
st.caption("Upload a CSV, select the text column, then download every QR code as a PNG ZIP file.")

with st.sidebar:
    st.header("QR settings")
    pixel_size = st.select_slider("PNG size", options=[512, 768, 1024, 1536, 2048], value=1024)
    quiet_zone = st.slider("White border / quiet zone", min_value=2, max_value=8, value=4)
    error_label = st.selectbox("Error correction", list(ERROR_LEVELS), index=3)
    st.caption("High correction is safest for print, especially if a QR is small.")

uploaded_file = st.file_uploader("Upload CSV", type=["csv"], help="UTF-8 CSV recommended. Quoted cells may contain commas and multiple lines.")

if not uploaded_file:
    st.info("CSV example: one QR value in each row of the first column. Bangla and multiline text are supported.")
    st.code('serial,text\nF00001,"বাংলাদেশ কৃষি উন্নয়ন কর্পোরেশন\nক্রমিক নং: F00001"', language="csv")
    st.stop()

try:
    csv_text = decode_csv(uploaded_file.getvalue())
except ValueError as error:
    st.error(str(error))
    st.stop()

delimiter_name = st.selectbox("CSV separator", ["Comma (,)", "Semicolon (;)", "Tab"], index=0)
delimiter = {"Comma (,)": ",", "Semicolon (;)": ";", "Tab": "\t"}[delimiter_name]

try:
    rows = read_rows(csv_text, delimiter)
except csv.Error as error:
    st.error(f"CSV could not be read: {error}")
    st.stop()

if not rows:
    st.warning("This CSV is empty.")
    st.stop()

has_header = st.checkbox("First row contains column names", value=True)
max_columns = max(len(row) for row in rows)
if has_header:
    headers = [(rows[0][i] or f"Column {i + 1}") for i in range(max_columns)]
    data_rows = rows[1:]
else:
    headers = [f"Column {i + 1}" for i in range(max_columns)]
    data_rows = rows

if not data_rows:
    st.warning("No data rows found after the header row.")
    st.stop()

data_column = st.selectbox("Column containing QR text", headers)
label_column = st.selectbox("Filename / label column", ["Row number"] + headers, index=0)
data_index = headers.index(data_column)
label_index = headers.index(label_column) if label_column != "Row number" else None

items: list[QRItem] = []
for row_number, row in enumerate(data_rows, start=2 if has_header else 1):
    value = row[data_index] if data_index < len(row) else ""
    if not nonempty(value):
        continue
    label = row[label_index] if label_index is not None and label_index < len(row) else f"QR_{row_number:04d}"
    items.append(QRItem(label=label, value=value.replace("\r\n", "\n").replace("\r", "\n")))

if not items:
    st.warning("The selected QR-text column has no non-empty values.")
    st.stop()

if len(items) > 1500:
    st.error("Please upload 1,500 or fewer QR values at a time.")
    st.stop()

st.success(f"{len(items)} QR code{'s' if len(items) != 1 else ''} ready.")

preview_col, info_col = st.columns([1, 2])
with preview_col:
    preview_png = make_qr_png(items[0].value, pixel_size, quiet_zone, ERROR_LEVELS[error_label])
    st.image(preview_png, caption=f"Preview: {items[0].label}", width=260)
with info_col:
    st.subheader("First QR data")
    st.code(items[0].value, language=None)
    st.caption("Spaces and blank lines are kept exactly as they appear in the CSV cell.")

if st.button("Generate ZIP file", type="primary"):
    with st.spinner("Generating QR PNG files…"):
        st.session_state["qr_zip"] = build_zip(items, pixel_size, quiet_zone, ERROR_LEVELS[error_label])
        st.session_state["qr_zip_name"] = f"qr_codes_{len(items)}.zip"

if "qr_zip" in st.session_state:
    st.download_button(
        "Download QR PNG ZIP",
        data=st.session_state["qr_zip"],
        file_name=st.session_state["qr_zip_name"],
        mime="application/zip",
        type="primary",
    )
