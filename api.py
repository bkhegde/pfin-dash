
from typing import TypedDict
from asyncio.log import logger
from compute.mf_functions import get_mf_holdings, process_cas_pdf, refresh_nav, compute_xirr, get_transaction_details, get_folio_list, update_folio_name, delete_transaction as delete_mf_transaction
from compute.eq_functions import get_equity_holdings, ingest_equity_transactions, refresh_equity_ltp, compute_equity_xirr, get_equity_transactions, delete_equity_transaction
from compute.nps_functions import get_nps_holdings, ingest_nps_transactions, refresh_nps_nav, compute_nps_xirr, get_nps_transactions
from compute.sgb_functions import get_sgb_holdings, add_sgb_holding, delete_sgb_holding, set_sgb_gold_price
from compute.fd_bond_functions import get_fd_bond_holdings, ingest_fd_bond_holdings, ingest_ppf_transactions, ingest_ppf_interest_rates, add_fd_bond_holding, delete_fd_bond_holding, update_fd_bond_holding

class ApiResponse(TypedDict):
	status: str # "success" or "error"
	message: str 
	payload: dict | list | None

class Api:
	def mf_get_holdings(self) -> ApiResponse:
		try:
			holdings = get_mf_holdings()
			return {"status": "success", "message": "Holdings retrieved successfully.", "payload": holdings}
		except Exception as e:
			logger.error(f"Error getting holdings: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def mf_refresh_nav_xirr(self) -> ApiResponse:
		try:
			refresh_nav()
			compute_xirr()
			return {"status": "success", "message": "NAV refreshed and XIRR computed successfully.", "payload": None}
		except Exception as e:
			logger.error(f"Error refreshing NAV: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def mf_process_cas_pdf(self, file_name: str, password: str, file_content: str) -> ApiResponse:
		try:
			result = process_cas_pdf(file_name, password, file_content)
			if result.get("status") == "success":
				refresh_nav()
				compute_xirr()
			return { 'status'  : 'success', 
		   			 'message' : f'{result["message"]}. NAV refreshed and XIRR computed successfully.', 
					 'payload'    : None }
		except Exception as e:
			logger.error(f"Error processing CAS PDF: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def mf_get_transactions(self, scheme: str = '', folio: str = '') -> ApiResponse:
		try:
			result =  get_transaction_details(scheme, folio)
			return { "status": "success", "message": f'{result.get("message")}', "payload": result.get("payload") }
		except Exception as e:
			logger.error(f"Error getting MF transactions: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def mf_get_folio_list(self) -> ApiResponse:
		try:
			result = get_folio_list()
			return { "status": "success", "message": f'{result.get("message")}', "payload": result.get("payload") }
		except Exception as e:
			logger.error(f"Error getting folio list: {e}")
			return {"status": "error", "message": str(e), "payload": []}
	
	def mf_update_folio_name(self, folio: str, new_name: str) -> ApiResponse:
		try:
			result = update_folio_name(folio, new_name)
			return { "status": "success", "message": f'{result.get("message")}', "payload": [] }
		except Exception as e:
			logger.error(f"Error updating folio name: {e}")
			return {"status": "error", "message": str(e), "payload": []}

	def mf_delete_transaction(self, folio_raw: str, isin: str, txn_date: str, type: str, units: float, balance: float, txn_id: int) -> ApiResponse:
		try:
			result = delete_mf_transaction(folio_raw, isin, txn_date, type, units, balance, txn_id)
			return {"status": result.get("status", "error"), "message": f'{result.get("message")}', "payload": []}
		except Exception as e:
			logger.error(f"Error deleting MF transaction: {e}")
			return {"status": "error", "message": str(e), "payload": []}

	def eq_get_holdings(self) -> ApiResponse:
		try:
			holdings = get_equity_holdings()
			return {"status": "success", "message": "Equity holdings retrieved successfully.", "payload": holdings}
		except Exception as e:
			logger.error(f"Error getting equity holdings: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def eq_refresh_ltp(self) -> ApiResponse:
		try:
			result = refresh_equity_ltp()
			compute_equity_xirr()
			return {"status": "success", "message": f'{result.get("message")}. XIRR recomputed.', "payload": None}
		except Exception as e:
			logger.error(f"Error refreshing equity LTP: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def eq_process_transactions_csv(self, file_name: str, file_content: str) -> ApiResponse:
		try:
			result = ingest_equity_transactions(file_name, file_content)
			message = result.get("message", "")
			if result.get("status") == "success":
				refresh_equity_ltp()
				compute_equity_xirr()
				message = f'{message}. LTP refreshed and XIRR computed successfully.'
			return {'status': result.get("status", "error"), 'message': message, 'payload': None}
		except Exception as e:
			logger.error(f"Error processing equity transactions CSV: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def eq_get_transactions(self, stock_name: str = '', demat_account: str = '') -> ApiResponse:
		try:
			result = get_equity_transactions(stock_name, demat_account)
			return {"status": "success", "message": f'{result.get("message")}', "payload": result.get("payload")}
		except Exception as e:
			logger.error(f"Error getting equity transactions: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def eq_delete_transaction(self, trans_id: str) -> ApiResponse:
		try:
			result = delete_equity_transaction(trans_id)
			return {"status": result.get("status", "error"), "message": f'{result.get("message")}', "payload": []}
		except Exception as e:
			logger.error(f"Error deleting equity transaction: {e}")
			return {"status": "error", "message": str(e), "payload": []}

	def nps_get_holdings(self) -> ApiResponse:
		try:
			holdings = get_nps_holdings()
			return {"status": "success", "message": "NPS holdings retrieved successfully.", "payload": holdings}
		except Exception as e:
			logger.error(f"Error getting NPS holdings: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def nps_refresh_nav(self) -> ApiResponse:
		try:
			result = refresh_nps_nav()
			compute_nps_xirr()
			return {"status": result.get("status", "error"), "message": f'{result.get("message")}. XIRR recomputed.', "payload": None}
		except Exception as e:
			logger.error(f"Error refreshing NPS NAV: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def nps_process_transactions_csv(self, file_name: str, file_content: str) -> ApiResponse:
		try:
			result = ingest_nps_transactions(file_name, file_content)
			message = result.get("message", "")
			if result.get("status") == "success":
				refresh_nps_nav()
				compute_nps_xirr()
				message = f'{message}. NAV refreshed and XIRR computed successfully.'
			return {'status': result.get("status", "error"), 'message': message, 'payload': None}
		except Exception as e:
			logger.error(f"Error processing NPS transactions CSV: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def nps_get_transactions(self, scheme: str = '', pran: str = '') -> ApiResponse:
		try:
			result = get_nps_transactions(scheme, pran)
			return {"status": "success", "message": f'{result.get("message")}', "payload": result.get("payload")}
		except Exception as e:
			logger.error(f"Error getting NPS transactions: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def sgb_get_holdings(self) -> ApiResponse:
		try:
			holdings = get_sgb_holdings()
			return {"status": "success", "message": "SGB holdings retrieved successfully.", "payload": holdings}
		except Exception as e:
			logger.error(f"Error getting SGB holdings: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def sgb_add_holding(self, sgb_name: str, purchase_date: str, units: float, purchase_price: float) -> ApiResponse:
		try:
			result = add_sgb_holding(sgb_name, purchase_date, units, purchase_price)
			return {
				"status": result.get("status", "error"),
				"message": result.get("message", "Failed to add SGB holding."),
				"payload": None,
			}
		except Exception as e:
			logger.error(f"Error adding SGB holding: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def sgb_delete_holding(self, entry_id: int) -> ApiResponse:
		try:
			result = delete_sgb_holding(entry_id)
			return {
				"status": result.get("status", "error"),
				"message": result.get("message", "Failed to delete SGB holding."),
				"payload": None,
			}
		except Exception as e:
			logger.error(f"Error deleting SGB holding: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def sgb_set_gold_price(self, gold_price: float) -> ApiResponse:
		try:
			result = set_sgb_gold_price(gold_price)
			return {
				"status": result.get("status", "error"),
				"message": result.get("message", "Failed to update gold price."),
				"payload": None,
			}
		except Exception as e:
			logger.error(f"Error updating SGB gold price: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def fd_bond_get_holdings(self) -> ApiResponse:
		try:
			holdings = get_fd_bond_holdings()
			return {"status": "success", "message": "FD/Bond holdings retrieved successfully.", "payload": holdings}
		except Exception as e:
			logger.error(f"Error getting FD/Bond holdings: {e}")
			return {"status": "error", "message": str(e), "payload": None}

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
			logger.error(f"Error adding FD/Bond row: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def fd_bond_process_ppf_csv(self, file_name: str, file_content: str) -> ApiResponse:
		try:
			result = ingest_ppf_transactions(file_name, file_content)
			return {
				"status": result.get("status", "error"),
				"message": result.get("message", "Failed to process PPF CSV."),
				"payload": None,
			}
		except Exception as e:
			logger.error(f"Error processing PPF CSV: {e}")
			return {"status": "error", "message": str(e), "payload": None}

	def fd_bond_process_ppf_rate_csv(self, file_name: str, file_content: str) -> ApiResponse:
		try:
			result = ingest_ppf_interest_rates(file_name, file_content)
			return {
				"status": result.get("status", "error"),
				"message": result.get("message", "Failed to process PPF rate CSV."),
				"payload": None,
			}
		except Exception as e:
			logger.error(f"Error processing PPF rate CSV: {e}")
			return {"status": "error", "message": str(e), "payload": None}

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
			logger.error(f"Error deleting FD/Bond row: {e}")
			return {"status": "error", "message": str(e), "payload": None}

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
			logger.error(f"Error updating FD/Bond row: {e}")
			return {"status": "error", "message": str(e), "payload": None}