"""Collection of functions to process mutual fund CAS PDF files, extract transactions, compute XIRR and holdings, using Polars and DuckDB."""

import logging
import polars as pl
import casparser
from datetime import date, timedelta
import asyncio
import httpx
import pyxirr
import base64, io
import duckdb

try:
    from . import db_duckdb as db
except ImportError:
    import db_duckdb as db

logger = logging.getLogger(__name__)


# *** Load Transactions data from PDF files ***
def process_cas_pdf(file_name: str, pdf_password: str, file_content: str) -> dict:
    """
    Receives raw file data and metadata directly from the front end Javascript.
    Flatten the CAS JSON structure to transaction-level rows.
    """
    try:
        # 1. Strip the HTML5 data header if present
        if "base64," in file_content:
            file_content = file_content.split("base64,", 1)[1]

        # 2. Decode the Base64 text string into raw binary bytes
        pdf_bytes = base64.b64decode(file_content)

        # 3. Wrap the bytes into an in-memory file-like object
        pdf_memory_file = io.BytesIO(pdf_bytes)

        # 4. Pass the memory buffer directly to casparser
        json_str = casparser.read_cas_pdf(
            pdf_memory_file, password=pdf_password, output="json"
        )

        output_df = _read_json_str(str(json_str), file_name)
        # remove rows with txn_date, type, units as null, since these are not valid transactions
        output_df = output_df.filter(
            pl.col("txn_date").is_not_null()
        ).collect()

        logger.info(f"{output_df.height} transactions found.")

        if output_df.height != 0:

            # Save the transactions to database
            result = _save_transactions_data(output_df)

        else:
            result = {
                "status": "success",
                "message": "No transactions found in the PDF.",
            }

        return result

    except Exception as e:
        logger.error(f"Error processing CAS PDF: {e}")
        return {"status": "error", "message": str(e)}


def _read_json_str(json_str: str, source_file_name: str) -> pl.LazyFrame:
    """Flatten one CAS JSON file to transaction-level rows using lazy Polars expressions."""

    flattened_lf = (
        pl.read_json(io.StringIO(json_str))
        .lazy()
        .with_columns(pl.lit(source_file_name).alias("source_file"))
        .explode("folios")
        .with_columns(
            folio=pl.col("folios").struct.field("folio").cast(pl.Utf8),
            schemes=pl.col("folios").struct.field("schemes"),
        )
        .drop("folios")
        .explode("schemes")
        .with_columns(
            scheme=pl.col("schemes").struct.field("scheme").cast(pl.Utf8),
            isin=pl.col("schemes").struct.field("isin").cast(pl.Utf8),
            amfi=pl.col("schemes").struct.field("amfi").cast(pl.Utf8),
            transactions=pl.col("schemes").struct.field("transactions"),
        )
        .drop("schemes")
        .explode("transactions")
        .with_columns(
            txn_date=pl.col("transactions")
            .struct.field("date")
            .str.strptime(pl.Date, format="%Y-%m-%d"),
            description=pl.col("transactions")
            .struct.field("description")
            .cast(pl.Utf8),
            amount=pl.col("transactions")
            .struct.field("amount")
            .cast(pl.Decimal(18, 4)),
            units=pl.col("transactions").struct.field("units").cast(pl.Decimal(18, 4)),
            nav=pl.col("transactions").struct.field("nav").cast(pl.Decimal(18, 4)),
            balance=pl.col("transactions")
            .struct.field("balance")
            .cast(pl.Decimal(18, 4)),
            type=pl.col("transactions").struct.field("type").cast(pl.Utf8),
            dividend_rate=pl.col("transactions")
            .struct.field("dividend_rate")
            .cast(pl.Decimal(18, 4)),
        )
        .drop("transactions")
        .select(
            [
                "folio",
                "isin",
                "amfi",
                "txn_date",
                "type",
                "units",
                "nav",
                "amount",
                "balance",
                "dividend_rate",
                "scheme",
                "description",
                "source_file",
            ]
        )
    )

    has_linked_tax_next = (
        pl.col("tax_type")
        .cast(pl.Utf8)
        .str.to_uppercase()
        .str.contains("_TAX")
        .fill_null(False)
    )

    is_tax_row = (
        pl.col("type")
        .cast(pl.Utf8)
        .str.to_uppercase()
        .str.contains("_TAX")
        .fill_null(False)
    )

    # Populate tax columns
    lf = (
        flattened_lf.with_columns(
            [
                pl.col("type").shift(-1).alias("tax_type"),
                pl.col("description").shift(-1).alias("tax_description"),
                pl.col("amount").shift(-1).alias("tax_amount"),
            ]
        )
        .with_columns(
            [
                pl.when(has_linked_tax_next)
                .then(pl.col("tax_amount"))
                .otherwise(None)
                .alias("tax_amount"),
                pl.when(has_linked_tax_next)
                .then(pl.col("tax_type"))
                .otherwise(None)
                .alias("tax_type"),
                pl.when(has_linked_tax_next)
                .then(pl.col("tax_description"))
                .otherwise(None)
                .alias("tax_description"),
            ]
        )
        .filter(~is_tax_row)
        .with_columns(
            pl.col("folio")
            .cum_count()
            .over(["folio", "scheme", "txn_date"])
            .alias("txn_id")
        )
    )

    # Compute residual units per folio/isin stream.
    lf = lf.with_columns(residual_units=_residual_units_expr())

    return lf


