# Functions for storing and computing equity holdings and transactions.
import logging, io, base64
from datetime import date
import polars as pl
import pandas as pd
import pyxirr
import yfinance as yf
import duckdb

try:
    from . import db_duckdb as db
except ImportError:
    import db_duckdb as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_CSV_COLUMNS = [
    "Transaction ID",
    "NSE Symbol",
    "Demat AC",
    "Transaction Date",
    "Transaction Type",
    "Units",
    "Price per Unit",
    "Expense per Unit",
]


def get_equity_prices(tickers: list[str], period: str = "7d") -> pl.DataFrame:

    if not tickers:
        return pl.DataFrame(schema={"ticker": pl.Utf8, "lt_date": pl.Datetime, "lt_price": pl.Float64, "prev_close": pl.Float64})

    # Add .NS suffix to tickers if not present
    ns_tickers = [f"{ticker}.NS" for ticker in tickers]

    pddf = pd.DataFrame(yf.Tickers(ns_tickers).history(period=period, progress=False, timeout=5))
    pddf = (
        pddf.stack(level="Ticker", future_stack=True)
        .reset_index()
        .drop(columns=["Dividends", "Stock Splits", "Open", "High", "Low", "Volume"])
    )

    df = ( pl.DataFrame(pddf)
        .select([
            pl.col("Date").alias("date"),
            # NOTE: str.strip_chars_end() strips a *set* of characters, not a literal suffix, so it
            # would mangle tickers ending in N/S/. (e.g. "TCS.NS" -> "TC"). strip_suffix() removes the
            # exact literal ".NS" we appended above.
            pl.col("Ticker").str.strip_suffix(".NS").alias("ticker"),
            pl.col("Close").alias("price"),
        ])
        .sort("date")
        .group_by("ticker").agg([
            pl.col("date").last().alias("lt_date"),
            pl.col("price").last().alias("lt_price"),
            pl.col("price").tail(2).first().alias("prev_close")
            ])
    )

    return df

def ingest_equity_transactions(file_name: str, file_content_b64: str) -> dict:
    """
    Decode a base64-encoded equity transactions CSV, insert any not-yet-seen rows into
    equity_trans (keyed by Transaction ID), and recompute residual_units for the whole table.
    """
    try:
        if "base64," in file_content_b64:
            file_content_b64 = file_content_b64.split("base64,", 1)[1]
        csv_text = base64.b64decode(file_content_b64).decode("utf-8")

        df = pl.read_csv(io.StringIO(csv_text), has_header=True)

        missing_columns = [col for col in REQUIRED_CSV_COLUMNS if col not in df.columns]
        if missing_columns:
            return {"status": "error",
                    "message": f"Missing required columns: {', '.join(missing_columns)}"}

        # Convert the "Transaction Date" column to datetime format
        df = df.with_columns(pl.col("Transaction Date").str.strptime(pl.Date, format="%Y-%m-%d"))

        # Rename Polars columns to match DuckDB table schema
        df = df.rename({
            "Transaction ID": "trans_id",
            "NSE Symbol": "symbol",
            "Demat AC": "demat_ac",
            "Transaction Date": "trans_date",
            "Transaction Type": "trans_type",
            "Units": "units",
            "Price per Unit": "price_per_unit",
            "Expense per Unit": "expense_per_unit"
        })

        df = df.select([pl.col("trans_id").cast(pl.Utf8),
                        pl.col("symbol").cast(pl.Utf8).str.to_uppercase(),
                        pl.col("demat_ac").cast(pl.Utf8),
                        pl.col("trans_date").cast(pl.Date),
                        pl.col("trans_type").cast(pl.Utf8),
                        pl.col("units").cast(pl.Utf8).str.replace_all(",", "").cast(pl.Float64).fill_null(0.0),
                        pl.col("price_per_unit").cast(pl.Utf8).str.replace_all(",", "").cast(pl.Float64).fill_null(0.0),
                        pl.col("expense_per_unit").cast(pl.Utf8).str.replace_all(",", "").cast(pl.Float64).fill_null(0.0),
                        pl.lit(file_name).alias("source_file"),
        ])

        conn = db.get_connection()
        try:
            # Perform the upsert operation using DuckDB SQL. 'df' is referenced directly in the SQL
            # string via DuckDB's replacement scan (it detects the Python variable by name).
            inserted = conn.execute(
                """
                INSERT INTO equity_trans
                BY NAME
                SELECT * FROM df
                ON CONFLICT (trans_id) DO NOTHING
                RETURNING trans_id;
                """
                ).fetchall()

            _recompute_residual_units(conn)
        finally:
            conn.close()

        return {"status": "success",
                "message": f"Equity transaction import: {df.height} rows in file, {len(inserted)} new rows added."}

    except Exception as e:
        logger.error(f"Error ingesting equity transactions: {e}")
        return {"status": "error", "message": str(e)}


