"""Streamlit dashboard for the trade intelligence collector."""

from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st

from ai.analyzer import TradeAnalytics

DEFAULT_DATABASE = "data/trade_intelligence.db"


@st.cache_data(ttl=60, show_spinner=False)
def load_dashboard_data(database_path: str) -> dict:
    analytics = TradeAnalytics(database_path)
    return {
        "ready": analytics.is_ready(),
        "overview": analytics.overview(),
        "health": analytics.source_health(),
        "countries": analytics.countries(),
        "world_snapshot": analytics.world_trade_snapshot(),
    }


def main() -> None:
    st.set_page_config(page_title="Atlas | Trade Intelligence", page_icon="◉", layout="wide", initial_sidebar_state="collapsed")
    apply_theme()
    st.markdown("""
        <section class="hero">
          <p class="eyebrow">GLOBAL TRADE INTELLIGENCE</p>
          <h1>See the forces moving trade.</h1>
          <p class="hero-copy">Explore public trade data, country flows, and policy developments in one focused workspace.</p>
        </section>
    """, unsafe_allow_html=True)

    configured_path = os.getenv("TRADE_DATABASE", DEFAULT_DATABASE)
    with st.sidebar:
        st.markdown("### Data controls")
        database_path = st.text_input("SQLite database", configured_path, label_visibility="collapsed")
        if st.button("Refresh data"):
            load_dashboard_data.clear()
            st.rerun()
        st.caption("Set `TRADE_DATABASE` to use another SQLite file.")

    data = load_dashboard_data(database_path)
    if not data["ready"]:
        st.markdown("## Your intelligence workspace is ready")
        st.info("No local trade data has been collected yet. Start the collector, then refresh this page.")
        st.code("python3 -m scraper.scraper --source all", language="bash")
        return

    page = st.radio("Navigation", ["Overview", "World map", "Country explorer", "Policy watch", "Data health"], horizontal=True, label_visibility="collapsed", key="selected_page")

    if page == "Overview":
        overview = data["overview"]
        st.markdown("<p class='section-kicker'>AT A GLANCE</p><h2>Trade, made legible.</h2>", unsafe_allow_html=True)
        one, two, three, four = st.columns(4, gap="medium")
        with one:
            metric_card("Records", f"{overview['record_count']:,}", "Collected observations")
        with two:
            metric_card("Sources", str(overview["source_count"]), "Official public sources")
        with three:
            metric_card("Countries", str(overview["country_count"]), "With trade observations")
        with four:
            metric_card("Last refresh", format_timestamp(overview["last_collected_at"]), "UTC collection time")
        left, right = st.columns((1.2, 0.8), gap="large")
        with left:
            st.markdown("<p class='section-kicker'>START HERE</p><h2>Explore the world map.</h2><p class='body-copy'>Compare measured merchandise imports, exports, and trade balances. Select a country to open its profile.</p>", unsafe_allow_html=True)
            st.button("Open world map", type="primary", use_container_width=True, on_click=go_to_map)
        with right:
            st.markdown("<div class='coverage-card'><p class='section-kicker'>CURRENT COVERAGE</p><p>WTO news<br>World Bank merchandise flows<br>UN Comtrade preview</p></div>", unsafe_allow_html=True)

    elif page == "World map":
        render_world_map(database_path, data["world_snapshot"])

    elif page == "Country explorer":
        countries = data["countries"]
        if not countries:
            st.info("No World Bank merchandise-trade observations have been collected yet.")
        else:
            st.markdown("<p class='section-kicker'>COUNTRY EXPLORER</p><h2>Compare a country over time.</h2>", unsafe_allow_html=True)
            labels = {f"{country['name']} ({country['code']})": country["code"] for country in countries}
            selected_label = st.selectbox("Country", list(labels))
            series = TradeAnalytics(database_path).trade_series(labels[selected_label])
            if not series:
                st.info("No trade-series data is available for this country.")
            else:
                frame = pd.DataFrame(series).set_index("year")
                st.line_chart(frame[["exports", "imports"]], y_label="Current USD")
                latest = frame.iloc[-1]
                left, middle, right = st.columns(3)
                left.metric("Latest exports", format_currency(latest["exports"]))
                middle.metric("Latest imports", format_currency(latest["imports"]))
                right.metric("Latest trade balance", format_currency(latest["trade_balance"]))
                with st.expander("View underlying observations"):
                    st.dataframe(frame, use_container_width=True)

    elif page == "Policy watch":
        st.markdown("<p class='section-kicker'>POLICY WATCH</p><h2>Latest WTO developments.</h2>", unsafe_allow_html=True)
        query = st.text_input("Search WTO news", placeholder="e.g. tariffs, agriculture, digital trade")
        articles = TradeAnalytics(database_path).news(query)
        if not articles:
            st.info("No matching WTO news has been collected yet.")
        for article in articles:
            with st.container(border=True):
                st.markdown(f"#### [{article['title']}]({article['url']})")
                st.caption(article["published_at"] or "Publication date unavailable")
                if article["summary"]:
                    st.write(article["summary"])

    elif page == "Data health":
        st.markdown("<p class='section-kicker'>DATA HEALTH</p><h2>Collection status.</h2>", unsafe_allow_html=True)
        health = data["health"]
        if health:
            st.dataframe(pd.DataFrame(health), use_container_width=True, hide_index=True)
        else:
            st.info("Collection-run history will appear after the collector is run.")


