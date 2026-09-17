<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { TabulatorFull as Tabulator } from "tabulator-tables";
  import type { RowComponent } from "tabulator-tables";
  import {
    getEquityHoldings,
    refreshEquityLtp,
    waitForApi,
    type EquityHolding,
    type EquityHoldings,
  } from "../../services/api";
  import { getEquityHoldingsColumns } from "./equity_table_columns";
  import { summaryTotals } from "../../services/summary_store.svelte";
  import EquityTransactionsModal from "./equity_transactions_modal.svelte";
  import EquityTransactionsUploadModal from "./equity_transactions_upload_modal.svelte";
  import "tabulator-tables/dist/css/tabulator.min.css";

  let status = $state("");
  let error = $state("");
  let uploadModalOpen = $state(false);
  let showTransactions = $state(false);
  let selectedStock = $state("");
  let selectedDematAccount = $state("");
  let tableContainer = $state<HTMLDivElement>();
  let payload = $state<EquityHoldings>({
    tree_rows: [],
    grand_totals: {
      invested_amount: 0,
      current_value: 0,
      abs_gain_pct: 0,
      xirr_pct: 0,
    },
  });
  let table: Tabulator | null = null;
  // Tabulator's constructor returns before its internal (async) DOM build finishes; calling
  // setColumns/setData before the one-time `tableBuilt` event throws "Cannot read properties of
  // null (reading 'firstChild')" if the $effect below re-runs in that window. This promise gates
  // every post-init update on that event instead of assuming the table is ready once `table` is set.
  let tableReady: Promise<void> | null = null;

  $effect(() => {
    const currentPayload: EquityHoldings = payload;

    if (!currentPayload || !tableContainer) return;

    if (!table) {
      initTable();
      return;
    }

    applyPayload(currentPayload);
  });

  function initTable() {
    if (!tableContainer) {
      return;
    }

    table = new Tabulator(tableContainer, {
      data: payload.tree_rows ?? [],
      columns: getEquityHoldingsColumns(payload.grand_totals),
      movableColumns: true,
      columnCalcs: "table",
      layout: "fitColumns",
      dataTree: true,
      dataTreeStartExpanded: false,
      dataTreeChildField: "_children",
      dataTreeSort: true,
      dataTreeElementColumn: "stock_or_demat",
      rowFormatter: (row: RowComponent) => {
        const d = row.getData();
        if (Array.isArray(d._children) && d._children.length > 0) {
          row.getElement().classList.add("mf-parent-row");
        }
      },
    });

    tableReady = new Promise((resolve) => {
      table!.on("tableBuilt", () => resolve());
    });

    table.on("rowDblClick", (_event, row) => {
      openTransactionsFromRow(row);
    });
  }

  async function applyPayload(currentPayload: EquityHoldings) {
    if (!tableReady) return;
    await tableReady;
    if (!table) return;

    table.setColumns(getEquityHoldingsColumns(currentPayload.grand_totals));
    table.setData(currentPayload.tree_rows ?? []);
    table.recalc();
  }

  function openTransactionsFromRow(row: RowComponent) {
    const parentRow = row.getTreeParent();
    if (!parentRow) {
      return;
    }

    status = "Getting transactions for selected demat account...";
    const rowData = row.getData() as Partial<EquityHolding>;
    const parentData = parentRow.getData() ?? {};

    const stockName = String(parentData.stock_name ?? parentData.stock_or_demat ?? "").trim();
    const dematAccount = String(rowData.demat_account ?? rowData.stock_or_demat ?? "").trim();

    if (!stockName || !dematAccount) {
      status = "Could not determine stock/demat account";
      return;
    }

    selectedStock = stockName;
    selectedDematAccount = dematAccount;
    showTransactions = true;
    status = "Opened transactions for selected demat account";
  }

  async function loadEquityHoldingsData() {
    error = "";
    try {
      status = "Loading equity holdings data...";
      const result = await getEquityHoldings();
      payload = result.payload;
      summaryTotals.equity = payload.grand_totals;

      if (!payload.tree_rows || payload.tree_rows.length === 0) {
        status = "No equity holdings data available";
        return;
      }

      status = result.message;
    } catch (e) {
      error = "Failed to load equity holdings: " + String(e);
      status = "Error";
    }
  }

  async function refreshLtpAndReload() {
    status = "Refresh LTP started...";
    try {
      const result = await refreshEquityLtp();
      status = result.message;
      await loadEquityHoldingsData();
    } catch (e) {
      status = "Refresh LTP failed";
      console.error(e);
    }
  }

  onMount(async () => {
    await waitForApi();
    await loadEquityHoldingsData();
  });

  onDestroy(() => table?.destroy());
</script>

<main class="app-page">
  <header class="app-header">
    <h1 class="app-title">Equity - Holding Statement</h1>

    <div class="app-header-actions">
      {#if status}
        <span class="app-status">{status}</span>
      {/if}

      <div class="app-toolbar">
        <button class="app-button" onclick={() => (uploadModalOpen = true)}>
          Upload Equity Transactions CSV
        </button>

        <button class="app-button" onclick={refreshLtpAndReload}>
          Refresh LTP
        </button>
      </div>
    </div>
  </header>

  <section class="app-table-wrap">
    <div class="app-table" bind:this={tableContainer}></div>
    {#if error}
      <p class="app-error">{error}</p>
    {/if}
  </section>
</main>

{#if uploadModalOpen}
  <EquityTransactionsUploadModal bind:open={uploadModalOpen} onProcessed={loadEquityHoldingsData} />
{/if}

{#if showTransactions}
  <EquityTransactionsModal
    bind:open={showTransactions}
    stockName={selectedStock}
    dematAccount={selectedDematAccount}
    onChanged={loadEquityHoldingsData}
  />
{/if}