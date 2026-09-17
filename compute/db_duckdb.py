# Shared DuckDB connection and schema management for all asset classes (Mutual Funds, Equity, NPS).
# A single place that knows the on-disk location and table shapes, so individual compute modules
# just open a connection and query. Mutual Funds used to live in a separate Delta Lake store
# (compute/db_deltalake.py, now removed) - everything is DuckDB now for consistency.

from pathlib import Path
import logging
from threading import Lock
import os
import sys
import duckdb

logger = logging.getLogger(__name__)

_SCHEMA_INIT_LOCK = Lock()
_SCHEMA_INITIALIZED = False

ROOT = Path(__file__).parent.parent


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _get_data_dir() -> Path:
    """
    Resolve a writable data directory.

    - Development: <repo>/data
    - Packaged executable: %LOCALAPPDATA%/PFIN-Dash/data
    - Optional override: PFIN_DASH_DATA_DIR env var
    """
    env_override = os.environ.get("PFIN_DASH_DATA_DIR", "").strip()
    if env_override:
        return Path(env_override)

    if _is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base_dir = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base_dir / "PFIN-Dash" / "data"

    return ROOT / "data"


DATA_DIR = _get_data_dir()
DB_PATH = DATA_DIR / "PFin.duckdb"

TABLE_DDL = {
    "mf_transactions": """
        CREATE TABLE IF NOT EXISTS mf_transactions (
            folio VARCHAR NOT NULL,
            isin VARCHAR NOT NULL,
            amfi VARCHAR,
            txn_date DATE NOT NULL,
            type VARCHAR NOT NULL,
            units DECIMAL(18,4) NOT NULL,
            nav DECIMAL(18,4),
            amount DECIMAL(18,4),
            balance DECIMAL(18,4) NOT NULL,
            dividend_rate DECIMAL(18,4),
            scheme VARCHAR,
            description VARCHAR,
            source_file VARCHAR,
            tax_type VARCHAR,
            tax_description VARCHAR,
            tax_amount DECIMAL(18,4),
            txn_id INTEGER,
            residual_units DECIMAL(38,4) DEFAULT 0,
            PRIMARY KEY (isin, folio, txn_date, type, units, balance)
        )
    """,
    "mf_nav": """
        CREATE TABLE IF NOT EXISTS mf_nav (
            amfi VARCHAR PRIMARY KEY,
            nav DECIMAL(12,4),
            nav_dt DATE,
            prev_nav DECIMAL(12,4),
            prev_nav_dt DATE,
            "1d_change" DECIMAL(18,4)
        )
    """,
    "mf_xirr": """
        CREATE TABLE IF NOT EXISTS mf_xirr (
            level VARCHAR NOT NULL,
            scheme VARCHAR NOT NULL DEFAULT '',
            folio VARCHAR NOT NULL DEFAULT '',
            xirr_pct DOUBLE NOT NULL DEFAULT 0,
            as_on_date DATE,
            PRIMARY KEY (level, scheme, folio)
        )
    """,
    "mf_folios": """
        CREATE TABLE IF NOT EXISTS mf_folios (
            folio VARCHAR PRIMARY KEY,
            folio_name VARCHAR
        )
    """,
    "equity_trans": """
        CREATE TABLE IF NOT EXISTS equity_trans (
            trans_id VARCHAR PRIMARY KEY,
            symbol VARCHAR NOT NULL,
            demat_ac VARCHAR NOT NULL,
            trans_date DATE NOT NULL,
            trans_type VARCHAR NOT NULL,
            units DECIMAL(10,4) NOT NULL DEFAULT 0,
            price_per_unit DECIMAL(10,4) NOT NULL DEFAULT 0,
            expense_per_unit DECIMAL(10,4) NOT NULL DEFAULT 0,
            residual_units DECIMAL(10,4) NOT NULL DEFAULT 0,
            source_file VARCHAR
        )
    """,
    "equity_master": """
        CREATE TABLE IF NOT EXISTS equity_master (
            symbol VARCHAR PRIMARY KEY,
            equity_name VARCHAR,
            lt_price DECIMAL(12,4),
            lt_time TIMESTAMP,
            prev_close DECIMAL(12,4)
        )
    """,
    "equity_xirr": """
        CREATE TABLE IF NOT EXISTS equity_xirr (
            level VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL DEFAULT '',
            demat_ac VARCHAR NOT NULL DEFAULT '',
            xirr_pct DOUBLE NOT NULL DEFAULT 0,
            as_on_date DATE,
            PRIMARY KEY (level, symbol, demat_ac)
        )
    """,
    "nps_trans": """
        CREATE TABLE IF NOT EXISTS nps_trans (
            pran VARCHAR NOT NULL,
            scheme VARCHAR NOT NULL,
            txn_date DATE NOT NULL,
            type VARCHAR NOT NULL,
            units DECIMAL(14,4) NOT NULL DEFAULT 0,
            nav DECIMAL(14,4) NOT NULL DEFAULT 0,
            amount DECIMAL(14,4) NOT NULL DEFAULT 0,
            balance DECIMAL(18,4) NOT NULL DEFAULT 0,
            residual_units DECIMAL(18,4) NOT NULL DEFAULT 0,
            description VARCHAR,
            source_file VARCHAR,
            PRIMARY KEY (pran, scheme, txn_date, description, units)
        )
    """,
    # Snapshot of the SchemeName -> SchemeID mapping published by npsnav.in (uploaded/refreshed
    # from an exported "daily NAV data" file - see ingest_nps_scheme_master() in nps_functions.py).
    # Used to resolve a scheme name as it appears on a Protean statement to the scheme ID needed
    # to query https://npsnav.in/api/detailed/<SchemeID>.
    "nps_scheme_master": """
        CREATE TABLE IF NOT EXISTS nps_scheme_master (
            scheme_id VARCHAR PRIMARY KEY,
            pfm_name VARCHAR,
            scheme_name VARCHAR,
            nav DECIMAL(12,4),
            nav_dt DATE
        )
    """,
    # Current NAV cache, keyed by the raw scheme name exactly as it appears in nps_trans.scheme
    # (mirrors equity_master, which is keyed by symbol to match equity_trans.symbol).
    "nps_master": """
        CREATE TABLE IF NOT EXISTS nps_master (
            scheme VARCHAR PRIMARY KEY,
            scheme_id VARCHAR,
            nav DECIMAL(12,4),
            nav_dt DATE
        )
    """,
    "nps_xirr": """
        CREATE TABLE IF NOT EXISTS nps_xirr (
            level VARCHAR NOT NULL,
            scheme VARCHAR NOT NULL DEFAULT '',
            pran VARCHAR NOT NULL DEFAULT '',
            xirr_pct DOUBLE NOT NULL DEFAULT 0,
            as_on_date DATE,
            PRIMARY KEY (level, scheme, pran)
        )
    """,
    "sgb_holdings": """
        CREATE TABLE IF NOT EXISTS sgb_holdings (
            entry_id BIGINT PRIMARY KEY,
            sgb_name VARCHAR NOT NULL,
            purchase_date DATE NOT NULL,
            units DECIMAL(18,4) NOT NULL,
            purchase_price DECIMAL(18,4) NOT NULL,
            source_note VARCHAR
        )
    """,
    "sgb_settings": """
        CREATE TABLE IF NOT EXISTS sgb_settings (
            setting_key VARCHAR PRIMARY KEY,
            setting_value DOUBLE,
            updated_at TIMESTAMP
        )
    """,
    "fd_bond_holdings": """
        CREATE TABLE IF NOT EXISTS fd_bond_holdings (
            instrument_name VARCHAR NOT NULL,
            instrument_type VARCHAR NOT NULL DEFAULT 'FD',
            purchase_date DATE NOT NULL,
            principal_amount DECIMAL(18,4) NOT NULL,
            interest_rate_pct DECIMAL(10,4) NOT NULL,
            interest_period_years DECIMAL(10,4) NOT NULL,
            payout_method VARCHAR NOT NULL,
            maturity_date DATE NOT NULL,
            source_file VARCHAR,
            PRIMARY KEY (
                instrument_name,
                purchase_date,
                principal_amount,
                interest_rate_pct,
                interest_period_years,
                payout_method,
                maturity_date
            )
        )
    """,
    "ppf_transactions": """
        CREATE TABLE IF NOT EXISTS ppf_transactions (
            account_name VARCHAR NOT NULL,
            txn_date DATE NOT NULL,
            txn_type VARCHAR NOT NULL,
            amount DECIMAL(18,4) NOT NULL,
            notes VARCHAR NOT NULL DEFAULT '',
            source_file VARCHAR,
            PRIMARY KEY (account_name, txn_date, txn_type, amount, notes)
        )
    """,
    "ppf_interest_rates": """
        CREATE TABLE IF NOT EXISTS ppf_interest_rates (
            effective_from DATE PRIMARY KEY,
            annual_rate_pct DECIMAL(8,4) NOT NULL,
            source_note VARCHAR
        )
    """,
}

