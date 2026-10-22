import streamlit as st
import os, sys, json, time, shutil, html, difflib
from collections import defaultdict
from itertools import combinations
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from hasher import find_exact_duplicates, get_file_hash
from near_duplicate_text import find_near_duplicate_texts, SIMILARITY_THRESHOLD
from image_similarity import find_near_duplicate_images, HASH_DIFFERENCE_THRESHOLD
from video_similarity import find_near_duplicate_videos, is_video_file, VIDEO_EXTENSIONS
from version_recommender import group_related_files, recommend_latest_version
from text_extractor import extract_text, is_text_file
from google_drive_connector import sync_drive_folder_to_local, list_owners_in_folder

st.set_page_config(page_title="DocDetect", page_icon="📄", layout="wide")

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
VIDEO_EXT = (".mp4", ".avi", ".mov", ".mkv", ".wmv")
HISTORY_FILE = "scan_history.json"
REVIEW_FOLDER_NAME = "_docdetect_review"

# ---- colour system: navy sidebar, light workspace, orange accent ----------
NAVY = "#0F172A"
ACCENT = "#F26B1D"          # primary orange accent
INDIGO = "#3B6FE0"          # near-duplicate blue
PURPLE = "#8B5CF6"
GREEN = "#1D9C6E"
AMBER = "#E0A021"
RED = "#D14343"
MUTED = "#667085"
LINE = "#E4E7EC"
BG = "#F4F6FA"
TYPE_ICONS = {"DOCX": "📄", "PDF": "📕", "TXT": "📝", "Image": "🖼️", "Video": "🎬", "Other": "📦"}
TYPE_COLORS = {"DOCX": INDIGO, "PDF": RED, "TXT": AMBER, "Image": PURPLE, "Video": GREEN, "Other": MUTED}


def _st_version():
    try:
        return tuple(int(x) for x in st.__version__.split(".")[:2])
    except Exception:
        return (0, 0)


STRETCH = {"width": "stretch"} if _st_version() >= (1, 50) else {"use_container_width": True}


def S(fn, *args, **kwargs):
    """Call a Streamlit element stretched to full width, working on old and new Streamlit versions."""
    for extra in (STRETCH, {"use_container_width": True}, {}):
        try:
            return fn(*args, **kwargs, **extra)
        except (TypeError, st.errors.StreamlitAPIException):
            continue
    return fn(*args, **kwargs)


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: __BG__; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.1rem; max-width: 1450px; }

/* ---------- brand bar ---------- */
.topbar-brand { display: flex; align-items: center; gap: 16px; justify-content: center; }
.topbar-brand .logo {
    width: 58px; height: 58px; border-radius: 14px;
    background: linear-gradient(135deg, __NAVY__ 0%, __ACCENT__ 100%);
    color: white; display: flex; align-items: center; justify-content: center; font-size: 1.7rem;
    transition: transform 0.25s ease, box-shadow 0.25s ease;
    box-shadow: 0 2px 6px rgba(16,24,40,0.15);
}
.topbar-brand .logo:hover { transform: scale(1.08) rotate(-3deg); box-shadow: 0 8px 18px rgba(242,107,29,0.35); }
.topbar-brand .name { font-size: 2.1rem; font-weight: 800; color: __NAVY__; line-height: 1.05; letter-spacing: 0.01em; transition: color 0.2s ease; }
.topbar-brand .name:hover { color: __ACCENT__; }
.topbar-brand .tag { font-size: 0.9rem; color: __MUTED__; }
.topbar-status { font-size: 0.8rem; color: __GREEN__; font-weight: 500; }

