<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { TabulatorFull as Tabulator } from "tabulator-tables";
  import {
    deleteSgbHolding,
    getSgbHoldings,
    setSgbGoldPrice,
    waitForApi,
    type SgbHoldings,
  } from "../../services/api";
  import { getSgbHoldingsColumns } from "./sgb_table_columns";
  import { summaryTotals } from "../../services/summary_store.svelte";
  import SgbAddHoldingModal from "./sgb_add_holding_modal.svelte";
  import "tabulator-tables/dist/css/tabulator.min.css";

  let status = $state("");
  let error = $state("");
  let addModalOpen = $state(false);

  let tableContainer = $state<HTMLDivElement>();
  let payload = $state<SgbHoldings>({
    rows: [],
    gold_price: 0,
    as_on_date: "",
    grand_totals: {
      invested_amount: 0,
      current_value: 0,
      abs_gain_pct: 0,
      xirr_pct: 0,
    },
  });

  let goldPriceDraft = $state("0");
  let table: Tabulator | null = null;
  let tableReady: Promise<void> | null = null;

  $effect(() => {
    const currentPayload: SgbHoldings = payload;

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
      columns: getSgbHoldingsColumns(payload.grand_totals, onDeleteRow),
      movableColumns: true,
      columnCalcs: "table",
      layout: "fitColumns",
    });

    tableReady = new Promise((resolve) => {
      table!.on("tableBuilt", () => resolve());
    });
  }

  async function applyPayload(currentPayload: SgbHoldings) {
    if (!tableReady) return;
    await tableReady;
    if (!table) return;

    table.setColumns(getSgbHoldingsColumns(currentPayload.grand_totals, onDeleteRow));
    table.setData(currentPayload.rows ?? []);
    table.recalc();
  }

  async function loadSgbHoldingsData() {
    error = "";
    try {
      status = "Loading SGB holdings data...";
      const result = await getSgbHoldings();
      payload = result.payload;
      goldPriceDraft = String(payload.gold_price ?? 0);
      summaryTotals.sgb = payload.grand_totals;

      if (!payload.rows || payload.rows.length === 0) {
        status = "No SGB holdings data available";
        return;
      }

      status = result.message;
    } catch (e) {
      error = "Failed to load SGB holdings: " + String(e);
      status = "Error";
    }
  }

  async function saveGoldPrice() {
    const parsed = Number(goldPriceDraft);
    if (!Number.isFinite(parsed) || parsed < 0) {
      status = "Enter a valid non-negative gold price";
      return;
    }

    status = "Saving gold price...";
    try {
      const result = await setSgbGoldPrice(parsed);
      status = result.message;
      await loadSgbHoldingsData();
    } catch (e) {
      status = "Gold price update failed";
      console.error(e);
    }
  }

  async function onDeleteRow(entryId: number) {
    status = "Deleting SGB row...";
    try {
      const result = await deleteSgbHolding(entryId);
      status = result.message;
      await loadSgbHoldingsData();
    } catch (e) {
      status = "Delete failed";
      console.error(e);
    }
  }

  onMount(async () => {
    await waitForApi();
    await loadSgbHoldingsData();
  });

  onDestroy(() => table?.destroy());
</script>

<main class="app-page">
  <header class="app-header">
    <h1 class="app-title">SGB - Holding Statement</h1>

    <div class="app-header-actions">
      {#if status}
        <span class="app-status">{status}</span>
      {/if}

      <div class="app-toolbar">
        <button class="app-button" onclick={() => (addModalOpen = true)}>
          Add SGB Holding
        </button>
      </div>
    </div>
  </header>

  <section class="app-table-wrap">
    <div class="app-inline-form">
      <label class="app-field-label" for="sgb-gold-price">Gold Price</label>
      <input
        id="sgb-gold-price"
        class="app-field-input app-inline-input"
        type="number"
        step="0.01"
        min="0"
        bind:value={goldPriceDraft}
      />
      <button class="app-button app-button--primary" onclick={saveGoldPrice}>Save Price</button>
    </div>

    <div class="app-table" bind:this={tableContainer}></div>
    {#if error}
      <p class="app-error">{error}</p>
    {/if}
  </section>
</main>

{#if addModalOpen}
  <SgbAddHoldingModal bind:open={addModalOpen} onProcessed={loadSgbHoldingsData} />
{/if}
