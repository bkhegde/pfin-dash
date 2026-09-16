import { DELETE_ICON_HTML, fmtAmount, fmtDate, fmtPct, fmtUnits } from "../../services/formatters";
import type { ColumnDefinition, CellComponent } from "tabulator-tables";

export function getSgbHoldingsColumns(
  grandTotals: {
    abs_gain_pct: number;
    xirr_pct: number;
  },
  onDelete: (entryId: number) => void,
): ColumnDefinition[] {
  return [
    {
      title: "SGB Name",
      field: "sgb_name",
      sorter: "string",
      widthGrow: 2,
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
      title: "Units",
      field: "units",
      sorter: "number",
      hozAlign: "right",
      headerHozAlign: "right",
      cssClass: "mf-num-cell",
      formatter: (cell: CellComponent) => fmtUnits(cell.getValue()),
      bottomCalc: "sum",
      bottomCalcFormatter: (cell: CellComponent) => fmtUnits(cell.getValue()),
    },
    {
      title: "Purchase Price",
      field: "purchase_price",
      sorter: "number",
      hozAlign: "right",
      headerHozAlign: "right",
      cssClass: "mf-num-cell",
      formatter: (cell: CellComponent) => fmtAmount(cell.getValue()),
    },
    {
      title: "Invested",
      field: "invested_amount",
      sorter: "number",
      hozAlign: "right",
      headerHozAlign: "right",
      cssClass: "mf-num-cell",
      formatter: (cell: CellComponent) => fmtAmount(cell.getValue()),
      bottomCalc: "sum",
      bottomCalcFormatter: (cell: CellComponent) => fmtAmount(cell.getValue()),
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
      title: "",
      field: "actions",
      width: 56,
      hozAlign: "center",
      headerSort: false,
      formatter: () => `<button class=\"mf-row-delete-btn\" type=\"button\" aria-label=\"Delete row\">${DELETE_ICON_HTML}</button>`,
      cellClick: (_event, cell) => {
        const rowData = cell.getData() as { entry_id?: number };
        const entryId = Number(rowData.entry_id ?? 0);
        if (entryId > 0) {
          onDelete(entryId);
        }
      },
    },
  ];
}
