import { DELETE_ICON_HTML, fmtAmount, fmtDate, fmtPct } from "../../services/formatters";
import type { CellComponent, ColumnDefinition } from "tabulator-tables";

const EDIT_ICON_HTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <path d="M4 20h4l10-10a2.2 2.2 0 0 0-4-4L4 16v4Z" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;

export function getFdBondColumns(
  grandTotals: { abs_gain_pct: number; xirr_pct: number },
  onEdit: (entryId: number) => void,
  onDelete: (entryId: number) => void,
): ColumnDefinition[] {
  return [
    {
      title: "Instrument",
      field: "instrument_name",
      sorter: "string",
      widthGrow: 2,
    },
    {
      title: "Type",
      field: "instrument_type",
      sorter: "string",
      hozAlign: "center",
      headerHozAlign: "center",
      width: 90,
    },
    {
      title: "Purchase Date",
      field: "purchase_date",
      sorter: "date",
      sorterParams: { format: "yyyy-MM-dd" },
      hozAlign: "center",
      headerHozAlign: "center",
      formatter: (cell: CellComponent) => fmtDate(String(cell.getValue() ?? "")),
    },
    {
      title: "Maturity Date",
      field: "maturity_date",
      sorter: "date",
      sorterParams: { format: "yyyy-MM-dd" },
      hozAlign: "center",
      headerHozAlign: "center",
      formatter: (cell: CellComponent) => fmtDate(String(cell.getValue() ?? "")),
    },
    {
      title: "Principal",
      field: "principal_amount",
      sorter: "number",
      hozAlign: "right",
      headerHozAlign: "right",
      cssClass: "mf-num-cell",
      formatter: (cell: CellComponent) => fmtAmount(cell.getValue()),
      bottomCalc: "sum",
      bottomCalcFormatter: (cell: CellComponent) => fmtAmount(cell.getValue()),
    },
    {
      title: "Rate%",
      field: "interest_rate_pct",
      sorter: "number",
      hozAlign: "center",
      headerHozAlign: "center",
      cssClass: "mf-num-cell",
      formatter: (cell: CellComponent) => fmtPct(cell.getValue()),
    },
    {
      title: "Payout",
      field: "payout_method",
      sorter: "string",
      hozAlign: "center",
      headerHozAlign: "center",
      width: 110,
    },
    {
      title: "Current Value",
      field: "current_value",
      sorter: "number",
      hozAlign: "right",
      headerHozAlign: "right",
      cssClass: "mf-num-cell",
      formatter: (cell: CellComponent) => fmtAmount(cell.getValue()),
      bottomCalc: "sum",
      bottomCalcFormatter: (cell: CellComponent) => fmtAmount(cell.getValue()),
    },
    {
      title: "Abs Gain%",
      field: "abs_gain_pct",
      sorter: "number",
      hozAlign: "center",
      headerHozAlign: "center",
      cssClass: "mf-num-cell",
      formatter: (cell: CellComponent) => fmtPct(cell.getValue()),
      bottomCalc: () => grandTotals.abs_gain_pct,
      bottomCalcFormatter: (cell: CellComponent) => fmtPct(cell.getValue()),
    },
    {
      title: "XIRR%",
      field: "xirr_pct",
      sorter: "number",
      hozAlign: "center",
      headerHozAlign: "center",
      cssClass: "mf-num-cell",
      formatter: (cell: CellComponent) => fmtPct(cell.getValue()),
      bottomCalc: () => grandTotals.xirr_pct,
      bottomCalcFormatter: (cell: CellComponent) => fmtPct(cell.getValue()),
    },
    {
      title: "Status",
      field: "status",
      sorter: "string",
      hozAlign: "center",
      headerHozAlign: "center",
      width: 95,
    },
    {
      title: "",
      field: "actions",
      width: 84,
      hozAlign: "center",
      headerSort: false,
      formatter: (cell: CellComponent) => {
        const rowData = cell.getData() as { can_edit?: boolean; can_delete?: boolean };
        const canEdit = rowData.can_edit !== false;
        const canDelete = rowData.can_delete !== false;
        if (!canEdit && !canDelete) {
          return "";
        }

        return `
          <div style="display:flex;gap:6px;justify-content:center;">
            ${canEdit ? `<button class="mf-row-delete-btn fd-edit-btn" type="button" aria-label="Edit row" style="background:#0d6772;">${EDIT_ICON_HTML}</button>` : ""}
            ${canDelete ? `<button class="mf-row-delete-btn fd-delete-btn" type="button" aria-label="Delete row">${DELETE_ICON_HTML}</button>` : ""}
          </div>
        `;
      },
      cellClick: (event, cell) => {
        const rowData = cell.getData() as { entry_id?: number };
        const entryId = Number(rowData.entry_id ?? 0);
        if (entryId <= 0) {
          return;
        }

        const target = event.target as HTMLElement;
        if (target.closest(".fd-edit-btn")) {
          onEdit(entryId);
          return;
        }

        if (target.closest(".fd-delete-btn")) {
          onDelete(entryId);
        }
      },
    },
  ];
}
