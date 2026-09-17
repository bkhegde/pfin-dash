<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { TabulatorFull as Tabulator } from "tabulator-tables";
  import {
    deleteFdBondHolding,
    getFdBondHoldings,
    updateFdBondHolding,
    waitForApi,
    type FdBondHolding,
    type FdBondHoldings,
  } from "../../services/api";
  import { getFdBondColumns } from "./fd_bond_table_columns";
  import { summaryTotals } from "../../services/summary_store.svelte";
  import FdBondAddHoldingModal from "./fd_bond_add_holding_modal.svelte";
  import FdBondEditModal from "./fd_bond_edit_modal.svelte";
  import FdBondUploadModal from "./fd_bond_upload_modal.svelte";
  import "tabulator-tables/dist/css/tabulator.min.css";

  let status = $state("");
  let error = $state("");
  let addModalOpen = $state(false);
  let uploadModalOpen = $state(false);
  let editModalOpen = $state(false);
  let editingRow = $state<FdBondHolding | null>(null);

  let tableContainer = $state<HTMLDivElement>();
  let payload = $state<FdBondHoldings>({
    rows: [],
    as_on_date: "",
    grand_totals: {
      invested_amount: 0,
      current_value: 0,
      abs_gain_pct: 0,
      xirr_pct: 0,
    },
  });

  let table: Tabulator | null = null;
  let tableReady: Promise<void> | null = null;

  $effect(() => {
    const currentPayload: FdBondHoldings = payload;

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
      data: payload.rows ?? [],
      columns: getFdBondColumns(payload.grand_totals, openEditByRowId, deleteByRowId),
      movableColumns: true,
      columnCalcs: "table",
      layout: "fitColumns",
    });

    tableReady = new Promise((resolve) => {
      table!.on("tableBuilt", () => resolve());
    });
  }

  async function applyPayload(currentPayload: FdBondHoldings) {
    if (!tableReady) return;
    await tableReady;
    if (!table) return;

    table.setColumns(getFdBondColumns(currentPayload.grand_totals, openEditByRowId, deleteByRowId));
    table.setData(currentPayload.rows ?? []);
    table.recalc();
  }

  function openEditByRowId(entryId: number) {
    const row = payload.rows.find((r) => r.entry_id === entryId) ?? null;
    if (!row || row.can_edit === false) {
      return;
    }

    editingRow = row;
    editModalOpen = true;
  }

  async function deleteByRowId(entryId: number) {
    const row = payload.rows.find((r) => r.entry_id === entryId);
    if (!row || row.can_delete === false) {
      return;
    }

    status = "Deleting FD/Bond row...";
    const result = await deleteFdBondHolding(row);
    status = result.message;
    await loadFdBondHoldingsData();
  }

  async function saveEditedRow(updated: FdBondHolding) {
    if (!editingRow) {
      return;
    }

    status = "Updating FD/Bond row...";
    const result = await updateFdBondHolding(editingRow, updated);
    status = result.message;
    await loadFdBondHoldingsData();
  }

  async function loadFdBondHoldingsData() {
    error = "";
    try {
      status = "Loading FD/Bond holdings data...";
      const result = await getFdBondHoldings();
      payload = result.payload;
      summaryTotals.fd_bond = payload.grand_totals;

      if (!payload.rows || payload.rows.length === 0) {
        status = "No FD/Bond holdings data available";
        return;
      }

      status = result.message;
    } catch (e) {
      error = "Failed to load FD/Bond holdings: " + String(e);
      status = "Error";
    }
  }

  onMount(async () => {
    await waitForApi();
    await loadFdBondHoldingsData();
  });

  onDestroy(() => table?.destroy());
</script>

<main class="app-page">
  <header class="app-header">
    <h1 class="app-title">FD and Bonds - Holding Statement</h1>

    <div class="app-header-actions">
      {#if status}
        <span class="app-status">{status}</span>
      {/if}

      <div class="app-toolbar">
        <button class="app-button" onclick={() => (addModalOpen = true)}>
          Add FD/Bond Row
        </button>
        <button class="app-button" onclick={() => (uploadModalOpen = true)}>
          Upload PPF CSV
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

{#if addModalOpen}
  <FdBondAddHoldingModal bind:open={addModalOpen} onProcessed={loadFdBondHoldingsData} />
{/if}

{#if uploadModalOpen}
  <FdBondUploadModal bind:open={uploadModalOpen} onProcessed={loadFdBondHoldingsData} />
{/if}

{#if editModalOpen}
  <FdBondEditModal bind:open={editModalOpen} initialRow={editingRow} onSave={saveEditedRow} />
{/if}
