import io
import zipfile
import csv
from PIL import Image
import streamlit as st

STANDARD_SIZES = {
    (300, 250): "Mrec",
    (728, 90): "Leaderboard",
    (300, 600): "Half Page",
    (160, 600): "Wide Skyscraper",
    (320, 50): "Mobile Banner",
    (300, 50): "Mobile Billboard",
    (120, 600): "Skyscraper",
    (970, 250): "Billboard",
}

FORMAT_MAP = {
    "png": "PNG",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "gif": "GIF",
    "webp": "WEBP",
}

STATUS_CORRECT = "correct"
STATUS_RESIZED = "auto_resized"
STATUS_CLIENT = "needs_client"


def find_nearest_size(w, h):
    best_size = None
    best_dist = float("inf")
    for (tw, th) in STANDARD_SIZES:
        dist = max(abs(w - tw), abs(h - th))
        if dist < best_dist:
            best_dist = dist
            best_size = (tw, th)
    return best_size, best_dist


def find_ratio_match(w, h):
    """Return the standard size whose ratio exactly matches (w, h), or None."""
    for (tw, th) in STANDARD_SIZES:
        if w * th == h * tw:
            return (tw, th)
    return None


def resize_image_bytes(img, target_w, target_h, fmt):
    img_resized = img.resize((target_w, target_h), Image.LANCZOS)
    buf = io.BytesIO()
    save_fmt = fmt if fmt != "JPEG" else "JPEG"
    if save_fmt == "JPEG" and img_resized.mode in ("RGBA", "P"):
        img_resized = img_resized.convert("RGB")
    img_resized.save(buf, format=save_fmt)
    return buf.getvalue()


def analyze_assets(uploaded_files, tolerance_px):
    results = []
    for f in uploaded_files:
        ext = f.name.rsplit(".", 1)[-1].lower()
        pil_fmt = FORMAT_MAP.get(ext, "PNG")
        try:
            img = Image.open(f)
            w, h = img.size
        except Exception:
            results.append({
                "filename": f.name,
                "detected": None,
                "nearest_standard": None,
                "standard_label": "—",
                "distance": None,
                "resize_reason": None,
                "status": STATUS_CLIENT,
                "error": "Could not read file",
                "resized_bytes": None,
            })
            continue

        nearest, dist = find_nearest_size(w, h)
        ratio_target = find_ratio_match(w, h)

        if dist == 0:
            status = STATUS_CORRECT
            resize_reason = None
            resized_bytes = None
        elif ratio_target:
            # Correct ratio — resize to the matching standard size
            status = STATUS_RESIZED
            resize_reason = "ratio"
            nearest = ratio_target
            f.seek(0)
            img = Image.open(f)
            resized_bytes = resize_image_bytes(img, nearest[0], nearest[1], pil_fmt)
        elif dist <= tolerance_px:
            status = STATUS_RESIZED
            resize_reason = "tolerance"
            f.seek(0)
            img = Image.open(f)
            resized_bytes = resize_image_bytes(img, nearest[0], nearest[1], pil_fmt)
        else:
            status = STATUS_CLIENT
            resize_reason = None
            resized_bytes = None

        results.append({
            "filename": f.name,
            "detected": (w, h),
            "nearest_standard": nearest,
            "standard_label": STANDARD_SIZES[nearest],
            "distance": dist,
            "resize_reason": resize_reason,
            "status": status,
            "error": None,
            "resized_bytes": resized_bytes,
        })
    return results


def build_zip(results):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            if r["status"] == STATUS_RESIZED and r["resized_bytes"]:
                zf.writestr(r["filename"], r["resized_bytes"])
    buf.seek(0)
    return buf.getvalue()


def build_csv(results):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Filename", "Detected Size", "Required Size", "Required Label"])
    for r in results:
        if r["status"] == STATUS_CLIENT:
            detected = f"{r['detected'][0]}x{r['detected'][1]}" if r["detected"] else "unreadable"
            required = f"{r['nearest_standard'][0]}x{r['nearest_standard'][1]}" if r["nearest_standard"] else "—"
            writer.writerow([r["filename"], detected, required, r["standard_label"]])
    return buf.getvalue().encode("utf-8")


def status_label(status):
    return {
        STATUS_CORRECT: "Correct",
        STATUS_RESIZED: "Auto-resized",
        STATUS_CLIENT: "Needs client",
    }[status]


# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Ad Creative Resizer", page_icon="🖼", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Settings")
    tolerance = st.slider(
        "Pixel tolerance for auto-resize",
        min_value=1,
        max_value=20,
        value=5,
        help="Assets within this many pixels of a standard size will be automatically resized.",
    )

    with st.expander("MediaWorks Display Sizes reference"):
        rows = [{"Size": f"{w}×{h}", "Label": label} for (w, h), label in STANDARD_SIZES.items()]
        st.table(rows)

# ── Main ──────────────────────────────────────────────────────────────────────

