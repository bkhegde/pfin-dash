/**
 * api.ts — single point of contact for all Python (pywebview) calls.
 *
 * Every function here maps 1-to-1 to a method exposed on window.pywebview.api.
 * Callers import from this file; they never touch window.pywebview directly.
 */

// ---------- types --------------------------------------------------------

export interface ApiResult {
  status: string;
  message: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload?: any; 
}

export interface HoldingsResult {
  status: string;
  message: string;
  payload: MF_Holdings;
}

export interface EquityHoldingsResult {
  status: string;
  message: string;
  payload: EquityHoldings;
}

export interface NpsHoldingsResult {
  status: string;
  message: string;
  payload: NpsHoldings;
}

export interface SgbHoldingsResult {
  status: string;
  message: string;
  payload: SgbHoldings;
}

export interface FdBondHoldingsResult {
  status: string;
  message: string;
  payload: FdBondHoldings;
}

export interface TransactionsResult {
  status: string;
  message: string;
  payload: MfTransaction[];
}

export interface EquityTransactionsResult {
  status: string;
  message: string;
  payload: EquityTransaction[];
}

export interface NpsTransactionsResult {
  status: string;
  message: string;
  payload: NpsTransaction[];
}

export interface Holding {
  scheme_or_folio: string;
  scheme: string;
  folio: string;
  total_units: number;
  invested_amount: number;
  current_value: number;
  abs_gain_pct: number;
  xirr_pct: number;
  nav: number;
  nav_dt: string; //expected in ISO format (yyyy-mm-dd)
  _children?: Holding[];
}

export interface MFGrandTotals {
  invested_amount: number;
  current_value: number;
  abs_gain_pct: number;
  xirr_pct: number;
}

export interface MF_Holdings {
  tree_rows: Holding[];
  grand_totals: MFGrandTotals;
}

export interface EquityHolding {
  stock_or_demat: string;
  stock_name: string;
  demat_account: string;
  total_units: number;
  invested_amount: number;
  current_value: number;
  abs_gain_pct: number;
  xirr_pct: number;
  last_price: number;
  ltp_date: string;
  _children?: EquityHolding[];
}

export interface EquityHoldings {
  tree_rows: EquityHolding[];
  grand_totals: MFGrandTotals;
}

export interface NpsHolding {
  scheme_or_pran: string;
  scheme: string;
  pran: string;
  total_units: number;
  invested_amount: number;
  current_value: number;
  abs_gain_pct: number;
  xirr_pct: number;
  nav: number;
  nav_dt: string;
  _children?: NpsHolding[];
}

export interface NpsHoldings {
  tree_rows: NpsHolding[];
  grand_totals: MFGrandTotals;
}

export interface SgbHolding {
  entry_id: number;
  sgb_name: string;
  purchase_date: string;
  units: number;
  purchase_price: number;
  invested_amount: number;
  current_value: number;
  abs_gain_pct: number;
  xirr_pct: number;
}

export interface SgbHoldings {
  rows: SgbHolding[];
  gold_price: number;
  as_on_date: string;
  grand_totals: MFGrandTotals;
}

export interface FdBondHolding {
  entry_id: number;
  instrument_name: string;
  instrument_type: string;
  purchase_date: string;
  maturity_date: string;
  principal_amount: number;
  interest_rate_pct: number;
  interest_period_years: number;
  payout_method: string;
  current_value: number;
  abs_gain_pct: number;
  xirr_pct: number;
  status: string;
  can_edit?: boolean;
  can_delete?: boolean;
}

export interface FdBondHoldings {
  rows: FdBondHolding[];
  as_on_date: string;
  grand_totals: MFGrandTotals;
}

export interface MfTransaction {
  scheme: string;
  txn_date: string; //expected in ISO format (yyyy-mm-dd)
  type: string;
  units: number;
  residual_units: number;
  nav: number;
  amount: number;
  balance: number;
  tax_type: string;
  tax_description: string;
  tax_amount: number;
  txn_id: number;
  folio: string;
  folio_raw: string; // underlying folio number (folio may be a renamed display value) - needed to delete this row
  isin: string;
  amfi: string;
  description: string;
  source_file: string;
}

export interface EquityTransaction {
  trans_id: string; // primary key in equity_trans - needed to delete this row
  stock_name: string;
  demat_account: string;
  txn_date: string;
  type: string;
  units: number;
  price: number;
  amount: number;
  charges: number;
  net_amount: number;
  exchange: string;
  order_id: string;
  source_file: string;
}

