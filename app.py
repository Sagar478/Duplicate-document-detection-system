import streamlit as st
import os, sys, json, time
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from hasher import find_exact_duplicates, get_file_hash
from near_duplicate_text import find_near_duplicate_texts, SIMILARITY_THRESHOLD
from image_similarity import find_near_duplicate_images, HASH_DIFFERENCE_THRESHOLD
from video_similarity import find_near_duplicate_videos, is_video_file, VIDEO_EXTENSIONS
from version_recommender import group_related_files, recommend_latest_version
from text_extractor import extract_text, is_text_file
from google_drive_connector import sync_drive_folder_to_local

st.set_page_config(page_title="DocDetect", page_icon="📄", layout="wide")

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
VIDEO_EXT = (".mp4", ".avi", ".mov", ".mkv", ".wmv")
HISTORY_FILE = "scan_history.json"

NAVY = "#101828"; INDIGO = "#4C5FD5"; PURPLE = "#7C6FE0"
GREEN = "#1D9C6E"; AMBER = "#C98A1B"; RED = "#D14343"
MUTED = "#667085"; LINE = "#E4E7EC"; BG = "#F8F9FB"
PALETTE = [INDIGO, PURPLE, GREEN, AMBER, RED]
TYPE_ICONS = {"DOCX": "📄", "PDF": "📕", "TXT": "📝", "Image": "🖼️", "Video": "🎬", "Other": "📦"}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
.stApp {{ background-color: {BG}; }}
#MainMenu, header[data-testid="stHeader"] {{ background: transparent; }}

.topbar-brand {{ display: flex; align-items: center; gap: 12px; justify-content: center; }}
.topbar-brand .logo {{
    width: 44px; height: 44px; border-radius: 10px; background: {NAVY};
    color: white; display: flex; align-items: center; justify-content: center; font-size: 1.3rem;
}}
.topbar-brand .name {{ font-size: 1.5rem; font-weight: 800; color: {NAVY}; line-height: 1.1; letter-spacing: 0.01em; }}
.topbar-brand .tag {{ font-size: 0.82rem; color: {MUTED}; }}
.topbar-status {{ font-size: 0.8rem; color: {GREEN}; font-weight: 500; }}

.page-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px; }}
.page-header h1 {{ font-size: 1.55rem; font-weight: 700; color: {NAVY}; margin: 0; }}
.page-header p {{ font-size: 0.87rem; color: {MUTED}; margin: 3px 0 0 0; }}
.last-scan {{ font-size: 0.78rem; color: {MUTED}; text-align: right; }}
.last-scan b {{ color: {NAVY}; }}

.kpi-card {{ border: 1px solid {LINE}; border-radius: 10px; padding: 16px 18px; background: white; }}
.kpi-label {{ font-size: 0.76rem; color: {MUTED}; font-weight: 500; }}
.kpi-value {{ font-size: 1.7rem; font-weight: 700; color: {NAVY}; margin: 4px 0 2px 0; }}
.kpi-sub {{ font-size: 0.75rem; color: {MUTED}; }}
.kpi-delta-good {{ font-size: 0.75rem; color: {GREEN}; font-weight: 600; }}
.kpi-delta-bad {{ font-size: 0.75rem; color: {RED}; font-weight: 600; }}

.section-title {{ font-size: 1.02rem; font-weight: 600; color: {NAVY}; margin: 24px 0 4px 0; }}
.section-sub {{ font-size: 0.84rem; color: {MUTED}; margin-bottom: 12px; }}

