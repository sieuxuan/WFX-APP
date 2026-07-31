# Thiết kế: Manual hệ thống trong ứng dụng WFX Smart

Ngày: 2026-08-01
Trạng thái: đã chốt với người dùng, chờ viết kế hoạch triển khai

## 1. Vấn đề

Nút Manual trên top nav (`wfx_panel/ui/index.html:19`) hiện chỉ gọi
`open_wfx_manual()` (`wfx_panel/panel_app.py:1217`) để mở một URL ngoài bằng
trình duyệt hệ thống. Người dùng WFX Smart không có tài liệu tra cứu nào nằm
trong chính ứng dụng: cần mạng, cần rời khỏi app, và nội dung trang web đó không
mô tả các tính năng của WFX Smart.

Tài liệu hiện có (`docs/USER_FEATURES.md`, `README.md`, `CLAUDE.md`) viết cho
người phát triển hoặc cho người đã biết sản phẩm, được cập nhật thủ công, và
không có cơ chế nào ngăn việc thêm tính năng mới mà quên viết tài liệu.

## 2. Mục tiêu

1. Người dùng bấm nút Manual là tra cứu được **toàn bộ** tính năng của WFX Smart,
   ngay trong ứng dụng, không cần mạng và không cần đăng nhập WFX.
2. Nội dung viết cho nhân viên nghiệp vụ dệt may, không dùng từ chuyên ngành
   công nghệ thông tin.
3. Tính năng mới thêm vào sản phẩm mà chưa có manual thì **test phải đỏ**.
4. Tài liệu người dùng chỉ tồn tại một nguồn; `docs/USER_FEATURES.md` sinh ra từ
   nguồn đó thay vì được duy trì song song.
5. Có sẵn một bản hướng dẫn (prompt) để phiên AI về sau viết bổ sung manual đúng
   giọng văn và đúng cấu trúc.

## 3. Không nằm trong phạm vi

- Không mở rộng kích thước panel chính (`WINDOW_WIDTH = 440`). Panel giữ vai trò
  thanh công cụ mảnh cạnh cửa sổ Chrome; nội dung đọc nhiều được đưa ra cửa sổ
  riêng.
- Không dịch manual sang ngôn ngữ khác. Toàn bộ nội dung tiếng Việt.
- Không làm nút "In toàn bộ hướng dẫn" thành một trang gộp riêng. `Ctrl+P` trên
  từng mục là đủ cho lần này.
- Không thay đổi bất kỳ luồng automation nào.

## 4. Kiến trúc

### 4.1 Thành phần mới

| Thành phần | Vai trò |
|---|---|
| `wfx_panel/manual/manifest.json` | Danh mục chương và mục, từ khoá, khai báo phủ tính năng |
| `wfx_panel/manual/NN-<chương>/<mục>.md` | Nội dung từng mục |
| `wfx_panel/manual_book.py` | Đọc manifest, dựng HTML, dựng chỉ mục tìm kiếm, kiểm tra phủ |
| `wfx_panel/ui/manual.html` | Khung cửa sổ tra cứu |
| `wfx_panel/ui/manual.css` | Trình bày, sáng/tối, CSS bản in |
| `wfx_panel/ui/manual.js` | Điều hướng, tìm kiếm, đánh dấu từ khoá |
| `scripts/generate_user_features.py` | Sinh `docs/USER_FEATURES.md` từ manual |
| `docs/MANUAL_AUTHORING.md` | Prompt/hướng dẫn viết manual cho lần sau |
| `docs/README.md` | Mục lục tài liệu, chỉ rõ file nào dùng cho việc gì |
| `tests/test_manual.py` | Test phủ tính năng và toàn vẹn manifest |

### 4.2 Luồng mở cửa sổ

`PanelApp.open_wfx_manual()` được viết lại:

- Lần đầu: `webview.create_window()` với tiêu đề `WFX Smart · Hướng dẫn sử dụng`,
  `url=MANUAL_INDEX`, `js_api=_ManualBridge(self)`, `width=1000`, `height=720`,
  `min_size=(720, 520)`, `resizable=True`, `frameless=False`.