EXPECTED_COLUMNS = {
    "mf_transactions": {
        "folio", "isin", "amfi", "txn_date", "type", "units", "nav", "amount",
        "balance", "dividend_rate", "scheme", "description", "source_file", "tax_type",
        "tax_description", "tax_amount", "txn_id", "residual_units",
    },
    "mf_nav": {"amfi", "nav", "nav_dt", "prev_nav", "prev_nav_dt", "1d_change"},
    "mf_xirr": {"level", "scheme", "folio", "xirr_pct", "as_on_date"},
    "mf_folios": {"folio", "folio_name"},
    "equity_trans": {
        "trans_id", "symbol", "demat_ac", "trans_date", "trans_type", "units",
        "price_per_unit", "expense_per_unit", "residual_units", "source_file",
    },
    "equity_master": {"symbol", "equity_name", "lt_price", "lt_time", "prev_close"},
    "equity_xirr": {"level", "symbol", "demat_ac", "xirr_pct", "as_on_date"},
    "nps_trans": {
        "pran", "scheme", "txn_date", "type", "units", "nav", "amount", "balance",
        "residual_units", "description", "source_file",
    },
    "nps_scheme_master": {"scheme_id", "pfm_name", "scheme_name", "nav", "nav_dt"},
    "nps_master": {"scheme", "scheme_id", "nav", "nav_dt"},
    "nps_xirr": {"level", "scheme", "pran", "xirr_pct", "as_on_date"},
    "sgb_holdings": {"entry_id", "sgb_name", "purchase_date", "units", "purchase_price", "source_note"},
    "sgb_settings": {"setting_key", "setting_value", "updated_at"},
    "fd_bond_holdings": {
        "instrument_name", "instrument_type", "purchase_date", "principal_amount",
        "interest_rate_pct", "interest_period_years", "payout_method", "maturity_date", "source_file",
    },
    "ppf_transactions": {
        "account_name", "txn_date", "txn_type", "amount", "notes", "source_file",
    },
    "ppf_interest_rates": {"effective_from", "annual_rate_pct", "source_note"},
}


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables for a fresh database using the canonical TABLE_DDL definitions."""

    for ddl in TABLE_DDL.values():
        conn.execute(ddl)


def warn_if_schema_missing_columns(conn: duckdb.DuckDBPyConnection) -> None:
    """Log a startup warning when an existing DB is missing expected columns."""

    missing_by_table: dict[str, list[str]] = {}

    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        table_exists = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main' AND table_name = ?",
            [table_name],
        ).fetchone()

        if not table_exists or int(table_exists[0]) == 0:
            missing_by_table[table_name] = sorted(expected_columns)
            continue

        existing_columns = {
            row[1] for row in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        }
        missing_columns = sorted(expected_columns - existing_columns)
        if missing_columns:
            missing_by_table[table_name] = missing_columns

    if not missing_by_table:
        return

    details = "; ".join(
        f"{table}: {', '.join(columns)}" for table, columns in sorted(missing_by_table.items())
    )
    logger.warning(
        "Manual migration required: existing DuckDB schema is missing expected columns. "
        "No automatic ALTER TABLE is performed. Missing -> %s",
        details,
    )


def get_connection() -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection. Create schema only when DB is first created."""

    global _SCHEMA_INITIALIZED

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_preexists = DB_PATH.exists()
    conn = duckdb.connect(str(DB_PATH))

    # TABLE_DDL is a first-run bootstrap only. Existing databases are not reconciled here.
    if not _SCHEMA_INITIALIZED:
        with _SCHEMA_INIT_LOCK:
            if not _SCHEMA_INITIALIZED:
                if not db_preexists:
                    ensure_schema(conn)
                else:
                    warn_if_schema_missing_columns(conn)
                _SCHEMA_INITIALIZED = True

    return conn