.empty-state {{ border: 1px dashed #CBD1DA; border-radius: 12px; padding: 38px 20px; text-align: center; background: white; }}
.empty-state .icon {{ font-size: 1.7rem; margin-bottom: 8px; }}
.empty-state h4 {{ color: {NAVY}; margin: 0 0 4px 0; }}
.empty-state p {{ color: {MUTED}; font-size: 0.87rem; margin: 0; }}

.status-badge {{ display:inline-block; font-size:0.7rem; font-weight:600; border-radius:5px; padding:2px 8px; }}
.badge-exact {{ background:{RED}14; color:{RED}; }}
.badge-near {{ background:{INDIGO}14; color:{INDIGO}; }}
.badge-unique {{ background:{GREEN}14; color:{GREEN}; }}
.rec-badge {{ display:inline-block; font-size:0.7rem; font-weight:600; color:{GREEN}; background:{GREEN}14; border-radius:6px; padding:2px 8px; margin-left:6px; }}

.finding-card {{ border:1px solid {LINE}; border-radius:10px; padding:14px 16px; background:white; margin-bottom:10px; }}
.scan-current-file {{ font-family: monospace; font-size: 0.8rem; color: {INDIGO}; background: {INDIGO}0D; border-radius: 6px; padding: 6px 10px; margin-top: 6px; }}
.stat-inline {{ font-family: monospace; font-size: 0.82rem; color: {MUTED}; }}

.sidebar-brand {{ font-size: 1.1rem; font-weight: 700; color: {NAVY}; margin-bottom: 0; }}
.sidebar-sub {{ font-size: 0.76rem; color: {MUTED}; margin: 0 0 16px 0; }}
.sidebar-section {{ font-size: 0.7rem; font-weight: 700; color: {MUTED}; letter-spacing: 0.05em; margin: 14px 0 4px 4px; }}
.local-note {{ font-size: 0.75rem; color: {MUTED}; border-top: 1px solid {LINE}; padding-top: 10px; margin-top: 14px; line-height: 1.4; }}
.version-footer {{ font-size: 0.7rem; color: #98A2B3; margin-top: 10px; }}
</style>
""", unsafe_allow_html=True)

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
        latest = recommend_latest_version(group)
        for f in group:
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
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []


def previous_scan_for_folder(folder):
    for record in load_history():
        if record.get("folder") == folder:
            return record
    return None


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
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[:20], f, indent=2)


# ---------------------------------------------------------------------------
# TOP APP BAR + SIDEBAR
# ---------------------------------------------------------------------------
def render_topbar():
    st.markdown("""
    <div class="topbar-brand">
        <div class="logo">📄</div>
        <div><div class="name">DOCDETECT</div><div class="tag">Duplicate Document Intelligence</div></div>
    </div>
    <div style="text-align:center; margin-top:6px;">
        <span class="topbar-status">● System Ready — Local Analysis</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div style="border-bottom:1px solid #E4E7EC; margin: 14px 0 16px 0;"></div>', unsafe_allow_html=True)


def render_sidebar():
    with st.sidebar:
        st.markdown('<p class="sidebar-brand">DOCDETECT</p>', unsafe_allow_html=True)
        st.markdown('<p class="sidebar-sub">Duplicate Intelligence</p>', unsafe_allow_html=True)

        def nav_btn(label, icon, page):
            if st.button(f"{icon}  {label}", use_container_width=True,
                         type="primary" if st.session_state.page == page else "secondary"):
                st.session_state.page = page
                st.rerun()

        st.markdown('<p class="sidebar-section">MAIN</p>', unsafe_allow_html=True)
        nav_btn("Overview", "▣", "Overview")
        nav_btn("Scan Folder", "⌕", "Scan Folder")
        nav_btn("Documents", "▤", "Documents")
        nav_btn("Images", "🖼", "Images")
        nav_btn("Videos", "🎬", "Videos")
        nav_btn("Duplicate Groups", "◈", "Duplicate Groups")
        nav_btn("Similarity Explorer", "⇄", "Similarity Explorer")

        st.markdown('<p class="sidebar-section">INSIGHTS</p>', unsafe_allow_html=True)
        nav_btn("Analytics", "◉", "Analytics")
        nav_btn("Performance", "⚡", "Performance")
        nav_btn("Scan History", "◷", "Scan History")

        st.markdown('<p class="sidebar-section">SYSTEM</p>', unsafe_allow_html=True)
        nav_btn("Settings", "⚙", "Settings")

        st.markdown(
            '<div class="local-note"><b>LOCAL ANALYSIS</b><br>● Active<br>'
            'Files remain on this device. Google Drive files are downloaded locally before analysis.</div>'
            '<div class="version-footer">v1.0 — FYP Prototype</div>',
            unsafe_allow_html=True
        )


def render_page_header(title, subtitle):
    last_scan = st.session_state.last_scan_time or "Not scanned yet"
    c1, c2 = st.columns([3, 1.4])
    with c1:
        st.markdown(f'<div class="page-header"><div><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="last-scan">Last Scan<br><b>{last_scan}</b></div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_kpi_row(items):
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value, sub = item[0], item[1], item[2]
        delta = item[3] if len(item) > 3 else None
        with col:
            delta_html = f'<div class="{delta[1]}">{delta[0]}</div>' if delta else ""
            st.markdown(f"""
            <div class="kpi-card"><div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div>{delta_html}</div>
            """, unsafe_allow_html=True)


def render_empty_state(icon, title, subtitle, cta_label=None, cta_page=None):
    st.markdown(f'<div class="empty-state"><div class="icon">{icon}</div><h4>{title}</h4><p>{subtitle}</p></div>', unsafe_allow_html=True)
    if cta_label:
        st.write("")
        _, mid, _ = st.columns([1, 1, 1])
        with mid:
            if st.button(cta_label, use_container_width=True, type="primary"):
                st.session_state.page = cta_page
                st.rerun()


def render_duplicate_group(group, index, show_hash=False):
    latest = recommend_latest_version(group)
    match_pct = "100% IDENTICAL" if show_hash else "RELATED"
    total_size = sum(os.path.getsize(f) for f in group) / 1024
    with st.expander(f"Duplicate Group #{index:02d} — {len(group)} files — {total_size:.1f} KB total"):
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
            st.markdown(f"{icon} **{filename}**{rec_tag}", unsafe_allow_html=True)
            st.caption(f"{filepath}  ·  {size_kb:.1f} KB  ·  modified {mtime}")


# ---------------------------------------------------------------------------
# PAGES
# ---------------------------------------------------------------------------
def page_overview():
    render_page_header("Dashboard", "Monitor duplicate documents, similarity and storage usage.")

    if not st.session_state.scanned:
        render_kpi_row([
            ("Files Analysed", "—", ""), ("Exact Duplicates", "—", "SHA-256"),
            ("Near Duplicates", "—", "Similar docs"), ("Potential Savings", "—", ""),
        ])
        st.write("")
        render_empty_state("📁", "Your workspace is ready", "Select a folder to begin document analysis.",
                            "Start a Folder Analysis", "Scan Folder")
        return

    groups, all_pairs = combined_groups()
    wasted_kb = total_wasted_kb(groups)
    n_near_groups = max(len(groups) - len(st.session_state.exact_groups), 0)
    total_files = len(st.session_state.all_files)

    prev = previous_scan_for_folder(st.session_state.scan_folder)
    def delta(curr, prev_val, lower_is_better=True):
        if prev_val is None: return None
        diff = curr - prev_val
        if diff == 0: return None
        good = (diff < 0) if lower_is_better else (diff > 0)
        arrow = "↓" if diff < 0 else "↑"
        return (f"{arrow} {abs(diff):.0f} vs last scan", "kpi-delta-good" if good else "kpi-delta-bad")

    d_exact = delta(len(st.session_state.exact_groups), prev.get("exact_duplicate_groups") if prev else None)
    d_near = delta(len(st.session_state.text_pairs) + len(st.session_state.image_pairs) + len(st.session_state.get("video_pairs", [])), prev.get("near_duplicate_pairs") if prev else None)
    d_save = delta(wasted_kb, prev.get("potential_savings_kb") if prev else None)

    render_kpi_row([
        ("Files Scanned", f"{total_files:,}", "+ this scan"),
        ("Exact Duplicates", f"{len(st.session_state.exact_groups)}", "SHA-256", d_exact),
        ("Near Duplicates", f"{n_near_groups}", "Similar documents", d_near),
        ("Potential Savings", f"{wasted_kb:.1f} KB", "Estimated", d_save),
    ])

    st.markdown('<p class="section-title">Duplicate Distribution &nbsp;/&nbsp; Storage Overview</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        unique_count = max(total_files - sum(len(g) for g in groups), 0)
        exact_files = sum(len(g) for g in st.session_state.exact_groups)
        near_files = sum(len(g) for g in groups) - exact_files
        fig = go.Figure(data=[go.Pie(labels=["Unique", "Exact Duplicate", "Near Duplicate"],
                                      values=[unique_count, exact_files, max(near_files, 0)],
                                      hole=0.55, marker=dict(colors=[GREEN, RED, INDIGO]))])
        fig.update_layout(height=250, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        total_size_kb = sum(os.path.getsize(f) for f in st.session_state.all_files) / 1024
        unique_kb = max(total_size_kb - wasted_kb, 0)
        fig2 = go.Figure(data=[go.Pie(labels=["Unique storage", "Duplicate storage"],
                                       values=[unique_kb, wasted_kb], hole=0.55,
                                       marker=dict(colors=[PURPLE, AMBER]))])
        fig2.update_layout(height=250, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig2, use_container_width=True)

    if groups:
        pct_redundant = (sum(len(g) for g in groups) / total_files * 100) if total_files else 0
        st.markdown('<p class="section-title">Document Health</p>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="finding-card">{pct_redundant:.0f}% of analysed documents are part of a '
            f'duplicate or near-duplicate group ({sum(len(g) for g in groups)} of {total_files} files).</div>',
            unsafe_allow_html=True
        )

        st.markdown('<p class="section-title">Recent Findings</p>', unsafe_allow_html=True)
        for i, group in enumerate(groups[:3], start=1):
            latest = recommend_latest_version(group)
            is_exact = any(set(group) <= set(eg) for eg in st.session_state.exact_groups)
            match_label = "100% match" if is_exact else "Near-duplicate"
            names = "<br>".join(f"· {os.path.basename(f)}" for f in sorted(group))
            st.markdown(f"""
            <div class="finding-card">
                <b>Duplicate Group #{i:02d}</b> — {len(group)} documents — {match_label}<br>
                <span style="color:{MUTED}; font-size:0.85rem;">{names}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success("✓ No duplicates detected — all analysed documents appear to be unique.")


def page_scan():
    render_page_header("Scan Folder", "Analyse a local folder or a Google Drive folder for duplicate and related documents.")

    with st.container(border=True):
        st.markdown("**Start a Folder Analysis**")
        source = st.radio("Source", ["Local folder", "Google Drive folder"], horizontal=True)

        if source == "Local folder":
            st.caption("Select a folder containing your documents to identify duplicates and related document versions.")
            folder = st.text_input("Selected folder path", value=st.session_state.scan_folder)
        else:
            st.caption(
                "Paste the folder ID from its Google Drive URL "
                "(the part after /folders/ in the address bar). "
                "Files will be downloaded locally before analysis, since detection runs on local files."
            )
            drive_folder_id = st.text_input("Google Drive folder ID", value="")
            folder = os.path.join(os.getcwd(), "drive_downloads")

            if drive_folder_id and st.button("⬇ Connect and download from Drive"):
                with st.spinner("Connecting to Google Drive and downloading files..."):
                    try:
                        downloaded = sync_drive_folder_to_local(drive_folder_id, folder)
                        st.success(f"Downloaded {len(downloaded)} file(s) from Google Drive to a local folder.")
                    except Exception as e:
                        st.error(f"Could not connect to Google Drive: {e}")

        if os.path.exists(folder):
            preview_files = [os.path.join(r, f) for r, d, fs in os.walk(folder) for f in fs]
            st.caption(f"Files detected: {len(preview_files)}  ·  Supported types: DOCX, PDF, TXT, JPG, PNG, MP4")

        st.markdown("**Analysis Options**")
        c1, c2, c3, c4 = st.columns(4)
        run_exact = c1.checkbox("Exact duplicates", value=True)
        run_text = c2.checkbox("Near-duplicates", value=True)
        c3.checkbox("Content similarity", value=True, disabled=True, help="Included automatically as part of near-duplicate detection")
        c4.checkbox("Version recommendation", value=True, disabled=True, help="Always applied to any detected duplicate group")

        scan_clicked = st.button("🔍 START ANALYSIS", type="primary", use_container_width=True)

    if scan_clicked:
        if not os.path.exists(folder):
            st.error(f"Folder not found: {folder}")
        else:
            discovered = [os.path.join(r, f) for r, d, fs in os.walk(folder) for f in fs]
            status_box = st.empty()
            bar = st.progress(0, text="Starting analysis...")
            live_file = st.empty()

            exact_groups = []
            if run_exact:
                from collections import defaultdict
                hash_to_files = defaultdict(list)
                for idx, filepath in enumerate(discovered):
                    live_file.markdown(f'<div class="scan-current-file">Currently analysing: {filepath}</div>', unsafe_allow_html=True)
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


def page_documents():
    render_page_header("Document Explorer", "Browse all documents discovered during the latest scan.")
    if not st.session_state.scanned:
        render_empty_state("📄", "No documents scanned yet", "Run a scan to see your files here.", "Start a Folder Analysis", "Scan Folder")
        return

    groups, all_pairs = combined_groups()
    search = st.text_input("Search filename", "")
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    type_filter = c1.selectbox("File type", ["All", "DOCX", "PDF", "TXT", "Image", "Video", "Other"])
    status_filter = c2.selectbox("Status", ["All", "Exact Duplicate", "Near Duplicate", "Unique"])
    sort_by = c3.selectbox("Sort by", ["Name", "Size", "Modified date"])
    sort_dir = c4.selectbox("Order", ["↑", "↓"])

    grouped_files = {f for g in groups for f in g}
    exact_files = {f for g in st.session_state.exact_groups for f in g}
    rows = []
    for f in st.session_state.all_files:
        ftype = file_type_of(f)
        status = "Unique"; sim_val = None
        if f in exact_files:
            status, sim_val = "Exact Duplicate", 100.0
        elif f in grouped_files:
            status = "Near Duplicate"
            for g in groups:
                if f in g:
                    sim_val = similarity_for(all_pairs, recommend_latest_version(g), f)
                    break
        rows.append({
            "File": f"{TYPE_ICONS.get(ftype,'📄')} {os.path.basename(f)}", "Type": ftype,
            "Size (KB)": round(os.path.getsize(f)/1024, 1),
            "Modified": datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M"),
            "Status": status, "Similarity": f"{sim_val:.0f}%" if sim_val is not None else "—",
        })
    df = pd.DataFrame(rows)
    if search: df = df[df["File"].str.contains(search, case=False)]
    if type_filter != "All": df = df[df["Type"] == type_filter]
    if status_filter != "All": df = df[df["Status"] == status_filter]
    sort_map = {"Name": "File", "Size": "Size (KB)", "Modified date": "Modified"}
    df = df.sort_values(sort_map[sort_by], ascending=(sort_dir == "↑"))
    st.dataframe(df, use_container_width=True, hide_index=True)


def page_images():
    render_page_header("Images", "Image files found in the last scan, with duplicate status.")
    if not st.session_state.scanned:
        render_empty_state("🖼", "No images scanned yet", "Run a scan to see image files here.", "Start a Folder Analysis", "Scan Folder")
        return

    groups, all_pairs = combined_groups()
    image_files = [f for f in st.session_state.all_files if file_type_of(f) == "Image"]

    if not image_files:
        render_empty_state("🖼", "No image files found", "The last scanned folder contained no supported image files.")
        return

    grouped_files = {f for g in groups for f in g}
    exact_files = {f for g in st.session_state.exact_groups for f in g}

    m1, m2 = st.columns(2)
    m1.metric("Images scanned", len(image_files))
    m2.metric("Images in a duplicate group", sum(1 for f in image_files if f in grouped_files))
    st.write("")

    for f in sorted(image_files):
        status = "Unique"; sim_val = None
        if f in exact_files:
            status, sim_val = "Exact Duplicate", 100.0
        elif f in grouped_files:
            status = "Near Duplicate"
            for g in groups:
                if f in g:
                    sim_val = similarity_for(all_pairs, recommend_latest_version(g), f)
                    break

        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            with c1:
                try:
                    st.image(f, width=90)
                except Exception:
                    st.caption("(preview unavailable)")
            with c2:
                size_kb = os.path.getsize(f) / 1024
                st.markdown(f"**{os.path.basename(f)}**")
                sim_str = f" · {sim_val:.0f}% match" if sim_val is not None else ""
                st.caption(f"{size_kb:.1f} KB · {status}{sim_str}")


def page_videos():
    render_page_header("Videos", "Video files found in the last scan, with duplicate status.")
    if not st.session_state.scanned:
        render_empty_state("🎬", "No videos scanned yet", "Run a scan to see video files here.", "Start a Folder Analysis", "Scan Folder")
        return

    groups, all_pairs = combined_groups()
    video_files = [f for f in st.session_state.all_files if file_type_of(f) == "Video"]

    if not video_files:
        render_empty_state("🎬", "No video files found", "The last scanned folder contained no supported video files.")
        return

    grouped_files = {f for g in groups for f in g}
    exact_files = {f for g in st.session_state.exact_groups for f in g}

    m1, m2 = st.columns(2)
    m1.metric("Videos scanned", len(video_files))
    m2.metric("Videos in a duplicate group", sum(1 for f in video_files if f in grouped_files))
    st.write("")

    for f in sorted(video_files):
        status = "Unique"; sim_val = None
        if f in exact_files:
            status, sim_val = "Exact Duplicate", 100.0
        elif f in grouped_files:
            status = "Near Duplicate"
            for g in groups:
                if f in g:
                    sim_val = similarity_for(all_pairs, recommend_latest_version(g), f)
                    break

        with st.container(border=True):
            size_kb = os.path.getsize(f) / 1024
            st.markdown(f"🎬 **{os.path.basename(f)}**")
            sim_str = f" · {sim_val:.0f}% frame match" if sim_val is not None else ""
            st.caption(f"{size_kb:.1f} KB · {status}{sim_str}")
            st.video(f)


def page_duplicate_groups():
    render_page_header("Duplicate Groups", "Files with identical content identified by SHA-256.")
    if not st.session_state.scanned:
        render_empty_state("◈", "No scan yet", "Run a scan to see duplicate groups.", "Start a Folder Analysis", "Scan Folder")
        return

    exact_groups = st.session_state.exact_groups
    total_files = sum(len(g) for g in exact_groups)
    total_kb = total_wasted_kb(exact_groups) if exact_groups else 0

    render_kpi_row([
        ("Total Groups", f"{len(exact_groups)}", ""),
        ("Total Duplicate Files", f"{total_files}", ""),
        ("Potential Storage", f"{total_kb:.1f} KB", ""),
    ])
    st.write("")

    if not exact_groups:
        render_empty_state("✓", "No exact duplicates detected", "All analysed documents appear to be unique.")
        return

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
        render_duplicate_group(group, i, show_hash=True)


def page_similarity():
    render_page_header("Similarity Explorer", "Discover documents that are related even when their filenames are different.")
    if not st.session_state.scanned:
        render_empty_state("⇄", "No scan yet", "Run a scan to see similarity results.", "Start a Folder Analysis", "Scan Folder")
        return

    pairs = list(st.session_state.text_pairs) + list(st.session_state.image_pairs) + list(st.session_state.get("video_pairs", []))
    if not pairs:
        render_empty_state("✓", "No near-duplicates detected", "All analysed documents appear to be unique.")
        return

    groups, _ = combined_groups()
    file_to_latest = {f: recommend_latest_version(g) for g in groups for f in g}

    for file_a, file_b, sim in pairs:
        sim_pct = sim * 100
        with st.container(border=True):
            c1, c2 = st.columns(2)
            c1.markdown(f"**DOCUMENT A**  \n{os.path.basename(file_a)}")
            c2.markdown(f"**DOCUMENT B**  \n{os.path.basename(file_b)}")
            st.progress(min(sim_pct/100, 1.0), text=f"SIMILARITY — {sim_pct:.1f}%")
            with st.expander("View Comparison"):
                for f in (file_a, file_b):
                    size_kb = os.path.getsize(f)/1024
                    mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
                    st.write(f"**{os.path.basename(f)}**")
                    st.caption(f"Path: {f}  ·  Size: {size_kb:.1f} KB  ·  Modified: {mtime}  ·  Similarity: {sim_pct:.1f}%")
                latest = file_to_latest.get(file_a)
                if latest:
                    st.markdown(f"★ **Recommended Current Version:** {os.path.basename(latest)}")
                    st.caption("Recommended based on modification date and document content.")


def page_analytics():
    render_page_header("Analytics", "Storage and duplicate distribution across the last scan.")
    if not st.session_state.scanned:
        render_empty_state("◉", "No scan yet", "Run a scan to see analytics.", "Start a Folder Analysis", "Scan Folder")
        return

    groups, _ = combined_groups()
    total_size_kb = sum(os.path.getsize(f) for f in st.session_state.all_files) / 1024
    wasted_kb = total_wasted_kb(groups)

    st.markdown('<p class="section-title">Storage Overview</p>', unsafe_allow_html=True)
    st.caption(f"Total folder size: {total_size_kb/1024:.2f} MB  ·  Duplicate storage: {wasted_kb/1024:.2f} MB  ·  Potential savings: {wasted_kb/1024:.2f} MB")
    st.caption("This is an estimate based on detected duplicate files. No files are automatically deleted.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<p class="section-title">File Distribution</p>', unsafe_allow_html=True)
        ext_counts = {}
        for f in st.session_state.all_files:
            ext_counts[file_type_of(f)] = ext_counts.get(file_type_of(f), 0) + 1
        fig = go.Figure(data=[go.Bar(x=list(ext_counts.keys()), y=list(ext_counts.values()), marker_color=INDIGO)])
        fig.update_layout(height=240, margin=dict(t=10,b=10,l=10,r=10))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown('<p class="section-title">Duplicate Distribution</p>', unsafe_allow_html=True)
        exact_n = sum(len(g) for g in st.session_state.exact_groups)
        near_n = max(sum(len(g) for g in groups) - exact_n, 0)
        unique_n = max(len(st.session_state.all_files) - exact_n - near_n, 0)
        fig2 = go.Figure(data=[go.Pie(labels=["Exact","Near","Unique"], values=[exact_n, near_n, unique_n],
                                       hole=0.55, marker=dict(colors=[RED, INDIGO, GREEN]))])
        fig2.update_layout(height=240, margin=dict(t=10,b=10,l=10,r=10))
        st.plotly_chart(fig2, use_container_width=True)

    if groups:
        st.markdown('<p class="section-title">Largest Duplicate Groups</p>', unsafe_allow_html=True)
        ranked = sorted(groups, key=lambda g: sum(os.path.getsize(f) for f in g), reverse=True)[:5]
        for i, g in enumerate(ranked, start=1):
            size_kb = sum(os.path.getsize(f) for f in g) / 1024
            st.markdown(f"**#{i}** — {len(g)} files — {size_kb:.1f} KB — " + ", ".join(os.path.basename(f) for f in list(g)[:3]))

        st.markdown('<p class="section-title">Most Common Duplicate Types</p>', unsafe_allow_html=True)
        type_counts = {}
        for g in groups:
            for f in g:
                type_counts[file_type_of(f)] = type_counts.get(file_type_of(f), 0) + 1
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            st.write(f"{TYPE_ICONS.get(t,'📄')} {t} — {c} files")


def page_performance():
    render_page_header("Performance", "Hashing and text extraction speed by file size, from the last scan.")

    if not st.session_state.scanned:
        render_empty_state("⚡", "No scan yet", "Run a scan to see performance data.", "Start a Folder Analysis", "Scan Folder")
        return

    if st.button("⏱ Run performance benchmark on last scanned files", type="primary"):
        rows = []
        with st.spinner("Timing hashing and text extraction..."):
            for filepath in st.session_state.all_files:
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
    st.markdown('<p class="section-title">Average Time by Size Category</p>', unsafe_allow_html=True)

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
        fig = go.Figure(data=[go.Bar(x=summary["Size Category"], y=summary["avg_hash"], marker_color=INDIGO)])
        fig.update_layout(height=260, margin=dict(t=30, b=10, l=10, r=10), title="Average hash time (s)")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig2 = go.Figure(data=[go.Bar(x=summary["Size Category"], y=summary["avg_extract"], marker_color=PURPLE)])
        fig2.update_layout(height=260, margin=dict(t=30, b=10, l=10, r=10), title="Average text extraction time (s)")
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown('<p class="section-title">Full Results</p>', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True)


def page_history():
    render_page_header("Scan History", "Previous scans performed on this device.")
    history = load_history()
    if not history:
        render_empty_state("◷", "No previous scans", "Your completed scans will appear here.")
        return
    st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)


def page_settings():
    render_page_header("Settings", "Analysis configuration and system information.")

    st.markdown('<p class="section-title">Analysis Settings</p>', unsafe_allow_html=True)
    st.write(f"**Default similarity threshold (documents):** {SIMILARITY_THRESHOLD*100:.0f}%")
    st.write(f"**Image perceptual hash difference threshold:** {HASH_DIFFERENCE_THRESHOLD}")
    st.write("**Supported document types:** DOCX, PDF, TXT")
    st.write("**Supported image types:** JPG, PNG, BMP, GIF")
    st.write("**Supported video types:** MP4, AVI, MOV, MKV, WMV (compared via sampled-frame perceptual hashing)")
    st.write("**Version recommendation:** rule-based — modification date and content length")
    st.write("**Cloud connectivity:** Google Drive folders can be connected and downloaded locally before analysis")

    st.markdown('<p class="section-title">System Information</p>', unsafe_allow_html=True)
    st.write(f"**Python version:** {sys.version.split()[0]}")
    st.write(f"**Streamlit version:** {st.__version__}")
    st.write("**Application version:** v1.0 — FYP Prototype")

    st.markdown('<p class="section-title">Privacy</p>', unsafe_allow_html=True)
    st.markdown(
        '<div class="finding-card">Files are analysed locally on this device. Google Drive files are '
        'downloaded to this device via an authenticated, read-only connection before analysis, and '
        'nothing is uploaded to a server controlled by this application.</div>', unsafe_allow_html=True
    )


# ---------------------------------------------------------------------------
# ROUTING
# ---------------------------------------------------------------------------
render_topbar()
render_sidebar()

PAGES = {
    "Overview": page_overview, "Scan Folder": page_scan, "Documents": page_documents,
    "Images": page_images, "Videos": page_videos,
    "Duplicate Groups": page_duplicate_groups, "Similarity Explorer": page_similarity,
    "Analytics": page_analytics, "Performance": page_performance,
    "Scan History": page_history, "Settings": page_settings,
}
PAGES[st.session_state.page]()