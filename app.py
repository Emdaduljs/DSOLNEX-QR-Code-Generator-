from __future__ import annotations

import csv
import io
import json
import math
import re
import zipfile
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
PRESET_FILE = Path("/tmp/dsolnex_qr_layout_presets.json")
LAYOUT_DEFAULTS = {
    "layout_type": "Sheet PDF (A4 / A3 / custom)", "layout_unit": "mm", "layout_columns": 1,
    "layout_qr_w": 35.0, "layout_qr_h": 35.0, "layout_row_gap": 5.0, "layout_middle_gap": 5.0,
    "layout_left_gap": 10.0, "layout_right_gap": 10.0, "layout_top_gap": 10.0, "layout_bottom_gap": 10.0,
    "layout_paper": "A4 (210 x 297 mm)", "layout_orientation": "Portrait",
    "layout_custom_w": 210.0, "layout_custom_h": 297.0, "layout_roll_w": 100.0,
    "layout_error": "High (30%) - recommended",
}


@dataclass
class QRItem:
    label: str
    value: str


def to_mm(value: float, unit: str) -> float:
    return value * MM_PER_UNIT[unit]


def load_presets() -> dict:
    try:
        saved = json.loads(PRESET_FILE.read_text(encoding="utf-8"))
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def save_presets(presets: dict) -> None:
    PRESET_FILE.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")


def current_layout_settings() -> dict:
    return {key: st.session_state.get(key, value) for key, value in LAYOUT_DEFAULTS.items()}


def safe_pdf_name(filename: str, index: int) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return f"{index:02d}_{stem or f'csv_{index:02d}'}.pdf"


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


def build_pdf(items, qr_w_mm, qr_h_mm, middle_gap_mm, row_gap_mm, margins_mm, page_size_mm, error_level, roll_mode, columns):
    left, right, top, bottom = margins_mm
    page_w_mm, page_h_mm = page_size_mm
    required_w = left + right + columns * qr_w_mm + max(0, columns - 1) * middle_gap_mm
    if required_w > page_w_mm:
        raise ValueError("Selected columns, QR width, left/right gaps, and middle gap do not fit the page width.")
    if roll_mode:
        rows_per_page = math.ceil(len(items) / columns)
        page_h_mm = top + bottom + rows_per_page * qr_h_mm + max(0, rows_per_page - 1) * row_gap_mm
        pages = 1
    else:
        usable_h = page_h_mm - top - bottom
        if usable_h < qr_h_mm:
            raise ValueError("QR height is larger than the printable page height.")
        rows_per_page = max(1, math.floor((usable_h + row_gap_mm) / (qr_h_mm + row_gap_mm)))
        pages = math.ceil(len(items) / (columns * rows_per_page))

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(page_w_mm * PT_PER_MM, page_h_mm * PT_PER_MM))
    qr_w_pt, qr_h_pt = qr_w_mm * PT_PER_MM, qr_h_mm * PT_PER_MM
    middle_gap_pt, row_gap_pt = middle_gap_mm * PT_PER_MM, row_gap_mm * PT_PER_MM
    left_pt, top_pt, page_h_pt = left * PT_PER_MM, top * PT_PER_MM, page_h_mm * PT_PER_MM
    per_sheet = columns * rows_per_page
    for index, item in enumerate(items):
        on_page = index if roll_mode else index % per_sheet
        if index and not roll_mode and on_page == 0:
            pdf.showPage()
        row, col = divmod(on_page, columns)
        x = left_pt + col * (qr_w_pt + middle_gap_pt)
        y = page_h_pt - top_pt - qr_h_pt - row * (qr_h_pt + row_gap_pt)
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

uploaded_files = st.file_uploader("Upload CSV file(s)", type=["csv"], accept_multiple_files=True, help="Upload up to 50 CSV files. Each CSV can contain up to 1,000 QR data rows.")
if not uploaded_files:
    st.info("Upload one or more CSV files to begin. One selected cell creates one QR code.")
    st.stop()
