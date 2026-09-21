/**
 * Chạy đúng những script lọc control mà `costing.py` gửi vào Chrome, trên một
 * DOM tối thiểu.
 *
 * Các script này thay cho `is_visible()`/`is_enabled()`/`get_attribute()` của
 * Playwright để bớt lượt gọi CDP, nên ngữ nghĩa của chúng chính là thứ quyết
 * định app điền vào ô nào của Costing. Fake Python không chạy JS nên không
 * chạm tới được phần này; chỉ thực thi thật mới thấy một vị từ bị bỏ sót.
 *
 * Đọc {scripts, cases} từ file JSON, in ra JSON kết quả để phía Python khẳng
 * định từng trường hợp.
 */
const fs = require("fs");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

class Element {
  constructor(spec) {
    this.spec = spec;
    this.tagName = String(spec.tag || "input").toUpperCase();
    this.textContent = spec.textContent === undefined ? "" : spec.textContent;
    this.value = spec.value === undefined ? "" : spec.value;
  }

  get isConnected() {
    return this.spec.connected !== false;
  }

  getAttribute(name) {
    const value = this.spec[name];
    return value === undefined || value === null ? null : String(value);
  }

  getBoundingClientRect() {
    const hidden = this.spec.display === "none";
    return {
      width: hidden ? 0 : this.spec.width === undefined ? 120 : this.spec.width,
      height: hidden ? 0 : this.spec.height === undefined ? 20 : this.spec.height,
    };
  }

  matches(selector) {
    if (selector === ":disabled") return this.spec.disabled === true;
    throw new Error("DOM giả chưa hỗ trợ selector: " + selector);
  }
}

globalThis.getComputedStyle = (element) => ({
  display: element.spec.display || "block",
  visibility: element.spec.visibility || "visible",
});

const compile = (source) => eval("(" + source + ")");

const results = payload.cases.map((testCase) => {
  const run = compile(payload.scripts[testCase.script]);
  const elements = testCase.elements.map((spec) => new Element(spec));
  try {
    return { name: testCase.name, value: run(elements, testCase.arg) };
  } catch (error) {
    return { name: testCase.name, error: String(error && error.message) };
  }
});

process.stdout.write(JSON.stringify(results));
