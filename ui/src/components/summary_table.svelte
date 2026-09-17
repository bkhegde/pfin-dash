<script lang="ts">
  import { summaryTotals } from "../services/summary_store.svelte";
  import { fmtAmount, fmtPct } from "../services/formatters";

  const rows = $derived([
    { label: "Mutual Funds", totals: summaryTotals.mf },
    { label: "Equity", totals: summaryTotals.equity },
    { label: "NPS", totals: summaryTotals.nps },
    { label: "SGB", totals: summaryTotals.sgb },
    { label: "FD and Bonds", totals: summaryTotals.fd_bond },
  ]);

  // XIRR isn't additive across asset classes - a true combined figure would need to be computed
  // from every underlying cashflow together, not derived from the three separate XIRR% values -
  // so the grand total row only covers Invested/Current Value/Abs Gain%, which sum validly.
  const grandInvested = $derived(rows.reduce((sum, row) => sum + row.totals.invested_amount, 0));
  const grandCurrent = $derived(rows.reduce((sum, row) => sum + row.totals.current_value, 0));
  const grandAbsGainPct = $derived(
    grandInvested !== 0 ? (grandCurrent / grandInvested - 1) * 100 : 0
  );
</script>

<main class="app-page">
  <header class="app-header">
    <h1 class="app-title">Portfolio Summary</h1>
  </header>

  <section class="app-table-wrap app-summary-wrap">
    <table class="app-summary-table">
      <thead>
        <tr>
          <th>Asset Class</th>
          <th>Invested</th>
          <th>Current Value</th>
          <th>Abs Gain%</th>
          <th>XIRR%</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row (row.label)}
          <tr>
            <td>{row.label}</td>
            <td class="app-num-cell">{fmtAmount(row.totals.invested_amount)}</td>
            <td class="app-num-cell">{fmtAmount(row.totals.current_value)}</td>
            <td class="app-num-cell">{fmtPct(row.totals.abs_gain_pct)}</td>
            <td class="app-num-cell">{fmtPct(row.totals.xirr_pct)}</td>
          </tr>
        {/each}
        <tr class="app-summary-total-row">
          <td>Grand Total</td>
          <td class="app-num-cell">{fmtAmount(grandInvested)}</td>
          <td class="app-num-cell">{fmtAmount(grandCurrent)}</td>
          <td class="app-num-cell">{fmtPct(grandAbsGainPct)}</td>
          <td class="app-num-cell">—</td>
        </tr>
      </tbody>
    </table>
  </section>
</main>