if len(uploaded_files) > 50:
    st.error("Please upload a maximum of 50 CSV files at one time.")
    st.stop()

try:
    csv_texts = [(uploaded.name, decode_csv(uploaded.getvalue())) for uploaded in uploaded_files]
except ValueError as error:
    st.error(str(error)); st.stop()

first, second = st.columns(2)
with first:
    delimiter_name = st.selectbox("CSV separator", ["Comma (,)", "Semicolon (;)", "Tab"])
    delimiter = {"Comma (,)": ",", "Semicolon (;)": ";", "Tab": "\t"}[delimiter_name]
    has_header = st.checkbox("First row contains column names", value=True)

try:
    parsed_csv_files = [(name, list(csv.reader(io.StringIO(csv_text, newline=""), delimiter=delimiter))) for name, csv_text in csv_texts]
except csv.Error as error:
    st.error(f"CSV could not be read: {error}"); st.stop()
empty_files = [name for name, rows in parsed_csv_files if not rows]
if empty_files:
    st.error(f"Empty CSV file: {', '.join(empty_files[:3])}"); st.stop()
first_rows = parsed_csv_files[0][1]
max_columns = max(len(row) for row in first_rows)
headers = [(first_rows[0][i] or f"Column {i + 1}") for i in range(max_columns)] if has_header else [f"Column {i + 1}" for i in range(max_columns)]

first, second = st.columns(2)
with first: data_column = st.selectbox("Column containing QR text", headers)
with second: label_column = st.selectbox("Reference / serial column", ["Row number"] + headers)
data_index = headers.index(data_column)
label_index = headers.index(label_column) if label_column != "Row number" else None
csv_batches = []
for csv_name, rows in parsed_csv_files:
    data_rows = rows[1:] if has_header else rows
    items = []
    for row_number, row in enumerate(data_rows, start=2 if has_header else 1):
        value = row[data_index] if data_index < len(row) else ""
        if value.strip():
            label = row[label_index] if label_index is not None and label_index < len(row) else f"Row {row_number}"
            items.append(QRItem(label, value.replace("\r\n", "\n").replace("\r", "\n")))
    if not items:
        st.error(f"No QR data found in: {csv_name}"); st.stop()
    if len(items) > 1000:
        st.error(f"{csv_name} contains {len(items):,} QR data. Each CSV must contain a maximum of 1,000."); st.stop()
    csv_batches.append((csv_name, items))
total_qr = sum(len(items) for _, items in csv_batches)
st.success(f"{len(csv_batches)} CSV file(s) ready: {total_qr:,} QR codes total. Each CSV will generate a separate PDF.")

st.subheader("QR and layout settings")
presets = load_presets()
with st.expander("Save and load layout settings", expanded=True):
    st.caption("Saved settings remain available while this app environment is running. Download the JSON file to keep a permanent backup and import it anytime.")
    preset_names = list(presets)
    save_col, load_col, action_col = st.columns([2, 2, 2])
    with save_col:
        new_preset_name = st.text_input("New setting name", placeholder="Example: RT 72.10 x 35 mm - 2 columns", key="new_preset_name")
        if st.button("Save current setting", key="save_preset"):
            if not new_preset_name.strip():
                st.warning("Write a setting name before saving.")
            else:
                presets[new_preset_name.strip()] = current_layout_settings()
                save_presets(presets)
                st.success(f"Saved: {new_preset_name.strip()}")
    with load_col:
        selected_preset = st.selectbox("Saved setting", ["Select a saved setting"] + preset_names, key="selected_preset")
        if st.button("Load selected setting", key="load_preset", disabled=selected_preset == "Select a saved setting"):
            for key, value in presets[selected_preset].items():
                if key in LAYOUT_DEFAULTS:
                    st.session_state[key] = value
            st.rerun()
    with action_col:
        if st.button("Delete selected setting", key="delete_preset", disabled=selected_preset == "Select a saved setting"):
            presets.pop(selected_preset, None)
            save_presets(presets)
            st.rerun()
        preset_json = json.dumps(presets, ensure_ascii=False, indent=2)
        st.download_button("Download all saved settings", preset_json, "dsolnex_qr_layout_settings.json", "application/json")
        imported_presets = st.file_uploader("Import saved settings JSON", type=["json"], key="import_presets")
        if imported_presets and st.button("Import settings", key="import_preset_button"):
            try:
                imported = json.loads(imported_presets.getvalue().decode("utf-8"))
                if not isinstance(imported, dict):
                    raise ValueError
                for name, setting in imported.items():
                    if isinstance(name, str) and isinstance(setting, dict):
                        presets[name] = {key: setting.get(key, default) for key, default in LAYOUT_DEFAULTS.items()}
                save_presets(presets)
                st.rerun()
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                st.error("This is not a valid DSOLNEX QR settings JSON file.")