export interface NpsTransaction {
  scheme: string;
  pran: string;
  txn_date: string;
  type: string;
  units: number;
  residual_units: number;
  nav: number;
  amount: number;
  balance: number;
  description: string;
  source_file: string;
}

export interface FolioList {
  folio: string;
  folio_name: string;
}

// ---------- global augment -----------------------------------------------

declare global {
  interface Window {
    pywebview: {
      ready: boolean;
      api: {
        mf_get_holdings(): Promise<HoldingsResult>;
        mf_get_transactions(scheme: string, folio: string): Promise<TransactionsResult>;
        mf_refresh_nav_xirr(): Promise<ApiResult>;
        mf_process_cas_pdf(filename: string, password: string, fileContent: string): Promise<ApiResult>;
        mf_get_folio_list(): Promise<ApiResult>;
        mf_update_folio_name(folio: string, new_name: string): Promise<ApiResult>;
        mf_delete_transaction(
          folioRaw: string,
          isin: string,
          txnDate: string,
          type: string,
          units: number,
          balance: number,
          txnId: number
        ): Promise<ApiResult>;
        eq_get_holdings(): Promise<EquityHoldingsResult>;
        eq_get_transactions(stockName: string, dematAccount: string): Promise<EquityTransactionsResult>;
        eq_refresh_ltp(): Promise<ApiResult>;
        eq_process_transactions_csv(filename: string, fileContent: string): Promise<ApiResult>;
        eq_delete_transaction(transId: string): Promise<ApiResult>;
        nps_get_holdings(): Promise<NpsHoldingsResult>;
        nps_get_transactions(scheme: string, pran: string): Promise<NpsTransactionsResult>;
        nps_refresh_nav(): Promise<ApiResult>;
        nps_process_transactions_csv(filename: string, fileContent: string): Promise<ApiResult>;
        sgb_get_holdings(): Promise<SgbHoldingsResult>;
        sgb_add_holding(sgbName: string, purchaseDate: string, units: number, purchasePrice: number): Promise<ApiResult>;
        sgb_delete_holding(entryId: number): Promise<ApiResult>;
        sgb_set_gold_price(goldPrice: number): Promise<ApiResult>;
        fd_bond_get_holdings(): Promise<FdBondHoldingsResult>;
        fd_bond_add_holding(
          instrumentName: string,
          instrumentType: string,
          purchaseDate: string,
          principalAmount: number,
          interestRatePct: number,
          interestPeriodYears: number,
          payoutMethod: string,
          maturityDate: string,
        ): Promise<ApiResult>;
        fd_bond_delete_holding(
          instrumentName: string,
          instrumentType: string,
          purchaseDate: string,
          principalAmount: number,
          interestRatePct: number,
          interestPeriodYears: number,
          payoutMethod: string,
          maturityDate: string,
        ): Promise<ApiResult>;
        fd_bond_update_holding(
          oldInstrumentName: string,
          oldInstrumentType: string,
          oldPurchaseDate: string,
          oldPrincipalAmount: number,
          oldInterestRatePct: number,
          oldInterestPeriodYears: number,
          oldPayoutMethod: string,
          oldMaturityDate: string,
          newInstrumentName: string,
          newInstrumentType: string,
          newPurchaseDate: string,
          newPrincipalAmount: number,
          newInterestRatePct: number,
          newInterestPeriodYears: number,
          newPayoutMethod: string,
          newMaturityDate: string,
        ): Promise<ApiResult>;
        fd_bond_process_ppf_csv(filename: string, fileContent: string): Promise<ApiResult>;
        fd_bond_process_ppf_rate_csv(filename: string, fileContent: string): Promise<ApiResult>;
        fd_bond_delete_ppf_transactions(): Promise<ApiResult>;
        fd_bond_delete_ppf_rates(): Promise<ApiResult>;
      };
    };
  }
}

// ---------- helpers ------------------------------------------------------

