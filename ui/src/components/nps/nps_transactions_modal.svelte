<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { TabulatorFull as Tabulator } from "tabulator-tables";
  import { npsTransactionColumns } from "./nps_transactions_columns";
  import { fmtAmount, fmtUnits } from "../../services/formatters";
  import { getNpsTransactions, type NpsTransaction } from "../../services/api";
  import { DateTime } from "luxon";

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).luxon = { DateTime };

  let {
    open = $bindable(),
    scheme,
    pran,
  } = $props<{ open: boolean; scheme: string; pran: string }>();

  let status = $state("Loading...");
  let summary = $state({
    transactionCount: 0,
    totalUnits: 0,
    grossAmount: 0,
    closingBalance: 0,
  });

  function hideMe() {
    open = false;
  }

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

  let table: Tabulator | null = null;
  let tableElement = $state<HTMLDivElement>();

  function toNumber(value: unknown): number {
    const parsed = Number(value ?? 0);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function buildSummary(transactions: NpsTransaction[]) {
    return transactions.reduce(
      (acc, transaction, index) => {
        acc.transactionCount += 1;
        acc.totalUnits += toNumber(transaction.units);
        acc.grossAmount += toNumber(transaction.amount);

        if (index === transactions.length - 1) {
          acc.closingBalance = toNumber(transaction.balance);
        }

        return acc;
      },
      {
        transactionCount: 0,
        totalUnits: 0,
        grossAmount: 0,
        closingBalance: 0,
      },
    );
  }

  async function refresh() {
    const result = await getNpsTransactions(scheme, pran);
    const transactions = result.payload ?? [];

    await table?.setData(transactions);
    summary = buildSummary(transactions);
    status = `${transactions.length} transactions`;
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
      columns: npsTransactionColumns,
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
      <header class="mf-txn-header" onmousedown={startDrag}>
        <div class="mf-txn-title">
          <h2>NPS Transactions</h2>

          <div class="mf-txn-subtitle">
            Scheme: {scheme} | PRAN: {pran}
          </div>
        </div>

        <button class="mf-btn" onclick={hideMe}>Close</button>
      </header>

      <div class="mf-txn-body">
        <div bind:this={tableElement} class="mf-txn-table"></div>
      </div>

      {#if status}
        <footer class="mf-txn-footer">
          <div class="mf-txn-footer-grid">
            <span>{status}</span>
            <span>Units: <span class="mf-num-cell">{fmtUnits(summary.totalUnits)}</span></span>
            <span>Contributions: <span class="mf-num-cell">{fmtAmount(summary.grossAmount)}</span></span>
            <span>Closing Balance: <span class="mf-num-cell">{fmtAmount(summary.closingBalance)}</span></span>
          </div>
        </footer>
      {/if}
    </div>
  </div>
{/if}