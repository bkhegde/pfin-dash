# Functions for storing and computing Sovereign Gold Bond (SGB) holdings.
import logging
from datetime import date, datetime

import pyxirr

try:
    from . import db_duckdb as db
except ImportError:
    import db_duckdb as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_GOLD_PRICE_KEY = "gold_price"


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


def _get_gold_price(conn) -> float:
    row = conn.execute(
        "SELECT setting_value FROM sgb_settings WHERE setting_key = ?",
        [_GOLD_PRICE_KEY],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def set_sgb_gold_price(gold_price: float) -> dict:
    try:
        price = float(gold_price)
        if price < 0:
            return {"status": "error", "message": "Gold price cannot be negative."}

        conn = db.get_connection()
        try:
            conn.execute(
                """
                INSERT INTO sgb_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT (setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at;
                """,
                [_GOLD_PRICE_KEY, price, datetime.now()],
            )
        finally:
            conn.close()

        return {"status": "success", "message": "Gold price updated successfully."}
    except Exception as e:
        logger.error(f"Error updating SGB gold price: {e}")
        return {"status": "error", "message": str(e)}


def add_sgb_holding(sgb_name: str, purchase_date: str, units: float, purchase_price: float) -> dict:
    try:
        sgb_name_value = str(sgb_name or "").strip()
        if not sgb_name_value:
            return {"status": "error", "message": "SGB name is required."}

        purchase_dt = datetime.strptime(str(purchase_date), "%Y-%m-%d").date()
        units_value = float(units)
        purchase_price_value = float(purchase_price)

        if units_value <= 0:
            return {"status": "error", "message": "Units must be greater than zero."}
        if purchase_price_value <= 0:
            return {"status": "error", "message": "Purchase price must be greater than zero."}

        conn = db.get_connection()
        try:
            next_id_row = conn.execute("SELECT COALESCE(MAX(entry_id), 0) + 1 FROM sgb_holdings").fetchone()
            next_id = int(next_id_row[0] if next_id_row else 1)

            conn.execute(
                """
                INSERT INTO sgb_holdings (entry_id, sgb_name, purchase_date, units, purchase_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                [next_id, sgb_name_value, purchase_dt, units_value, purchase_price_value],
            )
        finally:
            conn.close()

        return {"status": "success", "message": "SGB holding added successfully."}
    except ValueError:
        return {"status": "error", "message": "Purchase date must be in YYYY-MM-DD format."}
    except Exception as e:
        logger.error(f"Error adding SGB holding: {e}")
        return {"status": "error", "message": str(e)}


def delete_sgb_holding(entry_id: int) -> dict:
    try:
        conn = db.get_connection()
        try:
            deleted = conn.execute(
                "DELETE FROM sgb_holdings WHERE entry_id = ? RETURNING entry_id",
                [int(entry_id)],
            ).fetchone()
        finally:
            conn.close()

        if not deleted:
            return {"status": "error", "message": "SGB holding not found."}

        return {"status": "success", "message": "SGB holding deleted successfully."}
    except Exception as e:
        logger.error(f"Error deleting SGB holding: {e}")
        return {"status": "error", "message": str(e)}


def get_sgb_holdings() -> dict:
    conn = db.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                entry_id,
                sgb_name,
                purchase_date,
                CAST(units AS DOUBLE) AS units,
                CAST(purchase_price AS DOUBLE) AS purchase_price
            FROM sgb_holdings
            ORDER BY purchase_date, entry_id
            """
        ).fetchall()

        gold_price = _get_gold_price(conn)
    finally:
        conn.close()

    as_on = date.today()
    payload_rows: list[dict] = []

    total_invested = 0.0
    total_current = 0.0

    for entry_id, sgb_name, purchase_date, units, purchase_price in rows:
        invested_amount = float(units or 0.0) * float(purchase_price or 0.0)
        current_value = float(units or 0.0) * float(gold_price)
        abs_gain_pct = (current_value / invested_amount - 1.0) * 100.0 if invested_amount else 0.0
        xirr_pct = _safe_xirr([purchase_date, as_on], [-invested_amount, current_value])

        payload_rows.append(
            {
                "entry_id": int(entry_id),
                "sgb_name": str(sgb_name or ""),
                "purchase_date": purchase_date.isoformat() if purchase_date else "",
                "units": float(units or 0.0),
                "purchase_price": float(purchase_price or 0.0),
                "invested_amount": invested_amount,
                "current_value": current_value,
                "abs_gain_pct": abs_gain_pct,
                "xirr_pct": xirr_pct,
            }
        )

        total_invested += invested_amount
        total_current += current_value

    total_abs_gain_pct = (total_current / total_invested - 1.0) * 100.0 if total_invested else 0.0

    total_xirr = 0.0
    if payload_rows:
        dates = [datetime.strptime(row["purchase_date"], "%Y-%m-%d").date() for row in payload_rows]
        amounts = [-float(row["invested_amount"]) for row in payload_rows]
        dates.append(as_on)
        amounts.append(total_current)
        total_xirr = _safe_xirr(dates, amounts)

    return {
        "rows": payload_rows,
        "gold_price": float(gold_price),
        "as_on_date": as_on.isoformat(),
        "grand_totals": {
            "invested_amount": float(total_invested),
            "current_value": float(total_current),
            "abs_gain_pct": float(total_abs_gain_pct),
            "xirr_pct": float(total_xirr),
        },
    }