layout_type = st.radio("Print format", ["Sheet PDF (A4 / A3 / custom)", "Continuous roll PDF"], horizontal=True, key="layout_type")
unit = st.selectbox("Measurement unit", ["mm", "cm", "inch"], key="layout_unit")
default_size, default_gap, default_margin = (35.0, 5.0, 10.0) if unit == "mm" else (3.5, 0.5, 1.0)
columns_selected = st.number_input("Number of columns", min_value=1, max_value=20, value=1, step=1, key="layout_columns")
cols = st.columns(3)
with cols[0]: qr_w_value = st.number_input(f"QR width ({unit})", 0.1, value=default_size, step=0.1, key="layout_qr_w")
with cols[1]: qr_h_value = st.number_input(f"QR height ({unit})", 0.1, value=default_size, step=0.1, key="layout_qr_h")
with cols[2]: row_gap_value = st.number_input(f"Row gap - top / bottom ({unit})", 0.0, value=default_gap, step=0.1, key="layout_row_gap")
if columns_selected >= 2:
    middle_gap_value = st.number_input(f"Middle gap between columns ({unit})", 0.0, value=default_gap, step=0.1, key="layout_middle_gap")
else:
    middle_gap_value = 0.0
    st.caption("One column selected: no middle gap is required.")
cols = st.columns(4)
with cols[0]: margin_left = st.number_input(f"Left gap ({unit})", 0.0, value=default_margin, step=0.1, key="layout_left_gap")
with cols[1]: margin_right = st.number_input(f"Right gap ({unit})", 0.0, value=default_margin, step=0.1, key="layout_right_gap")
with cols[2]: margin_top = st.number_input(f"Top gap ({unit})", 0.0, value=default_margin, step=0.1, key="layout_top_gap")
with cols[3]: margin_bottom = st.number_input(f"Bottom gap ({unit})", 0.0, value=default_margin, step=0.1, key="layout_bottom_gap")
qr_w_mm, qr_h_mm = to_mm(qr_w_value, unit), to_mm(qr_h_value, unit)
middle_gap_mm, row_gap_mm = to_mm(middle_gap_value, unit), to_mm(row_gap_value, unit)
margins_mm = tuple(to_mm(value, unit) for value in (margin_left, margin_right, margin_top, margin_bottom))
if not math.isclose(qr_w_mm, qr_h_mm, rel_tol=0, abs_tol=0.01):
    st.error("QR width and height must be equal. A non-square QR may not scan correctly."); st.stop()

paper_choice = st.selectbox("Paper size", list(PAPER_SIZES_MM) + ["Custom size"], key="layout_paper")
orientation = st.radio("Orientation", ["Portrait", "Landscape"], horizontal=True, disabled=layout_type == "Continuous roll PDF", key="layout_orientation")
if paper_choice == "Custom size":
    first, second = st.columns(2)
    with first: custom_w = st.number_input(f"Custom page width ({unit})", 1.0, value=210.0 if unit == "mm" else 21.0, step=1.0, key="layout_custom_w")
    with second: custom_h = st.number_input(f"Custom page height ({unit})", 1.0, value=297.0 if unit == "mm" else 29.7, step=1.0, key="layout_custom_h")
    page_size_mm = (to_mm(custom_w, unit), to_mm(custom_h, unit))
