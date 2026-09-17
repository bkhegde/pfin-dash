<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { TabulatorFull as Tabulator } from "tabulator-tables";
  import type { RowComponent } from "tabulator-tables";
  import {
    getNpsHoldings,
    refreshNpsNav,
    waitForApi,
    type NpsHolding,
    type NpsHoldings,
  } from "../../services/api";
  import { getNpsHoldingsColumns } from "./nps_table_columns";
  import { summaryTotals } from "../../services/summary_store.svelte";
  import NpsTransactionsModal from "./nps_transactions_modal.svelte";
  import NpsTransactionsUploadModal from "./nps_transactions_upload_modal.svelte";
  import "tabulator-tables/dist/css/tabulator.min.css";

  let status = $state("");
  let error = $state("");
  let uploadModalOpen = $state(false);
  let showTransactions = $state(false);
  let selectedScheme = $state("");
  let selectedPran = $state("");

  let tableContainer = $state<HTMLDivElement>();
  let payload = $state<NpsHoldings>({
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
    const currentPayload: NpsHoldings = payload;

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
      columns: getNpsHoldingsColumns(payload.grand_totals),
      movableColumns: true,
      columnCalcs: "table",
      layout: "fitColumns",
      dataTree: true,
      dataTreeStartExpanded: false,
      dataTreeChildField: "_children",
      dataTreeSort: true,
      dataTreeElementColumn: "scheme_or_pran",
      rowFormatter: (row: RowComponent) => {
        const data = row.getData();
        if (Array.isArray(data._children) && data._children.length > 0) {
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

  async function applyPayload(currentPayload: NpsHoldings) {
    if (!tableReady) return;
    await tableReady;
    if (!table) return;

    table.setColumns(getNpsHoldingsColumns(currentPayload.grand_totals));
    table.setData(currentPayload.tree_rows ?? []);
    table.recalc();
  }

  async function loadNpsHoldingsData() {
    error = "";
    try {
      status = "Loading NPS holdings data...";
      const result = await getNpsHoldings();
      payload = result.payload;
      summaryTotals.nps = payload.grand_totals;

      if (!payload.tree_rows || payload.tree_rows.length === 0) {
        status = "No NPS holdings data available";
        return;
      }

      status = result.message;
    } catch (e) {
      error = "Failed to load NPS holdings: " + String(e);
      status = "Error";
    }
  }

  async function refreshNavAndReload() {
    status = "Refresh NPS NAV started...";
    try {
      const result = await refreshNpsNav();
      status = result.message;
      await loadNpsHoldingsData();
    } catch (e) {
      status = "Refresh NPS NAV failed";
      console.error(e);
    }
  }

  function openTransactionsFromRow(row: RowComponent) {
    const parentRow = row.getTreeParent();
    if (!parentRow) {
      return;
    }

    status = "Getting transactions for selected PRAN...";
    const rowData = row.getData() as Partial<NpsHolding>;
    const parentData = parentRow.getData() ?? {};

    const scheme = String(parentData.scheme ?? parentData.scheme_or_pran ?? "").trim();
    const pran = String(rowData.pran ?? rowData.scheme_or_pran ?? "").trim();

    if (!scheme || !pran) {
      status = "Could not determine scheme/PRAN";
      return;
    }

    selectedScheme = scheme;
    selectedPran = pran;
    showTransactions = true;
    status = "Opened transactions for selected PRAN";
  }

  onMount(async () => {
    await waitForApi();
    await loadNpsHoldingsData();
  });

  onDestroy(() => table?.destroy());
</script>

<main class="app-page">
  <header class="app-header">
    <h1 class="app-title">NPS - Holding Statement</h1>

    <div class="app-header-actions">
      {#if status}
        <span class="app-status">{status}</span>
      {/if}

      <div class="app-toolbar">
        <button class="app-button" onclick={() => (uploadModalOpen = true)}>
          Upload NPS Transactions CSV
        </button>

        <button class="app-button" onclick={refreshNavAndReload}>
          Refresh NAV
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
  <NpsTransactionsUploadModal bind:open={uploadModalOpen} onProcessed={loadNpsHoldingsData} />
{/if}

{#if showTransactions}
  <NpsTransactionsModal bind:open={showTransactions} scheme={selectedScheme} pran={selectedPran} />
{/if}