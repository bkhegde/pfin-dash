import { fmtAmount, fmtDate, fmtUnits } from "../../services/formatters";
import type { ColumnDefinition } from "tabulator-tables";
import type { CellComponent as CC } from "tabulator-tables";

export const npsTransactionColumns: ColumnDefinition[] = [
  {
    title: "Date",
    field: "txn_date",
    sorter: "date",
    sorterParams: { format: "yyyy-MM-dd" },
    width: 110,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtDate(String(c.getValue() ?? "")),
  },
  { title: "Type", field: "type", sorter: "string", width: 120 },
  {
    title: "Units",
    field: "units",
    sorter: "number",
    width: 110,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtUnits(c.getValue()),
  },
  {
    title: "Residual",
    field: "residual_units",
    sorter: "number",
    width: 120,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtUnits(c.getValue()),
  },
  {
    title: "NAV",
    field: "nav",
    sorter: "number",
    width: 100,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtUnits(c.getValue()),
  },
  {
    title: "Amount",
    field: "amount",
    sorter: "number",
    width: 120,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtAmount(c.getValue()),
  },
  {
    title: "Balance",
    field: "balance",
    sorter: "number",
    width: 120,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtAmount(c.getValue()),
  },
  { title: "PRAN", field: "pran", sorter: "string", width: 130 },
  { title: "Description", field: "description", sorter: "string", width: 180 },
  { title: "Source File", field: "source_file", sorter: "string", width: 180 },
];