/* ---------- page header ---------- */
.crumb { font-size: 0.78rem; color: __MUTED__; margin-bottom: 2px; }
.crumb span { margin: 0 4px; color: #B6BDC9; }
.crumb b { color: __NAVY__; font-weight: 600; }
.ph-title { font-size: 1.85rem; font-weight: 800; color: __NAVY__; margin: 0; line-height: 1.15; letter-spacing: -0.01em; }
.ph-sub { font-size: 0.92rem; color: __MUTED__; margin: 4px 0 10px 0; }
.chip { display: inline-block; background: white; border: 1px solid __LINE__; border-radius: 999px; padding: 3px 11px; font-size: 0.75rem; color: __MUTED__; margin: 0 6px 6px 0; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: top; }
.chip.ok { color: __GREEN__; border-color: rgba(29,156,110,0.35); background: rgba(29,156,110,0.06); }
.chip.idle { color: __AMBER__; border-color: rgba(224,160,33,0.4); background: rgba(224,160,33,0.07); }

/* ---------- cards ---------- */
div[class*="st-key-card_"] {
    background: white; border: 1px solid __LINE__ !important; border-radius: 14px;
    box-shadow: 0 1px 3px rgba(16,24,40,0.06); transition: box-shadow 0.2s ease, transform 0.2s ease;
}
div[class*="st-key-card_"]:hover { box-shadow: 0 8px 22px rgba(16,24,40,0.09); }
.card-title { font-size: 1rem; font-weight: 700; color: __NAVY__; margin: 2px 0 0 0; }
.card-sub { font-size: 0.8rem; color: __MUTED__; margin: 0 0 6px 0; }

.kpi-label { font-size: 0.72rem; color: __MUTED__; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
.kpi-value { font-size: 1.9rem; font-weight: 800; color: __NAVY__; margin: 4px 0 2px 0; line-height: 1.1; }
.kpi-sub { font-size: 0.78rem; color: __MUTED__; }
.kpi-delta-good { font-size: 0.75rem; color: __GREEN__; font-weight: 600; }
.kpi-delta-bad { font-size: 0.75rem; color: __RED__; font-weight: 600; }
div[class*="st-key-card_kpi_"] .stButton > button {
    background: transparent !important; border: none !important; box-shadow: none !important;
    color: __ACCENT__ !important; font-weight: 600; padding: 0; min-height: 0; justify-content: flex-start;
}
div[class*="st-key-card_kpi_"] .stButton > button:hover { text-decoration: underline; transform: none; }

.section-title { font-size: 1.02rem; font-weight: 700; color: __NAVY__; margin: 22px 0 4px 0; }
.section-sub { font-size: 0.84rem; color: __MUTED__; margin-bottom: 12px; }
.empty-state { border: 1px dashed #CBD1DA; border-radius: 14px; padding: 38px 20px; text-align: center; background: white; }
.empty-state .icon { font-size: 1.8rem; margin-bottom: 8px; }
.empty-state h4 { color: __NAVY__; margin: 0 0 4px 0; }
.empty-state p { color: __MUTED__; font-size: 0.87rem; margin: 0; }
.rec-badge { display: inline-block; font-size: 0.7rem; font-weight: 600; color: __GREEN__; background: rgba(29,156,110,0.09); border-radius: 6px; padding: 2px 8px; margin-left: 6px; }
.finding-card { border: 1px solid __LINE__; border-radius: 12px; padding: 14px 16px; background: white; margin-bottom: 10px; }
.scan-current-file { font-family: monospace; font-size: 0.8rem; color: __ACCENT__; background: rgba(242,107,29,0.07); border-radius: 6px; padding: 6px 10px; margin-top: 6px; }
.stat-inline { font-family: monospace; font-size: 0.82rem; color: __MUTED__; }
.bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.bar-row .lbl { width: 38%; font-size: 0.83rem; color: __NAVY__; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-row .track { flex: 1; background: #EEF1F6; border-radius: 6px; height: 10px; overflow: hidden; }
.bar-row .fill { height: 100%; border-radius: 6px; }
.bar-row .val { width: 22%; font-size: 0.8rem; color: __MUTED__; text-align: right; }
.cmp-box { border: 1px solid __LINE__; border-radius: 10px; padding: 8px 10px; max-height: 340px; overflow: auto; background: #FCFCFD; font-size: 0.82rem; line-height: 1.5; }
.cmp-box div { padding: 1px 4px; border-radius: 4px; margin-bottom: 1px; word-break: break-word; }
.cmp-del { background: #FEE2E2; }
.cmp-add { background: #DCFCE7; }

/* ---------- primary buttons (main area) ---------- */
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"],
.stDownloadButton > button[kind="primary"] {
    background: __ACCENT__; border: none; color: white; border-radius: 10px; font-weight: 600;
    box-shadow: 0 4px 12px rgba(242,107,29,0.28);
}
.stButton > button[kind="primary"]:hover, .stButton > button[data-testid="stBaseButton-primary"]:hover { background: #D95A10; color: white; }
.stButton > button, .stDownloadButton > button { border-radius: 10px; }

/* ---------- dark navy sidebar ---------- */
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0B1220 0%, #111B30 100%); border-right: 1px solid #1E293B; }
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] { gap: 0.2rem; }
section[data-testid="stSidebar"] .sidebar-brand { display: flex; align-items: center; gap: 10px; font-size: 1.15rem; font-weight: 800; color: white; margin: 4px 0 0 0; }
section[data-testid="stSidebar"] .sidebar-brand .mark { width: 32px; height: 32px; border-radius: 9px; background: linear-gradient(135deg, #1E293B, __ACCENT__); display: flex; align-items: center; justify-content: center; font-size: 1rem; }
section[data-testid="stSidebar"] .sidebar-sub { font-size: 0.74rem; color: #94A3B8; margin: 2px 0 14px 42px; }
section[data-testid="stSidebar"] .sidebar-section { font-size: 0.68rem; font-weight: 700; color: #64748B; letter-spacing: 0.08em; margin: 16px 0 6px 6px; }
section[data-testid="stSidebar"] .local-note { font-size: 0.74rem; color: #94A3B8; border-top: 1px solid #1E293B; padding-top: 12px; margin-top: 18px; line-height: 1.45; }
section[data-testid="stSidebar"] .local-note b { color: #E2E8F0; }
section[data-testid="stSidebar"] .version-footer { font-size: 0.7rem; color: #64748B; margin-top: 10px; }
section[data-testid="stSidebar"] .stButton > button {
    background: transparent; border: none; box-shadow: none; color: #CBD5E1; border-radius: 10px;
    padding: 8px 12px; margin-bottom: 1px; font-weight: 500; justify-content: flex-start; text-align: left;
    transition: transform 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}
section[data-testid="stSidebar"] .stButton > button > div { justify-content: flex-start; width: 100%; }
section[data-testid="stSidebar"] .stButton > button p { color: inherit; }
section[data-testid="stSidebar"] .stButton > button:hover { background: rgba(255,255,255,0.07); color: white; transform: translateX(4px); }
section[data-testid="stSidebar"] .stButton > button[kind="primary"],
section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(90deg, rgba(242,107,29,0.30), rgba(242,107,29,0.05));
    color: white; font-weight: 600; border-left: 3px solid __ACCENT__; box-shadow: none; border-radius: 10px;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"]:hover { background: linear-gradient(90deg, rgba(242,107,29,0.38), rgba(242,107,29,0.08)); }
</style>
"""
for _k, _v in {"__NAVY__": NAVY, "__ACCENT__": ACCENT, "__INDIGO__": INDIGO, "__GREEN__": GREEN,
               "__RED__": RED, "__AMBER__": AMBER, "__MUTED__": MUTED, "__LINE__": LINE, "__BG__": BG}.items():
    CSS = CSS.replace(_k, _v)
st.markdown(CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
defaults = {
    "page": "Overview", "scanned": False,
    "scan_folder": r"C:\Users\sagar\OneDrive\Documents\messy",
    "exact_groups": [], "text_pairs": [], "image_pairs": [], "video_pairs": [],
    "all_files": [], "last_scan_time": None, "benchmark_rows": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ---------------------------------------------------------------------------
# SMALL UI HELPERS
# ---------------------------------------------------------------------------
def go_to(page):
    st.session_state.page = page


def card(key):
    """A white rounded card. Uses a key so the CSS can style it (Streamlit >= 1.39)."""
    try:
        return st.container(border=True, key=f"card_{key}")
    except TypeError:
        return st.container(border=True)


def esc(text):
    return html.escape(str(text))


def hex_rgba(h, a):
    h = h.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def fmt_size(kb):
    if kb >= 1024 * 1024:
        return f"{kb / 1024 / 1024:.2f} GB"
    if kb >= 1024:
        return f"{kb / 1024:.2f} MB"
    return f"{kb:.1f} KB"


def style_fig(fig, height=300):
    fig.update_layout(
        height=height, margin=dict(t=10, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=NAVY),
    )
    fig.update_xaxes(showgrid=False, linecolor=LINE)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


def show_chart(fig, key):
    S(st.plotly_chart, fig, config={"displayModeBar": False}, key=key)


def card_title(title, sub=None):
    st.markdown(f'<p class="card-title">{title}</p>' + (f'<p class="card-sub">{sub}</p>' if sub else ""), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# BACKEND HELPERS
# ---------------------------------------------------------------------------
def combined_groups():
    all_pairs = (
        list(st.session_state.text_pairs)
        + list(st.session_state.image_pairs)
        + list(st.session_state.get("video_pairs", []))
    )
    for group in st.session_state.exact_groups:
        for i in range(len(group) - 1):
            all_pairs.append((group[i], group[i + 1], 1.0))
    return group_related_files(all_pairs), all_pairs


def similarity_for(all_pairs, latest, filepath):
    for a, b, sim in all_pairs:
        if (a == latest and b == filepath) or (b == latest and a == filepath):
            return sim * 100
    return 100.0


def total_wasted_kb(groups):
    wasted = 0
    for group in groups:
        existing = [f for f in group if os.path.exists(f)]
        if not existing:
            continue
        latest = recommend_latest_version(existing)
        for f in existing:
            if f != latest:
                wasted += os.path.getsize(f) / 1024
    return wasted


def file_type_of(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx": return "DOCX"
    if ext == ".pdf": return "PDF"
    if ext == ".txt": return "TXT"
    if ext in IMAGE_EXT: return "Image"
    if ext in VIDEO_EXT: return "Video"
    return "Other"


def classify_size(size_kb):
    if size_kb < 100:
        return "Small (<100 KB)"
    elif size_kb < 5000:
        return "Medium (100 KB-5 MB)"
    else:
        return "Large (>5 MB)"


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def previous_scan_for_folder(folder):
    """The scan BEFORE the most recent one for this folder (the most recent is the current scan)."""
    matches = [r for r in load_history() if r.get("folder") == folder]
    return matches[1] if len(matches) > 1 else None


def history_series(folder, key):
    """Values of one metric across past scans of this folder, oldest first."""
    matches = [r for r in load_history() if r.get("folder") == folder]
    return [r.get(key, 0) for r in reversed(matches)]


def save_scan_record():
    groups, _ = combined_groups()
    history = load_history()
    history.insert(0, {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "folder": st.session_state.scan_folder,
        "files_scanned": len(st.session_state.all_files),
        "exact_duplicate_groups": len(st.session_state.exact_groups),
        "near_duplicate_pairs": len(st.session_state.text_pairs) + len(st.session_state.image_pairs) + len(st.session_state.get("video_pairs", [])),
        "potential_savings_kb": round(total_wasted_kb(groups), 1),
    })
    save_history(history[:20])


def move_outdated_to_review(group, latest, source_folder):
    """Move every file in a group EXCEPT the recommended latest version
    into a review folder, so the user can confirm before permanently
    deleting anything. Nothing is deleted automatically."""
    review_folder = os.path.join(source_folder, REVIEW_FOLDER_NAME)
    os.makedirs(review_folder, exist_ok=True)

    moved = []
    for filepath in group:
        if filepath == latest:
            continue
        try:
            filename = os.path.basename(filepath)
            destination = os.path.join(review_folder, filename)
            counter = 1
            base, ext = os.path.splitext(destination)
            while os.path.exists(destination):
                destination = f"{base}_{counter}{ext}"
                counter += 1
            shutil.move(filepath, destination)
            moved.append(filepath)
        except Exception as e:
            st.warning(f"Could not move {os.path.basename(filepath)}: {e}")

    return moved


def apply_moved(moved):
    """Remove moved files from the current scan results so no page shows stale entries."""
    moved = set(moved)
    ss = st.session_state
    ss.all_files = [f for f in ss.all_files if f not in moved]
    cleaned = [[f for f in g if f not in moved] for g in ss.exact_groups]
    ss.exact_groups = [g for g in cleaned if len(g) > 1]
    for key in ("text_pairs", "image_pairs", "video_pairs"):
        ss[key] = [p for p in ss.get(key, []) if p[0] not in moved and p[1] not in moved]


def run_full_scan_timed(folder):
    """Runs the complete detection pipeline on a folder and returns
    both the results and how long the whole scan took, in seconds."""
    t0 = time.time()
    discovered = [os.path.join(r, f) for r, d, fs in os.walk(folder) for f in fs]

    exact_groups = find_exact_duplicates(folder)
    text_pairs = find_near_duplicate_texts(folder)
    image_pairs = find_near_duplicate_images(folder)
    video_pairs = find_near_duplicate_videos(folder)

    elapsed = time.time() - t0

    all_pairs = list(text_pairs) + list(image_pairs) + list(video_pairs)
    for group in exact_groups:
        for i in range(len(group) - 1):
            all_pairs.append((group[i], group[i + 1], 1.0))
    groups = group_related_files(all_pairs)

    wasted_kb = 0
    for group in groups:
        existing = [f for f in group if os.path.exists(f)]
        if not existing:
            continue
        latest = recommend_latest_version(existing)
        for f in existing:
            if f != latest:
                wasted_kb += os.path.getsize(f) / 1024

    return {
        "files_scanned": len(discovered),
        "exact_groups": len(exact_groups),
        "near_duplicate_pairs": len(text_pairs) + len(image_pairs) + len(video_pairs),
        "total_related_groups": len(groups),
        "potential_savings_kb": round(wasted_kb, 1),
        "scan_time_seconds": round(elapsed, 3),
    }


def analysis_context():
    """Everything the result pages need: groups, pairs, exact-duplicate files, and file -> (group, latest)."""
    groups, all_pairs = combined_groups()
    exact_files = {f for g in st.session_state.exact_groups for f in g}
    group_of = {}
    for g in groups:
        existing = [f for f in g if os.path.exists(f)]
        if len(existing) < 2:
            continue
        latest = recommend_latest_version(existing)
        for f in existing:
            group_of[f] = (existing, latest)
    return groups, all_pairs, exact_files, group_of


def group_stats(groups):
    """One row per duplicate group, largest reclaimable space first."""
    exact_sets = [set(g) for g in st.session_state.exact_groups]
    rows = []
    for g in groups:
        existing = [f for f in g if os.path.exists(f)]
        if len(existing) < 2:
            continue
        latest = recommend_latest_version(existing)
        total_kb = sum(os.path.getsize(f) for f in existing) / 1024
        reclaim_kb = sum(os.path.getsize(f) for f in existing if f != latest) / 1024
        is_exact = any(set(existing) <= s for s in exact_sets)
        rows.append({"files": existing, "latest": latest, "total_kb": total_kb,
                     "reclaim_kb": reclaim_kb, "kind": "Exact" if is_exact else "Near"})
    return sorted(rows, key=lambda r: -r["reclaim_kb"])


def build_file_rows(ctx=None):
    groups, all_pairs, exact_files, group_of = ctx or analysis_context()
    rows = []
    for f in st.session_state.all_files:
        if not os.path.exists(f):
            continue
        ftype = file_type_of(f)
        status, sim_val = "Unique", None
        if f in exact_files:
            status, sim_val = "Exact Duplicate", 100.0
        elif f in group_of:
            status = "Near Duplicate"
            sim_val = similarity_for(all_pairs, group_of[f][1], f)
        is_rec = f in group_of and group_of[f][1] == f
        rows.append({
            "File": f"{TYPE_ICONS.get(ftype, '📄')} {os.path.basename(f)}", "Type": ftype,
            "Size (KB)": round(os.path.getsize(f) / 1024, 1),
            "Modified": datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M"),
            "Status": status, "Similarity": f"{sim_val:.0f}%" if sim_val is not None else "—",
            "Recommended": "★" if is_rec else "", "Path": f,
        })
    return rows


def report_csv_bytes():
    rows = build_file_rows()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["File"] = df["Path"].apply(os.path.basename)
    return df.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------------------
# TOP APP BAR + SIDEBAR
# ---------------------------------------------------------------------------
def render_topbar():
    st.markdown("""
    <div class="topbar-brand">
        <div class="logo">📄</div>
        <div><div class="name">DOCDETECT</div><div class="tag">Duplicate Document Intelligence</div></div>
    </div>
    <div style="text-align:center; margin-top:8px;">
        <span class="topbar-status">● System Ready — Local Analysis</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div style="border-bottom:1px solid #E4E7EC; margin: 16px 0 18px 0;"></div>', unsafe_allow_html=True)


def render_sidebar():
    with st.sidebar:
        st.markdown('<div class="sidebar-brand"><span class="mark">📄</span>DocDetect</div>', unsafe_allow_html=True)
        st.markdown('<p class="sidebar-sub">Storage Intelligence</p>', unsafe_allow_html=True)

        def nav_btn(label, icon, page):
            st.button(f"{icon}  {label}", key=f"nav_{page}", **STRETCH_BTN,
                      type="primary" if st.session_state.page == page else "secondary",
                      on_click=go_to, args=(page,))

        st.markdown('<p class="sidebar-section">MAIN</p>', unsafe_allow_html=True)
        nav_btn("Overview", "▣", "Overview")
        nav_btn("Scan Folder", "⌕", "Scan Folder")
        nav_btn("Storage Comparison", "⇋", "Storage Comparison")
        nav_btn("Documents", "▤", "Documents")
        nav_btn("Images", "🖼", "Images")
        nav_btn("Videos", "🎬", "Videos")
        nav_btn("Duplicate Groups", "◈", "Duplicate Groups")
        nav_btn("Similarity Explorer", "⇄", "Similarity Explorer")

        st.markdown('<p class="sidebar-section">INSIGHTS</p>', unsafe_allow_html=True)
        nav_btn("Analytics", "◉", "Analytics")
        nav_btn("Optimization", "♻", "Optimization")
        nav_btn("Accuracy", "✔", "Accuracy")
        nav_btn("Performance", "⚡", "Performance")
        nav_btn("Scan History", "◷", "Scan History")

        st.markdown('<p class="sidebar-section">SYSTEM</p>', unsafe_allow_html=True)
        nav_btn("Settings", "⚙", "Settings")

        st.markdown(
            '<div class="local-note"><b>LOCAL ANALYSIS</b><br>● Active<br>'
            'Files remain on this device. Google Drive files are downloaded locally before analysis.</div>'
            '<div class="version-footer">v2.0 — FYP Prototype</div>',
            unsafe_allow_html=True
        )


STRETCH_BTN = STRETCH


def render_page_header(title, subtitle, crumb=None, export=False):
    folder = st.session_state.scan_folder
    last = st.session_state.last_scan_time
    left, right = st.columns([3.3, 1.2])
    with left:
        st.markdown(
            f'<div class="crumb">DocDetect<span>/</span><b>{esc(crumb or title)}</b></div>'
            f'<h1 class="ph-title">{esc(title)}</h1><p class="ph-sub">{esc(subtitle)}</p>',
            unsafe_allow_html=True)
        status_chip = (f'<span class="chip ok">● Last scan {esc(last)}</span>' if last
                       else '<span class="chip idle">○ No scan yet</span>')
        st.markdown(f'<span class="chip">📁 {esc(folder)}</span>{status_chip}', unsafe_allow_html=True)
    with right:
        st.write("")
        if st.session_state.page != "Scan Folder":
            st.button("＋  Scan New Folder", key=f"hdr_scan_{st.session_state.page}", type="primary",
                      on_click=go_to, args=("Scan Folder",), **STRETCH_BTN)
        if export and st.session_state.scanned:
            S(st.download_button, "⬇  Export report (CSV)", data=report_csv_bytes(),
              file_name=f"docdetect_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
              mime="text/csv", key=f"export_{st.session_state.page}")
    st.write("")


def kpi_card(key, label, value, sub="", delta=None, series=None, color=ACCENT, target=None, target_label="View details →"):
    with card(f"kpi_{key}"):
        delta_html = f'<div class="{delta[1]}">{delta[0]}</div>' if delta else ""
        st.markdown(
            f'<div class="kpi-label">{label}</div><div class="kpi-value">{value}</div>'
            f'<div class="kpi-sub">{sub}</div>{delta_html}', unsafe_allow_html=True)
        if series and len(series) >= 2:
            fig = go.Figure(go.Scatter(y=series, mode="lines", line=dict(color=color, width=2, shape="spline"),
                                       fill="tozeroy", fillcolor=hex_rgba(color, 0.12), hoverinfo="skip"))
            fig.update_layout(height=56, margin=dict(t=2, b=0, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(visible=False), yaxis=dict(visible=False, rangemode="tozero"))
            show_chart(fig, f"spark_{key}")
        if target:
            st.button(target_label, key=f"kpibtn_{key}", on_click=go_to, args=(target,))


def render_kpi_row(items):
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value, sub = item[0], item[1], item[2]
        with col:
            kpi_card(label.lower().replace(" ", "_"), label, value, sub,
                     delta=item[3] if len(item) > 3 else None)


def render_empty_state(icon, title, subtitle, cta_label=None, cta_page=None):
    st.markdown(f'<div class="empty-state"><div class="icon">{icon}</div><h4>{title}</h4><p>{subtitle}</p></div>', unsafe_allow_html=True)
    if cta_label:
        st.write("")
        _, mid, _ = st.columns([1, 1, 1])
        with mid:
            st.button(cta_label, key=f"empty_{cta_page}_{title}", type="primary", on_click=go_to, args=(cta_page,), **STRETCH_BTN)


def render_duplicate_group(group, index, show_hash=False, key_prefix="dg"):
    latest = recommend_latest_version(group)
    match_pct = "100% IDENTICAL" if show_hash else "RELATED"
    total_size = sum(os.path.getsize(f) for f in group) / 1024
    outdated_count = len(group) - 1

    with st.expander(f"Duplicate Group #{index:02d} — {len(group)} files — {fmt_size(total_size)} total"):
        st.markdown(f"**{match_pct}**")
        if show_hash:
            st.caption(f"SHA-256: `{get_file_hash(next(iter(group)))[:28]}…`")
        st.write("")
        for filepath in sorted(group, key=lambda f: f != latest):
            filename = os.path.basename(filepath)
            icon = TYPE_ICONS.get(file_type_of(filepath), "📄")
            size_kb = os.path.getsize(filepath) / 1024
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d %H:%M")
            rec_tag = '<span class="rec-badge">Recommended version</span>' if filepath == latest else ""
            st.markdown(f"{icon} **{esc(filename)}**{rec_tag}", unsafe_allow_html=True)
            st.caption(f"{filepath}  ·  {fmt_size(size_kb)}  ·  modified {mtime}")

        st.write("")
        st.caption(
            f"Moves the {outdated_count} outdated file(s) above into a "
            f"'{REVIEW_FOLDER_NAME}' folder inside your scanned folder. "
            "Nothing is permanently deleted — you can review and delete them yourself afterwards."
        )
        confirm = st.checkbox(f"I want to move {outdated_count} outdated file(s) to review", key=f"confirm_{key_prefix}_{index}_{show_hash}")
        if st.button("🗂 Move outdated files to review folder", key=f"cleanup_{key_prefix}_{index}_{show_hash}", disabled=not confirm):
            moved = move_outdated_to_review(group, latest, st.session_state.scan_folder)
            if moved:
                apply_moved(moved)
                st.success(f"Moved {len(moved)} file(s) to {REVIEW_FOLDER_NAME}. Results were updated.")


def render_text_compare(file_a, file_b):
    """Side-by-side text comparison. Lines only in A are red, lines only in B are green."""
    try:
        ta, tb = extract_text(file_a) or "", extract_text(file_b) or ""
    except Exception as e:
        st.caption(f"Text preview unavailable: {e}")
        return
    la = [l.strip() for l in ta.splitlines() if l.strip()][:150]
    lb = [l.strip() for l in tb.splitlines() if l.strip()][:150]
    if not la and not lb:
        st.caption("No extractable text in these files.")
        return
    left, right = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, la, lb, autojunk=False).get_opcodes():
        if tag == "equal":
            left += [("", l) for l in la[i1:i2]]
            right += [("", l) for l in lb[j1:j2]]
        else:
            left += [("cmp-del", l) for l in la[i1:i2]]
            right += [("cmp-add", l) for l in lb[j1:j2]]

    def box(rows):
        inner = "".join(f'<div class="{c}">{esc(t[:400])}</div>' for c, t in rows)
        return f'<div class="cmp-box">{inner}</div>'

    c1, c2 = st.columns(2)
    c1.markdown(f"**{esc(os.path.basename(file_a))}**", unsafe_allow_html=True)
    c1.markdown(box(left), unsafe_allow_html=True)
    c2.markdown(f"**{esc(os.path.basename(file_b))}**", unsafe_allow_html=True)
    c2.markdown(box(right), unsafe_allow_html=True)
    st.caption("Red = only in the left file · Green = only in the right file · first 150 non-empty lines shown.")


def render_file_details(path, ctx):
    groups, all_pairs, exact_files, group_of = ctx
    ftype = file_type_of(path)
    status, sim_val = "Unique", None
    if path in exact_files:
        status, sim_val = "Exact Duplicate", 100.0
    elif path in group_of:
        status, sim_val = "Near Duplicate", similarity_for(all_pairs, group_of[path][1], path)
    with card("filedetails"):
        card_title("File details", "Select another row in the table to inspect a different file.")
        c1, c2 = st.columns([1.4, 1])
        with c1:
            st.markdown(f"**{TYPE_ICONS.get(ftype, '📄')} {esc(os.path.basename(path))}**", unsafe_allow_html=True)
            st.markdown(
                f"- **Type:** {ftype}\n"
                f"- **Size:** {fmt_size(os.path.getsize(path) / 1024)}\n"
                f"- **Modified:** {datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M')}\n"
                f"- **Status:** {status}\n"
                f"- **Similarity:** {f'{sim_val:.0f}%' if sim_val is not None else '—'}"
            )
            st.caption(f"Path: {path}")
            if path in exact_files:
                try:
                    st.caption(f"SHA-256: `{get_file_hash(path)[:32]}…`")
                except Exception:
                    pass
            if path in group_of:
                members, latest = group_of[path]
                st.markdown("**Other files in this group**")
                for m in sorted(members, key=lambda f: f != latest):
                    tag = '<span class="rec-badge">Recommended version</span>' if m == latest else ""
                    st.markdown(f"· {esc(os.path.basename(m))}{tag}", unsafe_allow_html=True)
        with c2:
            if ftype == "Image":
                try:
                    st.image(path, width=240)
                except Exception:
                    st.caption("(preview unavailable)")
            elif ftype in ("DOCX", "PDF", "TXT"):
                try:
                    excerpt = (extract_text(path) or "")[:700]
                    st.markdown("**Content preview**")
                    st.caption(excerpt if excerpt.strip() else "No extractable text.")
                except Exception:
                    st.caption("Content preview unavailable.")
            elif ftype == "Video":
                st.caption("Video preview is available on the Videos page.")


# ---------------------------------------------------------------------------
# PAGES
# ---------------------------------------------------------------------------
def page_overview():
    render_page_header("Your Storage Intelligence Center",
                       "Find duplicate files, identify similar documents, and understand your storage usage.",
                       crumb="Overview", export=True)

    if not st.session_state.scanned:
        cols = st.columns(4)
        for col, (key, label, sub) in zip(cols, [("files", "Files Scanned", "Awaiting first scan"),
                                                  ("exact", "Exact Duplicates", "Awaiting scan results"),
                                                  ("near", "Near Duplicates", "Awaiting scan results"),
                                                  ("save", "Potential Savings", "Calculated after analysis")]):
            with col:
                kpi_card(f"empty_{key}", label, "—", sub)
        st.write("")
        render_empty_state("📁", "Your workspace is ready", "Select a folder to begin document analysis.",
                           "Scan New Folder", "Scan Folder")
        return

    ctx = analysis_context()
    groups, all_pairs, exact_files, group_of = ctx
    stats = group_stats(groups)
    wasted_kb = sum(r["reclaim_kb"] for r in stats)
    existing_files = [f for f in st.session_state.all_files if os.path.exists(f)]
    total_files = len(existing_files)
    near_pairs = len(st.session_state.text_pairs) + len(st.session_state.image_pairs) + len(st.session_state.get("video_pairs", []))
    folder = st.session_state.scan_folder

    prev = previous_scan_for_folder(folder)

    def delta(curr, prev_val, size=False):
        if prev_val is None or curr == prev_val:
            return None
        diff = curr - prev_val
        good = diff < 0
        arrow = "↓" if diff < 0 else "↑"
        amount = fmt_size(abs(diff)) if size else f"{abs(diff):.0f}"
        return (f"{arrow} {amount} vs previous scan", "kpi-delta-good" if good else "kpi-delta-bad")

    cols = st.columns(4)
    with cols[0]:
        kpi_card("files", "Total files scanned", f"{total_files:,}", "in the selected folder",
                 series=history_series(folder, "files_scanned"), color=INDIGO, target="Documents", target_label="Browse documents →")
    with cols[1]:
        kpi_card("exact", "Exact duplicate groups", f"{len(st.session_state.exact_groups)}", "identical content (SHA-256)",
                 delta=delta(len(st.session_state.exact_groups), prev.get("exact_duplicate_groups") if prev else None),
                 series=history_series(folder, "exact_duplicate_groups"), color=ACCENT, target="Duplicate Groups", target_label="Inspect groups →")
    with cols[2]:
        kpi_card("near", "Near-duplicate pairs", f"{near_pairs}", "similar but not identical",
                 delta=delta(near_pairs, prev.get("near_duplicate_pairs") if prev else None),
                 series=history_series(folder, "near_duplicate_pairs"), color=PURPLE, target="Similarity Explorer", target_label="Compare pairs →")
    with cols[3]:
        kpi_card("savings", "Estimated storage savings", fmt_size(wasted_kb), "if outdated copies are removed",
                 delta=delta(round(wasted_kb, 1), prev.get("potential_savings_kb") if prev else None, size=True),
                 series=history_series(folder, "potential_savings_kb"), color=GREEN, target="Optimization", target_label="Review savings →")
    if len([r for r in load_history() if r.get("folder") == folder]) < 2:
        st.caption("Trend lines and “vs previous scan” changes appear after this folder has been scanned at least twice.")

    # ---- row 2: stacked bar by type + donut ----
    st.write("")
    c1, c2 = st.columns([1.7, 1])
    rows = build_file_rows(ctx)
    df = pd.DataFrame(rows)
    with c1:
        with card("ov_bytype"):
            card_title("Files by type", "Unique files versus files that belong to a duplicate group.")
            if df.empty:
                st.caption("No files to chart.")
            else:
                order = [t for t in ["DOCX", "PDF", "TXT", "Image", "Video", "Other"] if t in set(df["Type"])]
                fig = go.Figure()
                for status, color in [("Unique", GREEN), ("Exact Duplicate", ACCENT), ("Near Duplicate", INDIGO)]:
                    fig.add_bar(name=status, x=order,
                                y=[int(((df["Type"] == t) & (df["Status"] == status)).sum()) for t in order],
                                marker_color=color)
                fig.update_layout(barmode="stack", legend=dict(orientation="h", y=1.12, x=0))
                show_chart(style_fig(fig, 300), "ov_bytype_chart")
    with c2:
        with card("ov_donut"):
            card_title("Duplicate distribution", "Share of scanned files by status.")
            exact_n = int((df["Status"] == "Exact Duplicate").sum()) if not df.empty else 0
            near_n = int((df["Status"] == "Near Duplicate").sum()) if not df.empty else 0
            unique_n = max(total_files - exact_n - near_n, 0)
            fig = go.Figure(go.Pie(labels=["Unique", "Exact duplicate", "Near duplicate"], values=[unique_n, exact_n, near_n],
                                   hole=0.66, marker=dict(colors=[GREEN, ACCENT, INDIGO], line=dict(color="white", width=2)),
                                   textinfo="percent", sort=False))
            fig.add_annotation(text=f"<b>{total_files}</b><br><span style='font-size:11px;color:{MUTED}'>files</span>",
                               showarrow=False, font=dict(size=22))
            fig.update_layout(legend=dict(orientation="h", y=-0.08, x=0.02))
            show_chart(style_fig(fig, 300), "ov_donut_chart")

    # ---- row 3: storage donut, health, top reclaimable ----
    c1, c2, c3 = st.columns([1, 1, 1.3])
    with c1:
        with card("ov_storage"):
            card_title("Storage overview", "Duplicate storage compared with the rest.")
            total_kb = sum(os.path.getsize(f) for f in existing_files) / 1024
            unique_kb = max(total_kb - wasted_kb, 0)
            fig = go.Figure(go.Pie(labels=["Unique storage", "Duplicate storage"], values=[unique_kb, wasted_kb], hole=0.66,
                                   marker=dict(colors=[PURPLE, AMBER], line=dict(color="white", width=2)), textinfo="percent", sort=False))
            fig.add_annotation(text=f"<b>{fmt_size(total_kb)}</b>", showarrow=False, font=dict(size=16))
            fig.update_layout(legend=dict(orientation="h", y=-0.08, x=0.02))
            show_chart(style_fig(fig, 260), "ov_storage_chart")
    with c2:
        with card("ov_health"):
            card_title("Document health", "How much of the folder is redundant.")
            in_groups = len(group_of)
            pct = (in_groups / total_files * 100) if total_files else 0
            st.markdown(f'<div class="kpi-value">{pct:.0f}%</div><div class="kpi-sub">of analysed files belong to a duplicate or near-duplicate group</div>', unsafe_allow_html=True)
            st.write("")
            st.progress(min(pct / 100, 1.0), text=f"{in_groups} of {total_files} files")
            if pct == 0:
                st.success("✓ No duplicates detected.")
            elif pct < 20:
                st.caption("Healthy: only a small share of files are redundant.")
            else:
                st.caption("A large share of files is redundant — review them on the Optimization page.")
    with c3:
        with card("ov_top"):
            card_title("Top reclaimable groups", "Groups where removing outdated copies frees the most space.")
            if not stats:
                st.caption("No duplicate groups to show.")
            else:
                biggest = max(r["reclaim_kb"] for r in stats[:5]) or 1
                for r in stats[:5]:
                    pct_w = max(r["reclaim_kb"] / biggest * 100, 3)
                    color = ACCENT if r["kind"] == "Exact" else INDIGO
                    st.markdown(
                        f'<div class="bar-row"><div class="lbl">{esc(os.path.basename(r["latest"]))}</div>'
                        f'<div class="track"><div class="fill" style="width:{pct_w}%;background:{color}"></div></div>'
                        f'<div class="val">{fmt_size(r["reclaim_kb"])}</div></div>', unsafe_allow_html=True)
                st.button("Review on Optimization page →", key="ov_to_opt", on_click=go_to, args=("Optimization",))


def page_scan():
    render_page_header("Scan Folder", "Analyse a local folder, Outlook storage, or a Google Drive folder for duplicate and related documents.")

    with card("scan_main"):
        st.markdown("**Start a Folder Analysis**")
        source = st.radio("Source", ["Local folder", "Outlook Storage", "Google Drive folder"], horizontal=True)

        if source == "Local folder":
            st.caption("Select a folder containing your documents to identify duplicates and related document versions. This also covers OneDrive folders, since OneDrive syncs to a normal local folder.")
            folder = st.text_input("Selected folder path", value=st.session_state.scan_folder)
        elif source == "Outlook Storage":
            st.caption("Outlook shares the same Microsoft cloud storage backend as OneDrive, so its synced files appear as a normal local folder. Point this at your Outlook attachments/files folder.")
            folder = st.text_input("Selected folder path", value=os.path.join(os.path.expanduser("~"), "OneDrive", "Outlook Files"), key="outlook_folder_path")
        else:
            st.caption(
                "Paste the folder ID from its Google Drive URL "
                "(the part after /folders/ in the address bar). "
                "Files will be downloaded locally before analysis, since detection runs on local files."
            )
            drive_folder_id = st.text_input("Google Drive folder ID", value="")
            folder = os.path.join(os.getcwd(), "drive_downloads")
            owner_filter = None

            if drive_folder_id and st.button("🔎 Check who uploaded files in this folder"):
                with st.spinner("Checking file owners..."):
                    try:
                        owners = list_owners_in_folder(drive_folder_id)
                        st.session_state["drive_owners"] = owners
                    except Exception as e:
                        st.error(f"Could not read this folder: {e}")

            owners = st.session_state.get("drive_owners", {})
            if owners:
                options = ["Everyone (all contributors)"] + [f"{name} ({email})" for email, name in owners.items()]
                choice = st.selectbox("Show files from", options)
                if choice != "Everyone (all contributors)":
                    owner_filter = choice.split("(")[-1].rstrip(")")

            if drive_folder_id and st.button("⬇ Connect and download from Drive"):
                with st.spinner("Connecting to Google Drive and downloading files..."):
                    try:
                        downloaded = sync_drive_folder_to_local(drive_folder_id, folder, owner_email_filter=owner_filter)
                        st.session_state.scanned = False
                        st.session_state.all_files = []
                        st.session_state.exact_groups = []
                        st.session_state.text_pairs = []
                        st.session_state.image_pairs = []
                        st.session_state.video_pairs = []
                        who = owner_filter if owner_filter else "all contributors"
                        st.success(f"Downloaded {len(downloaded)} file(s) from {who}. Click START ANALYSIS to scan them.")
                    except Exception as e:
                        st.error(f"Could not connect to Google Drive: {e}")

        if os.path.isdir(folder):
            preview_files = [os.path.join(r, f) for r, d, fs in os.walk(folder) for f in fs]
            st.caption(f"✓ Folder found  ·  Files detected: {len(preview_files)}  ·  Supported types: DOCX, PDF, TXT, JPG, PNG, MP4")
        else:
            st.caption("✗ Folder not found — check the path before starting.")

        st.markdown("**Analysis Options**")
        c1, c2, c3, c4 = st.columns(4)
        run_exact = c1.checkbox("Exact duplicates", value=True)
        run_text = c2.checkbox("Near-duplicates", value=True)
        c3.checkbox("Content similarity", value=True, disabled=True, help="Included automatically as part of near-duplicate detection")
        c4.checkbox("Version recommendation", value=True, disabled=True, help="Always applied to any detected duplicate group")

        scan_clicked = S(st.button, "🔍 START ANALYSIS", type="primary")

    if scan_clicked:
        if not os.path.isdir(folder):
            st.error(f"Folder not found: {folder}")
        else:
            discovered = [os.path.join(r, f) for r, d, fs in os.walk(folder) for f in fs]
            status_box = st.empty()
            bar = st.progress(0, text="Starting analysis...")
            live_file = st.empty()

            exact_groups = []
            if run_exact:
                hash_to_files = defaultdict(list)
                for idx, filepath in enumerate(discovered):
                    live_file.markdown(f'<div class="scan-current-file">Currently analysing: {esc(filepath)}</div>', unsafe_allow_html=True)
                    try:
                        h = get_file_hash(filepath)
                        hash_to_files[h].append(filepath)
                    except Exception:
                        pass
                    pct = int((idx / max(len(discovered), 1)) * 40)
                    bar.progress(pct, text=f"ANALYSING DOCUMENTS — {pct}%")
                    status_box.markdown(
                        f'<span class="stat-inline">Files discovered {len(discovered)} &nbsp;·&nbsp; '
                        f'Files analysed {idx+1} &nbsp;·&nbsp; Exact matches so far {sum(1 for v in hash_to_files.values() if len(v)>1)}</span>',
                        unsafe_allow_html=True
                    )
                exact_groups = [fs for fs in hash_to_files.values() if len(fs) > 1]
            live_file.empty()

            text_pairs = []
            if run_text:
                bar.progress(58, text="ANALYSING DOCUMENTS — 58%")
                text_pairs = find_near_duplicate_texts(folder)

            bar.progress(75, text="ANALYSING IMAGES — 75%")
            image_pairs = find_near_duplicate_images(folder)

            bar.progress(90, text="ANALYSING VIDEOS — 90%")
            video_pairs = find_near_duplicate_videos(folder)

            bar.progress(100, text="Analysis complete")
            time.sleep(0.3)
            bar.empty(); status_box.empty()

            st.session_state.update({
                "all_files": discovered, "exact_groups": exact_groups,
                "text_pairs": text_pairs, "image_pairs": image_pairs,
                "video_pairs": video_pairs,
                "scan_folder": folder, "scanned": True,
                "last_scan_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "benchmark_rows": None,
            })
            save_scan_record()
            st.success(
                f"Files discovered: {len(discovered)}  ·  Exact matches: {len(exact_groups)}  ·  "
                f"Near matches: {len(text_pairs) + len(image_pairs) + len(video_pairs)}"
            )
            st.session_state.page = "Overview"
            st.rerun()


def page_storage_comparison():
    render_page_header("Storage Comparison", "Run the same analysis on different storage sources and compare results side by side.")

    if "storage_comparison" not in st.session_state:
        st.session_state["storage_comparison"] = {}

    col_a, col_b, col_c = st.columns(3)

    def scan_column(col, key, default_label, default_path, help_text):
        with col:
            with card(f"cmp_{key}"):
                st.markdown(f"**{default_label}**")
                st.caption(help_text)
                folder = st.text_input("Folder path", value=default_path, key=f"cmp_folder_{key}")
                if st.button(f"▶ Scan {default_label}", key=f"scan_{key}"):
                    if not os.path.exists(folder):
                        st.error("Folder not found.")
                    else:
                        with st.spinner(f"Scanning {default_label}..."):
                            result = run_full_scan_timed(folder)
                            result["label"] = default_label
                            result["folder"] = folder
                            st.session_state["storage_comparison"][key] = result
                        st.success(f"Scan complete in {result['scan_time_seconds']}s")

    scan_column(
        col_a, "A", "Local / OneDrive", st.session_state.scan_folder,
        "OneDrive folders work here directly, since OneDrive syncs to a normal local folder."
    )
    scan_column(
        col_b, "B", "Google Drive", os.path.join(os.getcwd(), "drive_downloads"),
        "Uses already-downloaded Drive files. Run 'Connect and download' on the Scan Folder page first."
    )
    scan_column(
        col_c, "C", "Outlook Storage", os.path.join(os.path.expanduser("~"), "OneDrive", "Outlook Files"),
        "Outlook shares the same Microsoft cloud storage backend as OneDrive, so its synced files also "
        "appear as a normal local folder. Point this at your Outlook attachments/files folder."
    )

    results = st.session_state["storage_comparison"]
    if len(results) >= 2:
        st.markdown('<p class="section-title">Comparison</p>', unsafe_allow_html=True)

        rows_data = {"Metric": ["Storage", "Files Scanned", "Exact Duplicate Groups", "Near-Duplicate Pairs",
                                 "Total Related Groups", "Potential Savings (KB)", "Scan Time (seconds)"]}
        for key, r in results.items():
            rows_data[r["label"]] = [r["label"], r["files_scanned"], r["exact_groups"], r["near_duplicate_pairs"],
                                       r["total_related_groups"], r["potential_savings_kb"], r["scan_time_seconds"]]

        comparison_df = pd.DataFrame(rows_data).astype(str)
        S(st.dataframe, comparison_df, hide_index=True)

        with card("cmp_chart"):
            card_title("Scan time by storage source", "Seconds to run the full analysis (lower is faster).")
            colors = [INDIGO, PURPLE, GREEN]
            fig = go.Figure(data=[
                go.Bar(name=r["label"], x=["Scan time (s)"], y=[r["scan_time_seconds"]], marker_color=colors[i % 3],
                       text=[f"{r['scan_time_seconds']}s"], textposition="outside")
                for i, r in enumerate(results.values())
            ])
            fig.update_layout(yaxis_title="Seconds", legend=dict(orientation="h", y=1.12, x=0))
            show_chart(style_fig(fig, 300), "cmp_chart_fig")

        fastest = min(results.values(), key=lambda r: r["scan_time_seconds"])
        st.caption(f"**{fastest['label']}** completed the scan fastest in this test. Note this compares scanning already-local files in all cases — Google Drive's download time happens separately on the Scan Folder page.")
    elif len(results) == 1:
        st.info("Scan at least one more storage source to see a comparison.")


def page_documents():
    render_page_header("Document Explorer", "Browse, search and inspect every file discovered during the latest scan.", export=True)
    if not st.session_state.scanned:
        render_empty_state("📄", "No documents scanned yet", "Run a scan to see your files here.", "Scan New Folder", "Scan Folder")
        return

    ctx = analysis_context()
    rows = build_file_rows(ctx)
    if not rows:
        render_empty_state("📄", "No files available", "The scanned files no longer exist on disk. Run a new scan.", "Scan New Folder", "Scan Folder")
        return

    with card("doc_filters"):
        search = st.text_input("Search filename", "", placeholder="Type part of a file name…")
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        type_filter = c1.selectbox("File type", ["All", "DOCX", "PDF", "TXT", "Image", "Video", "Other"])
        status_filter = c2.selectbox("Status", ["All", "Exact Duplicate", "Near Duplicate", "Unique"])
        sort_by = c3.selectbox("Sort by", ["Name", "Size", "Modified date"])
        sort_dir = c4.selectbox("Order", ["↑", "↓"])

    df = pd.DataFrame(rows)
    if search: df = df[df["File"].str.contains(search, case=False, regex=False)]
    if type_filter != "All": df = df[df["Type"] == type_filter]
    if status_filter != "All": df = df[df["Status"] == status_filter]
    sort_map = {"Name": "File", "Size": "Size (KB)", "Modified date": "Modified"}
    df = df.sort_values(sort_map[sort_by], ascending=(sort_dir == "↑")).reset_index(drop=True)

    st.caption(f"Showing {len(df)} of {len(rows)} files — click a row to open its details panel.")
    if df.empty:
        st.info("No files match these filters.")
        return

    selected_path = None
    try:
        event = S(st.dataframe, df, hide_index=True, column_config={"Path": None},
                  on_select="rerun", selection_mode="single-row", key="doc_table")
        picked = event.selection.rows
        if picked and picked[0] < len(df):
            selected_path = df.iloc[picked[0]]["Path"]
    except (TypeError, AttributeError):
        S(st.dataframe, df, hide_index=True, column_config={"Path": None})
        choice = st.selectbox("Inspect a file", ["—"] + list(df["Path"]), format_func=lambda p: p if p == "—" else os.path.basename(p))
        if choice != "—":
            selected_path = choice

    if selected_path and os.path.exists(selected_path):
        st.write("")
        render_file_details(selected_path, ctx)


def page_images():
    render_page_header("Images", "Image files found in the last scan, with duplicate status.")
    if not st.session_state.scanned:
        render_empty_state("🖼", "No images scanned yet", "Run a scan to see image files here.", "Scan New Folder", "Scan Folder")
        return

    ctx = analysis_context()
    groups, all_pairs, exact_files, group_of = ctx
    image_files = [f for f in st.session_state.all_files if os.path.exists(f) and file_type_of(f) == "Image"]

    if not image_files:
        render_empty_state("🖼", "No image files found", "The last scanned folder contained no supported image files.")
        return

    m1, m2 = st.columns(2)
    m1.metric("Images scanned", len(image_files))
    m2.metric("Images in a duplicate group", sum(1 for f in image_files if f in group_of))
    st.write("")

    for n, f in enumerate(sorted(image_files)):
        status, sim_val = "Unique", None
        if f in exact_files:
            status, sim_val = "Exact Duplicate", 100.0
        elif f in group_of:
            status, sim_val = "Near Duplicate", similarity_for(all_pairs, group_of[f][1], f)

        with card(f"img_{n}"):
            c1, c2 = st.columns([1, 4])
            with c1:
                try:
                    st.image(f, width=90)
                except Exception:
                    st.caption("(preview unavailable)")
            with c2:
                size_kb = os.path.getsize(f) / 1024
                st.markdown(f"**{esc(os.path.basename(f))}**", unsafe_allow_html=True)
                sim_str = f" · {sim_val:.0f}% match" if sim_val is not None else ""
                st.caption(f"{fmt_size(size_kb)} · {status}{sim_str}")


def page_videos():
    render_page_header("Videos", "Video files found in the last scan, with duplicate status.")
    if not st.session_state.scanned:
        render_empty_state("🎬", "No videos scanned yet", "Run a scan to see video files here.", "Scan New Folder", "Scan Folder")
        return

    ctx = analysis_context()
    groups, all_pairs, exact_files, group_of = ctx
    video_files = [f for f in st.session_state.all_files if os.path.exists(f) and file_type_of(f) == "Video"]

    if not video_files:
        render_empty_state("🎬", "No video files found", "The last scanned folder contained no supported video files.")
        return

    m1, m2 = st.columns(2)
    m1.metric("Videos scanned", len(video_files))
    m2.metric("Videos in a duplicate group", sum(1 for f in video_files if f in group_of))
    st.write("")

    for n, f in enumerate(sorted(video_files)):
        status, sim_val = "Unique", None
        if f in exact_files:
            status, sim_val = "Exact Duplicate", 100.0
        elif f in group_of:
            status, sim_val = "Near Duplicate", similarity_for(all_pairs, group_of[f][1], f)

        with card(f"vid_{n}"):
            size_kb = os.path.getsize(f) / 1024
            st.markdown(f"🎬 **{esc(os.path.basename(f))}**", unsafe_allow_html=True)
            sim_str = f" · {sim_val:.0f}% frame match" if sim_val is not None else ""
            st.caption(f"{fmt_size(size_kb)} · {status}{sim_str}")
            try:
                st.video(f)
            except Exception:
                st.warning("Preview unavailable for this file (often due to very large file size or an unsupported codec). Detection results above are unaffected.")


def page_duplicate_groups():
    render_page_header("Duplicate Groups", "Click a group to inspect its files, see the recommended version and review outdated copies.")
    if not st.session_state.scanned:
        render_empty_state("◈", "No scan yet", "Run a scan to see duplicate groups.", "Scan New Folder", "Scan Folder")
        return

    exact_groups = [g for g in st.session_state.exact_groups if all(os.path.exists(f) for f in g)]
    total_files = sum(len(g) for g in exact_groups)
    total_kb = total_wasted_kb(exact_groups) if exact_groups else 0

    render_kpi_row([
        ("Total Groups", f"{len(exact_groups)}", "exact duplicate groups"),
        ("Total Duplicate Files", f"{total_files}", "files in those groups"),
        ("Potential Storage", fmt_size(total_kb), "reclaimable from exact copies"),
    ])
    st.write("")

    tab_exact, tab_near = st.tabs(["Exact duplicates", "Near-duplicate groups"])

    with tab_exact:
        if not exact_groups:
            render_empty_state("✓", "No exact duplicates detected", "All analysed documents appear to be unique.")
        else:
            search = st.text_input("Search files", "", key="dg_search")
            largest_group = max(len(g) for g in exact_groups)
            if largest_group > 2:
                min_size = st.slider("Minimum group size", 2, largest_group, 2)
            else:
                min_size = 2
                st.caption("All duplicate groups currently have 2 files — no filtering needed.")

            for i, group in enumerate(exact_groups, start=1):
                if len(group) < min_size: continue
                if search and not any(search.lower() in os.path.basename(f).lower() for f in group): continue
                render_duplicate_group(group, i, show_hash=True, key_prefix="ex")

    with tab_near:
        groups, _ = combined_groups()
        exact_sets = [set(g) for g in st.session_state.exact_groups]
        near_groups = [[f for f in g if os.path.exists(f)] for g in groups]
        near_groups = [g for g in near_groups if len(g) > 1 and not any(set(g) <= s for s in exact_sets)]
        if not near_groups:
            render_empty_state("✓", "No near-duplicate groups", "No documents, images or videos were found to be similar but not identical.")
        else:
            st.caption("Files that are similar but not byte-for-byte identical, grouped together.")
            for i, group in enumerate(near_groups, start=1):
                render_duplicate_group(group, i, show_hash=False, key_prefix="nr")


def page_similarity():
    render_page_header("Similarity Explorer", "Compare related documents, images and videos side by side, even when their file names differ.")
    if not st.session_state.scanned:
        render_empty_state("⇄", "No scan yet", "Run a scan to see similarity results.", "Scan New Folder", "Scan Folder")
        return

    pairs = [
        (a, b, s) for a, b, s in
        (list(st.session_state.text_pairs) + list(st.session_state.image_pairs) + list(st.session_state.get("video_pairs", [])))
        if os.path.exists(a) and os.path.exists(b)
    ]
    if not pairs:
        render_empty_state("✓", "No near-duplicates detected", "All analysed documents appear to be unique.")
        return

    groups, _ = combined_groups()
    file_to_latest = {}
    for g in groups:
        existing = [f for f in g if os.path.exists(f)]
        if len(existing) > 1:
            latest = recommend_latest_version(existing)
            for f in existing:
                file_to_latest[f] = latest

    def category(path):
        t = file_type_of(path)
        return "Images" if t == "Image" else "Videos" if t == "Video" else "Documents"

    with card("sim_filters"):
        c1, c2, c3 = st.columns([2, 2, 3])
        cat_filter = c1.selectbox("Type", ["All", "Documents", "Images", "Videos"])
        min_sim = c2.slider("Minimum similarity (%)", 0, 100, 0)
        search = c3.text_input("Search file name", "")

    shown = [(a, b, s) for a, b, s in pairs
             if (cat_filter == "All" or category(a) == cat_filter)
             and s * 100 >= min_sim
             and (not search or search.lower() in os.path.basename(a).lower() or search.lower() in os.path.basename(b).lower())]
    shown.sort(key=lambda p: -p[2])
    st.caption(f"{len(shown)} of {len(pairs)} similar pairs shown, most similar first.")
    if not shown:
        st.info("No pairs match these filters.")
        return

    for n, (file_a, file_b, sim) in enumerate(shown[:50]):
        sim_pct = sim * 100
        with card(f"sim_{n}"):
            c1, c2 = st.columns(2)
            c1.markdown(f"**DOCUMENT A**  \n{esc(os.path.basename(file_a))}", unsafe_allow_html=True)
            c2.markdown(f"**DOCUMENT B**  \n{esc(os.path.basename(file_b))}", unsafe_allow_html=True)
            st.progress(min(sim_pct / 100, 1.0), text=f"SIMILARITY — {sim_pct:.1f}%")
            with st.expander("View side-by-side comparison"):
                m1, m2 = st.columns(2)
                for col, f in ((m1, file_a), (m2, file_b)):
                    mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
                    col.caption(f"{fmt_size(os.path.getsize(f) / 1024)}  ·  modified {mtime}  ·  {file_type_of(f)}")
                    col.caption(f"Path: {f}")
                kind = category(file_a)
                if kind == "Images":
                    i1, i2 = st.columns(2)
                    for col, f in ((i1, file_a), (i2, file_b)):
                        try:
                            col.image(f, width=300)
                        except Exception:
                            col.caption("(preview unavailable)")
                elif kind == "Videos":
                    st.caption("Videos are compared by sampled-frame perceptual hashes; the score above is the fraction of matching frames. Preview them on the Videos page.")
                else:
                    render_text_compare(file_a, file_b)
                latest = file_to_latest.get(file_a)
                if latest:
                    st.markdown(f"★ **Recommended Current Version:** {esc(os.path.basename(latest))}", unsafe_allow_html=True)
                    st.caption("Recommended based on modification date and document content.")
    if len(shown) > 50:
        st.caption("Only the 50 most similar pairs are displayed. Use the filters to narrow the list.")


def page_analytics():
    render_page_header("Analytics", "Storage and duplicate distribution across the last scan.", export=True)
    if not st.session_state.scanned:
        render_empty_state("◉", "No scan yet", "Run a scan to see analytics.", "Scan New Folder", "Scan Folder")
        return

    ctx = analysis_context()
    groups, _, exact_files, group_of = ctx
    existing_files = [f for f in st.session_state.all_files if os.path.exists(f)]
    stats = group_stats(groups)
    total_size_kb = sum(os.path.getsize(f) for f in existing_files) / 1024
    wasted_kb = sum(r["reclaim_kb"] for r in stats)

    render_kpi_row([
        ("Total folder size", fmt_size(total_size_kb), f"{len(existing_files)} files"),
        ("Duplicate storage", fmt_size(wasted_kb), "outdated copies"),
        ("Share of storage", f"{(wasted_kb / total_size_kb * 100) if total_size_kb else 0:.1f}%", "that is duplicated"),
    ])
    st.caption("This is an estimate based on detected duplicate files. No files are automatically deleted.")
    st.write("")

    c1, c2 = st.columns(2)
    with c1:
        with card("an_dist"):
            card_title("File distribution", "Number of files per type.")
            ext_counts = {}
            for f in existing_files:
                ext_counts[file_type_of(f)] = ext_counts.get(file_type_of(f), 0) + 1
            present = [t for t in ["DOCX", "PDF", "TXT", "Image", "Video", "Other"] if t in ext_counts]
            fig = go.Figure(data=[go.Bar(
                x=present, y=[ext_counts[t] for t in present],
                marker_color=[TYPE_COLORS[t] for t in present],
                text=[ext_counts[t] for t in present], textposition="outside",
            )])
            fig.update_layout(yaxis_title="Files")
            show_chart(style_fig(fig, 320), "an_dist_chart")

    with c2:
        with card("an_pie"):
            card_title("Duplicate distribution", "Share of files by status.")
            exact_n = sum(1 for f in existing_files if f in exact_files)
            near_n = sum(1 for f in existing_files if f in group_of and f not in exact_files)
            unique_n = max(len(existing_files) - exact_n - near_n, 0)
            fig2 = go.Figure(data=[go.Pie(
                labels=["Exact duplicate", "Near duplicate", "Unique"], values=[exact_n, near_n, unique_n],
                hole=0.6, marker=dict(colors=[ACCENT, INDIGO, GREEN], line=dict(color="white", width=2)),
                textinfo="percent", sort=False,
            )])
            fig2.add_annotation(text=f"<b>{len(existing_files)}</b><br>files", showarrow=False, font=dict(size=18))
            fig2.update_layout(legend=dict(orientation="h", y=-0.08, x=0.02))
            show_chart(style_fig(fig2, 320), "an_pie_chart")

    if stats:
        st.markdown('<p class="section-title">Largest Duplicate Groups</p>', unsafe_allow_html=True)
        st.caption("Ranked by total storage used across all files in the group.")
        ranked = sorted(stats, key=lambda r: -r["total_kb"])[:5]
        for i, r in enumerate(ranked, start=1):
            with card(f"an_group_{i}"):
                c1, c2 = st.columns([0.5, 5])
                with c1:
                    st.markdown(f"<div style='font-size:1.3rem; font-weight:800; color:{ACCENT};'>#{i}</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"**{len(r['files'])} files** &nbsp;·&nbsp; **{fmt_size(r['total_kb'])}**", unsafe_allow_html=True)
                    for f in sorted(r["files"]):
                        st.caption(f"{TYPE_ICONS.get(file_type_of(f), '📄')} {os.path.basename(f)}")

        st.markdown('<p class="section-title">Most Common Duplicate Types</p>', unsafe_allow_html=True)
        st.caption("File types most frequently involved in duplicate or near-duplicate groups.")
        type_counts = {}
        for f in group_of:
            type_counts[file_type_of(f)] = type_counts.get(file_type_of(f), 0) + 1
        sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])
        max_count = sorted_types[0][1] if sorted_types else 1
        with card("an_types"):
            for t, c in sorted_types:
                pct = (c / max_count) * 100
                st.markdown(
                    f'<div class="bar-row"><div class="lbl">{TYPE_ICONS.get(t, "📄")} {t}</div>'
                    f'<div class="track"><div class="fill" style="width:{pct}%;background:{TYPE_COLORS.get(t, MUTED)}"></div></div>'
                    f'<div class="val">{c} files</div></div>', unsafe_allow_html=True)


def page_optimization():
    render_page_header("Storage Optimization",
                       "See which duplicate groups use the most space and review outdated copies safely.", export=True)
    if not st.session_state.scanned:
        render_empty_state("♻", "No scan yet", "Run a scan to see optimization recommendations.", "Scan New Folder", "Scan Folder")
        return

    groups, _ = combined_groups()
    stats = group_stats(groups)
    if not stats:
        st.success("✓ No duplicate groups found — there is nothing to optimise.")
        return

    existing_files = [f for f in st.session_state.all_files if os.path.exists(f)]
    total_kb = sum(os.path.getsize(f) for f in existing_files) / 1024
    reclaim_total = sum(r["reclaim_kb"] for r in stats)
    render_kpi_row([
        ("Reclaimable space", fmt_size(reclaim_total), f"{(reclaim_total / total_kb * 100) if total_kb else 0:.1f}% of the folder"),
        ("Groups to review", f"{len(stats)}", f"{sum(1 for r in stats if r['kind'] == 'Exact')} exact · {sum(1 for r in stats if r['kind'] == 'Near')} near"),
        ("Largest saving", fmt_size(stats[0]["reclaim_kb"]), os.path.basename(stats[0]["latest"])),
    ])
    st.write("")

    with card("opt_chart"):
        card_title("Where the space is wasted", "Top 10 groups by reclaimable storage (outdated copies only).")
        top = stats[:10]
        fig = go.Figure(go.Bar(
            y=[os.path.basename(r["latest"]) for r in reversed(top)], x=[r["reclaim_kb"] for r in reversed(top)],
            orientation="h", marker_color=[ACCENT if r["kind"] == "Exact" else INDIGO for r in reversed(top)],
            text=[fmt_size(r["reclaim_kb"]) for r in reversed(top)], textposition="outside",
        ))
        fig.update_layout(xaxis_title="Reclaimable KB")
        show_chart(style_fig(fig, max(240, 40 * len(top) + 60)), "opt_chart_fig")
        st.caption("Orange = exact duplicates · Blue = near-duplicates.")

    st.markdown('<p class="section-title">Select groups to review</p>', unsafe_allow_html=True)
    st.caption("Tick the groups you want to review. The recommended current version in each group is always kept in place.")
    table = pd.DataFrame({
        "Review": [False] * len(stats),
        "Type": [r["kind"] for r in stats],
        "Files": [len(r["files"]) for r in stats],
        "Recommended file (kept)": [os.path.basename(r["latest"]) for r in stats],
        "Group size": [fmt_size(r["total_kb"]) for r in stats],
        "Reclaimable": [fmt_size(r["reclaim_kb"]) for r in stats],
    })
    edited = S(st.data_editor, table, hide_index=True, key="opt_table",
               disabled=[c for c in table.columns if c != "Review"],
               column_config={"Review": st.column_config.CheckboxColumn("Review", default=False)})
    chosen = [stats[i] for i in range(len(stats)) if bool(edited.iloc[i]["Review"])]

    if chosen:
        n_files = sum(len(r["files"]) - 1 for r in chosen)
        gain = sum(r["reclaim_kb"] for r in chosen)
        st.markdown(f"**{len(chosen)} group(s) selected** — {n_files} outdated file(s), {fmt_size(gain)} to review.")
        with st.expander("Files that will be moved"):
            for r in chosen:
                for f in r["files"]:
                    if f != r["latest"]:
                        st.caption(f"{f}")
        st.caption(f"Nothing is deleted. The files are moved into a '{REVIEW_FOLDER_NAME}' folder inside the scanned folder, "
                   "where you can check them and delete them yourself.")
        confirm = st.checkbox(f"I confirm moving {n_files} file(s) to the review folder", key="opt_confirm")
        if st.button("🗂 Move selected outdated files to review folder", key="opt_move", type="primary", disabled=not confirm):
            all_moved = []
            for r in chosen:
                all_moved += move_outdated_to_review(r["files"], r["latest"], st.session_state.scan_folder)
            if all_moved:
                apply_moved(all_moved)
                st.success(f"Moved {len(all_moved)} file(s) to {REVIEW_FOLDER_NAME}. Results were updated.")
                st.rerun()
    else:
        st.info("No groups selected yet.")


def closure_pairs(raw_pairs):
    """Turn a list of (name_a, name_b) into every pair inside each connected group."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in raw_pairs:
        parent[find(a)] = find(b)
    members = defaultdict(list)
    for x in list(parent):
        members[find(x)].append(x)
    out = set()
    for m in members.values():
        for a, b in combinations(sorted(m), 2):
            out.add(frozenset((a, b)))
    return out


def name_category(name):
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXT: return "Images"
    if ext in VIDEO_EXT: return "Videos"
    return "Documents"


def page_accuracy():
    render_page_header("Accuracy", "Measure precision, recall and F1 by comparing the scan with a ground-truth list you labelled yourself.")
    if not st.session_state.scanned:
        render_empty_state("✔", "No scan yet", "Scan the folder you labelled, then come back to measure accuracy.", "Scan New Folder", "Scan Folder")
        return

    with st.expander("How to use this page", expanded=False):
        st.markdown(
            "1. **Before looking at the results**, list the file pairs that you know are duplicates or near-duplicates "
            "(one pair per row, file names only, for example `Report_v1.docx` and `Report_v2.docx`).\n"
            "2. For a group of three files, list two pairs that connect them (A–B and B–C). Groups are completed automatically.\n"
            "3. Type the pairs in the table or upload a CSV with the columns `file_a` and `file_b`.\n"
            "4. The page compares your list with what DocDetect detected in the last scan and calculates:\n"
            "   - **Precision** = correct detections ÷ all detections\n"
            "   - **Recall** = correct detections ÷ all real duplicate pairs\n"
            "   - **F1** = the balance of the two\n"
            "5. File names must be unique inside the scanned folder. Scan the same folder that you labelled."
        )

    up = st.file_uploader("Upload ground-truth CSV (optional)", type=["csv"])
    empty_gt = pd.DataFrame({"file_a": pd.Series(dtype="string"), "file_b": pd.Series(dtype="string")})
    base_df, editor_key = empty_gt, "gt_editor"
    if up is not None:
        try:
            base_df = pd.read_csv(up).astype(str)[["file_a", "file_b"]]
            editor_key = f"gt_editor_{up.name}_{up.size}"
        except Exception as e:
            st.error(f"Could not read the CSV: {e}. It needs the columns file_a and file_b.")

    st.markdown("**Ground-truth pairs**")
    st.caption("Type one pair per row. Press Enter after the last cell of a row to save it, then click an empty area.")
    # The editor keeps your edits by itself (via its key), so it must always receive the SAME starting table.
    gt_df = S(st.data_editor, base_df, num_rows="dynamic", key=editor_key, hide_index=True)
    S(st.download_button, "⬇ Download empty template (CSV)", data="file_a,file_b\n", file_name="ground_truth_template.csv", mime="text/csv", key="gt_template")

    truth_raw = [(str(a).strip(), str(b).strip()) for a, b in zip(gt_df["file_a"], gt_df["file_b"])
                 if str(a).strip() not in ("", "nan", "<NA>", "None") and str(b).strip() not in ("", "nan", "<NA>", "None")]
    if not truth_raw:
        st.info("Add at least one ground-truth pair to calculate accuracy.")
        return

    detected_raw = []
    for g in st.session_state.exact_groups:
        for i in range(len(g) - 1):
            detected_raw.append((os.path.basename(g[i]), os.path.basename(g[i + 1])))
    for a, b, _ in (list(st.session_state.text_pairs) + list(st.session_state.image_pairs) + list(st.session_state.get("video_pairs", []))):
        detected_raw.append((os.path.basename(a), os.path.basename(b)))

    truth = closure_pairs(truth_raw)
    detected = closure_pairs(detected_raw)

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if (tp + fp) else None
        r = tp / (tp + fn) if (tp + fn) else None
        f = (2 * p * r / (p + r)) if (p is not None and r is not None and (p + r) > 0) else None
        return p, r, f

    def pct(x):
        return "n/a" if x is None else f"{x * 100:.1f}%"

    def category_of_pair(pair):
        return name_category(sorted(pair)[0])

    rows = []
    for cat in ["Documents", "Images", "Videos", "All"]:
        t = {p for p in truth if cat == "All" or category_of_pair(p) == cat}
        d = {p for p in detected if cat == "All" or category_of_pair(p) == cat}
        if cat != "All" and not t and not d:
            continue
        tp, fp, fn = len(t & d), len(d - t), len(t - d)
        p, r, f = prf(tp, fp, fn)
        rows.append({"File type": cat, "True pairs": len(t), "Detected": len(d), "Correct (TP)": tp,
                     "False alarms (FP)": fp, "Missed (FN)": fn,
                     "Precision": pct(p), "Recall": pct(r), "F1": pct(f)})
    result_df = pd.DataFrame(rows)
    overall = rows[-1]

    st.markdown('<p class="section-title">Results</p>', unsafe_allow_html=True)
    cols = st.columns(3)
    with cols[0]:
        kpi_card("acc_p", "Precision", overall["Precision"], f"{overall['Correct (TP)']} correct of {overall['Detected']} detected pairs")
    with cols[1]:
        kpi_card("acc_r", "Recall", overall["Recall"], f"{overall['Correct (TP)']} found of {overall['True pairs']} real pairs")
    with cols[2]:
        kpi_card("acc_f", "F1 score", overall["F1"], "balance of precision and recall")

    st.write("")
    S(st.dataframe, result_df, hide_index=True)
    S(st.download_button, "⬇ Download accuracy table (CSV)", data=result_df.to_csv(index=False).encode("utf-8"),
      file_name="docdetect_accuracy.csv", mime="text/csv", key="acc_download")

    fps = sorted(tuple(sorted(p)) for p in detected - truth)
    fns = sorted(tuple(sorted(p)) for p in truth - detected)
    c1, c2 = st.columns(2)
    with c1:
        with st.expander(f"False alarms — detected but not in your list ({len(fps)})"):
            if not fps:
                st.caption("None.")
            for a, b in fps:
                st.caption(f"{a}  ↔  {b}")
    with c2:
        with st.expander(f"Missed — in your list but not detected ({len(fns)})"):
            if not fns:
                st.caption("None.")
            for a, b in fns:
                st.caption(f"{a}  ↔  {b}")
    st.caption("A false alarm can also mean a real duplicate that you forgot to list — check these first. "
               "Pairs are evaluated after groups are completed, the same way the dashboard shows groups.")


def page_performance():
    render_page_header("Performance", "Hashing and text extraction speed by file size, from the last scan.")

    if not st.session_state.scanned:
        render_empty_state("⚡", "No scan yet", "Run a scan to see performance data.", "Scan New Folder", "Scan Folder")
        return

    if st.button("⏱ Run performance benchmark on last scanned files", type="primary"):
        rows = []
        with st.spinner("Timing hashing and text extraction..."):
            for filepath in st.session_state.all_files:
                if not os.path.exists(filepath):
                    continue
                try:
                    size_kb = os.path.getsize(filepath) / 1024
                    category = classify_size(size_kb)

                    t0 = time.time()
                    get_file_hash(filepath)
                    hash_time = time.time() - t0

                    extract_time = None
                    if is_text_file(filepath):
                        t0 = time.time()
                        extract_text(filepath)
                        extract_time = time.time() - t0

                    rows.append({
                        "File": os.path.basename(filepath),
                        "Size Category": category,
                        "Size (KB)": round(size_kb, 1),
                        "Hash Time (s)": round(hash_time, 4),
                        "Extract Time (s)": round(extract_time, 4) if extract_time is not None else None,
                    })
                except Exception:
                    continue

        st.session_state["benchmark_rows"] = rows

    rows = st.session_state.get("benchmark_rows")
    if not rows:
        st.info("Click the button above to run the benchmark on your last scanned files.")
        return

    df = pd.DataFrame(rows)
    summary = df.groupby("Size Category").agg(
        avg_hash=("Hash Time (s)", "mean"),
        avg_extract=("Extract Time (s)", "mean"),
        count=("File", "count"),
    ).reset_index()
    order = ["Small (<100 KB)", "Medium (100 KB-5 MB)", "Large (>5 MB)"]
    summary["Size Category"] = pd.Categorical(summary["Size Category"], categories=order, ordered=True)
    summary = summary.sort_values("Size Category")

    c1, c2 = st.columns(2)
    with c1:
        with card("perf_hash"):
            card_title("Average hash time", "By file size category.")
            fig = go.Figure(data=[go.Bar(
                x=summary["Size Category"], y=summary["avg_hash"], marker_color=ACCENT,
                text=[f"{v:.4f}s" for v in summary["avg_hash"]], textposition="outside",
            )])
            fig.update_layout(yaxis_title="Seconds")
            show_chart(style_fig(fig, 300), "perf_hash_fig")
    with c2:
        with card("perf_extract"):
            card_title("Average text extraction time", "By file size category.")
            fig2 = go.Figure(data=[go.Bar(
                x=summary["Size Category"], y=summary["avg_extract"], marker_color=PURPLE,
                text=[f"{v:.4f}s" if pd.notna(v) else "N/A" for v in summary["avg_extract"]], textposition="outside",
            )])
            fig2.update_layout(yaxis_title="Seconds")
            show_chart(style_fig(fig2, 300), "perf_extract_fig")

    with card("perf_count"):
        card_title("File count by size category")
        fig3 = go.Figure(data=[go.Bar(
            x=summary["Size Category"], y=summary["count"], marker_color=GREEN,
            text=summary["count"], textposition="outside",
        )])
        fig3.update_layout(yaxis_title="Files")
        show_chart(style_fig(fig3, 260), "perf_count_fig")

    st.markdown('<p class="section-title">Full Results</p>', unsafe_allow_html=True)
    S(st.dataframe, df, hide_index=True)


def page_history():
    render_page_header("Scan History", "Previous scans performed on this device.")
    history = load_history()
    if not history:
        render_empty_state("◷", "No previous scans", "Your completed scans will appear here.")
        return

    folders = sorted({r.get("folder", "") for r in history})
    chosen = st.selectbox("Trend for folder", folders, index=folders.index(st.session_state.scan_folder) if st.session_state.scan_folder in folders else 0)
    series = [r for r in reversed(history) if r.get("folder") == chosen]
    if len(series) >= 2:
        with card("hist_trend"):
            card_title("Trend across scans", "How this folder's results changed over time.")
            fig = go.Figure()
            fig.add_scatter(x=[r["date"] for r in series], y=[r.get("exact_duplicate_groups", 0) for r in series], name="Exact groups", mode="lines+markers", line=dict(color=ACCENT))
            fig.add_scatter(x=[r["date"] for r in series], y=[r.get("near_duplicate_pairs", 0) for r in series], name="Near-duplicate pairs", mode="lines+markers", line=dict(color=INDIGO))
            fig.update_layout(legend=dict(orientation="h", y=1.15, x=0))
            show_chart(style_fig(fig, 260), "hist_trend_fig")
    else:
        st.caption("Scan this folder at least twice to see a trend.")

    st.caption("Delete individual scan records below. This only removes the history entry — it does not affect your files.")

    for i, record in enumerate(history):
        with card(f"hist_{i}"):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"**{esc(record.get('date', 'Unknown date'))}** — {esc(record.get('folder', 'Unknown folder'))}", unsafe_allow_html=True)
                st.caption(
                    f"Files scanned: {record.get('files_scanned', 0)}  ·  "
                    f"Exact duplicates: {record.get('exact_duplicate_groups', 0)}  ·  "
                    f"Near duplicates: {record.get('near_duplicate_pairs', 0)}  ·  "
                    f"Potential savings: {record.get('potential_savings_kb', 0)} KB"
                )
            with c2:
                if st.button("🗑 Delete", key=f"del_history_{i}"):
                    history.pop(i)
                    save_history(history)
                    st.rerun()

    st.write("")
    if st.button("🗑 Clear all scan history", type="secondary"):
        save_history([])
        st.rerun()


def page_settings():
    render_page_header("Settings", "Analysis configuration and system information.")

    with card("set_analysis"):
        card_title("Analysis settings")
        st.write(f"**Default similarity threshold (documents):** {SIMILARITY_THRESHOLD*100:.0f}%")
        st.write(f"**Image perceptual hash difference threshold:** {HASH_DIFFERENCE_THRESHOLD}")
        st.write("**Supported document types:** DOCX, PDF, TXT")
        st.write("**Supported image types:** JPG, PNG, BMP, GIF")
        st.write("**Supported video types:** MP4, AVI, MOV, MKV, WMV (compared via sampled-frame perceptual hashing)")
        st.write("**Version recommendation:** rule-based — modification date and content length")
        st.write("**Cloud connectivity:** Google Drive folders can be connected and downloaded locally before analysis, with an option to filter by uploader when a folder has multiple contributors. OneDrive and Outlook storage are supported natively via local folder scanning, since both share Microsoft's cloud storage backend. Google Cloud Storage was evaluated but not integrated, due to a mandatory billing account requirement.")

    with card("set_system"):
        card_title("System information")
        st.write(f"**Python version:** {sys.version.split()[0]}")
        st.write(f"**Streamlit version:** {st.__version__}")
        st.write("**Application version:** v2.0 — FYP Prototype")

    with card("set_privacy"):
        card_title("Privacy")
        st.markdown(
            '<div class="finding-card" style="margin:0">Files are analysed locally on this device. Google Drive files are '
            'downloaded to this device via an authenticated, read-only connection before analysis, and '
            'nothing is uploaded to a server controlled by this application.</div>', unsafe_allow_html=True
        )


# ---------------------------------------------------------------------------
# ROUTING
# ---------------------------------------------------------------------------
render_topbar()
render_sidebar()

PAGES = {
    "Overview": page_overview, "Scan Folder": page_scan, "Storage Comparison": page_storage_comparison,
    "Documents": page_documents, "Images": page_images, "Videos": page_videos,
    "Duplicate Groups": page_duplicate_groups, "Similarity Explorer": page_similarity,
    "Analytics": page_analytics, "Optimization": page_optimization, "Accuracy": page_accuracy,
    "Performance": page_performance, "Scan History": page_history, "Settings": page_settings,
}
PAGES.get(st.session_state.page, page_overview)()