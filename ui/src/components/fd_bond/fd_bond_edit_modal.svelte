<script lang="ts">
  import ModalShell from "../modal_shell.svelte";
  import type { FdBondHolding } from "../../services/api";

  let {
    open = $bindable(false),
    initialRow,
    onSave,
  }: {
    open: boolean;
    initialRow: FdBondHolding | null;
    onSave?: (updated: FdBondHolding) => void | Promise<void>;
  } = $props();

  let instrumentName = $state("");
  let instrumentType = $state("FD");
  let purchaseDate = $state("");
  let maturityDate = $state("");
  let principalAmount = $state("");
  let interestRatePct = $state("");
  let interestPeriodYears = $state("");
  let payoutMethod = $state("Cumulative");
  let saving = $state(false);
  let statusMsg = $state("");

  $effect(() => {
    const row = initialRow;
    if (!open || !row) {
      return;
    }

    instrumentName = row.instrument_name;
    instrumentType = row.instrument_type || "FD";
    purchaseDate = row.purchase_date;
    maturityDate = row.maturity_date;
    principalAmount = String(row.principal_amount ?? "");
    interestRatePct = String(row.interest_rate_pct ?? "");
    interestPeriodYears = String(row.interest_period_years ?? "");
    payoutMethod = row.payout_method || "Cumulative";
    statusMsg = "";
  });

  const canSave = $derived(
    !saving
    && initialRow !== null
    && instrumentName.trim().length > 0
    && purchaseDate.trim().length > 0
    && maturityDate.trim().length > 0
    && Number(principalAmount) > 0
    && Number(interestPeriodYears) > 0,
  );

  async function save() {
    if (!canSave || !initialRow || !onSave) {
      return;
    }

    saving = true;
    statusMsg = "Saving changes...";

    try {
      await onSave({
        ...initialRow,
        instrument_name: instrumentName.trim(),
        instrument_type: instrumentType,
        purchase_date: purchaseDate,
        maturity_date: maturityDate,
        principal_amount: Number(principalAmount),
        interest_rate_pct: Number(interestRatePct),
        interest_period_years: Number(interestPeriodYears),
        payout_method: payoutMethod,
      });
      open = false;
    } catch (e) {
      statusMsg = "Update failed: " + String(e);
    } finally {
      saving = false;
    }
  }
</script>

{#if open}
  <ModalShell bind:open={open} title="Edit FD/Bond Row" width="620px">
    <div class="mf-form-grid">
      <label class="mf-field-label" for="fd-name">FD/Bond Name</label>
      <input id="fd-name" class="mf-field-input" bind:value={instrumentName} type="text" />

      <label class="mf-field-label" for="fd-type">Type</label>
      <select id="fd-type" class="mf-field-input" bind:value={instrumentType}>
        <option value="FD">FD</option>
        <option value="Bond">Bond</option>
        <option value="PPF">PPF</option>
      </select>

      <label class="mf-field-label" for="fd-purchase-date">Purchase Date</label>
      <input id="fd-purchase-date" class="mf-field-input" bind:value={purchaseDate} type="date" />

      <label class="mf-field-label" for="fd-principal">Principal Amount</label>
      <input id="fd-principal" class="mf-field-input" bind:value={principalAmount} type="number" min="0" step="0.01" />

      <label class="mf-field-label" for="fd-rate">Simple Interest Rate (per year, %)</label>
      <input id="fd-rate" class="mf-field-input" bind:value={interestRatePct} type="number" step="0.01" />

      <label class="mf-field-label" for="fd-period">Interest calculation period (years)</label>
      <input id="fd-period" class="mf-field-input" bind:value={interestPeriodYears} type="number" min="0" step="0.01" />

      <label class="mf-field-label" for="fd-payout">Payout method</label>
      <select id="fd-payout" class="mf-field-input" bind:value={payoutMethod}>
        <option value="Cumulative">Cumulative</option>
        <option value="Periodic">Periodic</option>
      </select>

      <label class="mf-field-label" for="fd-maturity-date">Maturity Date</label>
      <input id="fd-maturity-date" class="mf-field-input" bind:value={maturityDate} type="date" />

      {#if statusMsg}
        <p class="mf-status-note">{statusMsg}</p>
      {/if}
    </div>

    {#snippet footer()}
      <div class="mf-modal-actions">
        <button class="mf-btn" onclick={() => (open = false)}>Close</button>
        <button class="mf-btn mf-btn-primary" disabled={!canSave} onclick={save}>Save</button>
      </div>
    {/snippet}
  </ModalShell>
{/if}
