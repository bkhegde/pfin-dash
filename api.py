import logging
from typing import TypedDict

from compute.eq_functions import (
    compute_equity_xirr,
    delete_equity_transaction,
    get_equity_holdings,
    get_equity_transactions,
    ingest_equity_transactions,
    refresh_equity_ltp,
)
from compute.fd_bond_functions import (
    add_fd_bond_holding,
    delete_ppf_interest_rates,
    delete_ppf_transactions,
    delete_fd_bond_holding,
    get_fd_bond_holdings,
    ingest_fd_bond_holdings,
    ingest_ppf_interest_rates,
    ingest_ppf_transactions,
    update_fd_bond_holding,
)
from compute.mf_functions import (
    compute_xirr,
    delete_transaction as delete_mf_transaction,
    get_folio_list,
    get_mf_holdings,
    get_transaction_details,
    process_cas_pdf,
    refresh_nav,
    update_folio_name,
)
from compute.nps_functions import (
    compute_nps_xirr,
    get_nps_holdings,
    get_nps_transactions,
    ingest_nps_transactions,
    refresh_nps_nav,
)
from compute.sgb_functions import add_sgb_holding, delete_sgb_holding, get_sgb_holdings, set_sgb_gold_price

logger = logging.getLogger(__name__)


class ApiResponse(TypedDict):
    status: str
    message: str
    payload: dict | list | None


