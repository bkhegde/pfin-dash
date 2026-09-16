<script lang="ts">
  import MFModalShell from "../modal_shell.svelte";
  import { processCasPdf, readFileAsBase64 } from "../../services/api";

  let {
    open = $bindable(false),
    onProcessed,
  }: {
    open: boolean;
    onProcessed?: () => void | Promise<void>;
  } = $props();

  let file: File | null = $state(null);
  let password = $state("");
  let showPassword = $state(false);
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
    statusMsg = "Processing... this may take a moment.";

    try {
      const b64 = await readFileAsBase64(file);
      const res = await processCasPdf(file.name, password, b64);
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
  <MFModalShell bind:open={open} title="Upload CAMS CAS PDF" width="560px">
    <div class="mf-form-grid">
      <label class="mf-field-label" for="cas-file">Choose PDF file</label>
      <input
        id="cas-file"
        class="mf-field-input"
        type="file"
        accept=".pdf,application/pdf"
        onchange={(e) => {
          const target = e.currentTarget as HTMLInputElement;
          file = target.files?.[0] ?? null;
          statusMsg = "";
        }}
      />

      <label class="mf-field-label" for="cas-password">PDF Password (optional)</label>
      <input
        id="cas-password"
        class="mf-field-input"
        type={showPassword ? "text" : "password"}
        placeholder="Enter password if needed"
        bind:value={password}
        oninput={() => {
          statusMsg = "";
        }}
      />

      <label class="mf-field-label" for="cas-show-password">Password visibility</label>
      <div>
        <label for="cas-show-password">
          <input id="cas-show-password" type="checkbox" bind:checked={showPassword} />
          Show password
        </label>
      </div>

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
