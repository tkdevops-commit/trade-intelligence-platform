"""Internal collection workspace for the trade intelligence platform."""

from __future__ import annotations

import json
import os
from io import BytesIO
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from scraper.scraper import TradeDatabase, TradeRecord
from scraper.web import CollectionError, collect_page

DEFAULT_DATABASE = "data/trade_intelligence.db"


def main() -> None:
    st.set_page_config(page_title="Atlas Internal", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
    apply_theme()
    database_path = os.getenv("TRADE_DATABASE", DEFAULT_DATABASE)
    st.sidebar.markdown("<p class='brand'>ATLAS / INTERNAL</p>", unsafe_allow_html=True)
    st.sidebar.caption("Research collection workspace")
    database_path = st.sidebar.text_input("Collection database", database_path)
    if st.sidebar.button("Refresh workspace", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.sidebar.divider()
    st.sidebar.caption("URL intake fetches public HTML pages only. It does not log in, run scripts, bypass site controls, or access private networks.")

    stats, recent = load_workspace(database_path)
    export = create_excel_export(load_export_records(database_path))
    st.sidebar.download_button(
        "Download Excel export",
        data=export,
        file_name=f"atlas-collection-{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.markdown("<p class='eyebrow'>INTERNAL RESEARCH OPERATIONS</p><h1>Collect once. Build on it.</h1><p class='subhead'>Bring public web pages into a structured local library, then tag, review, and extend the intelligence workflow from one place.</p>", unsafe_allow_html=True)
    one, two, three = st.columns(3)
    metric(one, "Library items", f"{stats['items']:,}", "All collected records")
    metric(two, "URL captures", f"{stats['url_captures'] or 0:,}", "Public web pages")
    metric(three, "Last collection", format_time(stats["last_collected"]), "Local workspace")

    page = st.radio("Workspace", ["Collect URL", "Library", "Trade sources"], horizontal=True, label_visibility="collapsed")
    if page == "Collect URL":
        render_collect(database_path)
    elif page == "Library":
        render_library(recent)
    else:
        render_trade_sources(recent)


@st.cache_data(ttl=30, show_spinner=False)
def load_workspace(database_path: str) -> tuple[dict, list[dict]]:
    database = TradeDatabase(database_path)
    try:
        rows = database.connection.execute("""SELECT id, source, record_type, title, url, summary, metadata_json, collected_at FROM trade_records ORDER BY collected_at DESC, id DESC LIMIT 200""").fetchall()
        stats = database.connection.execute("""SELECT COUNT(*) AS items, SUM(CASE WHEN source = 'web_intake' THEN 1 ELSE 0 END) AS url_captures, MAX(collected_at) AS last_collected FROM trade_records""").fetchone()
        return dict(stats), [dict(row) for row in rows]
    finally:
        database.close()


@st.cache_data(ttl=30, show_spinner=False)
def load_export_records(database_path: str) -> list[dict]:
    """Load the complete local record set for export, not just the UI preview."""
    database = TradeDatabase(database_path)
    try:
        rows = database.connection.execute("""SELECT source, record_type, title, url, summary, metadata_json, collected_at FROM trade_records ORDER BY collected_at DESC, id DESC""").fetchall()
        return [dict(row) for row in rows]
    finally:
        database.close()


def render_collect(database_path: str) -> None:
    st.markdown("<div class='section-header'><p class='eyebrow'>NEW CAPTURE</p><h2>Collect a public web page</h2><p>Paste one page URL. Atlas extracts the title, description, readable text, and your operational notes into the local library.</p></div>", unsafe_allow_html=True)
    with st.form("url_intake", clear_on_submit=True):
        url = st.text_input("Page URL", placeholder="https://example.com/research-report")
        left, right = st.columns(2)
        label = left.text_input("Internal label", placeholder="e.g. competitor update")
        tags = right.text_input("Tags", placeholder="e.g. policy, Australia, aluminium")
        notes = st.text_area("Collection notes", placeholder="Why does this matter? What should be checked next?", height=100)
        submitted = st.form_submit_button("Collect page", type="primary")
    if not submitted:
        return
    if not url.strip():
        st.error("Enter a URL to collect.")
        return
    try:
        with st.spinner("Fetching and extracting the page…"):
            page = collect_page(url)
            record = TradeRecord(source="web_intake", record_type="web_page", title=label.strip() or str(page["title"]), url=str(page["url"]), summary=str(page["description"]) or str(page["text"])[:800], metadata={"captured_title": page["title"], "tags": [tag.strip() for tag in tags.split(",") if tag.strip()], "notes": notes.strip(), "text": page["text"], "document_bytes": page["bytes"]})
            database = TradeDatabase(database_path)
            try:
                _, inserted = database.insert_records([record])
            finally:
                database.close()
        st.cache_data.clear()
        st.success(f"Collected {page['title']} into the library." if inserted else "That page is already in the library. The existing capture was kept.")
        with st.expander("Review extracted content", expanded=True):
            st.caption(f"{page['url']} · {page['bytes']:,} bytes")
            if page["description"]:
                st.write(page["description"])
            st.text_area("Readable text", str(page["text"]), height=300, disabled=True, label_visibility="collapsed")
    except CollectionError as error:
        st.error(str(error))


def render_library(recent: list[dict]) -> None:
    st.markdown("<div class='section-header'><p class='eyebrow'>COLLECTION LIBRARY</p><h2>Review what has been captured</h2></div>", unsafe_allow_html=True)
    captures = [row for row in recent if row["source"] == "web_intake"]
    if not captures:
        st.info("No web pages have been captured yet. Start from Collect URL.")
        return
    query = st.text_input("Filter library", placeholder="Search title, URL, or notes")
    for item in captures:
        metadata = decode_metadata(item["metadata_json"])
        haystack = " ".join([item["title"], item["url"] or "", item["summary"] or "", metadata.get("notes", ""), " ".join(metadata.get("tags", []))]).lower()
        if query and query.lower() not in haystack:
            continue
        with st.container(border=True):
            st.markdown(f"#### {item['title']}")
            st.caption(f"Captured {format_time(item['collected_at'])}")
            if item["url"]:
                st.link_button("Open source site ↗", item["url"])
            if metadata.get("tags"):
                st.markdown(" ".join(f"`{tag}`" for tag in metadata["tags"]))
            if metadata.get("notes"):
                st.write(metadata["notes"])
            if item["summary"]:
                st.caption(item["summary"][:500])
            with st.expander("Extracted text"):
                st.write(metadata.get("text", "No text was saved for this capture."))


def render_trade_sources(recent: list[dict]) -> None:
    st.markdown("<div class='section-header'><p class='eyebrow'>CONNECTED COLLECTORS</p><h2>Approved trade-source data</h2><p>The existing WTO, World Bank, and UN Comtrade collectors remain available for structured trade data.</p></div>", unsafe_allow_html=True)
    non_web = [row for row in recent if row["source"] != "web_intake"]
    if non_web:
        st.dataframe(pd.DataFrame(non_web)[["source", "record_type", "title", "url", "collected_at"]], use_container_width=True, hide_index=True)
    else:
        st.info("No structured trade data has been collected yet.")
    st.code("python3 -m scraper.scraper --source all", language="bash")


def create_excel_export(records: list[dict]) -> bytes:
    """Create a review-ready workbook without exporting the raw page-text blob."""
    library_rows: list[dict] = []
    trade_rows: list[dict] = []
    for record in records:
        metadata = decode_metadata(record["metadata_json"])
        row = {
            "Title": record["title"], "Source URL": record["url"], "Summary": record["summary"],
            "Source": record["source"], "Record type": record["record_type"],
            "Collected at": record["collected_at"],
        }
        if record["source"] == "web_intake":
            library_rows.append({**row, "Tags": ", ".join(metadata.get("tags", [])), "Internal notes": metadata.get("notes", "")})
        else:
            trade_rows.append(row)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(library_rows or [{"Message": "No URL captures yet."}]).to_excel(writer, sheet_name="Collection library", index=False)
        pd.DataFrame(trade_rows or [{"Message": "No structured trade records yet."}]).to_excel(writer, sheet_name="Trade records", index=False)
    return output.getvalue()


def decode_metadata(value: str) -> dict:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


def format_time(value: str | None) -> str:
    if not value:
        return "Not yet"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    except ValueError:
        return value


def metric(column, label: str, value: str, detail: str) -> None:
    with column:
        st.markdown(f"<div class='metric'><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>", unsafe_allow_html=True)


def apply_theme() -> None:
    st.markdown("""<style>
      :root { --ink:#18201d; --muted:#69736e; --line:#dfe5e1; --paper:#f4f6f4; --accent:#0d6b45; } .stApp { background:var(--paper); color:var(--ink); } [data-testid='stSidebar'] { background:#18251f; } [data-testid='stSidebar'] * { color:#edf5ef; }
      .block-container { max-width:1240px; padding-top:3.2rem; padding-bottom:4rem; } .brand { font-size:.75rem; font-weight:800; letter-spacing:.15em; color:#9ee0b8 !important; margin-bottom:.1rem; } h1 { font-size:clamp(2.4rem,5vw,4.6rem); letter-spacing:-.065em; line-height:.96; margin:.25rem 0 .8rem; } h2 { letter-spacing:-.04em; margin:0 0 .35rem; }
      .eyebrow { color:var(--accent); font-size:.72rem; font-weight:800; letter-spacing:.13em; margin:0 0 .5rem; } .subhead,.section-header p:last-child { color:var(--muted); max-width:680px; line-height:1.6; font-size:1.02rem; } .metric { background:#fff; border:1px solid var(--line); border-radius:14px; padding:1.15rem 1.25rem; min-height:130px; } .metric span,.metric small { display:block; color:var(--muted); font-size:.8rem; } .metric strong { display:block; font-size:1.8rem; letter-spacing:-.05em; margin:.4rem 0; }
      .section-header { margin:3rem 0 1.3rem; } div[data-testid='stRadio'] > div { gap:.35rem; background:#e7ece8; padding:.3rem; border-radius:12px; } div[data-testid='stRadio'] label { padding:.3rem .7rem; border-radius:8px; } div[data-testid='stRadio'] label:has(input:checked) { background:#fff; box-shadow:0 1px 3px #0001; } .stButton button { border-radius:9px; font-weight:700; } [data-testid='stSidebar'] .stButton button { color:#17251e; } @media(max-width:700px) { .block-container { padding-top:1.5rem; } }
    </style>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
