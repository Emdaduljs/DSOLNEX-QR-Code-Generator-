from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path

import qrcode
import streamlit as st
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

st.set_page_config(page_title="DSOLNEX QR Code Generator", page_icon="▣", layout="wide")

# Simple private-tool login. Use Streamlit secrets/proper auth before public release.
USERS = {"Emdaduljs": "123", "Test1": "1234", "Test2": "12345", "Test3": "123456"}
ERROR_LEVELS = {
    "Low (7%)": qrcode.constants.ERROR_CORRECT_L,
    "Medium (15%)": qrcode.constants.ERROR_CORRECT_M,
    "Quartile (25%)": qrcode.constants.ERROR_CORRECT_Q,
    "High (30%) - recommended": qrcode.constants.ERROR_CORRECT_H,
}
PAPER_SIZES_MM = {
    "A3 (297 x 420 mm)": (297.0, 420.0), "A4 (210 x 297 mm)": (210.0, 297.0),
    "A5 (148 x 210 mm)": (148.0, 210.0), "A6 (105 x 148 mm)": (105.0, 148.0),
    "Letter (216 x 279 mm)": (215.9, 279.4), "Legal (216 x 356 mm)": (215.9, 355.6),
    "Tabloid (279 x 432 mm)": (279.4, 431.8),
}
MM_PER_UNIT = {"mm": 1.0, "cm": 10.0, "inch": 25.4}
PT_PER_MM = 72 / 25.4


@dataclass
class QRItem:
    label: str
    value: str


def to_mm(value: float, unit: str) -> float:
    return value * MM_PER_UNIT[unit]


def decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("The CSV could not be decoded. Please export it as UTF-8 CSV.")


def make_qr_image(value: str, error_level: int) -> Image.Image:
    qr = qrcode.QRCode(version=None, error_correction=error_level, box_size=12, border=4)
    qr.add_data(value, optimize=0)  # UTF-8 byte mode preserves Bangla and multiline text.
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def build_pdf(items, qr_w_mm, qr_h_mm, gap_x_mm, gap_y_mm, margins_mm, page_size_mm, error_level, roll_mode):
    left, right, top, bottom = margins_mm
    page_w_mm, page_h_mm = page_size_mm
    usable_w = page_w_mm - left - right
    if usable_w < qr_w_mm:
        raise ValueError("QR width is larger than the printable page width.")
    columns = max(1, math.floor((usable_w + gap_x_mm) / (qr_w_mm + gap_x_mm)))
    if roll_mode:
        rows_per_page = math.ceil(len(items) / columns)
        page_h_mm = top + bottom + rows_per_page * qr_h_mm + max(0, rows_per_page - 1) * gap_y_mm
        pages = 1
    else:
        usable_h = page_h_mm - top - bottom
        if usable_h < qr_h_mm:
            raise ValueError("QR height is larger than the printable page height.")
        rows_per_page = max(1, math.floor((usable_h + gap_y_mm) / (qr_h_mm + gap_y_mm)))
        pages = math.ceil(len(items) / (columns * rows_per_page))

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(page_w_mm * PT_PER_MM, page_h_mm * PT_PER_MM))
    qr_w_pt, qr_h_pt = qr_w_mm * PT_PER_MM, qr_h_mm * PT_PER_MM
    gap_x_pt, gap_y_pt = gap_x_mm * PT_PER_MM, gap_y_mm * PT_PER_MM
    left_pt, top_pt, page_h_pt = left * PT_PER_MM, top * PT_PER_MM, page_h_mm * PT_PER_MM
    per_sheet = columns * rows_per_page
    for index, item in enumerate(items):
        on_page = index if roll_mode else index % per_sheet
        if index and not roll_mode and on_page == 0:
            pdf.showPage()
        row, col = divmod(on_page, columns)
        x = left_pt + col * (qr_w_pt + gap_x_pt)
        y = page_h_pt - top_pt - qr_h_pt - row * (qr_h_pt + gap_y_pt)
        png = io.BytesIO()
        make_qr_image(item.value, error_level).save(png, format="PNG", optimize=True)
        pdf.drawImage(ImageReader(png), x, y, width=qr_w_pt, height=qr_h_pt, mask="auto")
    pdf.save()
    return stream.getvalue(), columns, rows_per_page, pages