else:
    page_size_mm = PAPER_SIZES_MM[paper_choice]
if orientation == "Landscape": page_size_mm = (page_size_mm[1], page_size_mm[0])
if layout_type == "Continuous roll PDF":
    roll_width = st.number_input(f"Roll width ({unit})", 1.0, value=100.0 if unit == "mm" else 10.0, step=1.0, key="layout_roll_w")
    page_size_mm = (to_mm(roll_width, unit), 1.0)
    st.info("One PDF page is created at the selected roll width. Its height is calculated for all QR codes. Print at Actual Size / 100%.")
error_label = st.selectbox("QR error correction", list(ERROR_LEVELS), index=3, key="layout_error")

columns = int(columns_selected)
required_w = margins_mm[0] + margins_mm[1] + columns * qr_w_mm + max(0, columns - 1) * middle_gap_mm
if required_w > page_size_mm[0]:
    st.error("Selected columns, QR width, left/right gaps, and middle gap do not fit the paper / roll width."); st.stop()
if layout_type == "Continuous roll PDF":
    rows_per_page = math.ceil(max(len(batch_items) for _, batch_items in csv_batches) / columns)
    page_counts = [1 for _ in csv_batches]
else:
    available_h = page_size_mm[1] - margins_mm[2] - margins_mm[3]
    if available_h < qr_h_mm:
        st.error("QR height plus margins does not fit the selected paper."); st.stop()
    rows_per_page = max(1, math.floor((available_h + row_gap_mm) / (qr_h_mm + row_gap_mm)))
    page_counts = [math.ceil(len(batch_items) / (columns * rows_per_page)) for _, batch_items in csv_batches]
total_pages = sum(page_counts)
st.info(f"Layout: {columns} columns × {rows_per_page} rows{' on each roll' if layout_type == 'Continuous roll PDF' else ' per page'} - {len(csv_batches)} PDF files, {total_pages:,} PDF pages total.")

first, second = st.columns([1, 2])
preview_item = csv_batches[0][1][0]
with first: st.image(make_qr_image(preview_item.value, ERROR_LEVELS[error_label]), caption=f"Preview: {preview_item.label}", width=250)
with second:
    st.subheader("First QR data")
    st.code(preview_item.value, language=None)
    st.caption("Spaces and blank lines from the CSV cell are preserved.")
if st.button("Generate PDF ZIP", type="primary"):
    try:
        progress = st.progress(0, text="Preparing PDF batch…")
        pdf_zip = io.BytesIO()
        with zipfile.ZipFile(pdf_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, (csv_name, batch_items) in enumerate(csv_batches, start=1):
                progress.progress((index - 1) / len(csv_batches), text=f"Generating PDF {index} of {len(csv_batches)}: {csv_name}")
                pdf_bytes, _, _, _ = build_pdf(batch_items, qr_w_mm, qr_h_mm, middle_gap_mm, row_gap_mm, margins_mm, page_size_mm, ERROR_LEVELS[error_label], layout_type == "Continuous roll PDF", columns)
                archive.writestr(safe_pdf_name(csv_name, index), pdf_bytes)
        progress.progress(1.0, text="PDF ZIP ready.")
        st.session_state["qr_pdf_zip"] = pdf_zip.getvalue()
        st.session_state["qr_pdf_zip_name"] = "dsolnex_qr_pdf_batch.zip"
        st.success(f"{len(csv_batches)} PDF files are ready in one ZIP.")
    except ValueError as error:
        st.error(str(error))
if "qr_pdf_zip" in st.session_state:
    st.download_button("Download PDF ZIP", st.session_state["qr_pdf_zip"], st.session_state["qr_pdf_zip_name"], "application/zip", type="primary")