class Api:
    @staticmethod
    def _success(message: str, payload=None) -> ApiResponse:
        return {"status": "success", "message": message, "payload": payload}

    @staticmethod
    def _error(message: str, payload=None) -> ApiResponse:
        return {"status": "error", "message": str(message), "payload": payload}

    def mf_get_holdings(self) -> ApiResponse:
        try:
            return self._success("Holdings retrieved successfully.", get_mf_holdings())
        except Exception as e:
            logger.error("Error getting holdings: %s", e)
            return self._error(e)

    def mf_refresh_nav_xirr(self) -> ApiResponse:
        try:
            refresh_nav()
            compute_xirr()
            return self._success("NAV refreshed and XIRR computed successfully.")
        except Exception as e:
            logger.error("Error refreshing NAV: %s", e)
            return self._error(e)

    def mf_process_cas_pdf(self, file_name: str, password: str, file_content: str) -> ApiResponse:
        try:
            result = process_cas_pdf(file_name, password, file_content)
            if result.get("status") != "success":
                return self._error(result.get("message", "CAS PDF processing failed."))

            refresh_nav()
            compute_xirr()
            message = (
                f'{result.get("message", "CAS PDF processed successfully")}. '
                "NAV refreshed and XIRR computed successfully."
            )
            return self._success(message)
        except Exception as e:
            logger.exception("Error processing CAS PDF: %s", e)
            return self._error(e)

    def mf_get_transactions(self, scheme: str = "", folio: str = "") -> ApiResponse:
        try:
            result = get_transaction_details(scheme, folio)
            return self._success(result.get("message", "Transactions retrieved."), result.get("payload"))
        except Exception as e:
            logger.error("Error getting MF transactions: %s", e)
            return self._error(e)

    def mf_get_folio_list(self) -> ApiResponse:
        try:
            result = get_folio_list()
            return self._success(result.get("message", "Fetched folio list."), result.get("payload", []))
        except Exception as e:
            logger.error("Error getting folio list: %s", e)
            return self._error(e, [])

    def mf_update_folio_name(self, folio: str, new_name: str) -> ApiResponse:
        try:
            result = update_folio_name(folio, new_name)
            return self._success(result.get("message", "Folio name updated."), [])
        except Exception as e:
            logger.error("Error updating folio name: %s", e)
            return self._error(e, [])

    def mf_delete_transaction(
        self,
        folio_raw: str,
        isin: str,
        txn_date: str,
        type: str,
        units: float,
        balance: float,
        txn_id: int,
    ) -> ApiResponse:
        try:
            result = delete_mf_transaction(folio_raw, isin, txn_date, type, units, balance, txn_id)
            return self._success(result.get("message", "Transaction deleted."), [])
        except Exception as e:
            logger.error("Error deleting MF transaction: %s", e)
            return self._error(e, [])

    def eq_get_holdings(self) -> ApiResponse:
        try:
            return self._success("Equity holdings retrieved successfully.", get_equity_holdings())
        except Exception as e:
            logger.error("Error getting equity holdings: %s", e)
            return self._error(e)

    def eq_refresh_ltp(self) -> ApiResponse:
        try:
            result = refresh_equity_ltp()
            compute_equity_xirr()
            return self._success(f'{result.get("message")}. XIRR recomputed.')
        except Exception as e:
            logger.error("Error refreshing equity LTP: %s", e)
            return self._error(e)

    def eq_process_transactions_csv(self, file_name: str, file_content: str) -> ApiResponse:
        try:
            result = ingest_equity_transactions(file_name, file_content)
            message = result.get("message", "")
            if result.get("status") == "success":
                refresh_equity_ltp()
                compute_equity_xirr()
                message = f'{message}. LTP refreshed and XIRR computed successfully.'
            return {"status": result.get("status", "error"), "message": message, "payload": None}
        except Exception as e:
            logger.error("Error processing equity transactions CSV: %s", e)
            return self._error(e)

    def eq_get_transactions(self, stock_name: str = "", demat_account: str = "") -> ApiResponse:
        try:
            result = get_equity_transactions(stock_name, demat_account)
            return self._success(result.get("message", "Transactions retrieved."), result.get("payload"))
        except Exception as e:
            logger.error("Error getting equity transactions: %s", e)
            return self._error(e)

    def eq_delete_transaction(self, trans_id: str) -> ApiResponse:
        try:
            result = delete_equity_transaction(trans_id)
            return self._success(result.get("message", "Transaction deleted."), [])
        except Exception as e:
            logger.error("Error deleting equity transaction: %s", e)
            return self._error(e, [])

    def nps_get_holdings(self) -> ApiResponse:
        try:
            return self._success("NPS holdings retrieved successfully.", get_nps_holdings())
        except Exception as e:
            logger.error("Error getting NPS holdings: %s", e)
            return self._error(e)

    def nps_refresh_nav(self) -> ApiResponse:
        try:
            result = refresh_nps_nav()
            compute_nps_xirr()
            return self._success(f'{result.get("message")}. XIRR recomputed.')
        except Exception as e:
            logger.error("Error refreshing NPS NAV: %s", e)
            return self._error(e)

    def nps_process_transactions_csv(self, file_name: str, file_content: str) -> ApiResponse:
        try:
            result = ingest_nps_transactions(file_name, file_content)
            message = result.get("message", "")
            if result.get("status") == "success":
                refresh_nps_nav()
                compute_nps_xirr()
                message = f'{message}. NAV refreshed and XIRR computed successfully.'
            return {"status": result.get("status", "error"), "message": message, "payload": None}
        except Exception as e:
            logger.error("Error processing NPS transactions CSV: %s", e)
            return self._error(e)

    def nps_get_transactions(self, scheme: str = "", pran: str = "") -> ApiResponse:
        try:
            result = get_nps_transactions(scheme, pran)
            return self._success(result.get("message", "Transactions retrieved."), result.get("payload"))
        except Exception as e:
            logger.error("Error getting NPS transactions: %s", e)
            return self._error(e)

    def sgb_get_holdings(self) -> ApiResponse:
        try:
            return self._success("SGB holdings retrieved successfully.", get_sgb_holdings())
        except Exception as e:
            logger.error("Error getting SGB holdings: %s", e)
            return self._error(e)

    def sgb_add_holding(self, sgb_name: str, purchase_date: str, units: float, purchase_price: float) -> ApiResponse:
        try:
            result = add_sgb_holding(sgb_name, purchase_date, units, purchase_price)
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to add SGB holding."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error adding SGB holding: %s", e)
            return self._error(e)

    def sgb_delete_holding(self, entry_id: int) -> ApiResponse:
        try:
            result = delete_sgb_holding(entry_id)
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to delete SGB holding."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error deleting SGB holding: %s", e)
            return self._error(e)

    def sgb_set_gold_price(self, gold_price: float) -> ApiResponse:
        try:
            result = set_sgb_gold_price(gold_price)
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to update gold price."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error updating SGB gold price: %s", e)
            return self._error(e)

    def fd_bond_get_holdings(self) -> ApiResponse:
        try:
            return self._success("FD/Bond holdings retrieved successfully.", get_fd_bond_holdings())
        except Exception as e:
            logger.error("Error getting FD/Bond holdings: %s", e)
            return self._error(e)

    def fd_bond_add_holding(
        self,
        instrument_name: str,
        instrument_type: str,
        purchase_date: str,
        principal_amount: float,
        interest_rate_pct: float,
        interest_period_years: float,
        payout_method: str,
        maturity_date: str,
    ) -> ApiResponse:
        try:
            result = add_fd_bond_holding(
                instrument_name,
                instrument_type,
                purchase_date,
                principal_amount,
                interest_rate_pct,
                interest_period_years,
                payout_method,
                maturity_date,
            )
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to add FD/Bond row."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error adding FD/Bond row: %s", e)
            return self._error(e)

    def fd_bond_process_ppf_csv(self, file_name: str, file_content: str) -> ApiResponse:
        try:
            result = ingest_ppf_transactions(file_name, file_content)
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to process PPF CSV."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error processing PPF CSV: %s", e)
            return self._error(e)

    def fd_bond_process_ppf_rate_csv(self, file_name: str, file_content: str) -> ApiResponse:
        try:
            result = ingest_ppf_interest_rates(file_name, file_content)
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to process PPF rate CSV."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error processing PPF rate CSV: %s", e)
            return self._error(e)

    def fd_bond_delete_ppf_transactions(self) -> ApiResponse:
        try:
            result = delete_ppf_transactions()
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to delete PPF transactions."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error deleting PPF transactions: %s", e)
            return self._error(e)

    def fd_bond_delete_ppf_rates(self) -> ApiResponse:
        try:
            result = delete_ppf_interest_rates()
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to delete PPF rates."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error deleting PPF rates: %s", e)
            return self._error(e)

    def fd_bond_delete_holding(
        self,
        instrument_name: str,
        instrument_type: str,
        purchase_date: str,
        principal_amount: float,
        interest_rate_pct: float,
        interest_period_years: float,
        payout_method: str,
        maturity_date: str,
    ) -> ApiResponse:
        try:
            result = delete_fd_bond_holding(
                instrument_name,
                instrument_type,
                purchase_date,
                principal_amount,
                interest_rate_pct,
                interest_period_years,
                payout_method,
                maturity_date,
            )
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to delete FD/Bond row."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error deleting FD/Bond row: %s", e)
            return self._error(e)

    def fd_bond_update_holding(
        self,
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
    ) -> ApiResponse:
        try:
            result = update_fd_bond_holding(
                old_instrument_name,
                old_instrument_type,
                old_purchase_date,
                old_principal_amount,
                old_interest_rate_pct,
                old_interest_period_years,
                old_payout_method,
                old_maturity_date,
                new_instrument_name,
                new_instrument_type,
                new_purchase_date,
                new_principal_amount,
                new_interest_rate_pct,
                new_interest_period_years,
                new_payout_method,
                new_maturity_date,
            )
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", "Failed to update FD/Bond row."),
                "payload": None,
            }
        except Exception as e:
            logger.error("Error updating FD/Bond row: %s", e)
            return self._error(e)