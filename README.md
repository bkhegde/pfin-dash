# PFin-Dash

A personal finance dashboard for tracking Mutual Funds, Equity (stocks), and NPS (National Pension System) holdings in one place — upload your own statements, refresh live prices, and see consolidated gains and XIRR. Runs entirely on your machine as a desktop app; your financial data never leaves your computer.

## Features

**Mutual Funds**
- Upload a CAMS Consolidated Account Statement (CAS) PDF (password-protected supported) — this is the single source of truth for transactions.
- Refresh NAV for all held funds via [api.mfapi.in](https://api.mfapi.in).
- Holding statement grouped by scheme → folio, with invested amount, current value, absolute gain %, and XIRR %.
- Rename folios with human-readable nicknames.
- Drill into the full transaction history for any scheme/folio, and delete individual transaction rows (residual units and XIRR recompute automatically).

**Equity (Stocks)**
- Upload a CSV of equity transactions (symbol, demat account, buy/sell, units, price).
- Refresh last traded price via Yahoo Finance.
- Holding statement grouped by stock → demat account, with gains and XIRR.
- Drill into transactions per stock/demat account, with row-level delete.

**NPS (National Pension System)**
- Upload Protean (CRA) NPS transaction statements — multiple files at once (Tier I and Tier II are tracked separately).
- Refresh NAV via [npsnav.in](https://npsnav.in).
- Holding statement grouped by scheme → PRAN, with gains and XIRR.
- Drill into the transaction history for any scheme/PRAN.

## Tech Stack

- **Backend:** Python, [DuckDB](https://duckdb.org/) (single embedded database file for all data), [Polars](https://pola.rs/) for data processing, [pyxirr](https://github.com/Anexen/pyxirr) for XIRR, [casparser](https://github.com/codereverser/casparser) for CAS PDF parsing, [httpx](https://www.python-httpx.org/) for async API calls, [yfinance](https://github.com/ranaroussi/yfinance) for stock prices.
- **Desktop shell:** [pywebview](https://pywebview.flowrl.com/) — renders the UI in a native window backed by the system webview, no browser or separate server required.
- **Frontend:** [Svelte 5](https://svelte.dev/) + [Vite](https://vitejs.dev/) + TypeScript, [Tabulator](http://tabulator.info/) for interactive/tree tables, [Luxon](https://moment.github.io/luxon/) for date formatting.
- **Bridge:** the UI calls into Python exclusively through `window.pywebview.api` (wrapped by a typed `ui/src/services/api.ts`) — there's no HTTP server or REST API involved.

## Project Structure

```
├── main.py                  # pywebview entry point - opens the desktop window
├── api.py                   # Python API surface exposed to the UI (js_api)
├── requirements.txt         # Python dependencies
│
├── compute/                 # All business logic, one module per asset class
│   ├── db_duckdb.py         #   shared DuckDB connection + schema management
│   ├── mf_functions.py      #   Mutual Fund: CAS parsing, NAV refresh, XIRR, holdings
│   ├── eq_functions.py      #   Equity: CSV ingestion, LTP refresh, XIRR, holdings
│   └── nps_functions.py     #   NPS: statement parsing, NAV refresh, XIRR, holdings
│
├── data/                    # Not committed - created on first run
│   └── PFin.duckdb          #   the one database file backing the whole app
│
└── ui/                      # Svelte frontend
    ├── src/
    │   ├── components/
    │   │   ├── mutual_fund/ #   holdings page + transactions modal + upload modal
    │   │   ├── equity/
    │   │   └── nps/
    │   └── services/
    │       ├── api.ts       #   single point of contact for every Python call
    │       └── formatters.ts
    └── dist/                # Not committed - built output main.py actually loads
```

## Getting Started

**Prerequisites:** Python 3.10+, Node.js 20+

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Build the frontend (pywebview serves this static build, not a dev server)
cd ui
npm install
npm run build
cd ..

# 3. Run the app
python main.py
```

A fresh `data/PFin.duckdb` is created automatically on first run — no separate database setup needed. Upload your own CAS PDF, equity CSV, or NPS statements from within the app to get started.

For frontend development, `npm run dev` inside `ui/` starts a Vite dev server, but note that `window.pywebview.api` is only available inside the actual pywebview window — rebuild and restart `python main.py` to see backend changes reflected.
