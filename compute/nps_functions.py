# Functions for storing and computing NPS (National Pension System) holdings and transactions.
import logging, io, base64, csv, re, asyncio
from datetime import date, datetime
import polars as pl
import httpx
import pyxirr
import duckdb

try:
    from . import db_duckdb as db
except ImportError:
    import db_duckdb as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NPSNAV_DETAIL_URL = "https://npsnav.in/api/detailed/{scheme_id}"


# *** Ingest the SchemeName -> SchemeID mapping (from an npsnav.in "daily NAV data" export) ***
def ingest_nps_scheme_master(file_name: str, file_content_b64: str) -> dict:
    """
    Parse a tab-separated npsnav.in "daily NAV data" export (columns: ID, DATE OF NAV, PFM NAME,
    SCHEME ID, SCHEME NAME, NAV VALUE - despite the .xls extension it's plain TSV text) and store
    it as the SchemeName -> SchemeID reference table used to resolve scheme names found on Protean
    statements to the ID needed for https://npsnav.in/api/detailed/<SchemeID>.
    """
    try:
        if "base64," in file_content_b64:
            file_content_b64 = file_content_b64.split("base64,", 1)[1]
        text = base64.b64decode(file_content_b64).decode("utf-8-sig")

        df = pl.read_csv(io.StringIO(text), separator="\t", has_header=True)

        required_columns = ["SCHEME ID", "SCHEME NAME", "PFM NAME", "NAV VALUE", "DATE OF NAV"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return {"status": "error", "message": f"Missing required columns: {', '.join(missing_columns)}"}

        df = (
            df.select(
                pl.col("SCHEME ID").cast(pl.Utf8).alias("scheme_id"),
                pl.col("PFM NAME").cast(pl.Utf8).alias("pfm_name"),
                pl.col("SCHEME NAME").cast(pl.Utf8).alias("scheme_name"),
                pl.col("NAV VALUE").cast(pl.Float64).alias("nav"),
                pl.col("DATE OF NAV").str.strptime(pl.Date, format="%d-%m-%Y", strict=False).alias("nav_dt"),
            )
            .unique(subset=["scheme_id"], keep="last")
        )

        conn = db.get_connection()
        try:
            conn.execute(
                """
                INSERT INTO nps_scheme_master BY NAME
                SELECT * FROM df
                ON CONFLICT (scheme_id) DO UPDATE SET
                    pfm_name = excluded.pfm_name,
                    scheme_name = excluded.scheme_name,
                    nav = excluded.nav,
                    nav_dt = excluded.nav_dt;
                """
            )
        finally:
            conn.close()

        return {"status": "success", "message": f"Loaded {df.height} NPS scheme mappings from {file_name}."}
    except Exception as e:
        logger.error(f"Error ingesting NPS scheme master: {e}")
        return {"status": "error", "message": str(e)}


# *** Scheme name matching (Protean statement scheme text -> npsnav.in scheme_id) ***
_STOPWORDS = {
    "NPS", "TRUST", "A", "C", "AC", "PENSION", "FUND", "FUNDS", "MANAGEMENT", "COMPANY",
    "PRIVATE", "PVT", "LTD", "LIMITED", "SCHEME", "TIER", "I", "II", "GS", "DIRECT", "POP",
}


def _brand_tokens(name: str) -> frozenset:
    s = re.sub(r"[^A-Z0-9\s]", " ", name.upper())
    tokens = [t for t in s.split() if t not in _STOPWORDS and not re.fullmatch(r"[ECGA]", t)]
    return frozenset(tokens)


def _extract_tier(name: str) -> str:
    s = name.upper()
    if re.search(r"TIER\s*II\b", s) or re.search(r"TIER\s*2\b", s):
        return "II"
    if re.search(r"TIER\s*I\b", s) or re.search(r"TIER\s*1\b", s):
        return "I"
    return ""


def _extract_scheme_letter(name: str):
    m = re.search(r"SCHEME\s+([ECGA])\b", name.upper())
    return m.group(1) if m else None


def _match_scheme_id(scheme_name: str, master_rows: list[dict]):
    """
    Best-effort match of a raw scheme name (as it appears on a Protean statement) to a scheme_id
    in nps_scheme_master. Matches on (tier, scheme letter E/C/G/A, brand-word overlap), then prefers
    the DIRECT channel variant over the plain/POP variant over the GS (government-sector) variant,
    since NPS contributions in this app are assumed to come via the retail eNPS/Direct channel.
    Returns None if nothing matches (holdings for that scheme simply won't have a live NAV).
    """
    target_tier = _extract_tier(scheme_name)
    target_letter = _extract_scheme_letter(scheme_name)
    target_brand = _brand_tokens(scheme_name)

    candidates = []
    for row in master_rows:
        cand_name = row["scheme_name"]
        if _extract_tier(cand_name) != target_tier:
            continue
        cand_letter = _extract_scheme_letter(cand_name)
        if target_letter:
            if cand_letter != target_letter:
                continue
        elif cand_letter is not None:
            continue

        overlap = len(target_brand & _brand_tokens(cand_name))
        if overlap == 0:
            continue

        upper = cand_name.upper()
        if "DIRECT" in upper:
            rank = 0
        elif re.search(r"\bGS\b", upper):
            rank = 2
        else:
            rank = 1
        candidates.append((rank, -overlap, row["scheme_id"]))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


# *** Ingest a Protean NPS transaction statement CSV ***
def _parse_num(raw: str) -> float:
    s = raw.strip()
    if not s:
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    s = s.replace(",", "")
    try:
        value = float(s)
    except ValueError:
        return 0.0
    return -value if neg else value


def _parse_nps_statement(csv_text: str) -> tuple[str, list[dict]]:
    rows = list(csv.reader(io.StringIO(csv_text)))

    pran = ""
    for row in rows:
        if row and row[0].strip() == "PRAN" and len(row) > 1:
            pran = row[1].strip().lstrip("'").strip()
            break

    if not pran:
        raise ValueError("Could not find PRAN in statement")

    start_idx = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == "Transaction Details":
            start_idx = i + 1
            break

    if start_idx is None:
        raise ValueError("Could not find the Transaction Details table in statement")

    def _parse_scheme_header(header: list[str]) -> list[tuple[str, int, int, int]]:
        # Columns 0/1 are always Date/Particulars, but the number of columns between Particulars
        # and the first scheme's Amount column varies (some files have a "Withdrawal/deduction..."
        # column there, some don't) - so anchor on the "... Amount (Rs)" suffix rather than a fixed
        # offset. NAV and Units are always the two columns immediately following a scheme's Amount
        # column.
        cols = []
        i = 2
        n = len(header)
        while i < n:
            raw_title = header[i].strip()
            if re.search(r"Amount\s*\(Rs\)\s*$", raw_title, flags=re.I):
                scheme_name = re.sub(r"\s*Amount\s*\(Rs\)\s*$", "", raw_title, flags=re.I).strip()
                if i + 2 < n:
                    cols.append((scheme_name, i, i + 1, i + 2))
                i += 3
            else:
                i += 1
        return cols

    records = []
    scheme_cols: list[tuple[str, int, int, int]] = []

    for row in rows[start_idx:]:
        if len(row) < 2:
            continue

        # A mid-year PFM/scheme-preference change starts a second transaction table with its own
        # scheme columns, but Protean doesn't print a new "Transaction Details" marker before it -
        # just a bare Date/Particulars header row (see 110037291972_2025.csv, where the account
        # switched from SBI to HDFC in April 2024: the SBI table's rows end, then a fresh header
        # with HDFC's scheme names starts). Re-derive scheme_cols whenever such a header appears,
        # rather than assuming the file has only one - otherwise every row after the switch gets
        # silently parsed using the *first* table's (now wrong) column-to-scheme mapping, which
        # misattributes the switched-out balance to the old scheme indefinitely.
        if row[0].strip() == "Date" and len(row) > 1 and row[1].strip() == "Particulars":
            scheme_cols = _parse_scheme_header(row)
            continue

        if not scheme_cols:
            continue

        txn_date_str = row[0].strip()
        particulars = row[1].strip()
        if not txn_date_str or not particulars:
            continue
        if particulars.strip().lower() in ("opening balance", "closing balance"):
            continue

        try:
            txn_date = datetime.strptime(txn_date_str, "%d-%b-%Y").date()
        except ValueError:
            continue

        for scheme_name, amt_i, nav_i, units_i in scheme_cols:
            if amt_i >= len(row):
                continue
            amount_raw = row[amt_i].strip()
            if not amount_raw:
                continue

            units = _parse_num(row[units_i]) if units_i < len(row) else 0.0
            records.append({
                "pran": pran,
                "scheme": scheme_name,
                "txn_date": txn_date,
                "type": "Contribution" if units >= 0 else "Charge",
                "units": units,
                "nav": _parse_num(row[nav_i]) if nav_i < len(row) else 0.0,
                "amount": _parse_num(amount_raw),
                "description": particulars,
            })

    return pran, records


def ingest_nps_transactions(file_name: str, file_content_b64: str) -> dict:
    """
    Decode a base64-encoded Protean NPS transaction statement CSV, insert any not-yet-seen rows
    into nps_trans (keyed by pran+scheme+txn_date+description+units), and recompute running
    balance/residual_units for the whole table.
    """
    try:
        if "base64," in file_content_b64:
            file_content_b64 = file_content_b64.split("base64,", 1)[1]
        csv_text = base64.b64decode(file_content_b64).decode("utf-8-sig")

        pran, records = _parse_nps_statement(csv_text)

        if not records:
            return {"status": "success", "message": f"No transactions found in {file_name}."}

        df = pl.DataFrame(records).with_columns(
            pl.col("pran").cast(pl.Utf8),
            pl.col("scheme").cast(pl.Utf8),
            pl.col("txn_date").cast(pl.Date),
            pl.col("type").cast(pl.Utf8),
            pl.col("units").cast(pl.Float64),
            pl.col("nav").cast(pl.Float64),
            pl.col("amount").cast(pl.Float64),
            pl.col("description").cast(pl.Utf8),
            pl.lit(file_name).alias("source_file"),
        )

        conn = db.get_connection()
        try:
            inserted = conn.execute(
                """
                INSERT INTO nps_trans
                BY NAME
                SELECT * FROM df
                ON CONFLICT (pran, scheme, txn_date, description, units) DO NOTHING
                RETURNING pran;
                """
            ).fetchall()

            _recompute_nps_derived(conn)
        finally:
            conn.close()

        return {
            "status": "success",
            "message": f"NPS transaction import for PRAN {pran}: {df.height} rows in file, {len(inserted)} new rows added.",
        }
    except Exception as e:
        logger.error(f"Error ingesting NPS transactions: {e}")
        return {"status": "error", "message": str(e)}


def _recompute_nps_derived(conn: duckdb.DuckDBPyConnection) -> None:
    """
    Recompute running balance (cumulative units) and residual_units (FIFO-style, approximating
    consumption of contributions by later charge/rebalancing deductions - same formula used for
    MF and Equity transactions) for every row in nps_trans, ordered by (pran, scheme, txn_date).
    """
    trans_df = conn.sql("SELECT pran, scheme, txn_date, description, units FROM nps_trans").pl()
    if trans_df.height == 0:
        return

    derived_df = (
        trans_df.with_columns(
            balance=pl.col("units")
            .cum_sum()
            .over(["pran", "scheme"], order_by=[pl.col("txn_date")]),
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
                            .over(["pran", "scheme"], order_by=[pl.col("txn_date")])
                            + pl.when(pl.col("units") < 0)
                            .then(pl.col("units"))
                            .otherwise(pl.lit(0.0))
                            .sum()
                            .over(["pran", "scheme"])
                        ),
                        pl.lit(0.0),
                    ),
                    pl.col("units"),
                )
            ),
        )
        .select("pran", "scheme", "txn_date", "description", "units", "balance", "residual_units")
    )

    conn.execute(
        """
        UPDATE nps_trans
        SET balance = derived_df.balance, residual_units = derived_df.residual_units
        FROM derived_df
        WHERE nps_trans.pran = derived_df.pran
          AND nps_trans.scheme = derived_df.scheme
          AND nps_trans.txn_date = derived_df.txn_date
          AND nps_trans.description = derived_df.description
          AND nps_trans.units = derived_df.units;
        """
    )