def _recompute_residual_units(conn: duckdb.DuckDBPyConnection) -> None:
    """
    Recompute residual_units for every row in equity_trans, approximating FIFO consumption of buys
    by later sells within each (symbol, demat_ac) group. Mirrors the residual-units logic used for
    mutual fund transactions in compute/mf_functions.py, keyed by symbol/demat_ac instead of
    folio/isin and ordered by (trans_date, trans_id) instead of (txn_date, txn_id). Runs over the
    full table (not just newly-inserted rows) so it stays correct across incremental CSV uploads.
    """
    trans_df = conn.sql("SELECT trans_id, symbol, demat_ac, trans_date, units FROM equity_trans").pl()
    if trans_df.height == 0:
        return

    residual_df = (
        trans_df.with_columns(
            pl.col("trans_id").cast(pl.Int64, strict=False).fill_null(0).alias("_ord")
        )
        .with_columns(
            residual_units=pl.when(pl.col("units") <= 0)
            .then(pl.lit(0.0))
            .otherwise(
                pl.min_horizontal(
                    pl.max_horizontal(
                        (
                            pl.when(pl.col("units") > 0)
                            .then(pl.col("units"))
                            .otherwise(pl.lit(0.0))
                            .cum_sum()
                            .over(
                                ["symbol", "demat_ac"],
                                order_by=[pl.col("trans_date"), pl.col("_ord")],
                            )
                            + pl.when(pl.col("units") < 0)
                            .then(pl.col("units"))
                            .otherwise(pl.lit(0.0))
                            .sum()
                            .over(["symbol", "demat_ac"])
                        ),
                        pl.lit(0.0),
                    ),
                    pl.col("units"),
                )
            )
        )
        .select("trans_id", "residual_units")
    )

    conn.execute(
        """
        UPDATE equity_trans
        SET residual_units = residual_df.residual_units
        FROM residual_df
        WHERE equity_trans.trans_id = residual_df.trans_id;
        """
    )


def refresh_equity_ltp() -> dict:
    """Fetch last traded price (and previous close) for every symbol seen in equity_trans via Yahoo Finance."""
    try:
        conn = db.get_connection()
        try:
            symbols = [row[0] for row in conn.execute("SELECT DISTINCT symbol FROM equity_trans").fetchall()]
        finally:
            conn.close()

        if not symbols:
            return {"status": "success", "message": "No equity symbols to refresh."}

        prices_df = get_equity_prices(symbols)
        if prices_df.height == 0:
            return {"status": "success", "message": "No price data returned for the held symbols."}

        master_df = prices_df.select(
            pl.col("ticker").alias("symbol"),
            pl.col("ticker").alias("equity_name"),
            pl.col("lt_price").cast(pl.Float64),
            pl.col("lt_date").alias("lt_time"),
            pl.col("prev_close").cast(pl.Float64),
        )

        conn = db.get_connection()
        try:
            # equity_name is intentionally left out of the UPDATE SET so a friendlier name set later
            # (once a rename feature exists, mirroring MF folio renaming) won't be clobbered on refresh.
            conn.execute(
                """
                INSERT INTO equity_master
                BY NAME
                SELECT * FROM master_df
                ON CONFLICT (symbol) DO UPDATE SET
                    lt_price = excluded.lt_price,
                    lt_time = excluded.lt_time,
                    prev_close = excluded.prev_close;
                """
            )
        finally:
            conn.close()

        return {"status": "success", "message": f"Refreshed LTP for {master_df.height} of {len(symbols)} symbols."}

    except Exception as e:
        logger.error(f"Error refreshing equity LTP: {e}")
        return {"status": "error", "message": str(e)}