def _residual_units_expr() -> pl.Expr:
    """
    Residual units outstanding per row, approximating FIFO consumption of purchases by later
    redemptions within each (folio, isin) stream, ordered by (txn_date, txn_id). Shared between
    the CAS-flattening path (_read_json_str) and _recompute_residual_units() (used after a
    transaction is deleted) so both stay in sync.
    """
    return (
        pl.when(pl.col("units") <= 0)
        .then(pl.lit(0))
        .otherwise(
            pl.min_horizontal(
                pl.max_horizontal(
                    (
                        pl.when(pl.col("units") > 0)
                        .then(pl.col("units"))
                        .otherwise(pl.lit(0))
                        .cum_sum()
                        .over(
                            ["folio", "isin"],
                            order_by=[pl.col("txn_date"), pl.col("txn_id")],
                        )
                        + pl.when(pl.col("units") < 0)
                        .then(pl.col("units"))
                        .otherwise(pl.lit(0))
                        .sum()
                        .over(["folio", "isin"])
                    ),
                    pl.lit(0),
                ),
                pl.col("units"),
            )
        )
    )


def _recompute_residual_units() -> None:
    """Recompute residual_units for every stored transaction. Run after a transaction is deleted,
    since the remaining rows' residuals were computed assuming the deleted row still existed."""
    conn = db.get_connection()
    try:
        trans_df = conn.execute(
            "SELECT folio, isin, txn_date, txn_id, units FROM mf_transactions"
        ).pl()
        if trans_df.height == 0:
            return

        residual_df = trans_df.with_columns(residual_units=_residual_units_expr()).select(
            "folio", "isin", "txn_date", "txn_id", "residual_units"
        )

        conn.execute(
            """
            UPDATE mf_transactions
            SET residual_units = residual_df.residual_units
            FROM residual_df
            WHERE mf_transactions.folio = residual_df.folio
              AND mf_transactions.isin = residual_df.isin
              AND mf_transactions.txn_date = residual_df.txn_date
              AND mf_transactions.txn_id = residual_df.txn_id;
            """
        )
    finally:
        conn.close()