- Lần sau khi cửa sổ đang tồn tại: đưa cửa sổ đó lên trước, **không** tạo cửa sổ
  trùng. Nhận biết bằng thuộc tính `self.manual_window` cộng kiểm tra cửa sổ còn
  trong `webview.windows`.
- Khi người dùng đóng cửa sổ, `self.manual_window` được đặt lại `None` qua sự
  kiện `closed` để lần bấm kế tiếp mở lại được.

Ràng buộc bắt buộc:

- Cửa sổ Manual **không** tham gia logic tự-thu của panel. Panel thu lại khi
  người dùng chuyển sang Manual là hành vi đúng; Manual phải ở nguyên. Cụ thể:
  monitor foreground Win32 không được coi cửa sổ Manual là "cửa sổ lạ" khiến
  panel thu — nhưng cũng không được vì Manual mà giữ panel mở.
- Manual **không** gọi mạng, không cần Chrome, không cần phiên WFX. Mở được khi
  mất mạng và khi chưa cấu hình tài khoản.
- Manual không được ghi bất cứ dữ liệu nghiệp vụ nào; nó chỉ đọc file tĩnh.

### 4.3 Bridge JS

`_ManualBridge` theo đúng khuôn `_BubbleBridge` (`wfx_panel/panel_app.py:340`):

| Phương thức | Trả về |
|---|---|
| `get_manual_book()` | `{"chapters": [...], "entries": [...], "search_index": [...], "theme": "light\|dark", "version": "1.0.17"}` |
| `open_manual_external()` | Mở `WFX_MANUAL_URL` (trang System Manual của WFX) bằng trình duyệt hệ thống |
| `close_manual()` | Đóng cửa sổ |

`get_manual_book()` trả toàn bộ nội dung đã dựng sẵn thành HTML trong một lần
gọi. Manual nhỏ (dưới 1 MB) nên không cần tải theo yêu cầu; đổi lại tìm kiếm và
chuyển mục là tức thời, không phụ thuộc cầu nối pywebview.

### 4.4 Dựng Markdown

`manual_book.py` dựng một tập con Markdown có giới hạn, ở phía Python, để
JavaScript không phải mang theo thư viện ngoài:

| Cú pháp | Kết quả |
|---|---|
| `## Tiêu đề` | tiêu đề mục con, có `id` để nhảy tới |
| `1.` / `-` | danh sách có số và không số |
| `**đậm**` | chữ đậm |
| `` `Tên nút` `` | nhãn nút, tô nền để đối chiếu với màn hình |
| bảng `\|` | bảng |
| `> [!meo]` | khối Mẹo |
| `> [!luuy]` | khối Lưu ý |
| `> [!loi]` | khối Gặp lỗi thì sao |

Mọi văn bản đều được escape HTML trước khi dựng. Không cho phép HTML thô trong
file `.md`; có test chặn.

## 5. Nội dung

### 5.1 Bảy chương nội dung

Ngoài bảy chương dưới đây, Manual còn có chương "Có gì mới" đứng đầu, sinh từ
`whats_new.json` (mục 8.3).

1. **Bắt đầu** — cài đặt, mở và đóng panel, phím tắt, biểu tượng khay, bong bóng
   nổi, đăng nhập WFX, chọn Division, mở Chrome.
2. **Dùng panel hằng ngày** — tìm module, ghim yêu thích, quay lại danh sách,
   nút Stop, thanh trạng thái dưới cùng, thông báo khi xong việc.
3. **Catalog** — tìm Style theo Article Code / Buyer Reference / Article Name,
   mở Costing, mở BOM, tải file đính kèm, Thư viện Article, cây thư mục.
4. **File Costing** — xuất file, kiểm tra file, nhập, áp dụng, bảng Color
   Mapping và Size Mapping, xoá phụ thuộc, quét lại danh sách chi phí.
5. **Đơn hàng và chứng từ** — OC (tìm, Upload OC New, Revise OC), Sample List
   (tìm, tạo mới, kiểm tra file), Sale ASN (tìm, tạo mới, tải bộ Documents).
6. **Các danh sách khác** — RMPO, Indent, User Indent, QA, Advance PR, Supplier
   Inv, Expense Inv, Org Structure, System Coding, Company Setup, Buyer,
   Supplier.