const REQUIRED_API_METHODS = [
  "mf_get_holdings",
  "mf_get_transactions",
  "mf_refresh_nav_xirr",
  "mf_process_cas_pdf",
  "mf_get_folio_list",
  "mf_update_folio_name",
  "mf_delete_transaction",
  "eq_get_holdings",
  "eq_get_transactions",
  "eq_refresh_ltp",
  "eq_process_transactions_csv",
  "eq_delete_transaction",
  "nps_get_holdings",
  "nps_get_transactions",
  "nps_refresh_nav",
  "nps_process_transactions_csv",
  "sgb_get_holdings",
  "sgb_add_holding",
  "sgb_delete_holding",
  "sgb_set_gold_price",
  "fd_bond_get_holdings",
  "fd_bond_add_holding",
  "fd_bond_delete_holding",
  "fd_bond_update_holding",
  "fd_bond_process_ppf_csv",
  "fd_bond_process_ppf_rate_csv",
  "fd_bond_delete_ppf_transactions",
  "fd_bond_delete_ppf_rates",
] as const;

function hasRequiredApiMethods(candidate: unknown): candidate is typeof window.pywebview.api {
  if (!candidate || typeof candidate !== "object") {
    return false;
  }

  const apiCandidate = candidate as Record<string, unknown>;
  return REQUIRED_API_METHODS.every((method) => typeof apiCandidate[method] === "function");
}

function resolveApiFromWindow(win: Window): typeof window.pywebview.api | null {
  if (hasRequiredApiMethods(win.pywebview?.api)) {
    return win.pywebview.api;
  }

  return null;
}

function getApi(): typeof window.pywebview.api {
  const currentWindowApi = resolveApiFromWindow(window);
  if (currentWindowApi) return currentWindowApi;

  if (window.parent !== window) {
    try {
      const parentWindowApi = resolveApiFromWindow(window.parent);
      if (parentWindowApi) return parentWindowApi;
    } catch (e) { if (e instanceof DOMException) { /* cross-origin guard */ } }
  }

  throw new Error("pywebview API not ready");
}

/** Wait for pywebview to be ready, then resolve. */
export function waitForApi(): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    let interval: ReturnType<typeof setInterval> | null = null;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    const finish = (): void => {
      if (settled) {
        return;
      }

      settled = true;
      if (interval) {
        clearInterval(interval);
      }
      if (timeout) {
        clearTimeout(timeout);
      }
      resolve();
    };

    const tryResolve = (): boolean => {
      try {
        getApi();
        finish();
        return true;
      } catch {
        return false;
      }
    };

    if (tryResolve()) {
      return;
    }

    window.addEventListener("pywebviewready", () => {
      if (tryResolve()) {
        return;
      }
    }, { once: true });

    interval = setInterval(() => {
      if (tryResolve()) {
        return;
      }
    }, 50);

    timeout = setTimeout(() => {
      tryResolve();
    }, 10000);
  });
}

/** Read a File as a base-64 string (strips the data-URL prefix). */
export function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result ?? "");
      const parts = dataUrl.split(",", 2);
      resolve(parts.length === 2 ? parts[1] : "");
    };
    reader.onerror = () => reject(new Error("Unable to read selected file"));
    reader.readAsDataURL(file);
  });
}

// ---------- API calls ----------------------------------------------------

/** Fetch the grouped holdings tree for the main table. */
export async function getHoldings(): Promise<HoldingsResult> {
  const result: HoldingsResult = await getApi().mf_get_holdings();
  return result;
}

/** Fetch transactions for a specific scheme + folio. */
export async function getMfTransactions(
  scheme: string,
  folio: string
): Promise<TransactionsResult> {
  console.log(`Calling Python API mf_get_transactions with scheme: ${scheme}, folio: ${folio}`);
  const result: TransactionsResult = await getApi().mf_get_transactions(scheme, folio);
  console.log("Received transactions result:", result.message);
  return result;
}

/** Trigger a NAV refresh on the Python side. */
export async function refreshNav(): Promise<ApiResult> {
  console.log("Calling Python API mf_refresh_nav_xirr...");
  const result: ApiResult = await getApi().mf_refresh_nav_xirr();
  console.log("Received refresh NAV result:", result.message);
  return result;
}

/** Upload a CAMS CAS PDF (base-64 encoded) for processing. */
export async function processCasPdf(
  filename: string,
  password: string,
  fileContentBase64: string
): Promise<ApiResult> {
  console.log(`Calling Python API mf_process_cas_pdf with filename: ${filename}`);
  const result: ApiResult = await getApi().mf_process_cas_pdf(filename, password, fileContentBase64);
  console.log("Received process CAS PDF result:", result.message);
  return result;
}

