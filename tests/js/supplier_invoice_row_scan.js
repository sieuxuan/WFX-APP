/**
 * Chạy đúng hai script JS mà `supplier_invoice.py` gửi vào Chrome, trên một DOM
 * tối thiểu dựng theo WFXAPInvoiceList.aspx thật (29/10/2026): dòng
 * `tr.trContent`, ô mang id cột (`colInvoiceNo`, `colPoNumber`, `colASNGRN`…),
 * cột chọn là checkbox `chkSelector`. Đây là nhánh phá hủy dữ liệu
 * (Delete/Cancel Supplier Invoice) và là JS thuần, nên không lớp fake Python
 * nào chạm tới được: chỉ thực thi thật mới thấy lệch chỉ số dòng, đọc nhầm cột
 * hay tick nhầm dòng.
 */
const fs = require("fs");
const scripts = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

class Link {
  constructor(text) { this.textContent = text; }
}

class Cell {
  constructor({ id = "", text = "", links = [] }, index) {
    this.id = id;
    this.cellIndex = index;
    this.links = links.map((value) => new Link(value));
    this.ownText = text;
  }
  get textContent() {
    return this.links.length
      ? this.links.map((link) => link.textContent).join("")
      : this.ownText;
  }
  querySelectorAll(selector) { return selector === "a" ? this.links : []; }
}

class Checkbox {
  constructor() { this.checked = false; this.clicks = 0; }
  click() { this.checked = !this.checked; this.clicks += 1; }
}

class Row {
  constructor(cells, { id = "", visible = true, marked = true } = {}) {
    this.id = id;
    this.visible = visible;
    this.className = marked ? "trContent" : "";
    this.box = new Checkbox();
    this.cells = cells.map((cell, index) => new Cell(cell, index));
  }
  getAttribute() { return null; }
  querySelector(selector) {
    if (selector === "td") return this.cells[0] || null;
    if (selector.includes("checkbox")) return this.box;
    return null;
  }
  querySelectorAll(selector) { return selector === "td" ? this.cells : []; }
  click() {}
  get isConnected() { return true; }
  getBoundingClientRect() {
    return this.visible ? { width: 100, height: 20 } : { width: 0, height: 0 };
  }
}

// Thứ tự cột như WFX thật: colASN (ASN No.) đứng TRƯỚC colASNGRN.
const COLUMN_IDS = [
  "colSelector", "colStatus", "colSupplier", "colInvoiceNo",
  "colASN", "colPoNumber", "colASNGRN",
];
const HEADER_LABELS = [
  "", "Status", "Supplier", "Invoice No.", "ASN No.", "PO No.", "ASN/GRN No.",
];

function invoiceRow(invoice, status, options = {}) {
  const {
    pos = ["PO-1"], grns = ["GRN-1"], asn = "ASN-X", withIds = true, ...rowOptions
  } = options;
  const values = [
    { text: "" },
    { text: status },
    { text: "ACME" },
    { links: [invoice] },
    { links: [asn] },
    { links: pos },
    { links: grns },
  ];
  return new Row(
    values.map((value, index) => ({ ...value, id: withIds ? COLUMN_IDS[index] : "" })),
    rowOptions,
  );
}

function installDom() {
  global.document = {
    querySelector: (selector) =>
      selector === "#gridAPInvoiceList_trHeader"
        ? { cells: HEADER_LABELS.map((text) => ({ textContent: text })) }
        : null,
  };
  global.getComputedStyle = (element) => ({
    display: element.visible === false ? "none" : "block",
    visibility: "visible",
  });
}

function rootOf(rows) {
  return {
    querySelectorAll: (selector) => {
      if (selector === "tr.trContent") {
        return rows.filter((row) => row.className === "trContent");
      }
      if (selector === "tr") return rows;
      if (selector === 'input[type="checkbox"]') return rows.map((row) => row.box);
      return [];
    },
  };
}

function readRows(rows) {
  installDom();
  const root = rootOf(rows);
  return { root, read: eval(`(${scripts.rows})`)(root) };
}

function clickRow(root, expected) {
  return eval(`(${scripts.click})`)(root, expected);
}

const checkedInvoices = (rows) =>
  rows.filter((row) => row.box.checked).map((row) => row.cells[3].textContent);