7. **Cài đặt, cập nhật và xử lý sự cố** — ba tab cài đặt, Lịch sử hoạt động,
   Góp ý và báo lỗi, cập nhật phần mềm, bảng tra mã lỗi, quyền riêng tư, giới
   hạn cần biết.

### 5.2 Khuôn từng mục

Mỗi mục có bốn phần, theo đúng thứ tự:

1. **Dùng để làm gì** — một đến hai câu, nói lợi ích chứ không nói cơ chế.
2. **Các bước** — danh sách đánh số, mỗi bước một hành động, luôn nêu rõ bấm nút
   nào trên màn hình nào.
3. **Mẹo** — không bắt buộc, tối đa ba ý.
4. **Gặp lỗi thì sao** — bảng hai cột: hiện tượng, cách xử lý.

### 5.3 Bảng tra mã lỗi

Chương 7 có một mục sinh tự động từ `wfx_panel/telemetry.ERROR_CODE_INFO`
(84 mã tại thời điểm viết). `manual_book.py` đọc thẳng từ điển này lúc chạy, nên
mã lỗi mới thêm vào code tự xuất hiện trong manual mà không phải sửa file `.md`.
Bảng gồm: mã, tiêu đề dễ hiểu, cách xử lý, và liên kết tới mục manual đã khai
báo phủ mã đó.

### 5.4 Quy ước ngôn ngữ

Dùng: màn hình, nút, ô nhập, danh sách, file Excel, trình duyệt.

Không dùng: frame, selector, CDP, postback, iframe, XPath, grid, DOM, endpoint,
payload, token. Có test chặn các từ này trong file `.md`.

## 6. Cơ chế chống sót tính năng

### 6.1 Khai báo phủ

Mỗi mục trong `manifest.json`:

```json
{
  "id": "catalog-tim-style",
  "title": "Tìm Style",
  "file": "03-catalog/tim-style.md",
  "keywords": ["article", "buyer reference", "style code", "mã hàng"],
  "covers": {
    "modules": ["0003_6200"],
    "buttons": ["catalog-find-code"],
    "settings": ["focus-chrome-input"],
    "errors": ["CATALOG_NO_RESULTS", "CATALOG_DATA_NOT_READY"]
  }
}
```

### 6.2 Bốn kiểm tra phủ trong `tests/test_manual.py`

| Nguồn sự thật | Trích từ | Yêu cầu |
|---|---|---|
| Module | `MODULE_GROUPS` trong `wfx_panel/ui/panel.js` | mỗi `id` module có ít nhất một mục phủ |
| Nút thao tác | các class nút trong các `module-*-panel` của `index.html` | mỗi nút được ít nhất một mục nhắc tới |
| Cài đặt | các input `*-input` trong ba tab cài đặt của `index.html` | mỗi công tắc được giải thích |
| Mã lỗi | `telemetry.ERROR_CODE_INFO` | mỗi mã có mặt trong bảng tra lỗi |

Việc trích xuất dùng biểu thức chính quy trên chính file nguồn, cùng kiểu với
`tests/test_panel_js.py` và `tests/test_ui_assets.py` đang làm.

### 6.3 Kiểm tra toàn vẹn

- Mọi `file` trong manifest phải tồn tại trên đĩa.
- Mọi file `.md` trong `wfx_panel/manual/` phải có trong manifest (không mồ côi).
- Không có chuỗi `TODO`, `TBD`, `...`, `chưa viết`.
- Không có từ trong danh sách cấm ở mục 5.4.
- Không có thẻ HTML thô.
- Mỗi mục có đủ phần "Dùng để làm gì" và "Các bước".

## 7. Đồng bộ tài liệu hệ thống

### 7.1 Một nguồn, ba đích

- `wfx_panel/manual/` là nguồn duy nhất của nội dung dành cho người dùng.
- `docs/USER_FEATURES.md` sinh tự động bằng `scripts/generate_user_features.py`,
  có dòng đầu ghi rõ file được sinh và không sửa tay. Một test so sánh nội dung
  trên đĩa với kết quả sinh lại; lệch thì đỏ.
