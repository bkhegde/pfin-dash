/** fmt.ts — number / date formatting helpers used across components. */

import { DateTime } from "luxon";

function toNum(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

export const fmtUnits   = (v: unknown) => toNum(v).toLocaleString("en-IN", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
export const fmtAmount  = (v: unknown) => toNum(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtPct     = (v: unknown) => fmtAmount(v) + " %";
export function fmtDate(date: string): string { return DateTime.fromISO(date).toFormat("dd-MM-yyyy");}

/** Red circular trash-can icon used on row-delete buttons in transaction tables. */
export const DELETE_ICON_HTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <path d="M6 7h12M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-8 0 1 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l1-13" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M10 11v6M14 11v6" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round"/>
</svg>`;