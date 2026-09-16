# Functions for storing and computing Fixed Deposit (FD) and Bond holdings from a CSV template.
import base64
import calendar
import io
import logging
import re
from datetime import date, datetime, timedelta

import polars as pl
import pyxirr

try:
    from . import db_duckdb as db
except ImportError:
    import db_duckdb as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _normalize_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())


def _safe_xirr(dates: list[date], amounts: list[float]) -> float:
    if len(dates) < 2 or len(amounts) < 2:
        return 0.0
    if not any(a < 0 for a in amounts) or not any(a > 0 for a in amounts):
        return 0.0
    try:
        value = pyxirr.xirr(dates, amounts)
        return (value * 100.0) if value is not None else 0.0
    except Exception:
        return 0.0


def _classify_instrument(name: str) -> str:
    token = str(name or "").upper()
    if "PPF" in token or "PUBLIC PROVIDENT" in token:
        return "PPF"
    if "FD" in token or "FIXED" in token or "DEPOSIT" in token:
        return "FD"
    return "Bond"


def _normalize_instrument_type(value: str, name_hint: str = "") -> str:
    token = str(value or "").strip().upper()
    if token in {"PPF", "PUBLIC PROVIDENT FUND"}:
        return "PPF"
    if token in {"FD", "FIXED DEPOSIT"}:
        return "FD"
    if token == "BOND":
        return "Bond"
    return _classify_instrument(name_hint)


