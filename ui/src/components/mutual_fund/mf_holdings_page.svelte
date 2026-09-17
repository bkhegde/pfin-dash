<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { TabulatorFull as Tabulator } from "tabulator-tables";
  import type { RowComponent } from "tabulator-tables";
  import {
    getHoldings,
    refreshNav,
    waitForApi,
    type Holding,
    type MF_Holdings,
  } from "../../services/api";
  import { getHoldingsColumns } from "./mf_table_columns";
  import { summaryTotals } from "../../services/summary_store.svelte";
  import MFCasUploadModal from "./mf_cas_upload_modal.svelte";
  import MFFolioNameModal from "./mf_edit_folio_name_modal.svelte";
  import MFTransactionsModal from "./mf_transactions_modal.svelte";
  import "tabulator-tables/dist/css/tabulator.min.css";

  let status = $state("");
  let error = $state("");
  let casModalOpen = $state(false);
  let showTransactions = $state(false);
  let selectedScheme = $state("");
  let selectedFolio = $state("");
  let openFolioEditor = $state(false);

  let tableContainer = $state<HTMLDivElement>();
  let payload = $state<MF_Holdings>({
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
    const currentPayload: MF_Holdings = payload;

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
      columns: getHoldingsColumns(payload.grand_totals),
      movableColumns: true,
      columnCalcs: "table",
      layout: "fitColumns",
      dataTree: true,
      dataTreeStartExpanded: false,
      dataTreeChildField: "_children",
      dataTreeSort: true,
      dataTreeElementColumn: "scheme_or_folio",
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

  async function applyPayload(currentPayload: MF_Holdings) {
    if (!tableReady) return;
    await tableReady;
    if (!table) return;

    table.setColumns(getHoldingsColumns(currentPayload.grand_totals));
    table.setData(currentPayload.tree_rows ?? []);
    table.recalc();
  }

  async function loadHoldingsData() {
    error = "";
    try {
      status = "Loading MF holdings data...";
      const result = await getHoldings();
      payload = result.payload;
      summaryTotals.mf = payload.grand_totals;

      if (!payload || !payload.tree_rows || payload.tree_rows.length === 0) {
        status = "No holdings data available";
        return;
      }

      status = "MF holdings data loaded";
    } catch (e) {
      error = "Failed to load holdings: " + String(e);
      status = "Error";
    }
  }

  async function refreshNavAndReload() {
    status = "Refresh NAV started...";
    try {
      await refreshNav();
      await loadHoldingsData();
    } catch (e) {
      status = "Refresh NAV failed";
      console.error(e);
    }
  }

  function openTransactionsFromRow(row: RowComponent) {
    const parentRow = row.getTreeParent();
    if (!parentRow) {
      return;
    }

    status = "Getting transactions for selected folio...";
    const rowData = row.getData() as Partial<Holding>;
    const parentData = parentRow.getData() ?? {};

    const scheme = String(parentData.scheme ?? parentData.scheme_or_folio ?? "").trim();
    const folio = String(rowData.folio ?? rowData.scheme_or_folio ?? "").trim();

    if (!scheme || !folio) {
      status = "Could not determine scheme/folio";
      return;
    }

    selectedScheme = scheme;
    selectedFolio = folio;
    showTransactions = true;
    status = "Opened transactions for selected folio";
  }

  onMount(async () => {
    await waitForApi();
    await loadHoldingsData();
  });

  onDestroy(() => table?.destroy());
</script>

<main class="app-page">
  <header class="app-header">
    <h1 class="app-title">Mutual Funds - Holding Statement</h1>

    <div class="app-header-actions">
      {#if status}
        <span class="app-status">{status}</span>
      {/if}

      <div class="app-toolbar">
        <button class="app-button" onclick={() => (casModalOpen = true)}>
          Upload CAMS CAS PDF
        </button>

        <button class="app-button" onclick={refreshNavAndReload}>
          Refresh NAV
        </button>

        <button class="app-button" onclick={() => (openFolioEditor = true)}>
          Edit Folio Names
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

{#if casModalOpen}
  <MFCasUploadModal bind:open={casModalOpen} onProcessed={loadHoldingsData} />
{/if}

{#if showTransactions}
  <MFTransactionsModal
    bind:open={showTransactions}
    scheme={selectedScheme}
    folio={selectedFolio}
    onChanged={loadHoldingsData}
  />
{/if}

{#if openFolioEditor}
  <MFFolioNameModal bind:open={openFolioEditor} />
{/if}