# *** Compute XIRR ***
def _safe_xirr(dates: list[date], amounts: list[float]) -> float:
    if len(dates) < 2 or len(amounts) < 2:
        return 0.0
    if not any(a < 0 for a in amounts) or not any(a > 0 for a in amounts):
        return 0.0
    try:
        result = pyxirr.xirr(dates, amounts)
        return result * 100.0 if result is not None else 0.0
    except Exception:
        return 0.0


def compute_equity_xirr() -> None:
    """Compute XIRR at symbol-demat, symbol and total equity levels, mirroring compute_xirr() for MF."""

    conn = db.get_connection()
    try:
        trans_df = conn.execute(
            "SELECT symbol, demat_ac, trans_date, price_per_unit, residual_units "
            "FROM equity_trans WHERE residual_units > 0"
        ).pl()
        master_df = conn.execute(
            "SELECT symbol, lt_price, lt_time FROM equity_master WHERE lt_price IS NOT NULL"
        ).pl()
    finally:
        conn.close()

    if trans_df.height == 0:
        conn = db.get_connection()
        try:
            conn.execute("DELETE FROM equity_xirr")
        finally:
            conn.close()
        return

    # Investment cashflows are outflows at trans_date.
    lf_investment_cf = trans_df.lazy().select(
        "symbol",
        "demat_ac",
        pl.col("trans_date"),
        (-(pl.col("price_per_unit").cast(pl.Float64) * pl.col("residual_units").cast(pl.Float64))).alias("cashflow_amount"),
    )

    # Terminal cashflow is current valuation at last-traded-price date.
    lf_terminal_cf = (
        trans_df.lazy()
        .group_by("symbol", "demat_ac")
        .agg(pl.col("residual_units").cast(pl.Float64).sum().alias("total_units"))
        .join(master_df.lazy(), on="symbol", how="inner")
        .select(
            "symbol",
            "demat_ac",
            pl.col("lt_time").cast(pl.Date).alias("trans_date"),
            (pl.col("total_units") * pl.col("lt_price").cast(pl.Float64)).alias("cashflow_amount"),
        )
    )

    lf_cashflows = pl.concat([lf_investment_cf, lf_terminal_cf], how="vertical")

    def _build_xirr_level(cashflows: pl.LazyFrame, group_cols: list[str], level_name: str) -> pl.LazyFrame:
        effective_group_cols = group_cols if group_cols else ["_eq_total_group"]
        level_cashflows = (
            cashflows.with_columns(pl.lit("equity_total").alias("_eq_total_group"))
            if not group_cols
            else cashflows
        )

        lf = (
            level_cashflows.group_by(effective_group_cols + ["trans_date"])
            .agg(pl.col("cashflow_amount").sum().alias("cashflow_amount"))
            .group_by(effective_group_cols)
            .agg(
                pl.col("trans_date").sort().alias("dates"),
                pl.col("cashflow_amount").sort_by("trans_date").alias("amounts"),
            )
            .with_columns(
                pl.struct(["dates", "amounts"])
                .map_elements(
                    lambda row: _safe_xirr(row["dates"], row["amounts"]),
                    return_dtype=pl.Float64,
                )
                .alias("xirr_pct"),
                pl.lit(level_name).alias("level"),
            )
        )

        if "symbol" not in group_cols:
            lf = lf.with_columns(pl.lit("").alias("symbol"))
        if "demat_ac" not in group_cols:
            lf = lf.with_columns(pl.lit("").alias("demat_ac"))

        return lf.select("level", "symbol", "demat_ac", "xirr_pct")

    lf_symbol_demat = _build_xirr_level(lf_cashflows, ["symbol", "demat_ac"], "symbol_demat")
    lf_symbol = _build_xirr_level(lf_cashflows, ["symbol"], "symbol")
    lf_total = _build_xirr_level(lf_cashflows, [], "equity_total")

    xirr_df = pl.concat([lf_symbol_demat, lf_symbol, lf_total], how="vertical").collect()
    xirr_df = xirr_df.with_columns(pl.lit(date.today()).alias("as_on_date"))

    conn = db.get_connection()
    try:
        conn.execute("DELETE FROM equity_xirr")
        conn.execute(
            "INSERT INTO equity_xirr SELECT level, symbol, demat_ac, xirr_pct, as_on_date FROM xirr_df"
        )
    finally:
        conn.close()


