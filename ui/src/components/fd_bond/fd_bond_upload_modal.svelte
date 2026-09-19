<script lang="ts">
	import ModalShell from "../modal_shell.svelte";
	import {
		deletePpfRatesData,
		deletePpfTransactionsData,
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
		"2012-04-01,8.80,Government notification",
		"2013-04-01,8.70,Government notification",
		"2014-04-01,8.70,Government notification",
		"2015-04-01,8.70,Government notification",
		"2016-04-01,8.10,Government notification",
		"2016-10-01,8.00,Government notification",
		"2017-04-01,7.90,Government notification",
		"2017-07-01,7.80,Government notification",
		"2018-01-01,7.60,Government notification",
		"2018-10-01,8.00,Government notification",
		"2019-07-01,7.90,Government notification",
		"2020-04-01,7.10,Government notification",
	].join("\n");

	const canUploadTransactions = $derived(ppfFile !== null && !uploading);
	const canUploadRates = $derived(rateFile !== null && !uploading);

	async function close() {
		open = false;
		if (refreshNeeded && onProcessed) {
			await onProcessed();
		}
		refreshNeeded = false;
	}

	async function uploadTransactions() {
		if (!ppfFile) {
			statusMsg = "Choose a PPF transactions CSV before uploading.";
			return;
		}

		uploading = true;
		try {
			statusMsg = `Uploading ${ppfFile.name}...`;
			const ppfB64 = await readFileAsBase64(ppfFile);
			const ppfRes = await processPpfTransactionsCsv(ppfFile.name, ppfB64);
			statusMsg = ppfRes.message;
			refreshNeeded = ppfRes.status === "success";
		} catch (e) {
			statusMsg = "Upload failed: " + String(e);
		} finally {
			uploading = false;
		}
	}

	async function uploadRates() {
		if (!rateFile) {
			statusMsg = "Choose a PPF rates CSV before uploading.";
			return;
		}

		uploading = true;
		try {
			statusMsg = `Uploading ${rateFile.name}...`;
			const rateB64 = await readFileAsBase64(rateFile);
			const rateRes = await processPpfRateCsv(rateFile.name, rateB64);
			statusMsg = rateRes.message;
			refreshNeeded = rateRes.status === "success";
		} catch (e) {
			statusMsg = "Upload failed: " + String(e);
		} finally {
			uploading = false;
		}
	}

	async function deleteTransactions() {
		if (!window.confirm("Delete all uploaded PPF transaction rows?")) {
			return;
		}

		uploading = true;
		statusMsg = "Deleting uploaded PPF transactions...";
		try {
			const result = await deletePpfTransactionsData();
			statusMsg = result.message;
			ppfFile = null;
			refreshNeeded = result.status === "success";
		} catch (e) {
			statusMsg = "Delete failed: " + String(e);
		} finally {
			uploading = false;
		}
	}

	async function deleteRates() {
		if (!window.confirm("Delete all uploaded PPF rate rows and restore default fallback rate?")) {
			return;
		}

		uploading = true;
		statusMsg = "Deleting uploaded PPF rates...";
		try {
			const result = await deletePpfRatesData();
			statusMsg = result.message;
			rateFile = null;
			refreshNeeded = result.status === "success";
		} catch (e) {
			statusMsg = "Delete failed: " + String(e);
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
		anchor.style.display = "none";
		document.body.appendChild(anchor);
		anchor.click();
		setTimeout(() => {
			document.body.removeChild(anchor);
			URL.revokeObjectURL(url);
		}, 1000);
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

			<label class="mf-field-label" for="ppf-rate-file">PPF rates CSV (separate historical file)</label>
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
				Transactions CSV columns: Account Name, Transaction Date, Transaction Type, Amount, Notes (optional).
			</p>
			<p class="mf-status-note">
				Rates CSV columns: Effective From, Annual Rate %, Source. This is a separate historical file and can be uploaded independently of transactions.
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

			<div class="mf-modal-actions" style="justify-content:flex-start; gap:8px; padding:0; margin-top:8px;">
				<button class="mf-btn" type="button" disabled={uploading} onclick={deleteTransactions}>
					Delete Uploaded Transactions
				</button>
				<button class="mf-btn" type="button" disabled={uploading} onclick={deleteRates}>
					Delete Uploaded Rates
				</button>
			</div>

			{#if statusMsg}
				<p class="mf-status-note">{statusMsg}</p>
			{/if}
		</div>

		{#snippet footer()}
			<div class="mf-modal-actions">
				<button class="mf-btn" onclick={close}>Close</button>
				<button class="mf-btn mf-btn-primary" disabled={!canUploadTransactions} onclick={uploadTransactions}>
					Upload Transactions
				</button>
				<button class="mf-btn mf-btn-primary" disabled={!canUploadRates} onclick={uploadRates}>
					Upload Rates
				</button>
			</div>
		{/snippet}
	</ModalShell>
{/if}