def _save_transactions_data(df_transactions: pl.DataFrame) -> dict[str, str]:
    """Insert one CAS file's transactions into DuckDB, skipping rows already present."""

    df_transactions = df_transactions.with_columns(
        [
            pl.col("folio").cast(pl.Utf8),
            pl.col("isin").cast(pl.Utf8),
            pl.col("amfi").cast(pl.Utf8),
            pl.col("txn_date").cast(pl.Date),
            pl.col("txn_id").cast(pl.Int64),
            pl.col("type").cast(pl.Utf8),
            pl.col("units").cast(pl.Decimal(18, 4)),
            pl.col("nav").cast(pl.Decimal(18, 4)),
            pl.col("amount").cast(pl.Decimal(18, 4)),
            pl.col("balance").cast(pl.Decimal(18, 4)),
            pl.col("dividend_rate").cast(pl.Decimal(18, 4)),
            pl.col("tax_amount").cast(pl.Decimal(18, 4)),
            pl.col("tax_type").cast(pl.Utf8),
            pl.col("tax_description").cast(pl.Utf8),
            pl.col("scheme").cast(pl.Utf8),
            pl.col("description").cast(pl.Utf8),
            pl.col("source_file").cast(pl.Utf8),
        ]
    )
    
    df_folio = (
        df_transactions.select("folio")
        .unique()
        .with_columns(pl.col("folio").alias("folio_name"))
    )

    # For each ISIN in the uploaded file, pick the latest non-empty scheme name so we can
    # normalize historical aliases in storage to a single current display name.
    df_scheme_by_isin = (
        df_transactions
        .filter(pl.col("scheme").is_not_null() & (pl.col("scheme").str.strip_chars() != ""))
        .sort(["isin", "txn_date", "txn_id"])
        .group_by("isin")
        .agg(pl.col("scheme").last().alias("scheme"))
    )

    conn = db.get_connection()
    try:
        # New folios only - never overwrite a folio name the user has already set (mirrors
        # update_when_matched=False from the original Delta upsert).
        conn.execute(
            """
            INSERT INTO mf_folios
            BY NAME
            SELECT * FROM df_folio
            ON CONFLICT (folio) DO NOTHING;
            """
        )

        # Rows are keyed by (isin, folio, txn_date, type, units, balance) - the same composite
        # key used to disambiguate a transaction for deletion (see delete_transaction()).
        inserted = conn.execute(
            """
            INSERT INTO mf_transactions
            BY NAME
            SELECT * FROM df_transactions
            ON CONFLICT (isin, folio, txn_date, type, units, balance) DO NOTHING
            RETURNING isin;
            """
        ).fetchall()

        # If the latest import uses a newer scheme name for an existing ISIN, update all rows
        # for that ISIN so holdings don't split into multiple line items for aliases.
        if df_scheme_by_isin.height > 0:
            conn.execute(
                """
                UPDATE mf_transactions
                SET scheme = df_scheme_by_isin.scheme
                FROM df_scheme_by_isin
                WHERE mf_transactions.isin = df_scheme_by_isin.isin
                  AND COALESCE(mf_transactions.scheme, '') <> df_scheme_by_isin.scheme;
                """
            )
    finally:
        conn.close()

    message = f"MF Transaction Import metrics: {df_transactions.height} source rows, {len(inserted)} new rows added."
    logger.info(message)

    return {"status": "success", "message": message}


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