- `README.md` và `CLAUDE.md` giữ vai trò kỹ thuật, được rà và bổ sung.

### 7.2 Các thiếu sót đã xác định, sẽ vá trong lần này

1. `README.md` mục "Chức năng nổi bật" thiếu: Sale ASN Documents, Sample List
   Check File, Clear All Dependency, Thư viện Article.
2. `CLAUDE.md` chưa có mục nào mô tả Manual và chưa có luật bắt buộc cập nhật
   manual khi đổi hành vi sản phẩm.
3. `docs/CATALOG_COSTING_FILES.md` và `docs/PERFORMANCE_1.0.15.md` không được
   liên kết từ đâu; thêm `docs/README.md` làm mục lục.
4. `wfx_panel/ui/index.html` hiển thị cứng "Phiên bản 1.0" trong khi bản phát
   hành là 1.0.17; đổi sang lấy từ `wfx_panel/version.py`.

## 8. Ba bổ sung đã chốt

### 8.1 Nút trợ giúp trong từng màn module

Mỗi `module-page` có thêm một nút biểu tượng dấu hỏi cạnh tiêu đề. Bấm vào mở
cửa sổ Manual tại đúng mục của module đó. Cách xác định mục: tra ngược
`covers.modules` trong manifest theo `id` module đang mở; nếu module có nhiều
mục thì mở mục đầu tiên theo thứ tự manifest.

Đường dẫn gọi: `open_wfx_manual(entry_id)` — tham số tuỳ chọn, không truyền thì
mở trang chủ manual.

### 8.2 Liên kết từ thẻ lỗi

Khi một tác vụ thất bại và mã lỗi có trong `ERROR_CODE_INFO`, thẻ kết quả lỗi
hiện thêm liên kết `Xem hướng dẫn xử lý`. Bấm vào mở Manual tại mục đã khai báo
phủ mã lỗi đó; nếu không mục nào phủ thì mở bảng tra mã lỗi và cuộn tới đúng
dòng.

### 8.3 Chương "Có gì mới" và chấm báo sau khi cập nhật

**Nguồn nội dung.** `wfx_panel/manual/whats_new.json` là danh sách bản phát hành,
mới nhất trước:

```json
[
  {
    "version": "1.0.18",
    "date": "2026-08-01",
    "highlights": [
      {
        "title": "Hướng dẫn sử dụng ngay trong ứng dụng",
        "body": "Bấm nút sách ở góc trên để tra cứu mọi tính năng.",
        "entry": "bat-dau-manual"
      }
    ]
  }
]
```

`entry` là tuỳ chọn; có thì mỗi mục "Có gì mới" hiện thêm liên kết `Xem hướng
dẫn` mở thẳng mục manual tương ứng.

**Vị trí.** Hiển thị thành chương đầu tiên của Manual, đứng trước chương
"Bắt đầu", và là một thẻ nổi bật trên trang chủ Manual. Chương này sinh từ JSON
chứ không phải file `.md`.

**Chấm báo trên nút Manual.** `prefs` thêm khoá `manual_seen_version`:

- Cài mới, chưa từng có khoá này: ghi luôn phiên bản hiện tại và **không** hiện
  chấm. Người dùng mới không bị làm phiền bởi tin tức của bản họ vừa cài.
- Sau khi cập nhật, `manual_seen_version` khác `wfx_panel.version.__version__`
  và `whats_new.json` có mục cho phiên bản hiện tại: nút Manual hiện chấm đỏ, tái
  sử dụng đúng khuôn `.log-alert` đang có của nút Lịch sử hoạt động.
- Mở Manual làm sạch chấm và ghi `manual_seen_version` bằng phiên bản hiện tại.
  Khi vào bằng chấm đỏ, Manual mở thẳng chương "Có gì mới".

**Test bắt buộc.** `wfx_panel.version.__version__` phải có một mục trong
`whats_new.json`. Phát hành phiên bản mới mà quên ghi thay đổi thì test đỏ —
cùng nguyên tắc với các kiểm tra phủ ở mục 6.

## 9. Giao diện cửa sổ Manual

