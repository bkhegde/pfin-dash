<script lang="ts">
  import { onDestroy, tick } from "svelte";
  import { getFolioList, updateFolioName } from "../../services/api";
  import type { ApiResult, FolioList } from "../../services/api";
  import { TabulatorFull as Tabulator } from "tabulator-tables";
  import type { CellComponent, ColumnDefinition } from "tabulator-tables";
  import MFModalShell from "../modal_shell.svelte";
  import "tabulator-tables/dist/css/tabulator.min.css";

  let { open = $bindable() } = $props<{ open: boolean }>();

  let folioList: FolioList[] = [];
  let status = $state("");
  let tableContainer = $state<HTMLDivElement>();
  let table: Tabulator | null = null;

  async function loadFolioList() {
    status = "Loading folios...";
    const result: ApiResult = await getFolioList();
    if (result.status === "success") {
      folioList = (result.payload ?? []) as FolioList[];
      status = `${folioList.length} folios loaded`;
      return;
    }

    status = "Failed to load folios";
    console.error("Error loading folio list:", result.message);
  }

  function initOrRefreshTable() {
    if (!tableContainer) return;

    const columns: ColumnDefinition[] = [
      {
        title: "Folio",
        field: "folio",
        sorter: "string",
        headerSort: true,
        editable: false,
        widthGrow: 1,
      },
      {
        title: "Folio Name",
        field: "folio_name",
        sorter: "string",
        editor: "input",
        widthGrow: 2,
        cellEdited: async (cell: CellComponent) => {
          const row = cell.getRow().getData() as FolioList;
          const oldName = String(cell.getOldValue() ?? "").trim();
          const newName = String(cell.getValue() ?? "").trim();

          if (!row?.folio || newName === oldName) return;

          const ok = await handleUpdateFolioName(row.folio, newName);
          if (!ok) {
            cell.restoreOldValue();
          }
        },
      },
    ];

    if (!table) {
      table = new Tabulator(tableContainer, {
        data: folioList,
        columns,
        layout: "fitColumns",
        movableColumns: true,
        height: "420px",
      });
      return;
    }

    table.setData(folioList);
  }

  async function handleUpdateFolioName(
    selectedFolio: string,
    newFolioName: string,
  ): Promise<boolean> {
    const result: ApiResult = await updateFolioName(
      selectedFolio,
      newFolioName,
    );
    if (result.status !== "success") {
      console.error("Error updating folio name:", result.message);
      status = "Failed to update folio name";
      return false;
    }

    status = `Updated folio name for ${selectedFolio}`;
    return true;
  }

  $effect(() => {
    if (!open) {
      table?.destroy();
      table = null;
      return;
    }

    let disposed = false;

    (async () => {
      await tick();
      if (disposed) return;

      await loadFolioList();
      if (disposed) return;

      initOrRefreshTable();
    })();

    return () => {
      disposed = true;
    };
  });

  onDestroy(() => table?.destroy());
</script>

{#if open}
  <MFModalShell bind:open={open} title="Edit Folio Names" width="980px">
    <div class="mf-table-host" bind:this={tableContainer}></div>

    {#snippet footer()}
      <div class="mf-modal-actions">
        {#if status}
          <span class="mf-status-note">{status}</span>
        {/if}
        <button class="mf-btn" onclick={() => (open = false)}>Close</button>
      </div>
    {/snippet}
  </MFModalShell>
{/if}

<style>
  .mf-table-host {
    min-height: 420px;
  }
</style>