# *** Refresh NAV via npsnav.in ***
async def _fetch_all(urls: list[str]) -> list[dict | None]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        for r in responses:
            if isinstance(r, httpx.Response) and r.status_code == 200:
                try:
                    results.append(r.json())
                except Exception:
                    results.append(None)
            else:
                results.append(None)
        return results


def refresh_nps_nav() -> dict:
    try:
        conn = db.get_connection()
        try:
            schemes = [row[0] for row in conn.execute("SELECT DISTINCT scheme FROM nps_trans").fetchall()]
            master_rows = conn.execute("SELECT scheme_id, scheme_name FROM nps_scheme_master").pl().to_dicts()
        finally:
            conn.close()

        if not schemes:
            return {"status": "success", "message": "No NPS schemes to refresh."}

        scheme_ids = {scheme: _match_scheme_id(scheme, master_rows) for scheme in schemes}
        matched = [(scheme, sid) for scheme, sid in scheme_ids.items() if sid]
        unmatched = [scheme for scheme, sid in scheme_ids.items() if not sid]

        if not matched:
            return {"status": "success", "message": f"Could not resolve a npsnav.in scheme ID for any of {len(schemes)} scheme(s)."}

        urls = [NPSNAV_DETAIL_URL.format(scheme_id=sid) for _, sid in matched]
        responses = asyncio.run(_fetch_all(urls))

        rows = []
        for (scheme, scheme_id), resp in zip(matched, responses):
            if not resp:
                continue
            nav = resp.get("NAV")
            last_updated = resp.get("Last Updated")
            try:
                nav_val = float(nav) if nav is not None else None
            except (TypeError, ValueError):
                nav_val = None
            try:
                nav_dt = datetime.strptime(last_updated, "%d-%m-%Y").date() if last_updated else None
            except ValueError:
                nav_dt = None
            if nav_val is None:
                continue
            rows.append({"scheme": scheme, "scheme_id": scheme_id, "nav": nav_val, "nav_dt": nav_dt})

        if not rows:
            return {"status": "success", "message": "npsnav.in returned no usable NAV data."}

        master_df = pl.DataFrame(rows)

        conn = db.get_connection()
        try:
            conn.execute(
                """
                INSERT INTO nps_master
                BY NAME
                SELECT * FROM master_df
                ON CONFLICT (scheme) DO UPDATE SET
                    scheme_id = excluded.scheme_id,
                    nav = excluded.nav,
                    nav_dt = excluded.nav_dt;
                """
            )
        finally:
            conn.close()

        message = f"Refreshed NAV for {len(rows)} of {len(schemes)} scheme(s)."
        if unmatched:
            message += f" Could not resolve scheme ID for: {', '.join(unmatched)}."

        return {"status": "success", "message": message}
    except Exception as e:
        logger.error(f"Error refreshing NPS NAV: {e}")
        return {"status": "error", "message": str(e)}