st.title("Ad Creative Resizer")
st.caption(
    "Upload your display creatives. Assets within the pixel tolerance are auto-resized; "
    "larger mismatches are flagged for the client."
)

uploaded = st.file_uploader(
    "Drop creatives here (select all files from your folder with Ctrl+A / Cmd+A)",
    type=["png", "jpg", "jpeg", "gif", "webp"],
    accept_multiple_files=True,
)

if uploaded:
    if st.button("Analyse creatives", type="primary"):
        with st.spinner("Analysing…"):
            results = analyze_assets(uploaded, tolerance)
        st.session_state["results"] = results

if "results" in st.session_state:
    results = st.session_state["results"]

    correct = sum(1 for r in results if r["status"] == STATUS_CORRECT)
    resized = sum(1 for r in results if r["status"] == STATUS_RESIZED)
    client = sum(1 for r in results if r["status"] == STATUS_CLIENT)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total assets", len(results))
    col2.metric("Correct", correct)
    col3.metric("Auto-resized", resized)
    col4.metric("Needs client", client)

    st.divider()

    # Build display rows — no row background colours so text stays readable in any theme.
    # Colour is conveyed solely via the left border accent and the status badge.
    rows_html = ""
    for r in results:
        detected_str = f"{r['detected'][0]}×{r['detected'][1]}" if r["detected"] else "⚠ unreadable"
        standard_str = f"{r['nearest_standard'][0]}×{r['nearest_standard'][1]}" if r["nearest_standard"] else "—"
        if r["resize_reason"] == "ratio":
            dist_str = "Ratio match"
        elif r["distance"] is not None:
            dist_str = str(r["distance"]) + "px"
        else:
            dist_str = "—"
        status = r["status"]
        label = status_label(status)
        if status == STATUS_CORRECT:
            accent = "#22c55e"   # green
            badge_bg = "#16a34a"
        elif status == STATUS_RESIZED:
            accent = "#f59e0b"   # amber
            badge_bg = "#d97706"
        else:
            accent = "#ef4444"   # red
            badge_bg = "#dc2626"

        rows_html += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid rgba(128,128,128,0.2);border-left:4px solid {accent};padding-left:14px;">{r['filename']}</td>
          <td style="padding:10px 12px;border-bottom:1px solid rgba(128,128,128,0.2);">{detected_str}</td>
          <td style="padding:10px 12px;border-bottom:1px solid rgba(128,128,128,0.2);">{standard_str}</td>
          <td style="padding:10px 12px;border-bottom:1px solid rgba(128,128,128,0.2);opacity:0.75;">{r['standard_label']}</td>
          <td style="padding:10px 12px;border-bottom:1px solid rgba(128,128,128,0.2);">{dist_str}</td>
          <td style="padding:10px 12px;border-bottom:1px solid rgba(128,128,128,0.2);">
            <span style="background:{badge_bg};color:#fff;padding:3px 11px;border-radius:12px;font-size:0.8em;font-weight:600;letter-spacing:0.02em;">{label}</span>
          </td>
        </tr>"""

    table_html = f"""
    <table style="width:100%;border-collapse:collapse;font-size:0.9em;">
      <thead>
        <tr>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid rgba(128,128,128,0.35);padding-left:18px;opacity:0.6;font-weight:600;text-transform:uppercase;font-size:0.78em;letter-spacing:0.06em;">Filename</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid rgba(128,128,128,0.35);opacity:0.6;font-weight:600;text-transform:uppercase;font-size:0.78em;letter-spacing:0.06em;">Detected</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid rgba(128,128,128,0.35);opacity:0.6;font-weight:600;text-transform:uppercase;font-size:0.78em;letter-spacing:0.06em;">Standard</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid rgba(128,128,128,0.35);opacity:0.6;font-weight:600;text-transform:uppercase;font-size:0.78em;letter-spacing:0.06em;">Format</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid rgba(128,128,128,0.35);opacity:0.6;font-weight:600;text-transform:uppercase;font-size:0.78em;letter-spacing:0.06em;">Offset</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid rgba(128,128,128,0.35);opacity:0.6;font-weight:600;text-transform:uppercase;font-size:0.78em;letter-spacing:0.06em;">Status</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>"""

    st.markdown(table_html, unsafe_allow_html=True)

    st.divider()

    dl_col1, dl_col2 = st.columns(2)

    if resized > 0:
        zip_bytes = build_zip(results)
        dl_col1.download_button(
            label=f"Download resized assets ({resized} file{'s' if resized != 1 else ''})",
            data=zip_bytes,
            file_name="resized_creatives.zip",
            mime="application/zip",
        )
    else:
        dl_col1.info("No assets were auto-resized.")

    if client > 0:
        csv_bytes = build_csv(results)
        dl_col2.download_button(
            label=f"Download client report ({client} file{'s' if client != 1 else ''})",
            data=csv_bytes,
            file_name="client_report.csv",
            mime="text/csv",
        )
    else:
        dl_col2.success("No assets need to go back to the client.")
