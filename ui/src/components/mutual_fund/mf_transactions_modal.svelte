<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { TabulatorFull as Tabulator } from "tabulator-tables";
  import type { CellComponent } from "tabulator-tables";
  import { mfTransactionColumns, MF_TXN_DELETE_FIELD } from "./mf_table_columns";
  import { getMfTransactions, deleteMfTransaction, type MfTransaction } from "../../services/api";
  import { fmtDate } from "../../services/formatters";
  import { DateTime } from "luxon";

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).luxon = { DateTime };

  // Props
  let {
    open = $bindable(),
    scheme,
    folio,
    onChanged,
  } = $props<{ open: boolean; scheme: string; folio: string; onChanged?: () => void | Promise<void> }>();

  let status = $state("Loading...");

  function hideMe() {
    open = false;
  }

  // Draggable related
  let left = $state(100);
  let top = $state(100);
  let zIndex = $state(100);

  let dragging = false;
  let startX = 0;
  let startY = 0;

  function startDrag(event: MouseEvent) {
    dragging = true;

    startX = event.clientX - left;
    startY = event.clientY - top;

    window.addEventListener("mousemove", drag);
    window.addEventListener("mouseup", stopDrag);
  }

  function drag(event: MouseEvent) {
    if (!dragging) return;

    left = event.clientX - startX;
    top = event.clientY - startY;
  }

  function stopDrag() {
    dragging = false;

    window.removeEventListener("mousemove", drag);
    window.removeEventListener("mouseup", stopDrag);
  }

  function bringToFront() {
    zIndex++;
  }

  // Table related
  let table: Tabulator | null = null;
  let tableElement = $state<HTMLDivElement>();


  async function refresh() {
    const result = await getMfTransactions(scheme, folio);

    await table?.setData(result.payload ?? []);

    status = `${result.payload?.length ?? 0} transactions`;
  }

  async function deleteRow(cell: CellComponent) {
    const txn = cell.getRow().getData() as MfTransaction;

    const confirmed = window.confirm(
      `Delete this transaction?\n\n${fmtDate(txn.txn_date)}  ${txn.type}  ${txn.units} units`
    );
    if (!confirmed) return;

    status = "Deleting transaction...";
    try {
      const result = await deleteMfTransaction(txn);
      status = result.message;

      if (result.status === "success") {
        await refresh();
        await onChanged?.();
      }
    } catch (e) {
      status = "Delete failed: " + String(e);
    }
  }

  onMount(async () => {
    if (!tableElement) {
      status = "Unable to initialize transactions table";
      return;
    }

    table = new Tabulator(tableElement, {
      layout: "fitDataStretch",

      columnDefaults: {
        minWidth: 100,
      },

      columns: mfTransactionColumns,
    });

    table.on("cellClick", (_event, cell) => {
      if (cell.getColumn().getField() === MF_TXN_DELETE_FIELD) {
        void deleteRow(cell);
      }
    });

    await refresh();
  });

  onDestroy(() => table?.destroy());
</script>

{#if open}
  <div class="mf-txn-overlay" role="presentation" onclick={(e) => e.target === e.currentTarget && hideMe()}>
    <div
      class="mf-txn-modal"
      role="dialog"
      tabindex="-1"
      style:left={`${left}px`}
      style:top={`${top}px`}
      style:z-index={zIndex}
      onmousedown={bringToFront}
    >
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <header class="mf-txn-header" onmousedown={startDrag}
  >
        <div class="mf-txn-title">
          <h2>Mutual Fund Transactions</h2>

          <div class="mf-txn-subtitle">
            Scheme: {scheme} | Folio: {folio}
          </div>
        </div>

        <button class="mf-btn" onclick={hideMe}>Close</button>
      </header>

      <div class="mf-txn-body">
        <div bind:this={tableElement} class="mf-txn-table"></div>
      </div>

      {#if status}
        <footer class="mf-txn-footer">
          {status}
        </footer>
      {/if}
    </div>
  </div>
{/if}