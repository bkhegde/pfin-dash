<script lang="ts">
  import ModalShell from "../modal_shell.svelte";
  import { addFdBondHolding } from "../../services/api";

  let {
    open = $bindable(false),
    onProcessed,
  }: {
    open: boolean;
    onProcessed?: () => void | Promise<void>;
  } = $props();

  let instrumentName = $state("");
  let instrumentType = $state("FD");
  let purchaseDate = $state("");
  let maturityDate = $state("");
  let principalAmount = $state("");
  let interestRatePct = $state("");
  let interestPeriodYears = $state("1");
  let payoutMethod = $state("Cumulative");
  let statusMsg = $state("");
  let saving = $state(false);
  let refreshNeeded = false;

  const canSave = $derived(
    !saving
    && instrumentName.trim().length > 0
    && purchaseDate.trim().length > 0
    && maturityDate.trim().length > 0
    && Number(principalAmount) > 0
    && Number(interestPeriodYears) > 0,
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
    statusMsg = "Saving FD/Bond row...";

    try {
      const res = await addFdBondHolding(
        instrumentName.trim(),
        instrumentType,
        purchaseDate,
        Number(principalAmount),
        Number(interestRatePct || 0),
        Number(interestPeriodYears),
        payoutMethod,
        maturityDate,
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
  <ModalShell bind:open={open} title="Add FD/Bond Row" width="620px">
    <div class="mf-form-grid">
      <label class="mf-field-label" for="fd-add-name">FD/Bond Name</label>
      <input id="fd-add-name" class="mf-field-input" bind:value={instrumentName} type="text" />

      <label class="mf-field-label" for="fd-add-type">Type</label>
      <select id="fd-add-type" class="mf-field-input" bind:value={instrumentType}>
        <option value="FD">FD</option>
        <option value="Bond">Bond</option>
        <option value="PPF">PPF</option>
      </select>

      <label class="mf-field-label" for="fd-add-purchase-date">Purchase Date</label>
      <input id="fd-add-purchase-date" class="mf-field-input" bind:value={purchaseDate} type="date" />

      <label class="mf-field-label" for="fd-add-principal">Principal Amount</label>
      <input id="fd-add-principal" class="mf-field-input" bind:value={principalAmount} type="number" min="0" step="0.01" />

      <label class="mf-field-label" for="fd-add-rate">Simple Interest Rate (per year, %)</label>
      <input id="fd-add-rate" class="mf-field-input" bind:value={interestRatePct} type="number" step="0.01" />

      <label class="mf-field-label" for="fd-add-period">Interest calculation period (years)</label>
      <input id="fd-add-period" class="mf-field-input" bind:value={interestPeriodYears} type="number" min="0" step="0.01" />

      <label class="mf-field-label" for="fd-add-payout">Payout method</label>
      <select id="fd-add-payout" class="mf-field-input" bind:value={payoutMethod}>
        <option value="Cumulative">Cumulative</option>
        <option value="Periodic">Periodic</option>
      </select>

      <label class="mf-field-label" for="fd-add-maturity-date">Maturity Date</label>
      <input id="fd-add-maturity-date" class="mf-field-input" bind:value={maturityDate} type="date" />

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
