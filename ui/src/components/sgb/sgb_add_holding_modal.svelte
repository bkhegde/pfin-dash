<script lang="ts">
  import ModalShell from "../modal_shell.svelte";
  import { addSgbHolding } from "../../services/api";

  let {
    open = $bindable(false),
    onProcessed,
  }: {
    open: boolean;
    onProcessed?: () => void | Promise<void>;
  } = $props();

  let sgbName = $state("");
  let purchaseDate = $state("");
  let units = $state("");
  let purchasePrice = $state("");
  let statusMsg = $state("");
  let saving = $state(false);
  let refreshNeeded = false;

  const canSave = $derived(
    !saving &&
    sgbName.trim().length > 0 &&
    purchaseDate.trim().length > 0 &&
    Number(units) > 0 &&
    Number(purchasePrice) > 0,
  );

  async function close() {
    open = false;
    if (refreshNeeded && onProcessed) {
      await onProcessed();
    }
    refreshNeeded = false;
  }

  async function saveHolding() {
    if (!canSave) {
      return;
    }

    saving = true;
    statusMsg = "Saving SGB holding...";

    try {
      const res = await addSgbHolding(
        sgbName.trim(),
        purchaseDate,
        Number(units),
        Number(purchasePrice),
      );

      statusMsg = res.message;
      if (res.status === "success") {
        refreshNeeded = true;
      }
    } catch (e) {
      statusMsg = "Save failed: " + String(e);
    } finally {
      saving = false;
    }
  }
</script>

{#if open}
  <ModalShell bind:open={open} title="Add SGB Holding" width="560px">
    <div class="mf-form-grid">
      <label class="mf-field-label" for="sgb-name">SGB Name</label>
      <input id="sgb-name" class="mf-field-input" bind:value={sgbName} type="text" />

      <label class="mf-field-label" for="sgb-purchase-date">Purchase Date</label>
      <input id="sgb-purchase-date" class="mf-field-input" bind:value={purchaseDate} type="date" />

      <label class="mf-field-label" for="sgb-units">Units</label>
      <input id="sgb-units" class="mf-field-input" bind:value={units} type="number" step="0.0001" min="0" />

      <label class="mf-field-label" for="sgb-purchase-price">Purchase Price</label>
      <input
        id="sgb-purchase-price"
        class="mf-field-input"
        bind:value={purchasePrice}
        type="number"
        step="0.01"
        min="0"
      />

      {#if statusMsg}
        <p class="mf-status-note">{statusMsg}</p>
      {/if}
    </div>

    {#snippet footer()}
      <div class="mf-modal-actions">
        <button class="mf-btn" onclick={close}>Close</button>
        <button class="mf-btn mf-btn-primary" disabled={!canSave} onclick={saveHolding}>Save</button>
      </div>
    {/snippet}
  </ModalShell>
{/if}