# *** Get Holding statement ***
def get_equity_holdings() -> dict:
    """
    Generate equity holdings (grouped by symbol -> demat account) from equity_trans, equity_master
    (for last traded price) and equity_xirr (for XIRR%), live - matching how get_mf_holdings() builds
    the mutual fund tree from mf_transactions/mf_nav/mf_xirr rather than a persisted holdings table.
    """
    conn = db.get_connection()
    try:
        trans_df = conn.execute(
            """
            SELECT symbol, demat_ac,
                   SUM(residual_units) AS total_units,
                   SUM(residual_units * price_per_unit) AS invested_amount
            FROM equity_trans
            GROUP BY symbol, demat_ac
            """
        ).pl()
        master_df = conn.execute(
            "SELECT symbol, COALESCE(equity_name, symbol) AS stock_name, lt_price, lt_time FROM equity_master"
        ).pl()
        xirr_df = conn.execute("SELECT level, symbol, demat_ac, xirr_pct FROM equity_xirr").pl()
    finally:
        conn.close()

    empty_result = {
        "tree_rows": [],
        "grand_totals": {"invested_amount": 0.0, "current_value": 0.0, "abs_gain_pct": 0.0, "xirr_pct": 0.0},
    }

    if trans_df.height == 0:
        return empty_result

    xirr_symbol_demat = xirr_df.filter(pl.col("level") == "symbol_demat").select("symbol", "demat_ac", "xirr_pct")
    xirr_symbol = xirr_df.filter(pl.col("level") == "symbol").select("symbol", "xirr_pct")
    xirr_total = xirr_df.filter(pl.col("level") == "equity_total").select("xirr_pct")

    holdings = (
        trans_df.with_columns(
            pl.col("total_units").cast(pl.Float64),
            pl.col("invested_amount").cast(pl.Float64),
        )
        .join(master_df, on="symbol", how="left")
        .join(xirr_symbol_demat, on=["symbol", "demat_ac"], how="left")
        .with_columns(
            pl.col("xirr_pct").fill_null(0.0),
            pl.col("lt_price").fill_null(0.0).cast(pl.Float64).alias("last_price"),
        )
        .with_columns(current_value=pl.col("total_units") * pl.col("last_price"))
        .with_columns(
            abs_gain_pct=pl.when(pl.col("invested_amount") != 0)
            .then((pl.col("current_value") / pl.col("invested_amount") - 1.0) * 100.0)
            .otherwise(0.0),
            ltp_date=pl.col("lt_time").cast(pl.Date).cast(pl.Utf8),
            stock_or_demat=pl.col("demat_ac"),
        )
    )

    # Drop zero-balance demat rows (e.g. fully sold) from the holdings report - the underlying
    # transactions and XIRR are still tracked, this only affects what's displayed. A stock where
    # every demat account nets to zero simply won't produce a group below.
    holdings = holdings.filter(pl.col("total_units").abs() > 1e-6)

    tree = (
        holdings.group_by("symbol")
        .agg(
            stock_name=pl.col("stock_name").drop_nulls().first(),
            total_units=pl.col("total_units").sum(),
            invested_amount=pl.col("invested_amount").sum(),
            current_value=pl.col("current_value").sum(),
            last_price=pl.col("last_price").drop_nulls().first(),
            ltp_date=pl.col("ltp_date").drop_nulls().first(),
            _children=pl.struct(
                [
                    "stock_or_demat",
                    "total_units",
                    "invested_amount",
                    "current_value",
                    "abs_gain_pct",
                    "xirr_pct",
                    "last_price",
                    "ltp_date",
                ]
            ),
        )
        .with_columns(
            stock_or_demat=pl.col("stock_name"),
            abs_gain_pct=pl.when(pl.col("invested_amount") != 0)
            .then((pl.col("current_value") / pl.col("invested_amount") - 1.0) * 100.0)
            .otherwise(0.0),
        )
        .join(xirr_symbol, on="symbol", how="left")
        .with_columns(pl.col("xirr_pct").fill_null(0.0))
        .select(
            [
                "stock_or_demat",
                "total_units",
                "invested_amount",
                "current_value",
                "abs_gain_pct",
                "xirr_pct",
                "last_price",
                "ltp_date",
                "_children",
            ]
        )
    )

    bottom_calc_df = tree.select(
        grand_invested_amount=pl.col("invested_amount").sum(),
        grand_current_value=pl.col("current_value").sum(),
    ).with_columns(
        grand_abs_gain_pct=pl.when(pl.col("grand_invested_amount") != 0)
        .then((pl.col("grand_current_value") / pl.col("grand_invested_amount") - 1.0) * 100.0)
        .otherwise(0.0),
        grand_xirr_pct=xirr_total.select(pl.col("xirr_pct").first().fill_null(0)).item()
        if xirr_total.height
        else 0.0,
    )

    bottom_calc = bottom_calc_df.to_dicts()[0] if bottom_calc_df.height else {
        "grand_invested_amount": 0.0,
        "grand_current_value": 0.0,
        "grand_abs_gain_pct": 0.0,
        "grand_xirr_pct": 0.0,
    }

    return {
        "tree_rows": tree.to_dicts(),
        "grand_totals": {
            "invested_amount": float(bottom_calc["grand_invested_amount"] or 0.0),
            "current_value": float(bottom_calc["grand_current_value"] or 0.0),
            "abs_gain_pct": float(bottom_calc["grand_abs_gain_pct"] or 0.0),
            "xirr_pct": float(bottom_calc["grand_xirr_pct"] or 0.0),
        },
    }