def format_currency(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "Unavailable"
    prefix = "-" if value < 0 else ""
    magnitude = abs(value)
    if magnitude >= 1_000_000_000_000:
        return f"{prefix}${magnitude / 1_000_000_000_000:.2f}T"
    if magnitude >= 1_000_000_000:
        return f"{prefix}${magnitude / 1_000_000_000:.2f}B"
    if magnitude >= 1_000_000:
        return f"{prefix}${magnitude / 1_000_000:.2f}M"
    return f"{prefix}${magnitude:,.0f}"


def format_timestamp(value: str | None) -> str:
    if not value:
        return "Not recorded"
    return value.replace("T", " ").replace("+00:00", " UTC")


def metric_card(label: str, value: str, detail: str) -> None:
    st.markdown(f"<div class='metric-card'><p>{label}</p><strong>{value}</strong><span>{detail}</span></div>", unsafe_allow_html=True)


def go_to_map() -> None:
    st.session_state["selected_page"] = "World map"


def apply_theme() -> None:
    st.markdown("""
    <style>
      :root { --ink: #132018; --muted: #68746b; --line: #dce4dc; --paper: #f7f8f5; --accent: #166534; --deep: #0d2818; }
      .stApp { background: var(--paper); color: var(--ink); }
      [data-testid="stHeader"] { background: rgba(247, 248, 245, .92); }
      .block-container { max-width: 1320px; padding-top: 2.4rem; padding-bottom: 4rem; }
      .hero { background: radial-gradient(circle at 88% 20%, #2a764d 0, #123d27 34%, #0d2818 68%); border-radius: 22px; padding: 3.5rem 4rem; color: #fff; margin-bottom: 1.8rem; box-shadow: 0 18px 45px rgba(13, 40, 24, .18); }
      .hero h1 { font-size: clamp(2.2rem, 5vw, 4.4rem); letter-spacing: -.06em; line-height: .98; margin: .4rem 0 .9rem; color: #fff; }
      .hero-copy { max-width: 600px; font-size: 1.1rem; color: #d9eadf; line-height: 1.55; margin: 0; }
      .eyebrow, .section-kicker { color: #4e7d60; font-size: .72rem; font-weight: 750; letter-spacing: .14em; margin-bottom: .4rem; }
      .hero .eyebrow { color: #b8e0c4; }
      h2 { color: var(--ink); letter-spacing: -.035em; }
      .metric-card, .coverage-card { height: 100%; min-height: 142px; background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 1.3rem; }
      .metric-card p, .metric-card span { color: var(--muted); margin: 0; font-size: .83rem; }
      .metric-card strong { display: block; color: var(--ink); font-size: 1.9rem; letter-spacing: -.04em; line-height: 1.25; margin: .35rem 0; overflow-wrap: anywhere; }
      .coverage-card p:last-child { color: var(--ink); line-height: 1.8; margin-bottom: 0; }
      .body-copy { color: var(--muted); font-size: 1.02rem; line-height: 1.65; }
      div[data-testid="stRadio"] > div { gap: .25rem; background: #e9eee9; border-radius: 12px; padding: .3rem; width: fit-content; }
      div[data-testid="stRadio"] label { background: transparent; border-radius: 9px; padding: .35rem .65rem; }
      div[data-testid="stRadio"] label:has(input:checked) { background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.09); }
      .stButton > button { border-radius: 10px; font-weight: 650; }
      @media (max-width: 700px) { .hero { padding: 2.2rem 1.6rem; } .block-container { padding-top: 1rem; } }
    </style>
    """, unsafe_allow_html=True)


def render_world_map(database_path: str, snapshot: list[dict]) -> None:
    st.subheader("World trade map")
    st.caption("Click a coloured country to open its trade profile. Countries remain uncoloured until their official data is collected.")
    if not snapshot:
        st.info("No country trade observations are available yet. Run the World Bank collector, then refresh this page.")
        return

    frame = pd.DataFrame(snapshot)
    colour_metric = st.radio("Colour countries by", ("Trade balance", "Trade volume"), horizontal=True)
    colour_column = "trade_balance" if colour_metric == "Trade balance" else "trade_volume"
    colour_scale = "RdYlGn" if colour_column == "trade_balance" else "Blues"
    figure = px.choropleth(
        frame,
        locations="country_name",
        locationmode="country names",
        color=colour_column,
        hover_name="country_name",
        hover_data={"country": False, "year": True, "exports": ":,.0f", "imports": ":,.0f", "trade_balance": ":,.0f", "trade_volume": False},
        color_continuous_scale=colour_scale,
        projection="natural earth",
        labels={"trade_balance": "Trade balance (USD)", "trade_volume": "Trade volume (USD)"},
        custom_data=["country"],
    )
    figure.update_geos(showcoastlines=True, coastlinecolor="#A0A0A0", showland=True, landcolor="#F3F4F6", showocean=True, oceancolor="#E8F4FC")
    figure.update_layout(height=620, margin={"l": 0, "r": 0, "t": 10, "b": 0}, coloraxis_colorbar={"title": "USD"})
    selection = st.plotly_chart(figure, use_container_width=True, on_select="rerun", selection_mode="points")
    selected_points = selection.get("selection", {}).get("points", []) if isinstance(selection, dict) else []
    if not selected_points:
        return
    selected_code = selected_points[0].get("customdata", [None])[0]
    selected = next((country for country in snapshot if country["country"] == selected_code), None)
    if not selected:
        return
    st.subheader(f"{selected['country_name']} trade profile")
    one, two, three = st.columns(3)
    one.metric(f"Exports ({selected['year']})", format_currency(selected["exports"]))
    two.metric(f"Imports ({selected['year']})", format_currency(selected["imports"]))
    three.metric("Trade balance", format_currency(selected["trade_balance"]))
    series = TradeAnalytics(database_path).trade_series(selected_code)
    if series:
        chart = pd.DataFrame(series).set_index("year")
        st.line_chart(chart[["exports", "imports"]], y_label="Current USD")


if __name__ == "__main__":
    main()
