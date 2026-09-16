<script lang="ts">
  import EquityHoldingsPage from "./components/equity/equity_holdings_page.svelte";
  import FdBondHoldingsPage from "./components/fd_bond/fd_bond_holdings_page.svelte";
  import MFHoldingsPage from "./components/mutual_fund/mf_holdings_page.svelte";
  import NpsHoldingsPage from "./components/nps/nps_holdings_page.svelte";
  import SgbHoldingsPage from "./components/sgb/sgb_holdings_page.svelte";
  import SummaryTable from "./components/summary_table.svelte";
  import "./styles/global.css";
  import "./styles/app.css";
</script>

<div class="app-shell">
  <SummaryTable />

  <MFHoldingsPage />

  <EquityHoldingsPage />

  <NpsHoldingsPage />

  <SgbHoldingsPage />

  <FdBondHoldingsPage />
</div>
