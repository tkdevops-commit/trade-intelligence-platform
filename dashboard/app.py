"""Streamlit dashboard for the trade intelligence collector."""

from __future__ import annotations

import os

import pandas as pd
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
    }


def main() -> None:
    st.set_page_config(page_title="Trade Intelligence Platform", page_icon="🌐", layout="wide")
    st.title("Trade Intelligence Platform")
    st.caption("Public-source monitoring for international trade developments and merchandise flows.")

    configured_path = os.getenv("TRADE_DATABASE", DEFAULT_DATABASE)
    with st.sidebar:
        st.header("Data")
        database_path = st.text_input("SQLite database", configured_path)
        if st.button("Refresh data"):
            load_dashboard_data.clear()
            st.rerun()
        st.caption("Set `TRADE_DATABASE` to use a database outside the project folder.")

    data = load_dashboard_data(database_path)
    if not data["ready"]:
        st.info("No local trade database found yet. Collect data first, then refresh this page.")
        st.code("python3 -m scraper.scraper --source all", language="bash")
        return

    overview_tab, trade_tab, news_tab, source_tab = st.tabs(["Overview", "Trade flows", "WTO news", "Source health"])

    with overview_tab:
        overview = data["overview"]
        one, two, three, four = st.columns(4)
        one.metric("Records", overview["record_count"])
        two.metric("Sources", overview["source_count"])
        three.metric("Countries", overview["country_count"])
        four.metric("Last collection", overview["last_collected_at"] or "Not recorded")
        st.subheader("What this release covers")
        st.write("WTO news, World Bank merchandise trade indicators, and a limited UN Comtrade preview feed.")

    with trade_tab:
        countries = data["countries"]
        if not countries:
            st.info("No World Bank merchandise-trade observations have been collected yet.")
        else:
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

    with news_tab:
        query = st.text_input("Search WTO news", placeholder="e.g. tariffs, agriculture, digital trade")
        articles = TradeAnalytics(database_path).news(query)
        if not articles:
            st.info("No matching WTO news has been collected yet.")
        for article in articles:
            st.markdown(f"#### [{article['title']}]({article['url']})")
            st.caption(article["published_at"] or "Publication date unavailable")
            if article["summary"]:
                st.write(article["summary"])

    with source_tab:
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


if __name__ == "__main__":
    main()
