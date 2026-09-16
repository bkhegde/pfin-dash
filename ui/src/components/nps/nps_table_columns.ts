import { fmtAmount, fmtDate, fmtPct, fmtUnits } from "../../services/formatters";
import type { ColumnDefinition } from "tabulator-tables";
import type { CellComponent as CC } from "tabulator-tables";

export function getNpsHoldingsColumns(grandTotals: {
  abs_gain_pct: number;
  xirr_pct: number;
}): ColumnDefinition[] {
  return [
    {
      title: "Scheme / PRAN",
      field: "scheme_or_pran",
      sorter: "string",
      resizable: true,
      widthGrow: 2.4,
    },
    {
      title: "Units",
      field: "total_units",
      sorter: "number",
      hozAlign: "right",
      headerHozAlign: "right",
      cssClass: "mf-num-cell",
      formatter: (c: CC) => fmtUnits(c.getValue()),
    },
    {
      title: "Invested",
      field: "invested_amount",
      sorter: "number",
      hozAlign: "right",
      headerHozAlign: "right",
      cssClass: "mf-num-cell",
      formatter: (c: CC) => fmtAmount(c.getValue()),
      bottomCalc: "sum",
      bottomCalcFormatter: (c: CC) => fmtAmount(c.getValue()),
    },
    {
      title: "Current Value",
      field: "current_value",
      sorter: "number",
      hozAlign: "right",
      headerHozAlign: "right",
      cssClass: "mf-num-cell",
      formatter: (c: CC) => fmtAmount(c.getValue()),
      bottomCalc: "sum",
      bottomCalcFormatter: (c: CC) => fmtAmount(c.getValue()),
    },
    {
      title: "Abs Gain%",
      field: "abs_gain_pct",
      sorter: "number",
      hozAlign: "center",
      headerHozAlign: "center",
      cssClass: "mf-num-cell",
      formatter: (c: CC) => fmtPct(c.getValue()),
      bottomCalc: () => grandTotals.abs_gain_pct,
      bottomCalcFormatter: (c: CC) => fmtPct(c.getValue()),
    },
    {
      title: "XIRR%",
      field: "xirr_pct",
      sorter: "number",
      hozAlign: "center",
      headerHozAlign: "center",
      cssClass: "mf-num-cell",
      formatter: (c: CC) => fmtPct(c.getValue()),
      bottomCalc: () => grandTotals.xirr_pct,
      bottomCalcFormatter: (c: CC) => fmtPct(c.getValue()),
    },
    {
      title: "NAV",
      field: "nav",
      sorter: "number",
      hozAlign: "right",
      headerHozAlign: "right",
      cssClass: "mf-num-cell",
      formatter: (c: CC) => fmtUnits(c.getValue()),
    },
    {
      title: "NAV Dt",
      field: "nav_dt",
      sorter: "date",
      sorterParams: { format: "yyyy-MM-dd" },
      hozAlign: "center",
      headerHozAlign: "center",
      cssClass: "mf-num-cell",
      formatter: (c: CC) => fmtDate(String(c.getValue() ?? "")),
    },
  ];
}