def compute_xirr() -> None:
    # Load data from mf_transactions and mf_nav and compute xirr at scheme-folio, scheme and total MF levels.
    conn = db.get_connection()
    try:
        lf_trans = (
            conn.execute(
                "SELECT folio, isin, amfi, txn_date, scheme, nav, residual_units FROM mf_transactions"
            )
            .pl()
            .lazy()
            .with_columns(
                pl.col("txn_date").cast(pl.Date, strict=False),
                pl.col("nav").cast(pl.Float64, strict=False),
                pl.col("residual_units").cast(pl.Float64, strict=False),
            )
            .filter(
                pl.col("txn_date").is_not_null()
                & pl.col("nav").is_not_null()
                & pl.col("residual_units").is_not_null()
                & (pl.col("residual_units") > 0)
            )
        )

        lf_folios = conn.execute("SELECT folio, folio_name FROM mf_folios").pl().lazy()

        # In lf_trans replace folio with folio_name from lf_folios for better readability in the output. Use left join to retain all transactions even if folio name is missing.
        lf_trans = (
            lf_trans.join(lf_folios, on="folio", how="left")
            .drop("folio")
            .with_columns(pl.col("folio_name").alias("folio"))
            .drop("folio_name")
        )

        lf_nav = (
            conn.execute('SELECT amfi, nav, nav_dt FROM mf_nav')
            .pl()
            .lazy()
            .with_columns(
                pl.col("nav").cast(pl.Float64, strict=False),
                pl.col("nav_dt").cast(pl.Date, strict=False),
            )
            .filter(pl.col("nav").is_not_null() & pl.col("nav_dt").is_not_null())
            .select("amfi", "nav", "nav_dt")
        )
    finally:
        conn.close()

    # Investment cashflows are outflows at txn_date.
    lf_investment_cf = lf_trans.select(
        "scheme",
        "folio",
        pl.col("txn_date"),
        (-(pl.col("nav") * pl.col("residual_units"))).alias("cashflow_amount"),
        pl.lit(None).cast(pl.Date).alias("as_on_date"),
    )

    # Terminal cashflow is current valuation at NAV date.
    lf_terminal_cf = (
        lf_trans.group_by("amfi", "scheme", "folio")
        .agg(pl.col("residual_units").sum().alias("total_units"))
        .join(lf_nav, on="amfi", how="inner")
        .select(
            "scheme",
            "folio",
            pl.col("nav_dt").alias("txn_date"),
            (pl.col("total_units") * pl.col("nav")).alias("cashflow_amount"),
            pl.col("nav_dt").alias("as_on_date"),
        )
    )

    lf_cashflows = pl.concat([lf_investment_cf, lf_terminal_cf], how="vertical")

    def _build_xirr_level(
        cashflows: pl.LazyFrame, group_cols: list[str], level_name: str
    ) -> pl.LazyFrame:
        effective_group_cols = group_cols if group_cols else ["_mf_total_group"]
        level_cashflows = (
            cashflows.with_columns(pl.lit("mf_total").alias("_mf_total_group"))
            if not group_cols
            else cashflows
        )

        lf = (
            level_cashflows.group_by(effective_group_cols + ["txn_date"])
            .agg(
                pl.col("cashflow_amount").sum().alias("cashflow_amount"),
                pl.col("as_on_date").max().alias("as_on_date"),
            )
            .group_by(effective_group_cols)
            .agg(
                pl.col("txn_date").sort().alias("dates"),
                pl.col("cashflow_amount").sort_by("txn_date").alias("amounts"),
                pl.col("as_on_date").max().alias("as_on_date"),
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

        if "scheme" not in group_cols:
            lf = lf.with_columns(pl.lit("").alias("scheme"))
        if "folio" not in group_cols:
            lf = lf.with_columns(pl.lit("").alias("folio"))

        return lf.select("level", "scheme", "folio", "xirr_pct", "as_on_date")

    lf_scheme_folio = _build_xirr_level(
        lf_cashflows,
        group_cols=["scheme", "folio"],
        level_name="scheme_folio",
    )
    lf_scheme = _build_xirr_level(
        lf_cashflows,
        group_cols=["scheme"],
        level_name="scheme",
    )
    lf_total = _build_xirr_level(
        lf_cashflows,
        group_cols=[],
        level_name="mf_total",
    )

    xirr_df = pl.concat(
        [lf_scheme_folio, lf_scheme, lf_total], how="vertical"
    ).collect()

    conn = db.get_connection()
    try:
        conn.execute("DELETE FROM mf_xirr")
        conn.execute(
            "INSERT INTO mf_xirr SELECT level, scheme, folio, xirr_pct, as_on_date FROM xirr_df"
        )
    finally:
        conn.close()


# *** Refresh NAV *****
async def _fetch_all_urls(urls: list[str]) -> list[str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Create concurrent tasks for all URLs
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for r in responses:
            if isinstance(r, httpx.Response):
                output.append(r.text)
            else:
                output.append(
                    '{"data":[{"date":"02-01-1900","nav":"0.0"},{"date":"01-01-1900","nav":"0.1"}]}'
                )
        return output


def _download_batch(series: pl.Series) -> pl.Series:
    urls = series.to_list()
    results = asyncio.run(_fetch_all_urls(urls))
    return pl.Series(results, dtype=pl.Utf8)


def refresh_nav() -> None:

    # Get all the AMFIs from the mf_nav table which have nav_dt as of yestereday or later.
    weekday = date.today().weekday()
    days_to_subtract = 3 if weekday == 0 else (2 if weekday == 6 else 1)
    last_working_day = date.today() - timedelta(days=days_to_subtract)

    conn = db.get_connection()
    try:
        lf_nav = (
            conn.execute('SELECT amfi, nav_dt FROM mf_nav')
            .pl()
            .lazy()
            .with_columns(pl.col("nav_dt").cast(pl.Date, strict=False))
            .filter(pl.col("nav_dt") >= last_working_day)
            .select("amfi")
        )

        lf_isins = (
            conn.execute("SELECT DISTINCT amfi FROM mf_transactions")
            .pl()
            .lazy()
            .with_columns(
                pl.col("amfi").cast(pl.String)
            )  # To ensure consistent type for the join, especially when mf_nav is empty
        )

        # Remove the amfis which already have nav_dt as of last working day or later in mf_nav to avoid unnecessary API calls
        df_isins = lf_isins.join(lf_nav, on="amfi", how="anti").collect()
    finally:
        conn.close()

    if df_isins.height == 0:
        logger.info("No new AMFIs to refresh NAV for.")
        return

    # URL to fetch NAVs: https://api.mfapi.in/mf/125497?startDate=2023-01-01&endDate=2023-12-31
    end_dt = date.today().isoformat()
    start_dt = (date.today() - timedelta(days=6)).isoformat()
    RESP_SCHEMA = pl.Struct(
        {
            "data": pl.List(
                pl.Struct(
                    {
                        "date": pl.Utf8,
                        "nav": pl.Decimal(12, 4),
                    }
                )
            )
        }
    )

    df_isins = (
        df_isins.with_columns(
            url=pl.lit("https://api.mfapi.in/mf/")
            + pl.col("amfi")
            + pl.lit(f"?startDate={start_dt}&endDate={end_dt}")
        )
        .with_columns(resp_text=pl.col("url").map_batches(_download_batch))
        .with_columns(resp_json=pl.col("resp_text").str.json_decode(RESP_SCHEMA))
        .with_columns(
            [
                pl.col("resp_json")
                .struct.field("data")
                .list.get(0)
                .struct.field("nav")
                .cast(pl.Decimal(12, 4))
                .alias("nav"),
                pl.col("resp_json")
                .struct.field("data")
                .list.get(0)
                .struct.field("date")
                .str.strptime(pl.Date, format="%d-%m-%Y")
                .alias("nav_dt"),
                pl.col("resp_json")
                .struct.field("data")
                .list.get(1)
                .struct.field("nav")
                .cast(pl.Decimal(12, 4))
                .alias("prev_nav"),
                pl.col("resp_json")
                .struct.field("data")
                .list.get(1)
                .struct.field("date")
                .str.strptime(pl.Date, format="%d-%m-%Y")
                .alias("prev_nav_dt"),
            ]
        )
        .drop(["resp_json", "url", "resp_text"])
        .filter(pl.col("nav") != pl.lit(0.0))  # These are http error lines
        .with_columns(
            ((pl.col("nav") / pl.col("prev_nav") - pl.lit(1)) * 100).alias("1d_change")
        )
    )

    conn = db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO mf_nav
            BY NAME
            SELECT * FROM df_isins
            ON CONFLICT (amfi) DO UPDATE SET
                nav = excluded.nav,
                nav_dt = excluded.nav_dt,
                prev_nav = excluded.prev_nav,
                prev_nav_dt = excluded.prev_nav_dt,
                "1d_change" = excluded."1d_change";
            """
        )
    finally:
        conn.close()


# *** Get Holding statement ***
def get_mf_holdings() -> dict:

    conn = db.get_connection()
    try:
        # Get folio names from mf_folios table and join
        lf_folios = conn.execute("SELECT folio, folio_name FROM mf_folios").pl().lazy()

        lf_trans = (
            conn.execute(
                "SELECT folio, isin, amfi, scheme, nav, residual_units FROM mf_transactions"
            )
            .pl()
            .lazy()
            .with_columns(
                pl.col("nav").cast(pl.Float64, strict=False),
                pl.col("residual_units").cast(pl.Float64, strict=False),
            )
        )

        lf_trans = (
            lf_trans.join(lf_folios, on="folio", how="left")
            .drop("folio")
            .with_columns(pl.col("folio_name").alias("folio"))
            .drop("folio_name")
        )

        lf_holdings = lf_trans.group_by(
            "isin",
            "amfi",
            "scheme",
            "folio",
        ).agg(
            total_units=pl.col("residual_units").sum().cast(pl.Float64),
            invested_amount=(pl.col("nav") * pl.col("residual_units"))
            .sum()
            .cast(pl.Float64),
        )

        lf_nav = (
            conn.execute("SELECT amfi, nav, nav_dt FROM mf_nav")
            .pl()
            .lazy()
            .with_columns(pl.col("nav").cast(pl.Float64))
        )

        lf_xirr = conn.execute("SELECT level, scheme, folio, xirr_pct, as_on_date FROM mf_xirr").pl().lazy()
    finally:
        conn.close()

    lf_holdings = (
        lf_holdings.join(lf_nav, on="amfi", how="left")
        .with_columns(
            current_value=pl.col("total_units") * pl.col("nav").cast(pl.Float64)
        )
        .with_columns(
            abs_gain_pct=100
            * (pl.col("current_value") / pl.col("invested_amount") - pl.lit(1.0)).cast(
                pl.Float64
            )
        )
        .join(lf_xirr, on=["scheme", "folio"])
        .select(
            [
                "scheme",
                "folio",
                "total_units",
                "invested_amount",
                "current_value",
                "abs_gain_pct",
                "xirr_pct",
                "nav",
                "nav_dt",
            ]
        )
        .with_columns(pl.col("nav_dt").cast(pl.String))
    )

    # Build the grouped rows for the consumption in HTML Tabulator

    # Create child row values
    lf_children = lf_holdings.with_columns(
        scheme_or_folio=pl.col("folio").cast(pl.Utf8),
        total_units=pl.col("total_units").fill_null(0.0),
        invested_amount=pl.col("invested_amount").fill_null(0.0),
        current_value=pl.col("current_value").fill_null(0.0),
        abs_gain_pct=pl.col("abs_gain_pct").fill_null(0.0),
        xirr_pct=pl.col("xirr_pct").fill_null(0.0),
    )

    # Drop zero-balance folios (e.g. fully redeemed or switched out) from the holdings report -
    # the underlying transactions and XIRR are still tracked, this only affects what's displayed.
    # A scheme where every folio nets to zero simply won't produce a group below.
    lf_children = lf_children.filter(pl.col("total_units").abs() > 1e-6)

    lf_xirr_scheme_level = lf_xirr.filter(pl.col("level") == "scheme")
    # Generate the tree grouped row values and children for each
    lf_tree = (
        lf_children.group_by("scheme")
        .agg(
            total_units=pl.col("total_units").sum(),
            invested_amount=pl.col("invested_amount").sum(),
            current_value=pl.col("current_value").sum(),
            nav=pl.col("nav").drop_nulls().first(),
            nav_dt=pl.col("nav_dt").drop_nulls().first(),
            _children=pl.struct(
                [
                    "scheme_or_folio",
                    "total_units",
                    "invested_amount",
                    "nav_dt",
                    "nav",
                    "current_value",
                    "abs_gain_pct",
                    "xirr_pct",
                ]
            ),
        )
        .with_columns(
            scheme_or_folio=pl.col("scheme"),
            abs_gain_pct=pl.when(pl.col("invested_amount") != 0)
            .then((pl.col("current_value") / pl.col("invested_amount") - 1.0) * 100.0)
            .otherwise(0.0),
        )
        .join(lf_xirr_scheme_level, on=["scheme"])
        .select(
            [
                "scheme_or_folio",
                "total_units",
                "invested_amount",
                "current_value",
                "abs_gain_pct",
                "xirr_pct",
                "nav",
                "nav_dt",
                "_children",
            ]
        )
    )

    tree_df = lf_tree.collect()

    # Compute the grand totals
    bottom_calc_df = tree_df.select(
        grand_invested_amount=pl.col("invested_amount").sum(),
        grand_current_value=pl.col("current_value").sum(),
    ).with_columns(
        grand_abs_gain_pct=pl.when(pl.col("grand_invested_amount") != 0)
        .then(
            (pl.col("grand_current_value") / pl.col("grand_invested_amount") - 1.0)
            * 100.0
        )
        .otherwise(0.0),
        grand_xirr_pct=lf_xirr.filter(pl.col("level") == "mf_total")
        .select(pl.col("xirr_pct").first().fill_null(0))
        .collect()
        .item(),
    )

    bottom_calc = (
        bottom_calc_df.to_dicts()[0]
        if bottom_calc_df.height
        else {
            "grand_invested_amount": 0.0,
            "grand_current_value": 0.0,
            "grand_abs_gain_pct": 0.0,
            "grand_xirr_pct": 0.0,
        }
    )

    tree_rows = tree_df.to_dicts()

    return {
        "tree_rows": tree_rows,
        "grand_totals": {
            "invested_amount": float(bottom_calc["grand_invested_amount"] or 0.0),
            "current_value": float(bottom_calc["grand_current_value"] or 0.0),
            "abs_gain_pct": float(bottom_calc["grand_abs_gain_pct"] or 0.0),
            "xirr_pct": float(bottom_calc["grand_xirr_pct"] or 0.0),
        },
    }


# Get Transaction details for a given scheme-folio
def get_transaction_details(scheme: str = "", folio: str = "") -> dict:
    # Read from mf_transactions and return all txn details for the given scheme-folio combination.
    # Uses ILIKE pattern matching (case-insensitive substring), same style as the Equity/NPS lookups.

    try:
        conn = db.get_connection()
        try:
            payload = conn.execute(
                """
                SELECT
                    t.folio AS folio_raw,
                    COALESCE(f.folio_name, t.folio) AS folio,
                    t.isin,
                    t.amfi,
                    CAST(t.txn_date AS VARCHAR) AS txn_date,
                    t.type,
                    CAST(t.units AS DOUBLE) AS units,
                    CAST(t.nav AS DOUBLE) AS nav,
                    CAST(t.amount AS DOUBLE) AS amount,
                    CAST(t.balance AS DOUBLE) AS balance,
                    CAST(t.dividend_rate AS DOUBLE) AS dividend_rate,
                    t.scheme,
                    t.description,
                    t.source_file,
                    t.tax_type,
                    t.tax_description,
                    CAST(t.tax_amount AS DOUBLE) AS tax_amount,
                    t.txn_id,
                    CAST(t.residual_units AS DOUBLE) AS residual_units
                FROM mf_transactions t
                LEFT JOIN mf_folios f ON f.folio = t.folio
                WHERE t.scheme ILIKE ? AND COALESCE(f.folio_name, t.folio) ILIKE ?
                ORDER BY t.txn_date, t.txn_id
                """,
                [f"%{scheme}%", f"%{folio}%"],
            ).pl().to_dicts()
        finally:
            conn.close()

        return {
            "status": "success",
            "message": f"{len(payload)} transactions found for scheme pattern '{scheme}' and folio pattern '{folio}'.",
            "payload": payload,
        }
    except Exception as e:
        logger.error(f"Error fetching transaction details: {e}")
        return {"status": "error", "message": str(e), "payload": []}


def delete_transaction(
    folio_raw: str,
    isin: str,
    txn_date: str,
    type: str,
    units: float,
    balance: float,
    txn_id: int,
) -> dict:
    """
    Delete a single row from mf_transactions, identified by the same composite key
    (isin, folio, txn_date, type, units, balance) already used to de-dupe on insert
    (see _save_transactions_data), plus txn_id to disambiguate exact duplicate rows
    within that key. Recomputes residual_units and XIRR afterwards since both depend
    on the full remaining transaction stream for the folio/isin.
    """
    try:
        conn = db.get_connection()
        try:
            deleted = conn.execute(
                """
                DELETE FROM mf_transactions
                WHERE folio = ? AND isin = ? AND txn_date = ? AND type = ?
                  AND units = ? AND balance = ? AND txn_id = ?
                RETURNING isin;
                """,
                [folio_raw, isin, txn_date, type, units, balance, txn_id],
            ).fetchall()
        finally:
            conn.close()

        if not deleted:
            return {
                "status": "error",
                "message": "Transaction not found - it may have already been deleted.",
                "payload": [],
            }

        _recompute_residual_units()
        compute_xirr()

        return {
            "status": "success",
            "message": f"Deleted {len(deleted)} transaction(s).",
            "payload": [],
        }
    except Exception as e:
        logger.error(f"Error deleting MF transaction: {e}")
        return {"status": "error", "message": str(e), "payload": []}


def get_folio_list() -> dict:
    # Read from mf_folios and return the list of folios.
    try:
        conn = db.get_connection()
        try:
            payload = conn.execute("SELECT folio, folio_name FROM mf_folios").pl().to_dicts()
        finally:
            conn.close()

        return {
            "status": "success",
            "message": f"{len(payload)} folios found.",
            "payload": payload,
        }

    except Exception as e:
        logger.error(f"Error fetching folio list: {e}")
        return {"status": "error", "message": str(e), "payload": []}


def update_folio_name(folio: str, new_name: str) -> dict:
    # Update the folio name in mf_folios table for the given folio.
    try:
        conn = db.get_connection()
        try:
            conn.execute(
                """
                INSERT INTO mf_folios (folio, folio_name)
                VALUES (?, ?)
                ON CONFLICT (folio) DO UPDATE SET folio_name = excluded.folio_name;
                """,
                [folio, new_name],
            )
        finally:
            conn.close()

        logger.info(f"Folio {folio} updated to {new_name}.")
        return {
            "status": "success",
            "message": f"Folio {folio} updated to {new_name}.",
            "payload": [],
        }

    except Exception as e:
        logger.error(f"Error updating folio name: {e}")
        return {"status": "error", "message": str(e), "payload": []}


if __name__ == "__main__":

    # **************
    import locale
    from pprint import pprint

    locale.setlocale(locale.LC_ALL, "")  # use system locale
    conv = locale.localeconv()
    if hasattr(pl.Config, "set_decimal_separator"):
        pl.Config.set_decimal_separator(conv.get("decimal_point", "."))
    if hasattr(pl.Config, "set_thousands_separator"):
        pl.Config.set_thousands_separator(conv.get("thousands_sep", ","))
    pl.Config.set_tbl_rows(-1)
    pl.Config.set_tbl_cell_numeric_alignment("RIGHT")

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s %(levelname)s %(name)s]: %(message)s",
    )
    # **************

    # refresh_nav()
    # compute_xirr()
    # pprint(get_mf_holdings(), width=100 )

    # pprint(get_transaction_details(), width=100)
    # pprint(get_folio_list(), width=100)