export async function getFolioList(): Promise<ApiResult> {
  console.log("Calling Python API mf_get_folio_list...");
  const result: ApiResult = await getApi().mf_get_folio_list();
  console.log("Received folio list result:", result.message);
  return result;
}

export async function updateFolioName(folio: string, new_name: string): Promise<ApiResult> {
  console.log(`Calling Python API mf_update_folio_name with folio: ${folio}, new_name: ${new_name}`);
  const result: ApiResult = await getApi().mf_update_folio_name(folio, new_name);
  console.log("Received update folio name result:", result.message);
  return result;
}

/** Delete a single MF transaction, identified by its natural key (see MfTransaction.folio_raw). */
export async function deleteMfTransaction(txn: MfTransaction): Promise<ApiResult> {
  console.log(`Calling Python API mf_delete_transaction for txn_id: ${txn.txn_id}, folio: ${txn.folio_raw}`);
  const result: ApiResult = await getApi().mf_delete_transaction(
    txn.folio_raw,
    txn.isin,
    txn.txn_date,
    txn.type,
    txn.units,
    txn.balance,
    txn.txn_id
  );
  console.log("Received delete MF transaction result:", result.message);
  return result;
}

/** Fetch the grouped equity holdings tree for the main table. */
export async function getEquityHoldings(): Promise<EquityHoldingsResult> {
  const result: EquityHoldingsResult = await getApi().eq_get_holdings();
  return result;
}

/** Trigger an LTP refresh on the Python side. */
export async function refreshEquityLtp(): Promise<ApiResult> {
  console.log("Calling Python API eq_refresh_ltp...");
  const result: ApiResult = await getApi().eq_refresh_ltp();
  console.log("Received refresh LTP result:", result.message);
  return result;
}

/** Upload an equity transactions CSV (base-64 encoded) for processing. */
export async function processEquityTransactionsCsv(
  filename: string,
  fileContentBase64: string
): Promise<ApiResult> {
  console.log(`Calling Python API eq_process_transactions_csv with filename: ${filename}`);
  const result: ApiResult = await getApi().eq_process_transactions_csv(filename, fileContentBase64);
  console.log("Received process equity transactions CSV result:", result.message);
  return result;
}

/** Fetch transactions for a specific stock + demat account. */
export async function getEquityTransactions(
  stockName: string,
  dematAccount: string
): Promise<EquityTransactionsResult> {
  console.log(`Calling Python API eq_get_transactions with stock: ${stockName}, demat account: ${dematAccount}`);
  const result: EquityTransactionsResult = await getApi().eq_get_transactions(stockName, dematAccount);
  console.log("Received equity transactions result:", result.message);
  return result;
}

/** Delete a single equity transaction by its trans_id. */
export async function deleteEquityTransaction(transId: string): Promise<ApiResult> {
  console.log(`Calling Python API eq_delete_transaction for trans_id: ${transId}`);
  const result: ApiResult = await getApi().eq_delete_transaction(transId);
  console.log("Received delete equity transaction result:", result.message);
  return result;
}

/** Fetch the grouped NPS holdings tree for the main table. */
export async function getNpsHoldings(): Promise<NpsHoldingsResult> {
  const result: NpsHoldingsResult = await getApi().nps_get_holdings();
  return result;
}

/** Trigger an NPS NAV refresh on the Python side (via npsnav.in). */
export async function refreshNpsNav(): Promise<ApiResult> {
  console.log("Calling Python API nps_refresh_nav...");
  const result: ApiResult = await getApi().nps_refresh_nav();
  console.log("Received refresh NPS NAV result:", result.message);
  return result;
}

/** Upload a Protean NPS transaction statement CSV (base-64 encoded) for processing. */
export async function processNpsTransactionsCsv(
  filename: string,
  fileContentBase64: string
): Promise<ApiResult> {
  console.log(`Calling Python API nps_process_transactions_csv with filename: ${filename}`);
  const result: ApiResult = await getApi().nps_process_transactions_csv(filename, fileContentBase64);
  console.log("Received process NPS transactions CSV result:", result.message);
  return result;
}

/** Fetch transactions for a specific scheme + PRAN. */
export async function getNpsTransactions(
  scheme: string,
  pran: string
): Promise<NpsTransactionsResult> {
  console.log(`Calling Python API nps_get_transactions with scheme: ${scheme}, pran: ${pran}`);
  const result: NpsTransactionsResult = await getApi().nps_get_transactions(scheme, pran);
  console.log("Received NPS transactions result:", result.message);
  return result;
}

