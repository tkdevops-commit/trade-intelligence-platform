# Trade Intelligence Platform — Project Documentation

## Purpose

The Trade Intelligence Platform is a local-first workspace for collecting, storing, analysing, and visualising public international-trade information. It combines official trade news, macroeconomic trade indicators, and selected trade-flow observations in one place.

It only uses attributed, public official sources. The platform does not bypass authentication, CAPTCHAs, robots directives, rate limits, or source terms.

## Data collection

| Source | Information | Access method |
| --- | --- | --- |
| World Trade Organization (WTO) | Latest policy and trade news | Official attributed RSS feed |
| World Bank | Merchandise imports and exports in current US dollars | World Development Indicators API |
| UN Comtrade | Small targeted annual trade-flow previews | Public preview API |

The collector identifies itself with a user agent, waits at least one second between requests, normalises the results, and records collection errors.

Run standard collection from the project folder:

`python3 -m scraper.scraper --source all`

Useful targeted commands:

`python3 -m scraper.scraper --source wto`

`python3 -m scraper.scraper --source world-bank --countries AUS,USA,CHN --years 5`

`python3 -m scraper.scraper --source comtrade-preview --reporter-code 36 --partner-code 156 --commodity-code 2701 --flow-code X --period 2025`

The final example means Australia (M49 code 36) exports coal (HS code 2701) to China (M49 code 156). `X` means exports and `M` means imports.

## Local database and Excel

All runtime data is stored locally in `data/trade_intelligence.db`, a SQLite database.

| Table | Purpose |
| --- | --- |
| `trade_records` | Normalised news, trade indicators, and trade-flow observations |
| `collection_runs` | Source collection timing, counts, and errors |
| `agent_runs` | Autonomous-agent timing, status, reports, and errors |

Every record has a stable SHA-256 fingerprint. Inserts use `INSERT OR IGNORE`, so repeated collection does not create duplicate records.

Open the database with `sqlite3 data/trade_intelligence.db`. Useful queries are `.tables`, `SELECT * FROM trade_records LIMIT 10;`, `SELECT * FROM collection_runs ORDER BY id DESC;`, and `SELECT * FROM agent_runs ORDER BY id DESC;`.

Export data for Microsoft Excel with:

`sqlite3 -header -csv "/Users/tg/trade-intelligence-platform/data/trade_intelligence.db" "SELECT * FROM trade_records;" > ~/Desktop/trade_records.csv`

Open `trade_records.csv` from the Desktop in Excel. Replace `trade_records` with `collection_runs` to export collection history.

## Dashboard and analytics

The read-only analysis layer calculates import/export series, trade balances, country snapshots, source health, and searchable WTO news without changing source records.

The Streamlit dashboard includes a collection overview, interactive trade map, country profiles, WTO policy watch, data-health view, and autonomous-agent briefing history.

Start it with:

`python3 -m pip install -r requirements.txt`

`python3 -m streamlit run dashboard/app.py`

It uses `data/trade_intelligence.db` by default. Set `TRADE_DATABASE` to use another SQLite file.

## Autonomous trade-intelligence agent

The autonomous local agent coordinates collection, monitoring, analysis, and reporting in one auditable workflow. Each run:

1. Collects data from the approved WTO and World Bank sources.
2. Optionally requests a small UN Comtrade preview.
3. Reviews WTO updates for policy-risk terms: tariffs, sanctions, export controls, restrictions, subsidies, anti-dumping, and disputes.
4. Compares the latest and prior annual import/export values for the configured country watchlist, flagging changes above the selected threshold.
5. Writes a dated JSON briefing under `reports/`.
6. Stores a full run record in `agent_runs`.

Run it once with `./scripts/run_agent.sh`.

Run it daily while the Terminal remains open with `./scripts/run_agent.sh --watch --interval-hours 24`.

The configuration template is `config/agent.example.json`. Copy it to `config/agent.json` to customise countries, years of data, alert threshold, report location, or the optional Comtrade preview. Run a custom configuration with `./scripts/run_agent.sh --config config/agent.json`.

The default watchlist is Australia, the United States, China, Japan, Germany, India, Indonesia, South Korea, the United Kingdom, Canada, Mexico, and Brazil. The default alert threshold is 15 percent.

### Safeguards

The agent autonomously performs its local workflow, but it does not send messages, publish content, execute trades, submit forms, or add new data sources by itself. All alerts are for human review.

The initial agent uses transparent rule-based detection, not a paid or cloud-hosted language model. It therefore requires no API key and sends no database data to a third party. A future language-model layer can summarise the structured findings after a provider, privacy approach, and approval process are selected.

## Project structure

- `ai/analyzer.py` — Read-only dashboard analytics.
- `ai/agent.py` — Autonomous collection, monitoring, analysis, and briefing workflow.
- `config/agent.example.json` — Agent watchlist and threshold template.
- `dashboard/app.py` — Streamlit dashboard.
- `scraper/scraper.py` — Official-source collector and SQLite persistence.
- `scripts/run_agent.sh` — Runs the agent from any Terminal folder.
- `tests/test_scraper.py` — Collector, analytics, and agent tests.
- `data/` — Local database; not version controlled.
- `reports/` — Runtime briefings; not version controlled.

## Validation and current status

Six automated tests pass. They cover deduplication, WTO normalisation, World Bank collection, UN Comtrade filter handling, trade-balance calculation, and material-change alert detection.

The initial agent run created an audit record and local briefing. In the restricted development environment, fresh requests to external source domains could not resolve, and the resulting collection failures were recorded transparently in the report without corrupting existing data.

## Recommended next steps

1. Configure macOS `launchd` or another managed scheduler for daily runs without an open Terminal.
2. Add approved notification channels for reviewed high-priority alerts.
3. Add licensed UN Comtrade access for deeper product and partner analysis.
4. Add approved tariff, sanctions, shipping, and supply-chain sources.
5. Add an optional local or approved hosted language model for citations-first summaries.