# Get Transaction details for a given stock-demat account
def get_equity_transactions(stock: str = "", demat_account: str = "") -> dict:
    try:
        conn = db.get_connection()
        try:
            payload = conn.execute(
                """
                SELECT
                    t.trans_id AS trans_id,
                    COALESCE(m.equity_name, t.symbol) AS stock_name,
                    t.demat_ac AS demat_account,
                    CAST(t.trans_date AS VARCHAR) AS txn_date,
                    t.trans_type AS type,
                    CAST(t.units AS DOUBLE) AS units,
                    CAST(t.price_per_unit AS DOUBLE) AS price,
                    CAST(t.units * t.price_per_unit AS DOUBLE) AS amount,
                    CAST(ABS(t.units) * t.expense_per_unit AS DOUBLE) AS charges,
                    CAST(
                        t.units * t.price_per_unit
                        + CASE WHEN t.units >= 0 THEN ABS(t.units) * t.expense_per_unit
                               ELSE -ABS(t.units) * t.expense_per_unit END
                    AS DOUBLE) AS net_amount,
                    'NSE' AS exchange,
                    t.trans_id AS order_id,
                    COALESCE(t.source_file, '') AS source_file
                FROM equity_trans t
                LEFT JOIN equity_master m ON m.symbol = t.symbol
                WHERE t.symbol ILIKE ? AND t.demat_ac ILIKE ?
                ORDER BY t.trans_date, t.trans_id
                """,
                [f"%{stock}%", f"%{demat_account}%"],
            ).pl().to_dicts()
        finally:
            conn.close()

        return {
            "status": "success",
            "message": f"{len(payload)} transactions found for stock pattern '{stock}' and demat account pattern '{demat_account}'.",
            "payload": payload,
        }
    except Exception as e:
        logger.error(f"Error fetching equity transaction details: {e}")
        return {"status": "error", "message": str(e), "payload": []}


def delete_equity_transaction(trans_id: str) -> dict:
    """Delete a single row from equity_trans by its primary key, then recompute residual_units
    and XIRR for the remaining rows since both depend on the full transaction stream."""
    try:
        conn = db.get_connection()
        try:
            deleted = conn.execute(
                "DELETE FROM equity_trans WHERE trans_id = ? RETURNING trans_id",
                [trans_id],
            ).fetchall()

            if not deleted:
                return {
                    "status": "error",
                    "message": "Transaction not found - it may have already been deleted.",
                    "payload": [],
                }

            _recompute_residual_units(conn)
        finally:
            conn.close()

        compute_equity_xirr()

        return {"status": "success", "message": f"Deleted transaction {trans_id}.", "payload": []}
    except Exception as e:
        logger.error(f"Error deleting equity transaction: {e}")
        return {"status": "error", "message": str(e), "payload": []}


if __name__ == "__main__":
    from pathlib import Path

    ROOT = Path(__file__).parent.parent
    with open(ROOT / "data" / "equity_transactions.csv", "r", encoding="utf-8") as f:
        file_content = f.read()

    result = ingest_equity_transactions("equity_transactions.csv", base64.b64encode(file_content.encode("utf-8")).decode("ascii"))
    print(result)

    print(refresh_equity_ltp())
    compute_equity_xirr()
    print(get_equity_holdings())
