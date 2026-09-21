/**
 * Chạy đúng hai script JS mà `modules.py` gửi vào Chrome, trên một DOM tối
 * thiểu. Đây là nhánh phá hủy dữ liệu (Delete/Cancel Supplier Invoice) và là
 * JS thuần, nên không lớp fake Python nào chạm tới được: chỉ thực thi thật mới
 * thấy lệch chỉ số dòng hay fallback khớp nhầm.
 */
const fs = require("fs");
const scripts = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

class Cell {
  constructor(text, index) {
    this.id = "";
    this.textContent = text;
    this.cellIndex = index;
    this.tagName = "TD";
    this.row = null;
  }
  getAttribute() { return null; }
  querySelector() { return null; }
  click() { if (this.row) this.row.clicked = true; }
}

class Row {
  constructor(texts, { id = "", visible = true } = {}) {
    this.id = id;
    this.visible = visible;
    this.clicked = false;
    this.tagName = "TR";
    this.cells = texts.map((text, index) => {
      const cell = new Cell(text, index);
      cell.row = this;
      return cell;
    });
  }
  getAttribute() { return null; }
  querySelector(selector) { return selector === "td" ? this.cells[0] || null : null; }
  querySelectorAll(selector) { return selector === "td" ? this.cells : []; }
  click() { this.clicked = true; }
  get textContent() { return this.cells.map((cell) => cell.textContent).join(" "); }
  get isConnected() { return true; }
  getBoundingClientRect() {
    return this.visible ? { width: 100, height: 20 } : { width: 0, height: 0 };
  }
}

const HEADERS = ["Invoice No", "Supplier", "PO No", "ASN GRN No", "Status"];

function installDom() {
  global.document = {
    querySelectorAll: () =>
      HEADERS.map((text, index) => ({
        id: "", textContent: text, cellIndex: index, getAttribute: () => null,
      })),
  };
  global.getComputedStyle = (element) => ({
    display: element.visible === false ? "none" : "block",
    visibility: "visible",
  });
}

const invoiceRow = (invoice, status, options) =>
  new Row([invoice, "ACME", "PO-1", "GRN-1", status], options);

function readRows(rows) {
  installDom();
  const root = { querySelectorAll: () => rows };
  return { root, read: eval(`(${scripts.rows})`)(root) };
}

function clickRow(root, expected) {
  return eval(`(${scripts.click})`)(root, expected);
}

const clickedInvoices = (rows) =>
  rows.filter((row) => row.clicked).map((row) => row.cells[0].textContent);

let failures = 0;
function check(name, ok, detail) {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : "  -> " + detail}`);
  if (!ok) failures += 1;
}

// row_key có thể chỉ là chỉ số dòng. Nếu script đọc bỏ qua dòng ẩn còn script
// click thì không, chỉ số lệch và WFX bị bấm Delete lên dòng khác.
{
  const rows = [
    invoiceRow("SI-999", "Confirm", { visible: false }),
    invoiceRow("SI-102", "Confirm"),
    invoiceRow("SI-777", "Confirm"),
  ];
  const { root, read } = readRows(rows);
  check(
    "đọc bỏ qua dòng ẩn",
    read.length === 2 && read[0].invoice_no === "SI-102",
    JSON.stringify(read),
  );
  clickRow(root, { row_key: read[0].row_key, invoice_no: read[0].invoice_no });
  check(
    "click đúng dòng đã đọc dù có dòng ẩn đứng trước",
    JSON.stringify(clickedInvoices(rows)) === JSON.stringify(["SI-102"]),
    JSON.stringify(clickedInvoices(rows)),
  );
}

// Search WFX là tìm chứa chuỗi nên grid luôn có dòng gần đúng đứng cạnh.
{
  const rows = [
    invoiceRow("SI-1024", "Confirm", { id: "r1" }),
    invoiceRow("SI-102", "Confirm", { id: "r2" }),
  ];
  const { root } = readRows(rows);
  rows[0].id = "x1";
  rows[1].id = "x2";
  clickRow(root, { row_key: "r2", invoice_no: "SI-102" });
  check(
    "row_key hết hiệu lực thì vẫn phải khớp exact Invoice No.",
    JSON.stringify(clickedInvoices(rows)) === JSON.stringify(["SI-102"]),
    JSON.stringify(clickedInvoices(rows)),
  );
}

// Grid re-render giữ nguyên id nhưng đổi nội dung dòng.
{
  const rows = [invoiceRow("SI-OTHER", "Confirm", { id: "r1" })];
  const { root } = readRows(rows);
  const clicked = clickRow(root, { row_key: "r1", invoice_no: "SI-102" });
  check(
    "row_key trùng nhưng Invoice No. đã đổi thì từ chối",
    clicked === false && rows[0].clicked === false,
    `clicked=${clicked} row.clicked=${rows[0].clicked}`,
  );
}

process.exit(failures ? 1 : 0);
