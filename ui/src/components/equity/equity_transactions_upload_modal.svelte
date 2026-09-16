<script lang="ts">
  import MFModalShell from "../modal_shell.svelte";
  import { processEquityTransactionsCsv, readFileAsBase64 } from "../../services/api";

  let {
    open = $bindable(false),
    onProcessed,
  }: {
    open: boolean;
    onProcessed?: () => void | Promise<void>;
  } = $props();

  let file: File | null = $state(null);
  let statusMsg = $state("");
  let uploading = $state(false);
  let refreshNeeded = false;

  const canUpload = $derived(file !== null && !uploading);

  async function close() {
    open = false;
    if (refreshNeeded && onProcessed) {
      await onProcessed();
    }
    refreshNeeded = false;
  }

  async function upload() {
    if (!file) return;

    uploading = true;
    statusMsg = "Uploading equity transactions CSV...";

    try {
      const b64 = await readFileAsBase64(file);
      const res = await processEquityTransactionsCsv(file.name, b64);
      statusMsg = res.message;

      if (res.status === "success") {
        refreshNeeded = true;
      }
    } catch (e) {
      statusMsg = "Upload failed: " + String(e);
    } finally {
      uploading = false;
    }
  }
</script>

{#if open}
  <MFModalShell bind:open={open} title="Upload Equity Transactions CSV" width="560px">
    <div class="mf-form-grid">
      <label class="mf-field-label" for="equity-csv-file">Choose CSV file</label>
      <input
        id="equity-csv-file"
        class="mf-field-input"
        type="file"
        accept=".csv,text/csv"
        onchange={(e) => {
          const target = e.currentTarget as HTMLInputElement;
          file = target.files?.[0] ?? null;
          statusMsg = "";
        }}
      />

      {#if statusMsg}
        <p class="mf-status-note">{statusMsg}</p>
      {/if}
    </div>

    {#snippet footer()}
      <div class="mf-modal-actions">
        <button class="mf-btn" onclick={close}>Close</button>
        <button class="mf-btn mf-btn-primary" disabled={!canUpload} onclick={upload}>Upload</button>
      </div>
    {/snippet}
  </MFModalShell>
{/if}