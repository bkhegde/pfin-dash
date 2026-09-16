<script lang="ts">
  import MFModalShell from "../modal_shell.svelte";
  import { processNpsTransactionsCsv, readFileAsBase64 } from "../../services/api";

  let {
    open = $bindable(false),
    onProcessed,
  }: {
    open: boolean;
    onProcessed?: () => void | Promise<void>;
  } = $props();

  let files = $state<File[]>([]);
  let statusMsg = $state("");
  let uploading = $state(false);
  let refreshNeeded = false;

  const canUpload = $derived(files.length > 0 && !uploading);

  async function close() {
    open = false;
    if (refreshNeeded && onProcessed) {
      await onProcessed();
    }
    refreshNeeded = false;
  }

  async function upload() {
    if (files.length === 0) return;

    uploading = true;
    const messages: string[] = [];
    let successCount = 0;

    try {
      for (const file of files) {
        statusMsg = `Uploading ${file.name}...`;
        const b64 = await readFileAsBase64(file);
        const res = await processNpsTransactionsCsv(file.name, b64);
        messages.push(res.message);
        if (res.status === "success") {
          successCount += 1;
        }
      }

      refreshNeeded = successCount > 0;
      statusMsg = messages.join(" ");
    } catch (e) {
      statusMsg = "Upload failed: " + String(e);
    } finally {
      uploading = false;
    }
  }
</script>

{#if open}
  <MFModalShell bind:open={open} title="Upload NPS Transactions CSV" width="560px">
    <div class="mf-form-grid">
      <label class="mf-field-label" for="nps-csv-file">Choose one or more CSV files</label>
      <input
        id="nps-csv-file"
        class="mf-field-input"
        type="file"
        accept=".csv,text/csv"
        multiple
        onchange={(e) => {
          const target = e.currentTarget as HTMLInputElement;
          files = Array.from(target.files ?? []);
          statusMsg = "";
        }}
      />

      {#if files.length > 0}
        <p class="mf-status-note">Selected {files.length} file(s): {files.map((file) => file.name).join(", ")}</p>
      {/if}

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