- Bố cục hai cột: cột trái 260 px (ô tìm kiếm trên cùng, cây chương và mục), cột
  phải là nội dung.
- Trang chủ: thẻ nổi bật `Có gì mới` ở trên cùng, dưới là lưới bảy thẻ chương,
  cộng hai lối tắt `Tra nhanh mã lỗi` và `Câu hỏi thường gặp`.
- Tìm kiếm: từ hai ký tự trở lên, cột trái đổi thành danh sách kết quả kèm đoạn
  trích và tô vàng từ khoá. `Enter` mở kết quả đầu, `Esc` xoá ô tìm.
- Phạm vi tìm: tiêu đề mục, nội dung, `keywords`, và mã lỗi.
- Phím tắt: `Ctrl+F` nhảy vào ô tìm, `←`/`→` chuyển mục trước và sau, `Esc` đóng
  cửa sổ khi ô tìm đang trống.
- Sáng/tối theo cài đặt Giao diện của panel, lấy qua `get_manual_book()`.
- CSS riêng cho bản in để `Ctrl+P` ra trang sạch.

## 10. Đóng gói và kiểm thử

- `wfx_panel/wfx-panel.spec` thêm `("manual", "wfx_panel/manual")` vào `datas`.
  `tests/test_installer.py` hoặc test tương đương kiểm tra dòng này còn nguyên.
- `tests/test_manual.py`: phủ tính năng, toàn vẹn manifest, dựng Markdown, và
  `whats_new.json` có mục cho phiên bản hiện tại.
- `tests/test_prefs.py`: `manual_seen_version` mặc định bằng phiên bản hiện tại
  ở lần chạy đầu và không sinh chấm báo.
- `tests/test_ui_assets.py`: `manual.html` có ô tìm kiếm, mục lục, vùng nội dung.
- `tests/test_panel_app.py`: sửa `test_wfx_manual_opens_the_configured_url` thành
  kiểm tra mở cửa sổ Manual, không tạo cửa sổ trùng khi bấm lần hai, và mở đúng
  mục khi truyền `entry_id`.
- `tests/test_panel_js.py`: nút trợ giúp trong module page và liên kết trong thẻ
  lỗi được nối đúng.
- `python -m pytest` và `ruff check .` phải xanh.

## 11. Thứ tự triển khai

Phạm vi lớn, nên chia bốn giai đoạn, mỗi giai đoạn tự chạy được và có test xanh
trước khi sang giai đoạn sau:

1. **Nền** — `manual_book.py`, manifest, bộ dựng Markdown, hai mục mẫu, test
   toàn vẹn. Chưa động tới giao diện.
2. **Cửa sổ** — `manual.html`/`css`/`js`, `_ManualBridge`, viết lại
   `open_wfx_manual()`, test cửa sổ.
3. **Nội dung** — viết đủ bảy chương, bật bốn kiểm tra phủ ở mục 6.2. Đây là
   giai đoạn tốn công nhất.
4. **Kết nối và đồng bộ** — nút trợ giúp trong module, liên kết từ thẻ lỗi,
   chương "Có gì mới" và chấm báo, generator `docs/USER_FEATURES.md`,
   `docs/MANUAL_AUTHORING.md`, `docs/README.md`, vá `README.md` và `CLAUDE.md`,
   thêm `datas` vào file spec đóng gói.

## 12. Rủi ro

| Rủi ro | Xử lý |
|---|---|
| Cửa sổ Manual làm panel tự thu sai lúc | Test riêng cho logic foreground; Manual không nằm trong tập cửa sổ giữ panel mở |
| Test phủ quá chặt gây phiền khi sửa UI nhỏ | Chỉ phủ ở mức module, nút thao tác chính, công tắc cài đặt và mã lỗi — không phủ từng nhãn chữ |
| Nội dung manual phình to làm chậm mở cửa sổ | Dựng HTML một lần và nhớ trong bộ nhớ; đo, nếu vượt 1 MB thì chuyển sang tải theo chương |
| `docs/USER_FEATURES.md` sinh ra khác bản viết tay hiện có | Chấp nhận; bản sinh là nguồn chính thức từ nay |