def _end_of_month(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def _seed_default_ppf_rates(conn) -> None:
    existing_count = int(conn.execute("SELECT COUNT(*) FROM ppf_interest_rates").fetchone()[0])
    if existing_count > 0:
        return

    conn.execute(
        """
        INSERT INTO ppf_interest_rates (effective_from, annual_rate_pct, source_note)
        VALUES (CAST(? AS DATE), CAST(? AS DECIMAL(8,4)), ?);
        """,
        ["1900-01-01", 7.10, "default-fallback-rate"],
    )


def _ensure_ppf_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ppf_transactions (
            account_name VARCHAR NOT NULL,
            txn_date DATE NOT NULL,
            txn_type VARCHAR NOT NULL,
            amount DECIMAL(18,4) NOT NULL,
            notes VARCHAR NOT NULL DEFAULT '',
            source_file VARCHAR,
            PRIMARY KEY (account_name, txn_date, txn_type, amount, notes)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ppf_interest_rates (
            effective_from DATE PRIMARY KEY,
            annual_rate_pct DECIMAL(8,4) NOT NULL,
            source_note VARCHAR
        );
        """
    )
    _seed_default_ppf_rates(conn)


def _periodic_terminal_value(
    principal: float,
    annual_rate: float,
    purchase_dt: date,
    terminal_dt: date,
    period_years: float,
) -> tuple[float, list[tuple[date, float]]]:
    step_days = max(1, int(round(period_years * 365.0)))
    coupon_amount = principal * annual_rate * period_years

    coupons: list[tuple[date, float]] = []
    coupon_dt = purchase_dt + timedelta(days=step_days)
    last_coupon_dt = purchase_dt

    while coupon_dt <= terminal_dt:
        coupons.append((coupon_dt, coupon_amount))
        last_coupon_dt = coupon_dt
        coupon_dt = coupon_dt + timedelta(days=step_days)

    residual_years = max(0.0, (terminal_dt - last_coupon_dt).days / 365.0)
    unpaid_residual = principal * annual_rate * residual_years

    # For a holdings statement, show the principal plus any accrued-but-unpaid interest.
    terminal_value = principal + unpaid_residual
    return terminal_value, coupons


def _parse_dates(expr: pl.Expr) -> pl.Expr:
    stripped = expr.cast(pl.Utf8).str.strip_chars()
    return (
        stripped.str.strptime(pl.Date, format="%Y-%m-%d", strict=False)
        .fill_null(stripped.str.strptime(pl.Date, format="%d-%b-%Y", strict=False))
        .fill_null(stripped.str.strptime(pl.Date, format="%d-%b-%y", strict=False))
        .fill_null(stripped.str.strptime(pl.Date, format="%d/%m/%Y", strict=False))
        .fill_null(stripped.str.strptime(pl.Date, format="%m/%d/%Y", strict=False))
    )


def ingest_fd_bond_holdings(file_name: str, file_content_b64: str) -> dict:
    try:
        payload = file_content_b64.split("base64,", 1)[1] if "base64," in file_content_b64 else file_content_b64
        csv_text = base64.b64decode(payload).decode("utf-8-sig")

        raw_df = pl.read_csv(io.StringIO(csv_text), has_header=True)
        if raw_df.height == 0:
            return {"status": "error", "message": "CSV has no rows."}

        header_map = {_normalize_header(col): col for col in raw_df.columns}
        required = {
            "fdbondname": "FD/Bond Name",
            "purchasedate": "Purchase Date",
            "principalamount": "Principal Amount",
            "simpleinterestrateperyear": "Simple Interest Rate (per year)",
            "interestcalculationperiodinyearseg025quarterly": "Interest calculation period (in years)",
            "payoutmethodcumulativeorperiodic": "Payout method",
            "maturitydate": "Maturity Date",
        }

        missing = [label for key, label in required.items() if key not in header_map]
        if missing:
            return {"status": "error", "message": f"Missing required columns: {', '.join(missing)}"}

        instrument_type_col = header_map.get("type") or header_map.get("instrumenttype")

        instrument_type_expr = (
            pl.col(instrument_type_col).cast(pl.Utf8).str.strip_chars()
            if instrument_type_col
            else pl.lit("")
        )

        df = raw_df.select(
            pl.col(header_map["fdbondname"]).cast(pl.Utf8).str.strip_chars().alias("instrument_name"),
            instrument_type_expr.alias("instrument_type"),
            _parse_dates(pl.col(header_map["purchasedate"])).alias("purchase_date"),
            pl.col(header_map["principalamount"]).cast(pl.Utf8).str.replace_all(",", "").cast(pl.Float64).alias("principal_amount"),
            pl.col(header_map["simpleinterestrateperyear"]).cast(pl.Utf8).str.replace_all(",", "").cast(pl.Float64).alias("interest_rate_pct"),
            pl.col(header_map["interestcalculationperiodinyearseg025quarterly"]).cast(pl.Utf8).str.replace_all(",", "").cast(pl.Float64).alias("interest_period_years"),
            pl.col(header_map["payoutmethodcumulativeorperiodic"]).cast(pl.Utf8).str.to_titlecase().str.strip_chars().alias("payout_method"),
            _parse_dates(pl.col(header_map["maturitydate"])).alias("maturity_date"),
        ).with_columns(pl.lit(file_name).alias("source_file"))

        if df.filter(pl.col("purchase_date").is_null() | pl.col("maturity_date").is_null()).height > 0:
            return {"status": "error", "message": "Invalid date format in Purchase Date or Maturity Date."}

        invalid_rows = df.filter(
            (pl.col("instrument_name") == "")
            | (pl.col("principal_amount") <= 0)
            | (pl.col("interest_period_years") <= 0)
        )
        if invalid_rows.height > 0:
            return {
                "status": "error",
                "message": "Each row must have name, positive principal amount, and positive interest period.",
            }

        df = df.with_columns(
            pl.struct(["instrument_type", "instrument_name"])
            .map_elements(
                lambda r: _normalize_instrument_type(
                    str(r.get("instrument_type") or ""),
                    str(r.get("instrument_name") or ""),
                ),
                return_dtype=pl.Utf8,
            )
            .alias("instrument_type"),
            pl.when(pl.col("payout_method").str.to_lowercase() == "periodic")
            .then(pl.lit("Periodic"))
            .otherwise(pl.lit("Cumulative"))
            .alias("payout_method")
        )

        df = df.with_columns(
            pl.when(pl.col("instrument_type") == "PPF")
            .then(pl.lit("Cumulative"))
            .otherwise(pl.col("payout_method"))
            .alias("payout_method"),
            pl.when(pl.col("instrument_type") == "PPF")
            .then(pl.lit(1.0 / 12.0))
            .otherwise(pl.col("interest_period_years"))
            .alias("interest_period_years"),
        )

        conn = db.get_connection()
        try:
            inserted = conn.execute(
                """
                INSERT INTO fd_bond_holdings
                (
                    instrument_name,
                    instrument_type,
                    purchase_date,
                    principal_amount,
                    interest_rate_pct,
                    interest_period_years,
                    payout_method,
                    maturity_date,
                    source_file
                )
                SELECT
                    instrument_name,
                    instrument_type,
                    purchase_date,
                    principal_amount,
                    interest_rate_pct,
                    interest_period_years,
                    payout_method,
                    maturity_date,
                    source_file
                FROM df
                ON CONFLICT (
                    instrument_name,
                    purchase_date,
                    principal_amount,
                    interest_rate_pct,
                    interest_period_years,
                    payout_method,
                    maturity_date
                ) DO NOTHING
                RETURNING instrument_name;
                """
            ).fetchall()
        finally:
            conn.close()

        return {
            "status": "success",
            "message": f"FD/Bond import: {df.height} rows in file, {len(inserted)} new rows added.",
        }
    except Exception as e:
        logger.error(f"Error ingesting FD/Bond CSV: {e}")
        return {"status": "error", "message": str(e)}


def ingest_ppf_transactions(file_name: str, file_content_b64: str) -> dict:
    try:
        payload = file_content_b64.split("base64,", 1)[1] if "base64," in file_content_b64 else file_content_b64
        csv_text = base64.b64decode(payload).decode("utf-8-sig")

        raw_df = pl.read_csv(io.StringIO(csv_text), has_header=True)
        if raw_df.height == 0:
            return {"status": "error", "message": "CSV has no rows."}

        header_map = {_normalize_header(col): col for col in raw_df.columns}

        account_col = header_map.get("accountname") or header_map.get("ppfaccount") or header_map.get("account")
        txn_date_col = header_map.get("transactiondate") or header_map.get("txndate") or header_map.get("date")
        txn_type_col = header_map.get("transactiontype") or header_map.get("txntype") or header_map.get("type")
        amount_col = header_map.get("amount")
        notes_col = header_map.get("notes") or header_map.get("description") or header_map.get("particulars")

        missing_labels: list[str] = []
        if account_col is None:
            missing_labels.append("Account Name")
        if txn_date_col is None:
            missing_labels.append("Transaction Date")
        if txn_type_col is None:
            missing_labels.append("Transaction Type")
        if amount_col is None:
            missing_labels.append("Amount")
        if missing_labels:
            return {"status": "error", "message": f"Missing required columns: {', '.join(missing_labels)}"}

        notes_expr = pl.col(notes_col).cast(pl.Utf8).fill_null("").str.strip_chars() if notes_col else pl.lit("")

        df = raw_df.select(
            pl.col(account_col).cast(pl.Utf8).str.strip_chars().alias("account_name"),
            _parse_dates(pl.col(txn_date_col)).alias("txn_date"),
            pl.col(txn_type_col).cast(pl.Utf8).str.strip_chars().alias("txn_type_raw"),
            pl.col(amount_col).cast(pl.Utf8).str.replace_all(",", "").cast(pl.Float64).alias("amount"),
            notes_expr.alias("notes"),
        ).with_columns(pl.lit(file_name).alias("source_file"))

        df = df.with_columns(
            pl.when(pl.col("txn_type_raw").str.to_lowercase().str.contains("withdra"))
            .then(pl.lit("Withdrawal"))
            .when(pl.col("txn_type_raw").str.to_lowercase().str.contains("interest"))
            .then(pl.lit("Interest"))
            .otherwise(pl.lit("Deposit"))
            .alias("txn_type")
        ).drop("txn_type_raw")

        if df.filter(pl.col("txn_date").is_null()).height > 0:
            return {"status": "error", "message": "Invalid date format in Transaction Date."}

        invalid_rows = df.filter(
            (pl.col("account_name") == "")
            | (pl.col("amount") <= 0)
            | (pl.col("txn_type") == "")
        )
        if invalid_rows.height > 0:
            return {
                "status": "error",
                "message": "Each row must have account name, transaction type, and positive amount.",
            }

        conn = db.get_connection()
        try:
            _ensure_ppf_tables(conn)
            inserted = conn.execute(
                """
                INSERT INTO ppf_transactions
                (
                    account_name,
                    txn_date,
                    txn_type,
                    amount,
                    notes,
                    source_file
                )
                SELECT
                    account_name,
                    txn_date,
                    txn_type,
                    amount,
                    notes,
                    source_file
                FROM df
                ON CONFLICT (account_name, txn_date, txn_type, amount, notes) DO NOTHING
                RETURNING account_name;
                """
            ).fetchall()
        finally:
            conn.close()

        return {
            "status": "success",
            "message": f"PPF import: {df.height} rows in file, {len(inserted)} new rows added.",
        }
    except Exception as e:
        logger.error(f"Error ingesting PPF CSV: {e}")
        return {"status": "error", "message": str(e)}


def ingest_ppf_interest_rates(file_name: str, file_content_b64: str) -> dict:
    try:
        payload = file_content_b64.split("base64,", 1)[1] if "base64," in file_content_b64 else file_content_b64
        csv_text = base64.b64decode(payload).decode("utf-8-sig")

        raw_df = pl.read_csv(io.StringIO(csv_text), has_header=True)
        if raw_df.height == 0:
            return {"status": "error", "message": "CSV has no rows."}

        header_map = {_normalize_header(col): col for col in raw_df.columns}
        effective_col = header_map.get("effectivefrom") or header_map.get("startdate") or header_map.get("date")
        rate_col = header_map.get("annualratepct") or header_map.get("ratepct") or header_map.get("rate")
        source_col = header_map.get("sourcenote") or header_map.get("source")

        missing_labels: list[str] = []
        if effective_col is None:
            missing_labels.append("Effective From")
        if rate_col is None:
            missing_labels.append("Annual Rate %")
        if missing_labels:
            return {"status": "error", "message": f"Missing required columns: {', '.join(missing_labels)}"}

        source_expr = pl.col(source_col).cast(pl.Utf8).fill_null("").str.strip_chars() if source_col else pl.lit("")

        df = raw_df.select(
            _parse_dates(pl.col(effective_col)).alias("effective_from"),
            pl.col(rate_col).cast(pl.Utf8).str.replace_all(",", "").cast(pl.Float64).alias("annual_rate_pct"),
            source_expr.alias("source_note"),
        )

        invalid_rows = df.filter(pl.col("effective_from").is_null() | (pl.col("annual_rate_pct") <= 0))
        if invalid_rows.height > 0:
            return {
                "status": "error",
                "message": "Each rate row must have valid Effective From date and positive Annual Rate %.",
            }

        conn = db.get_connection()
        try:
            _ensure_ppf_tables(conn)
            conn.execute(
                """
                INSERT INTO ppf_interest_rates (effective_from, annual_rate_pct, source_note)
                SELECT effective_from, annual_rate_pct, source_note
                FROM df
                ON CONFLICT (effective_from) DO UPDATE
                SET annual_rate_pct = excluded.annual_rate_pct,
                    source_note = excluded.source_note;
                """
            )
        finally:
            conn.close()

        return {
            "status": "success",
            "message": f"PPF rates import: {df.height} rows upserted from {file_name}.",
        }
    except Exception as e:
        logger.error(f"Error ingesting PPF rate CSV: {e}")
        return {"status": "error", "message": str(e)}


def add_fd_bond_holding(
    instrument_name: str,
    instrument_type: str,
    purchase_date: str,
    principal_amount: float,
    interest_rate_pct: float,
    interest_period_years: float,
    payout_method: str,
    maturity_date: str,
) -> dict:
    try:
        name = str(instrument_name or "").strip()
        if not name:
            return {"status": "error", "message": "FD/Bond name is required."}

        instrument_type_value = str(instrument_type or "").strip().title()
        instrument_type_value = _normalize_instrument_type(instrument_type_value, name)

        principal = float(principal_amount)
        rate = float(interest_rate_pct)
        period = float(interest_period_years)
        if principal <= 0 or period <= 0:
            return {"status": "error", "message": "Principal and interest period must be greater than zero."}

        payout = str(payout_method or "").strip().title()
        if payout not in {"Cumulative", "Periodic"}:
            return {"status": "error", "message": "Payout method must be Cumulative or Periodic."}

        if instrument_type_value == "PPF":
            payout = "Cumulative"
            period = 1.0 / 12.0

        purchase_dt = datetime.strptime(str(purchase_date), "%Y-%m-%d")
        maturity_dt = datetime.strptime(str(maturity_date), "%Y-%m-%d")
        if maturity_dt.date() < purchase_dt.date():
            return {"status": "error", "message": "Maturity date cannot be earlier than purchase date."}

        conn = db.get_connection()
        try:
            inserted = conn.execute(
                """
                INSERT INTO fd_bond_holdings
                (
                    instrument_name,
                    instrument_type,
                    purchase_date,
                    principal_amount,
                    interest_rate_pct,
                    interest_period_years,
                    payout_method,
                    maturity_date,
                    source_file
                )
                VALUES
                (
                    ?,
                    ?,
                    CAST(? AS DATE),
                    CAST(? AS DECIMAL(18,4)),
                    CAST(? AS DECIMAL(10,4)),
                    CAST(? AS DECIMAL(10,4)),
                    ?,
                    CAST(? AS DATE),
                    ?
                )
                ON CONFLICT (
                    instrument_name,
                    purchase_date,
                    principal_amount,
                    interest_rate_pct,
                    interest_period_years,
                    payout_method,
                    maturity_date
                ) DO NOTHING
                RETURNING instrument_name;
                """,
                [
                    name,
                    instrument_type_value,
                    purchase_date,
                    round(principal, 4),
                    round(rate, 4),
                    round(period, 4),
                    payout,
                    maturity_date,
                    "manual-entry",
                ],
            ).fetchone()
        finally:
            conn.close()

        if not inserted:
            return {"status": "error", "message": "Duplicate FD/Bond row already exists."}

        return {"status": "success", "message": "FD/Bond row added successfully."}
    except ValueError:
        return {"status": "error", "message": "Dates must be in YYYY-MM-DD format."}
    except Exception as e:
        logger.error(f"Error adding FD/Bond row: {e}")
        return {"status": "error", "message": str(e)}


def delete_fd_bond_holding(
    instrument_name: str,
    instrument_type: str,
    purchase_date: str,
    principal_amount: float,
    interest_rate_pct: float,
    interest_period_years: float,
    payout_method: str,
    maturity_date: str,
) -> dict:
    try:
        conn = db.get_connection()
        try:
            deleted = conn.execute(
                """
                DELETE FROM fd_bond_holdings
                WHERE instrument_name = ?
                  AND instrument_type = ?
                  AND purchase_date = CAST(? AS DATE)
                  AND principal_amount = CAST(? AS DECIMAL(18,4))
                  AND interest_rate_pct = CAST(? AS DECIMAL(10,4))
                  AND interest_period_years = CAST(? AS DECIMAL(10,4))
                  AND payout_method = ?
                  AND maturity_date = CAST(? AS DATE)
                RETURNING instrument_name;
                """,
                [
                    str(instrument_name or "").strip(),
                    str(instrument_type or "").strip().title() if str(instrument_type or "").strip() else _classify_instrument(str(instrument_name or "")),
                    purchase_date,
                    round(float(principal_amount), 4),
                    round(float(interest_rate_pct), 4),
                    round(float(interest_period_years), 4),
                    str(payout_method or "").strip().title(),
                    maturity_date,
                ],
            ).fetchone()
        finally:
            conn.close()

        if not deleted:
            return {"status": "error", "message": "FD/Bond row not found."}

        return {"status": "success", "message": "FD/Bond row deleted successfully."}
    except Exception as e:
        logger.error(f"Error deleting FD/Bond row: {e}")
        return {"status": "error", "message": str(e)}


def update_fd_bond_holding(
    old_instrument_name: str,
    old_instrument_type: str,
    old_purchase_date: str,
    old_principal_amount: float,
    old_interest_rate_pct: float,
    old_interest_period_years: float,
    old_payout_method: str,
    old_maturity_date: str,
    new_instrument_name: str,
    new_instrument_type: str,
    new_purchase_date: str,
    new_principal_amount: float,
    new_interest_rate_pct: float,
    new_interest_period_years: float,
    new_payout_method: str,
    new_maturity_date: str,
) -> dict:
    try:
        new_name = str(new_instrument_name or "").strip()
        if not new_name:
            return {"status": "error", "message": "Instrument name is required."}

        new_type = str(new_instrument_type or "").strip().title()
        new_type = _normalize_instrument_type(new_type, new_name)

        new_principal = float(new_principal_amount)
        new_rate = float(new_interest_rate_pct)
        new_period = float(new_interest_period_years)
        if new_principal <= 0 or new_period <= 0:
            return {"status": "error", "message": "Principal and interest period must be greater than zero."}

        if new_type == "PPF":
            new_period = 1.0 / 12.0

        # Validate dates early.
        datetime.strptime(str(new_purchase_date), "%Y-%m-%d")
        datetime.strptime(str(new_maturity_date), "%Y-%m-%d")

        conn = db.get_connection()
        try:
            updated = conn.execute(
                """
                UPDATE fd_bond_holdings
                SET instrument_name = ?,
                    instrument_type = ?,
                    purchase_date = CAST(? AS DATE),
                    principal_amount = CAST(? AS DECIMAL(18,4)),
                    interest_rate_pct = CAST(? AS DECIMAL(10,4)),
                    interest_period_years = CAST(? AS DECIMAL(10,4)),
                    payout_method = ?,
                    maturity_date = CAST(? AS DATE)
                WHERE instrument_name = ?
                  AND instrument_type = ?
                  AND purchase_date = CAST(? AS DATE)
                  AND principal_amount = CAST(? AS DECIMAL(18,4))
                  AND interest_rate_pct = CAST(? AS DECIMAL(10,4))
                  AND interest_period_years = CAST(? AS DECIMAL(10,4))
                  AND payout_method = ?
                  AND maturity_date = CAST(? AS DATE)
                RETURNING instrument_name;
                """,
                [
                    new_name,
                    new_type,
                    new_purchase_date,
                    round(new_principal, 4),
                    round(new_rate, 4),
                    round(new_period, 4),
                    "Cumulative" if new_type == "PPF" else str(new_payout_method or "").strip().title(),
                    new_maturity_date,
                    str(old_instrument_name or "").strip(),
                    str(old_instrument_type or "").strip().title() if str(old_instrument_type or "").strip() else _classify_instrument(str(old_instrument_name or "")),
                    old_purchase_date,
                    round(float(old_principal_amount), 4),
                    round(float(old_interest_rate_pct), 4),
                    round(float(old_interest_period_years), 4),
                    str(old_payout_method or "").strip().title(),
                    old_maturity_date,
                ],
            ).fetchone()
        finally:
            conn.close()

        if not updated:
            return {"status": "error", "message": "FD/Bond row not found for update."}

        return {"status": "success", "message": "FD/Bond row updated successfully."}
    except ValueError:
        return {"status": "error", "message": "Dates must be in YYYY-MM-DD format."}
    except Exception as e:
        logger.error(f"Error updating FD/Bond row: {e}")
        return {"status": "error", "message": str(e)}


def _ppf_rate_for_date(rates: list[tuple[date, float]], as_of: date) -> float:
    selected = rates[0][1]
    for effective_from, annual_rate_pct in rates:
        if effective_from <= as_of:
            selected = annual_rate_pct
        else:
            break
    return selected


def _compute_ppf_terminal_value(
    txns: list[tuple[date, str, float]],
    rates: list[tuple[date, float]],
    as_on: date,
) -> tuple[float, float]:
    if not txns:
        return 0.0, 0.0

    first_txn_date = txns[0][0]
    month_cursor = date(first_txn_date.year, first_txn_date.month, 1)
    tx_idx = 0
    balance = 0.0
    pending_interest = 0.0

    while month_cursor <= as_on:
        month_end = _end_of_month(month_cursor)
        if month_end > as_on:
            month_end = as_on

        month_events: list[tuple[date, str, float]] = []
        while tx_idx < len(txns) and txns[tx_idx][0] <= month_end:
            month_events.append(txns[tx_idx])
            tx_idx += 1

        delta_upto_5 = 0.0
        month_delta = 0.0
        for txn_date, txn_type, amount in month_events:
            if txn_type == "Deposit":
                delta = amount
            elif txn_type == "Withdrawal":
                delta = -amount
            else:
                delta = 0.0

            month_delta += delta
            if txn_date.day <= 5:
                delta_upto_5 += delta

        balance_after_5 = balance + delta_upto_5
        month_end_balance = balance + month_delta
        eligible_balance = min(balance_after_5, month_end_balance)

        if eligible_balance > 0:
            annual_rate_pct = _ppf_rate_for_date(rates, month_end)
            pending_interest += eligible_balance * (annual_rate_pct / 100.0) / 12.0

        balance = month_end_balance
        if month_end.month == 3 and month_end.day == 31:
            balance += pending_interest
            pending_interest = 0.0

        month_cursor = date(
            month_cursor.year + (1 if month_cursor.month == 12 else 0),
            1 if month_cursor.month == 12 else month_cursor.month + 1,
            1,
        )

    return max(0.0, balance + pending_interest), pending_interest


def _build_ppf_holdings_rows(as_on: date, start_entry_id: int) -> list[dict]:
    conn = db.get_connection()
    try:
        _ensure_ppf_tables(conn)
        rates = conn.execute(
            """
            SELECT effective_from, CAST(annual_rate_pct AS DOUBLE) AS annual_rate_pct
            FROM ppf_interest_rates
            ORDER BY effective_from;
            """
        ).fetchall()

        txn_rows = conn.execute(
            """
            SELECT
                account_name,
                txn_date,
                txn_type,
                CAST(amount AS DOUBLE) AS amount
            FROM ppf_transactions
            WHERE txn_date <= CAST(? AS DATE)
            ORDER BY account_name, txn_date, txn_type;
            """,
            [as_on.isoformat()],
        ).fetchall()
    finally:
        conn.close()

    if not rates or not txn_rows:
        return []

    grouped: dict[str, list[tuple[date, str, float]]] = {}
    for account_name, txn_date, txn_type, amount in txn_rows:
        grouped.setdefault(str(account_name), []).append(
            (txn_date, str(txn_type or "Deposit"), float(amount or 0.0))
        )

    rows: list[dict] = []
    next_entry_id = start_entry_id
    for account_name in sorted(grouped.keys()):
        account_txns = grouped[account_name]
        if not account_txns:
            continue

        deposits = sum(amount for _, txn_type, amount in account_txns if txn_type == "Deposit")
        withdrawals = sum(amount for _, txn_type, amount in account_txns if txn_type == "Withdrawal")
        net_invested = deposits - withdrawals

        terminal_value, accrued_interest = _compute_ppf_terminal_value(account_txns, rates, as_on)

        cf_dates = [d for d, t, _ in account_txns if t in {"Deposit", "Withdrawal"}]
        cf_amounts = [(-a if t == "Deposit" else a) for _, t, a in account_txns if t in {"Deposit", "Withdrawal"}]
        if cf_dates:
            cf_dates.append(as_on)
            cf_amounts.append(terminal_value)
        xirr_pct = _safe_xirr(cf_dates, cf_amounts) if cf_dates else 0.0

        abs_gain_pct = ((terminal_value / net_invested) - 1.0) * 100.0 if net_invested > 0 else 0.0
        latest_rate_pct = _ppf_rate_for_date(rates, as_on)

        rows.append(
            {
                "entry_id": next_entry_id,
                "instrument_name": account_name,
                "instrument_type": "PPF",
                "purchase_date": account_txns[0][0].isoformat(),
                "maturity_date": "",
                "principal_amount": float(max(net_invested, 0.0)),
                "interest_rate_pct": float(latest_rate_pct),
                "interest_period_years": float(1.0 / 12.0),
                "payout_method": "Cumulative",
                "current_value": float(terminal_value),
                "abs_gain_pct": float(abs_gain_pct),
                "xirr_pct": float(xirr_pct),
                "status": f"Active (accrued interest: {accrued_interest:.2f})",
                "can_edit": False,
                "can_delete": False,
            }
        )
        next_entry_id += 1

    return rows


def get_fd_bond_holdings() -> dict:
    conn = db.get_connection()
    try:
        _ensure_ppf_tables(conn)
        rows = conn.execute(
            """
            SELECT
                instrument_name,
                COALESCE(instrument_type, CASE
                    WHEN UPPER(instrument_name) LIKE '%PPF%' OR UPPER(instrument_name) LIKE '%PUBLIC PROVIDENT%' THEN 'PPF'
                    WHEN UPPER(instrument_name) LIKE '%FD%' OR UPPER(instrument_name) LIKE '%FIXED%' OR UPPER(instrument_name) LIKE '%DEPOSIT%' THEN 'FD'
                    ELSE 'Bond'
                END) AS instrument_type,
                purchase_date,
                maturity_date,
                CAST(principal_amount AS DOUBLE) AS principal_amount,
                CAST(interest_rate_pct AS DOUBLE) AS interest_rate_pct,
                CAST(interest_period_years AS DOUBLE) AS interest_period_years,
                payout_method
            FROM fd_bond_holdings
            ORDER BY maturity_date, purchase_date, instrument_name
            """
        ).fetchall()
    finally:
        conn.close()

    today = date.today()
    payload_rows: list[dict] = []

    total_invested = 0.0
    total_current = 0.0

    for row_num, (
        instrument_name,
        instrument_type,
        purchase_date,
        maturity_date,
        principal_amount,
        interest_rate_pct,
        interest_period_years,
        payout_method,
    ) in enumerate(rows, start=1):
        purchase_dt = purchase_date
        maturity_dt = maturity_date
        principal = float(principal_amount or 0.0)
        annual_rate = float(interest_rate_pct or 0.0) / 100.0
        period_years = float(interest_period_years or 0.0)
        payout = str(payout_method or "Cumulative")

        terminal_dt = min(today, maturity_dt)

        if payout.lower() == "periodic":
            terminal_value, coupons = _periodic_terminal_value(
                principal=principal,
                annual_rate=annual_rate,
                purchase_dt=purchase_dt,
                terminal_dt=terminal_dt,
                period_years=period_years,
            )

            cf_dates = [purchase_dt]
            cf_amounts = [-principal]
            for d, a in coupons:
                cf_dates.append(d)
                cf_amounts.append(a)
            cf_dates.append(terminal_dt)
            cf_amounts.append(terminal_value)
        else:
            years_elapsed = max(0.0, (terminal_dt - purchase_dt).days / 365.0)
            terminal_value = principal + (principal * annual_rate * years_elapsed)
            cf_dates = [purchase_dt, terminal_dt]
            cf_amounts = [-principal, terminal_value]

        xirr_pct = _safe_xirr(cf_dates, cf_amounts)
        abs_gain_pct = ((terminal_value / principal) - 1.0) * 100.0 if principal else 0.0

        payload_rows.append(
            {
                "entry_id": row_num,
                "instrument_name": str(instrument_name or ""),
                "instrument_type": _normalize_instrument_type(str(instrument_type or ""), str(instrument_name or "")),
                "purchase_date": purchase_dt.isoformat() if purchase_dt else "",
                "maturity_date": maturity_dt.isoformat() if maturity_dt else "",
                "principal_amount": principal,
                "interest_rate_pct": float(interest_rate_pct or 0.0),
                "interest_period_years": period_years,
                "payout_method": payout,
                "current_value": float(terminal_value),
                "abs_gain_pct": float(abs_gain_pct),
                "xirr_pct": float(xirr_pct),
                "status": "Matured" if today >= maturity_dt else "Active",
                "can_edit": True,
                "can_delete": True,
            }
        )

        total_invested += principal
        total_current += float(terminal_value)

    ppf_rows = _build_ppf_holdings_rows(today, start_entry_id=len(payload_rows) + 1)
    payload_rows.extend(ppf_rows)
    for ppf_row in ppf_rows:
        total_invested += float(ppf_row["principal_amount"])
        total_current += float(ppf_row["current_value"])

    total_abs_gain_pct = ((total_current / total_invested) - 1.0) * 100.0 if total_invested else 0.0

    total_xirr = 0.0
    if payload_rows:
        dates = [datetime.strptime(row["purchase_date"], "%Y-%m-%d").date() for row in payload_rows]
        amounts = [-float(row["principal_amount"]) for row in payload_rows]
        dates.append(today)
        amounts.append(total_current)
        total_xirr = _safe_xirr(dates, amounts)

    return {
        "rows": payload_rows,
        "as_on_date": today.isoformat(),
        "grand_totals": {
            "invested_amount": float(total_invested),
            "current_value": float(total_current),
            "abs_gain_pct": float(total_abs_gain_pct),
            "xirr_pct": float(total_xirr),
        },
    }