with st.sidebar:
    logo = Path("assets/ui_logo.png")
    if logo.exists():
        st.image(str(logo), use_container_width=True)
    st.divider()
    st.subheader("🔒 Login")
    username = st.selectbox("Username", list(USERS), key="login_user")
    password = st.text_input("Password", type="password", key="login_pass")
    if password != USERS.get(username):
        st.warning("Invalid username or password. Please login to continue.")
        st.stop()
    st.success(f"{'Editor' if username == 'Emdaduljs' else 'User'}: {username}")
    st.divider()
    st.caption("DSOLNEX QR Code Generator")

st.title("DSOLNEX QR Code Generator")
st.caption("CSV to print-ready PDF - standard sheets, custom page sizes, and continuous roll printing.")
with st.expander("CSV format example"):
    st.code('serial,qr_text\nF00001,"বাংলাদেশ কৃষি উন্নয়ন কর্পোরেশন\nক্রমিক নং: F00001"', language="csv")

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
if not uploaded_file:
    st.info("Upload a CSV to begin. One selected cell creates one QR code.")
    st.stop()

try:
    csv_text = decode_csv(uploaded_file.getvalue())
except ValueError as error:
    st.error(str(error)); st.stop()

first, second = st.columns(2)
with first:
    delimiter_name = st.selectbox("CSV separator", ["Comma (,)", "Semicolon (;)", "Tab"])
    delimiter = {"Comma (,)": ",", "Semicolon (;)": ";", "Tab": "\t"}[delimiter_name]
    has_header = st.checkbox("First row contains column names", value=True)
with second:
    layout_type = st.radio("Print format", ["Sheet PDF (A4 / A3 / custom)", "Continuous roll PDF"], horizontal=True)

try:
    rows = list(csv.reader(io.StringIO(csv_text, newline=""), delimiter=delimiter))
except csv.Error as error:
    st.error(f"CSV could not be read: {error}"); st.stop()
if not rows:
    st.warning("This CSV is empty."); st.stop()
max_columns = max(len(row) for row in rows)
headers = [(rows[0][i] or f"Column {i + 1}") for i in range(max_columns)] if has_header else [f"Column {i + 1}" for i in range(max_columns)]
data_rows = rows[1:] if has_header else rows
if not data_rows:
    st.warning("No data rows found."); st.stop()

first, second = st.columns(2)
with first: data_column = st.selectbox("Column containing QR text", headers)
with second: label_column = st.selectbox("Reference / serial column", ["Row number"] + headers)
data_index = headers.index(data_column)
label_index = headers.index(label_column) if label_column != "Row number" else None
items = []
for row_number, row in enumerate(data_rows, start=2 if has_header else 1):
    value = row[data_index] if data_index < len(row) else ""
    if value.strip():
        label = row[label_index] if label_index is not None and label_index < len(row) else f"Row {row_number}"
        items.append(QRItem(label, value.replace("\r\n", "\n").replace("\r", "\n")))
if not items:
    st.warning("The selected QR-text column has no values."); st.stop()
if len(items) > 1000:
    st.error("Please generate a maximum of 1,000 QR codes per PDF."); st.stop()
st.success(f"{len(items)} QR codes found in your CSV.")

st.subheader("QR and layout settings")
unit = st.selectbox("Measurement unit", ["mm", "cm", "inch"])
default_size, default_gap, default_margin = (35.0, 5.0, 10.0) if unit == "mm" else (3.5, 0.5, 1.0)
cols = st.columns(4)
with cols[0]: qr_w_value = st.number_input(f"QR width ({unit})", 0.1, value=default_size, step=0.1)
with cols[1]: qr_h_value = st.number_input(f"QR height ({unit})", 0.1, value=default_size, step=0.1)
with cols[2]: gap_x_value = st.number_input(f"Left / right gap ({unit})", 0.0, value=default_gap, step=0.1)
with cols[3]: gap_y_value = st.number_input(f"Top / bottom gap ({unit})", 0.0, value=default_gap, step=0.1)
cols = st.columns(4)
with cols[0]: margin_left = st.number_input(f"Left margin ({unit})", 0.0, value=default_margin, step=0.1)
with cols[1]: margin_right = st.number_input(f"Right margin ({unit})", 0.0, value=default_margin, step=0.1)
with cols[2]: margin_top = st.number_input(f"Top margin ({unit})", 0.0, value=default_margin, step=0.1)
with cols[3]: margin_bottom = st.number_input(f"Bottom margin ({unit})", 0.0, value=default_margin, step=0.1)
qr_w_mm, qr_h_mm = to_mm(qr_w_value, unit), to_mm(qr_h_value, unit)
gap_x_mm, gap_y_mm = to_mm(gap_x_value, unit), to_mm(gap_y_value, unit)
margins_mm = tuple(to_mm(value, unit) for value in (margin_left, margin_right, margin_top, margin_bottom))
if not math.isclose(qr_w_mm, qr_h_mm, rel_tol=0, abs_tol=0.01):
    st.error("QR width and height must be equal. A non-square QR may not scan correctly."); st.stop()

