import { DELETE_ICON_HTML, fmtAmount, fmtDate, fmtUnits } from "../../services/formatters";
import type { ColumnDefinition } from "tabulator-tables";
import type { CellComponent as CC } from "tabulator-tables";

export const EQ_TXN_DELETE_FIELD = "_delete";

export const equityTransactionColumns: ColumnDefinition[] = [
  {
    title: "Date",
    field: "txn_date",
    sorter: "date",
    sorterParams: { format: "yyyy-MM-dd" },
    width: 110,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtDate(String(c.getValue() ?? "")),
  },
  { title: "Type", field: "type", sorter: "string", width: 100 },
  {
    title: "Units",
    field: "units",
    sorter: "number",
    width: 100,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtUnits(c.getValue()),
  },
  {
    title: "Price",
    field: "price",
    sorter: "number",
    width: 110,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtAmount(c.getValue()),
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
    title: "Charges",
    field: "charges",
    sorter: "number",
    width: 110,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtAmount(c.getValue()),
  },
  {
    title: "Net Amount",
    field: "net_amount",
    sorter: "number",
    width: 130,
    cssClass: "mf-num-cell",
    formatter: (c: CC) => fmtAmount(c.getValue()),
  },
  { title: "Exchange", field: "exchange", sorter: "string", width: 100 },
  { title: "Order ID", field: "order_id", sorter: "string", width: 120 },
  { title: "Source File", field: "source_file", sorter: "string", width: 180 },
  {
    title: "",
    field: EQ_TXN_DELETE_FIELD,
    width: 60,
    hozAlign: "center",
    headerSort: false,
    formatter: () => `<button class="mf-row-delete-btn" title="Delete transaction">${DELETE_ICON_HTML}</button>`,
  },
];
