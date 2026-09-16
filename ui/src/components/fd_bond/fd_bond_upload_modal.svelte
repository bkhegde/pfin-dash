<script lang="ts">
	import ModalShell from "../modal_shell.svelte";
	import {
		processPpfRateCsv,
		processPpfTransactionsCsv,
		readFileAsBase64,
	} from "../../services/api";

	let {
		open = $bindable(false),
		onProcessed,
	}: {
		open: boolean;
		onProcessed?: () => void | Promise<void>;
	} = $props();

	let ppfFile: File | null = $state(null);
	let rateFile: File | null = $state(null);
	let statusMsg = $state("");
	let uploading = $state(false);
	let refreshNeeded = false;

	const PPF_TRANSACTIONS_TEMPLATE = [
		"Account Name,Transaction Date,Transaction Type,Amount,Notes",
		"My PPF Account,2025-04-01,Deposit,50000,Initial contribution",
		"My PPF Account,2025-06-10,Deposit,10000,Monthly savings",
		"My PPF Account,2026-03-31,Interest,3650,Interest credited by bank/post office",
		"My PPF Account,2026-07-12,Withdrawal,5000,Partial withdrawal",
	].join("\n");

	const PPF_RATES_TEMPLATE = [
		"Effective From,Annual Rate %,Source",
		"2023-04-01,7.10,DEA small savings notification",
		"2023-07-01,7.10,DEA small savings notification",
		"2023-10-01,7.10,DEA small savings notification",
		"2024-01-01,7.10,DEA small savings notification",
	].join("\n");

	const canUpload = $derived(ppfFile !== null && !uploading);

	async function close() {
		open = false;
		if (refreshNeeded && onProcessed) {
			await onProcessed();
		}
		refreshNeeded = false;
	}

	async function upload() {
		if (!ppfFile) {
			return;
		}

		uploading = true;
		const messages: string[] = [];

		try {
			statusMsg = `Uploading ${ppfFile.name}...`;
			const ppfB64 = await readFileAsBase64(ppfFile);
			const ppfRes = await processPpfTransactionsCsv(ppfFile.name, ppfB64);
			messages.push(ppfRes.message);

			if (rateFile) {
				statusMsg = `Uploading ${rateFile.name}...`;
				const rateB64 = await readFileAsBase64(rateFile);
				const rateRes = await processPpfRateCsv(rateFile.name, rateB64);
				messages.push(rateRes.message);
			}

			refreshNeeded = ppfRes.status === "success";
			statusMsg = messages.join(" ");
		} catch (e) {
			statusMsg = "Upload failed: " + String(e);
		} finally {
			uploading = false;
		}
	}

	function downloadTemplate(fileName: string, csvContent: string) {
		const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
		const url = URL.createObjectURL(blob);
		const anchor = document.createElement("a");
		anchor.href = url;
		anchor.download = fileName;
		document.body.appendChild(anchor);
		anchor.click();
		document.body.removeChild(anchor);
		URL.revokeObjectURL(url);
	}
</script>

{#if open}
	<ModalShell bind:open={open} title="Upload PPF Records" width="620px">
		<div class="mf-form-grid">
			<label class="mf-field-label" for="ppf-trans-file">PPF transactions CSV</label>
			<input
				id="ppf-trans-file"
				class="mf-field-input"
				type="file"
				accept=".csv,text/csv"
				onchange={(e) => {
					const target = e.currentTarget as HTMLInputElement;
					ppfFile = target.files?.[0] ?? null;
					statusMsg = "";
				}}
			/>

			<label class="mf-field-label" for="ppf-rate-file">PPF rates CSV (optional)</label>
			<input
				id="ppf-rate-file"
				class="mf-field-input"
				type="file"
				accept=".csv,text/csv"
				onchange={(e) => {
					const target = e.currentTarget as HTMLInputElement;
					rateFile = target.files?.[0] ?? null;
					statusMsg = "";
				}}
			/>

			<p class="mf-status-note">
				Transaction CSV columns: Account Name, Transaction Date, Transaction Type, Amount, Notes (optional).
			</p>
			<p class="mf-status-note">
				Optional rates CSV columns: Effective From, Annual Rate % (Source optional).
			</p>

			<div class="mf-modal-actions" style="justify-content:flex-start; gap:8px; padding:0;">
				<button
					class="mf-btn"
					type="button"
					onclick={() => downloadTemplate("ppf_transactions_template.csv", PPF_TRANSACTIONS_TEMPLATE)}
				>
					Download Transaction Template
				</button>
				<button
					class="mf-btn"
					type="button"
					onclick={() => downloadTemplate("ppf_rates_template.csv", PPF_RATES_TEMPLATE)}
				>
					Download Rates Template
				</button>
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
	</ModalShell>
{/if}