paper_choice = st.selectbox("Paper size", list(PAPER_SIZES_MM) + ["Custom size"])
orientation = st.radio("Orientation", ["Portrait", "Landscape"], horizontal=True, disabled=layout_type == "Continuous roll PDF")
if paper_choice == "Custom size":
    first, second = st.columns(2)
    with first: custom_w = st.number_input(f"Custom page width ({unit})", 1.0, value=210.0 if unit == "mm" else 21.0, step=1.0)
    with second: custom_h = st.number_input(f"Custom page height ({unit})", 1.0, value=297.0 if unit == "mm" else 29.7, step=1.0)
    page_size_mm = (to_mm(custom_w, unit), to_mm(custom_h, unit))
else:
    page_size_mm = PAPER_SIZES_MM[paper_choice]
if orientation == "Landscape": page_size_mm = (page_size_mm[1], page_size_mm[0])
if layout_type == "Continuous roll PDF":
    roll_width = st.number_input(f"Roll width ({unit})", 1.0, value=100.0 if unit == "mm" else 10.0, step=1.0)
    page_size_mm = (to_mm(roll_width, unit), 1.0)
    st.info("One PDF page is created at the selected roll width. Its height is calculated for all QR codes. Print at Actual Size / 100%.")
error_label = st.selectbox("QR error correction", list(ERROR_LEVELS), index=3)

available_w = page_size_mm[0] - margins_mm[0] - margins_mm[1]
if available_w < qr_w_mm:
    st.error("QR width plus margins does not fit the selected paper / roll width."); st.stop()
columns = max(1, math.floor((available_w + gap_x_mm) / (qr_w_mm + gap_x_mm)))
if layout_type == "Continuous roll PDF":
    rows_per_page, pages = math.ceil(len(items) / columns), 1
else:
    available_h = page_size_mm[1] - margins_mm[2] - margins_mm[3]
    if available_h < qr_h_mm:
        st.error("QR height plus margins does not fit the selected paper."); st.stop()
    rows_per_page = max(1, math.floor((available_h + gap_y_mm) / (qr_h_mm + gap_y_mm)))
    pages = math.ceil(len(items) / (columns * rows_per_page))
st.info(f"Layout: {columns} columns × {rows_per_page} rows{' on the roll' if layout_type == 'Continuous roll PDF' else ' per page'} - {pages} PDF page{'s' if pages != 1 else ''}.")

first, second = st.columns([1, 2])
with first: st.image(make_qr_image(items[0].value, ERROR_LEVELS[error_label]), caption=f"Preview: {items[0].label}", width=250)
with second:
    st.subheader("First QR data")
    st.code(items[0].value, language=None)
    st.caption("Spaces and blank lines from the CSV cell are preserved.")
if st.button("Generate print-ready PDF", type="primary"):
    try:
        with st.spinner("Generating QR PDF…"):
            pdf_bytes, _, _, pages = build_pdf(items, qr_w_mm, qr_h_mm, gap_x_mm, gap_y_mm, margins_mm, page_size_mm, ERROR_LEVELS[error_label], layout_type == "Continuous roll PDF")
        st.session_state["qr_pdf"] = pdf_bytes
        st.session_state["qr_pdf_name"] = "dsolnex_qr_roll.pdf" if layout_type == "Continuous roll PDF" else "dsolnex_qr_codes.pdf"
        st.success(f"PDF ready: {pages} page{'s' if pages != 1 else ''}.")
    except ValueError as error:
        st.error(str(error))
if "qr_pdf" in st.session_state:
    st.download_button("Download QR PDF", st.session_state["qr_pdf"], st.session_state["qr_pdf_name"], "application/pdf", type="primary")