let failures = 0;
function check(name, ok, detail) {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : "  -> " + detail}`);
  if (!ok) failures += 1;
}

// Cột đọc theo id: ASN No. đứng trước ASN/GRN No. và PO có nhiều link.
{
  const rows = [
    invoiceRow("SI-1", "Confirmed", {
      id: "774", pos: ["PSW-TRM-26-7072", "PSW-TRM-26-7290"],
      grns: ["R-PSW-26-12047", "R-PSW-26-12048"],
    }),
  ];
  const { read } = readRows(rows);
  const row = read[0] || {};
  check(
    "đọc đúng cột theo id, không lấy cột ASN No.",
    row.row_key === "774"
      && row.invoice_no === "SI-1"
      && row.status === "Confirmed"
      && row.po_no === "PSW-TRM-26-7072, PSW-TRM-26-7290"
      && row.asn_grn_no === "R-PSW-26-12047, R-PSW-26-12048",
    JSON.stringify(read),
  );
}

// Ô mất id thì dùng nhãn tiêu đề exact cùng chỉ số cột.
{
  const rows = [invoiceRow("SI-2", "Saved", { withIds: false, pos: ["PO-9"] })];
  const { read } = readRows(rows);
  const row = read[0] || {};
  check(
    "ô không có id vẫn đọc theo nhãn tiêu đề",
    row.po_no === "PO-9" && row.asn_grn_no === "GRN-1" && row.status === "Saved",
    JSON.stringify(read),
  );
}

// row_key có thể chỉ là chỉ số dòng. Nếu script đọc bỏ qua dòng ẩn còn script
// click thì không, chỉ số lệch và WFX bị bấm Delete lên dòng khác.
{
  const rows = [
    invoiceRow("SI-999", "Confirmed", { visible: false }),
    invoiceRow("SI-102", "Confirmed"),
    invoiceRow("SI-777", "Confirmed"),
  ];
  const { root, read } = readRows(rows);
  check(
    "đọc bỏ qua dòng ẩn",
    read.length === 2 && read[0].invoice_no === "SI-102",
    JSON.stringify(read),
  );
  clickRow(root, { row_key: read[0].row_key, invoice_no: read[0].invoice_no });
  check(
    "tick đúng dòng đã đọc dù có dòng ẩn đứng trước",
    JSON.stringify(checkedInvoices(rows)) === JSON.stringify(["SI-102"]),
    JSON.stringify(checkedInvoices(rows)),
  );
}

// Search WFX là tìm chứa chuỗi nên grid luôn có dòng gần đúng đứng cạnh.
{
  const rows = [
    invoiceRow("SI-1024", "Confirmed", { id: "r1" }),
    invoiceRow("SI-102", "Confirmed", { id: "r2" }),
  ];
  const { root } = readRows(rows);
  rows[0].id = "x1";
  rows[1].id = "x2";
  clickRow(root, { row_key: "r2", invoice_no: "SI-102" });
  check(
    "row_key hết hiệu lực thì vẫn phải khớp exact Invoice No.",
    JSON.stringify(checkedInvoices(rows)) === JSON.stringify(["SI-102"]),
    JSON.stringify(checkedInvoices(rows)),
  );
}

// Grid re-render giữ nguyên id nhưng đổi nội dung dòng.
{
  const rows = [invoiceRow("SI-OTHER", "Confirmed", { id: "r1" })];
  const { root } = readRows(rows);
  const clicked = clickRow(root, { row_key: "r1", invoice_no: "SI-102" });
  check(
    "row_key trùng nhưng Invoice No. đã đổi thì từ chối",
    clicked === false && rows[0].box.clicks === 0,
    `clicked=${clicked} clicks=${rows[0].box.clicks}`,
  );
}

// Delete/Cancel áp lên mọi dòng đang tick: dòng khác đã tick phải được bỏ, dòng
// đích đã tick sẵn không được bị click đảo thành bỏ tick.
{
  const rows = [
    invoiceRow("SI-5", "Saved", { id: "a" }),
    invoiceRow("SI-6", "Saved", { id: "b" }),
  ];
  rows[0].box.checked = true;
  rows[1].box.checked = true;
  const { root } = readRows(rows);
  const clicked = clickRow(root, { row_key: "b", invoice_no: "SI-6" });
  check(
    "chỉ còn đúng dòng đích được tick",
    clicked === true
      && JSON.stringify(checkedInvoices(rows)) === JSON.stringify(["SI-6"])
      && rows[1].box.clicks === 0,
    `clicked=${clicked} checked=${JSON.stringify(checkedInvoices(rows))}`,
  );
}

process.exit(failures ? 1 : 0);
