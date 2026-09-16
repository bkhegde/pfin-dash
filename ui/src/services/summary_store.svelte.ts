/**
 * summary_store.svelte.ts — shared reactive totals for the top-of-page portfolio summary.
 *
 * Each holdings page writes its own grand_totals here whenever it loads or refreshes data;
 * the summary table just reads this reactively, so it stays in sync without any direct
 * coupling between the three (otherwise independent) holdings pages.
 */

import type { MFGrandTotals } from "./api";

function emptyTotals(): MFGrandTotals {
  return { invested_amount: 0, current_value: 0, abs_gain_pct: 0, xirr_pct: 0 };
}

export const summaryTotals: {
  mf: MFGrandTotals;
  equity: MFGrandTotals;
  nps: MFGrandTotals;
  sgb: MFGrandTotals;
  fd_bond: MFGrandTotals;
} = $state({
  mf: emptyTotals(),
  equity: emptyTotals(),
  nps: emptyTotals(),
  sgb: emptyTotals(),
  fd_bond: emptyTotals(),
});