/** Fetch SGB holdings table with computed valuations and XIRR. */
export async function getSgbHoldings(): Promise<SgbHoldingsResult> {
  const result: SgbHoldingsResult = await getApi().sgb_get_holdings();
  return result;
}

/** Add one SGB holding lot row. */
export async function addSgbHolding(
  sgbName: string,
  purchaseDate: string,
  units: number,
  purchasePrice: number,
): Promise<ApiResult> {
  const result: ApiResult = await getApi().sgb_add_holding(sgbName, purchaseDate, units, purchasePrice);
  return result;
}

/** Delete one SGB holding row by entry id. */
export async function deleteSgbHolding(entryId: number): Promise<ApiResult> {
  const result: ApiResult = await getApi().sgb_delete_holding(entryId);
  return result;
}

/** Persist the latest SGB gold price used for valuation and XIRR. */
export async function setSgbGoldPrice(goldPrice: number): Promise<ApiResult> {
  const result: ApiResult = await getApi().sgb_set_gold_price(goldPrice);
  return result;
}

/** Fetch FD/Bond holdings table with computed valuation and XIRR. */
export async function getFdBondHoldings(): Promise<FdBondHoldingsResult> {
  const result: FdBondHoldingsResult = await getApi().fd_bond_get_holdings();
  return result;
}

/** Add one FD/Bond row from manual form input. */
export async function addFdBondHolding(
  instrumentName: string,
  instrumentType: string,
  purchaseDate: string,
  principalAmount: number,
  interestRatePct: number,
  interestPeriodYears: number,
  payoutMethod: string,
  maturityDate: string,
): Promise<ApiResult> {
  const result: ApiResult = await getApi().fd_bond_add_holding(
    instrumentName,
    instrumentType,
    purchaseDate,
    principalAmount,
    interestRatePct,
    interestPeriodYears,
    payoutMethod,
    maturityDate,
  );
  return result;
}

/** Delete one FD/Bond row identified by its composite key fields. */
export async function deleteFdBondHolding(row: FdBondHolding): Promise<ApiResult> {
  const result: ApiResult = await getApi().fd_bond_delete_holding(
    row.instrument_name,
    row.instrument_type,
    row.purchase_date,
    row.principal_amount,
    row.interest_rate_pct,
    row.interest_period_years,
    row.payout_method,
    row.maturity_date,
  );
  return result;
}

/** Update one FD/Bond row; oldRow is the identity key and newRow is the replacement payload. */
export async function updateFdBondHolding(oldRow: FdBondHolding, newRow: FdBondHolding): Promise<ApiResult> {
  const result: ApiResult = await getApi().fd_bond_update_holding(
    oldRow.instrument_name,
    oldRow.instrument_type,
    oldRow.purchase_date,
    oldRow.principal_amount,
    oldRow.interest_rate_pct,
    oldRow.interest_period_years,
    oldRow.payout_method,
    oldRow.maturity_date,
    newRow.instrument_name,
    newRow.instrument_type,
    newRow.purchase_date,
    newRow.principal_amount,
    newRow.interest_rate_pct,
    newRow.interest_period_years,
    newRow.payout_method,
    newRow.maturity_date,
  );
  return result;
}

/** Upload PPF transaction CSV for valuation under FD/Bond section. */
export async function processPpfTransactionsCsv(
  filename: string,
  fileContentBase64: string,
): Promise<ApiResult> {
  const result: ApiResult = await getApi().fd_bond_process_ppf_csv(filename, fileContentBase64);
  return result;
}

/** Upload PPF interest-rate CSV (effective_from, annual_rate_pct). */
export async function processPpfRateCsv(
  filename: string,
  fileContentBase64: string,
): Promise<ApiResult> {
  const result: ApiResult = await getApi().fd_bond_process_ppf_rate_csv(filename, fileContentBase64);
  return result;
}

/** Delete all uploaded PPF transaction rows. */
export async function deletePpfTransactionsData(): Promise<ApiResult> {
  const result: ApiResult = await getApi().fd_bond_delete_ppf_transactions();
  return result;
}

/** Delete all uploaded PPF rate rows and restore fallback default rate. */
export async function deletePpfRatesData(): Promise<ApiResult> {
  const result: ApiResult = await getApi().fd_bond_delete_ppf_rates();
  return result;
}