# *** Compute XIRR ***
def _safe_xirr(dates: list, amounts: list[float]) -> float:
    if len(dates) < 2 or len(amounts) < 2:
        return 0.0
    if not any(a < 0 for a in amounts) or not any(a > 0 for a in amounts):
        return 0.0
    try:
        result = pyxirr.xirr(dates, amounts)
        return result * 100.0 if result is not None else 0.0
    except Exception:
        return 0.0


def compute_nps_xirr() -> None:
    conn = db.get_connection()
    try:
        trans_df = conn.execute(
            "SELECT scheme, pran, txn_date, nav, residual_units FROM nps_trans WHERE residual_units > 0"
        ).pl()
        master_df = conn.execute(
            "SELECT scheme, nav, nav_dt FROM nps_master WHERE nav IS NOT NULL"
        ).pl()
    finally:
        conn.close()

    if trans_df.height == 0:
        conn = db.get_connection()
        try:
            conn.execute("DELETE FROM nps_xirr")
        finally:
            conn.close()
        return

    lf_investment_cf = trans_df.lazy().select(
        "scheme",
        "pran",
        pl.col("txn_date"),
        (-(pl.col("nav").cast(pl.Float64) * pl.col("residual_units").cast(pl.Float64))).alias("cashflow_amount"),
    )

    lf_terminal_cf = (
        trans_df.lazy()
        .group_by("scheme", "pran")
        .agg(pl.col("residual_units").cast(pl.Float64).sum().alias("total_units"))
        .join(master_df.lazy(), on="scheme", how="inner")
        .select(
            "scheme",
            "pran",
            pl.col("nav_dt").alias("txn_date"),
            (pl.col("total_units") * pl.col("nav").cast(pl.Float64)).alias("cashflow_amount"),
        )
    )

    lf_cashflows = pl.concat([lf_investment_cf, lf_terminal_cf], how="vertical")

    def _build_xirr_level(cashflows: pl.LazyFrame, group_cols: list[str], level_name: str) -> pl.LazyFrame:
        effective_group_cols = group_cols if group_cols else ["_nps_total_group"]
        level_cashflows = (
            cashflows.with_columns(pl.lit("nps_total").alias("_nps_total_group"))
            if not group_cols
            else cashflows
        )

        lf = (
            level_cashflows.group_by(effective_group_cols + ["txn_date"])
            .agg(pl.col("cashflow_amount").sum().alias("cashflow_amount"))
            .group_by(effective_group_cols)
            .agg(
                pl.col("txn_date").sort().alias("dates"),
                pl.col("cashflow_amount").sort_by("txn_date").alias("amounts"),
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
        if "pran" not in group_cols:
            lf = lf.with_columns(pl.lit("").alias("pran"))

        return lf.select("level", "scheme", "pran", "xirr_pct")

    lf_scheme_pran = _build_xirr_level(lf_cashflows, ["scheme", "pran"], "scheme_pran")
    lf_scheme = _build_xirr_level(lf_cashflows, ["scheme"], "scheme")
    lf_total = _build_xirr_level(lf_cashflows, [], "nps_total")

    xirr_df = pl.concat([lf_scheme_pran, lf_scheme, lf_total], how="vertical").collect()
    xirr_df = xirr_df.with_columns(pl.lit(date.today()).alias("as_on_date"))

    conn = db.get_connection()
    try:
        conn.execute("DELETE FROM nps_xirr")
        conn.execute("INSERT INTO nps_xirr SELECT level, scheme, pran, xirr_pct, as_on_date FROM xirr_df")
    finally:
        conn.close()


# *** Get Holding statement ***
def get_nps_holdings() -> dict:
    """Generate NPS holdings (grouped by scheme -> PRAN), live from nps_trans/nps_master/nps_xirr,
    matching how get_mf_holdings()/get_equity_holdings() build their trees."""

    conn = db.get_connection()
    try:
        trans_df = conn.execute(
            """
            SELECT scheme, pran,
                   SUM(residual_units) AS total_units,
                   SUM(residual_units * nav) AS invested_amount
            FROM nps_trans
            GROUP BY scheme, pran
            """
        ).pl()
        master_df = conn.execute("SELECT scheme, nav, nav_dt FROM nps_master").pl()
        xirr_df = conn.execute("SELECT level, scheme, pran, xirr_pct FROM nps_xirr").pl()
    finally:
        conn.close()

    empty_result = {
        "tree_rows": [],
        "grand_totals": {"invested_amount": 0.0, "current_value": 0.0, "abs_gain_pct": 0.0, "xirr_pct": 0.0},
    }

    if trans_df.height == 0:
        return empty_result

    xirr_scheme_pran = xirr_df.filter(pl.col("level") == "scheme_pran").select("scheme", "pran", "xirr_pct")
    xirr_scheme = xirr_df.filter(pl.col("level") == "scheme").select("scheme", "xirr_pct")
    xirr_total = xirr_df.filter(pl.col("level") == "nps_total").select("xirr_pct")

    holdings = (
        trans_df.with_columns(
            pl.col("total_units").cast(pl.Float64),
            pl.col("invested_amount").cast(pl.Float64),
        )
        .join(master_df, on="scheme", how="left")
        .join(xirr_scheme_pran, on=["scheme", "pran"], how="left")
        .with_columns(
            pl.col("xirr_pct").fill_null(0.0),
            pl.col("nav").fill_null(0.0).cast(pl.Float64),
        )
        .with_columns(current_value=pl.col("total_units") * pl.col("nav"))
        .with_columns(
            abs_gain_pct=pl.when(pl.col("invested_amount") != 0)
            .then((pl.col("current_value") / pl.col("invested_amount") - 1.0) * 100.0)
            .otherwise(0.0),
            nav_dt=pl.col("nav_dt").cast(pl.Utf8),
            scheme_or_pran=pl.col("pran"),
        )
    )

    # Drop zero-balance PRAN rows (e.g. fully withdrawn or switched to another PFM) from the
    # holdings report - the underlying transactions and XIRR are still tracked, this only affects
    # what's displayed. A scheme where every PRAN nets to zero simply won't produce a group below.
    holdings = holdings.filter(pl.col("total_units").abs() > 1e-6)

    tree = (
        holdings.group_by("scheme")
        .agg(
            total_units=pl.col("total_units").sum(),
            invested_amount=pl.col("invested_amount").sum(),
            current_value=pl.col("current_value").sum(),
            nav=pl.col("nav").drop_nulls().first(),
            nav_dt=pl.col("nav_dt").drop_nulls().first(),
            _children=pl.struct(
                [
                    "scheme_or_pran",
                    "pran",
                    "total_units",
                    "invested_amount",
                    "current_value",
                    "abs_gain_pct",
                    "xirr_pct",
                    "nav",
                    "nav_dt",
                ]
            ),
        )
        .with_columns(
            scheme_or_pran=pl.col("scheme"),
            abs_gain_pct=pl.when(pl.col("invested_amount") != 0)
            .then((pl.col("current_value") / pl.col("invested_amount") - 1.0) * 100.0)
            .otherwise(0.0),
        )
        .join(xirr_scheme, on="scheme", how="left")
        .with_columns(pl.col("xirr_pct").fill_null(0.0))
        .select(
            [
                "scheme_or_pran",
                "scheme",
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


# Get Transaction details for a given scheme-PRAN
def get_nps_transactions(scheme: str = "", pran: str = "") -> dict:
    try:
        conn = db.get_connection()
        try:
            payload = conn.execute(
                """
                SELECT
                    scheme, pran,
                    CAST(txn_date AS VARCHAR) AS txn_date,
                    type,
                    CAST(units AS DOUBLE) AS units,
                    CAST(residual_units AS DOUBLE) AS residual_units,
                    CAST(nav AS DOUBLE) AS nav,
                    CAST(amount AS DOUBLE) AS amount,
                    CAST(balance AS DOUBLE) AS balance,
                    COALESCE(description, '') AS description,
                    COALESCE(source_file, '') AS source_file
                FROM nps_trans
                WHERE scheme ILIKE ? AND pran ILIKE ?
                ORDER BY txn_date
                """,
                [f"%{scheme}%", f"%{pran}%"],
            ).pl().to_dicts()
        finally:
            conn.close()

        return {
            "status": "success",
            "message": f"{len(payload)} transactions found for scheme pattern '{scheme}' and PRAN pattern '{pran}'.",
            "payload": payload,
        }
    except Exception as e:
        logger.error(f"Error fetching NPS transaction details: {e}")
        return {"status": "error", "message": str(e), "payload": []}


if __name__ == "__main__":
    from pathlib import Path

    ROOT = Path(__file__).parent.parent
    nps_dir = ROOT / "data" / "nps"

    for csv_path in sorted(nps_dir.glob("*.csv")):
        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()
        result = ingest_nps_transactions(csv_path.name, base64.b64encode(content.encode("utf-8")).decode("ascii"))
        print(csv_path.name, result)

    print(refresh_nps_nav())
    compute_nps_xirr()
    from pprint import pprint
    pprint(get_nps_holdings())
