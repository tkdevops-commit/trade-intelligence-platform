Trade Intelligence Platform

Overview

The Trade Intelligence Platform is an open-source project exploring how artificial intelligence, data analytics, and automation can be used to understand global trade systems.

The platform aims to collect, process, analyse, and visualise information relating to international trade, including tariffs, imports, exports, supply chains, and economic policy changes.

The goal is to transform large amounts of public information into structured insights that help users understand complex global economic relationships.

Objectives

Project Aim: Global Trade Intelligence Platform

Current Capabilities

* Monitor global trade developments and economic trends.
* Track tariffs, trade policies, sanctions, and regulatory changes.
* Analyse import and export relationships between countries.
* Map global trade networks, supply chains, and resource dependencies.
* Identify emerging trade patterns and economic risks.
* Use AI to collect, classify, and analyse large volumes of trade-related information.
* Create interactive tools for exploring global trade flows and relationships.

⸻

Predictive Analytics, Economic Forecasting & Strategic Risk Assessment

* Analyse resource import patterns to identify emerging industrial priorities (futures & critical minerals; Who, when, where and why).
* Forecast potential economic development pathways and investment opportunities.
* Identify emerging markets, strategic industries, and future growth regions.
* Assess national security risks linked to critical resources and supply chain dependencies.
* Detect vulnerabilities in global supply chains and strategic trade relationships.
* Model potential impacts of tariffs, trade disruptions, and geopolitical events.
* Generate AI-driven intelligence reports, risk assessments, and strategic insights.

⸻

System Architecture

Data Sources
     |
     ↓
Web Scrapers / APIs
     |
     ↓
Data Processing
     |
     ↓
Database
     |
     ↓
AI Analysis
     |
     ↓
Interactive Dashboard

Features (Planned)

Data Collection

* Automated collection of trade-related information.
* Web scraping of public sources.
* Integration with economic and trade datasets.

### First collector

The initial collector is ready to ingest publicly available, official sources into
SQLite. It uses the WTO's attributed news RSS feed, the World Bank Indicators API,
and the limited UN Comtrade preview API. It deliberately does not bypass logins,
CAPTCHAs, robots directives, rate limits, or source terms.

Run it from the repository root:

```bash
python -m scraper.scraper --source all
```

Data is stored in `data/trade_intelligence.db`. Re-running the command is safe:
records are deduplicated by a stable fingerprint. Useful targeted runs include:

```bash
python -m scraper.scraper --source wto
python -m scraper.scraper --source world-bank --countries AUS,USA,CHN --years 5
python -m scraper.scraper --source world-bank --countries all --years 3
python -m scraper.scraper --source comtrade-preview --reporter-code 36 --period 2025
```

UN Comtrade preview data is intentionally small and rate-limited. For regular or
large-scale Comtrade extraction, add a subscription-key-backed adapter after
obtaining the appropriate API access.

### Dashboard

After collecting data, launch the local dashboard:

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run dashboard/app.py
```

It provides a collection overview, a clickable world trade map, country import/export
trends and trade balance, searchable WTO news, and collection-source health. By default it reads
`data/trade_intelligence.db`; set `TRADE_DATABASE` to point to another SQLite file.

On macOS, `Trade Intelligence Dashboard.app` on your Desktop starts the dashboard
quietly and opens it in your browser. Its local server remains available until you
restart your computer or stop the Streamlit process.

Data Processing

* Data cleaning and validation.
* Structured storage of trade events.
* Historical tracking of changes.

AI Analysis

AI capabilities will support:

* Extracting key information from documents.
* Identifying countries, products, and organisations.
* Summarising trade developments.
* Detecting patterns and relationships.
* Supporting risk and scenario analysis.

Dashboard

Future dashboard features include:

* Interactive global trade map.
* Country trade profiles.
* Import and export analysis.
* Tariff monitoring.
* Supply chain relationship mapping.

Technology Stack

Development

* Python
* Visual Studio Code
* Git/GitHub

Data Collection

* BeautifulSoup
* Scrapy
* Playwright

Data Analysis

* Pandas
* NetworkX

Database

* SQLite (initial development)
* PostgreSQL (future scaling)

AI

* Open-source local AI models
* AI-assisted data analysis workflows

Visualisation

* Streamlit
* Interactive mapping tools

Development Roadmap

Phase 1 — Foundation

* Set up project structure.
* Build initial data collectors.
* Store trade information.

Phase 2 — Intelligence Layer

* Add AI-powered extraction.
* Classify trade events.
* Generate analytical summaries.

Phase 3 — Visualisation

* Build dashboards.
* Create interactive trade maps.
* Display relationships between countries and industries.

Phase 4 — Modelling

* Explore the impacts of tariff changes.
* Simulate potential trade disruptions.
* Analyse second-order economic effects.

Vision

The long-term vision is to create a global trade intelligence system that helps users understand how decisions in one part of the world can influence markets, industries, and supply chains elsewhere.

This project combines international business, artificial intelligence, data engineering, and systems thinking to explore the future of economic analysis.
