# Thiết kế lại UI/UX màn Sale ASN

Ngày: 2026-08-03

## Bối cảnh

Màn Sale ASN (`data-module-view="sale_asn"`) được phát triển dồn qua 5 commit gần
nhất và tích tụ nợ giao diện. Panel chỉ rộng 440px, cao 620px nên chiều dọc là
tài nguyên khan hiếm, trong khi màn hiện tại bắt người dùng đi qua hai tầng tab
rồi mới thấy nút thao tác thật.

### Vấn đề đã xác định trong bản hiện tại

1. **Hai tầng tab.** `Tra cứu | Tạo & điền`, rồi bên trong lại
   `Tạo mới / chọn bước | Chỉ Order Details (8 cột)`.
2. **Hai form Excel song song** (19 cột và 8 cột) với hai nút xuất gần trùng
   nghĩa — `Xuất PO đang mở` và `Xuất form Order Details từ WFX` — dù cả hai đều
   gọi `scan_sale_asn_order_details`.
3. **Khái niệm nâng cao đặt ở bước 1.** Bốn checkbox chọn bước
   (`Thêm PO`/`Order Details`/`Style Details`/`Shipping Info`) là cơ chế
   chạy-một-phần và resume, nhưng lại nằm trước cả ô Buyer.
4. **Không có tiến độ.** Flow chạy tuần tự bốn bước khá lâu mà UI im lặng, trong
   khi GDN Dispatch đã có thẻ tiến độ 6 bước.
5. **Trạng thái tản mát**: hai phần tử `.sale-asn-inline-status` riêng, cộng thẻ
   review, thẻ pending và footer.
6. **`Mở Sale ASN List` bị chôn trong pane Tra cứu**, trái với quy định trong
   `CLAUDE.md` là nút mở List luôn nằm ở thanh trên, và khiến tab Tạo không mở
   được List.
7. **Nhãn lệch nhau giữa ba nguồn**: `CLAUDE.md` ghi tab mặc định là
   `Tạo từ Excel` và `Tra cứu & Invoice/PKL`; manual ghi `Chỉ điền Order Details`;
   HTML ghi `Tra cứu` và `Chỉ Order Details (8 cột)`.
8. **Buyer dùng `<datalist>`**, không phản hồi được trạng thái "chưa khớp" ngay
   tại ô nhập, trong khi app đã có sẵn component listbox gợi ý ở Catalog.

### Cách dùng thực tế của người dùng

Luồng chính là **tạo mới trọn gói từ Excel**, sau đó **xuất Invoice + Packing
List** cho chính chứng từ vừa tạo. Hai tab hiện tại là hai đầu của cùng một hành
trình chứ không phải hai chức năng rời.

## Mục tiêu

- Màn mặc định chỉ còn ba việc: chọn Buyer, chọn file, bấm chạy.
- Nhìn là biết đang ở bước nào trong bốn bước và bước nào đã xong.
- Giữ nguyên 100% năng lực hiện có, kể cả chạy-một-phần và form 8 cột.
- Không đổi bất kỳ hành vi automation nào trên WFX.

## Phi mục tiêu

- Không đổi định dạng file Excel 19 cột hoặc 8 cột.
- Không đổi thứ tự thao tác trên WFX, không đổi selector, không tự bấm Save.
- Không đụng hành vi GDN Dispatch ngoài việc tổng quát hóa hàm progress.

## Kiến trúc giao diện mới

### Thanh trên

```
[ Tạo mới ] [ Tra cứu & Invoice/PKL ]        [☰]
```

- Hai tab, mặc định `Tạo mới`.
- `[☰]` là nút icon `Mở Sale ASN List`, hiện ở cả hai tab.
- Bỏ hẳn tầng tab thứ hai (`.sale-asn-create-modes`).

### Tab `Tạo mới`

Một cột dọc, ba khối cố định cộng một khối gấp:

**Khối 1 — Buyer.** Ô nhập kèm listbox gợi ý, tái dùng đúng cơ chế của
`catalog-article-suggestions` và `bindListboxKeys`:

- Gợi ý bắt đầu sau 2 ký tự, tối đa 20 kết quả, lọc trên `saleAsnBuyers` đang có
  trong bộ nhớ (không gọi backend).
- Khớp đúng exact một Buyer thì hiện dấu ✓ ngay trong ô.
- Có nội dung nhưng chưa khớp thì hiện chú thích lỗi ngay dưới ô.
- Nút `↻` quét lại Buyer từ WFX nằm cùng hàng.
- Khi bước `Thêm PO` bị bỏ tích, cả khối chuyển sang trạng thái không bắt buộc và
  làm mờ, không ẩn.

**Khối 2 — File.** Một nút chính `Chọn file & kiểm tra`. Bên dưới là một hàng hai
link phụ: `Tải form trống` và `Xuất PO đang mở`. Hai link này giữ nguyên hành vi
hiện tại, chỉ hạ trọng số thị giác.

**Khối 3 — Review, sau đó chuyển thành Tiến độ.** Đây là cùng một vùng, đổi nội
dung theo trạng thái:

- *Sau khi validate file:* thẻ review giữ đủ thông tin hiện có — tên file,
  Invoice No., số PO, số Style, Destination — cộng hai nút `Chọn lại` và
  `Bắt đầu tạo Sale ASN`.
- *Trong khi chạy:* thẻ tiến độ bốn dòng theo `SALE_ASN_STAGE_ORDER`, mỗi dòng có
  một trong bốn trạng thái `pending` / `active` / `done` / `warn`, kèm bộ đếm phụ
  cho bước có nhiều dòng (`Thêm PO · 3/4`).
- *Khi xong:* thẻ kết quả, xem mục Bàn giao bên dưới.

**Khối gấp — `Tùy chọn nâng cao`.** Mặc định đóng. Chứa:

- Bốn checkbox chọn bước, giữ nguyên `data-sale-asn-stage`.
- Nhóm `Chỉ điền Order Details (8 cột)` với hai nút xuất và chọn file, cộng thẻ
  review riêng của nó.
- Nút `Mở Sale ASN New trống`.

Khối tự bung khi mở module nếu có bất kỳ checkbox bước nào đang bỏ tích, để người
dùng không bị bất ngờ vì app chạy thiếu bước.

### Gộp trạng thái chờ và lỗi vào thẻ tiến độ

Thẻ `.sale-asn-pending` riêng biệt bị bỏ. Hai trạng thái của nó chuyển thành phần
mở rộng ngay tại dòng bước tương ứng trong thẻ tiến độ:

| Trạng thái backend | Dòng bước | Nội dung mở rộng |
|---|---|---|
| `SALE_ASN_PO_SELECTION_REQUIRED` | `Thêm PO` → `warn` | Thông báo dòng/PO cần chọn, checkbox xác nhận đã bấm `Add & Continue` hoặc `OK` trên WFX, nút `Tiếp tục dòng kế` (khóa tới khi tích) |
| `resumable = true` ở bước bất kỳ | Đúng bước đó → `warn` | Thông báo lỗi, nút `Thử lại bước này`, nút `Bỏ qua <tên bước>` khi `can_skip` |

Các dòng bước phía trước giữ trạng thái `done`, nên người dùng thấy ngay đã đi
được tới đâu thay vì chỉ đọc một thẻ vàng rời ngữ cảnh.

### Bàn giao sang Invoice/PKL

Khi nhận `SALE_ASN_FORM_COMPLETED`, thẻ kết quả hiện:

- Câu nhắc kiểm tra và tự bấm `Save` trên WFX (giữ nguyên nguyên tắc app không tự
  Save).
- Danh sách cảnh báo Shipping Info nếu có.
- Nút `Xuất Invoice + PKL cho <Invoice No.>`: chuyển sang tab
  `Tra cứu & Invoice/PKL`, đặt bộ lọc về `Invoice No.`, điền sẵn Invoice No. lấy
  từ review token và focus nút `Tìm`. Nút này **không** tự chạy xuất, vì người
  dùng còn phải Save trên WFX trước.

### Tab `Tra cứu & Invoice/PKL`

Giữ nguyên chức năng, chỉnh trọng số:

- `Tìm` là nút chính duy nhất trên hàng nhập.
- `Xuất Buyer Invoice + Packing List` đứng riêng một hàng bên dưới, không còn
  cạnh tranh với `Tìm`.
- `Mở Sale ASN List` rời khỏi pane này, lên thanh trên.

### Trạng thái gộp

Hai `.sale-asn-inline-status` gộp thành một vùng duy nhất trong tab `Tạo mới`.
Nhóm 8 cột trong khối nâng cao có vùng trạng thái riêng của nó vì đó là luồng
độc lập. Footer giữ nguyên vai trò hiện tại, không lặp lại nội dung.

## Thay đổi backend

### Tổng quát hóa progress

`PanelAPI._progress()` tại `wfx_panel/panel_api.py` đang hardcode
`"method": "run_gdn_dispatch"`. Thêm tham số `method: str` bắt buộc và truyền
đúng method của flow đang chạy. Payload giữ nguyên các khóa
`stage`/`message`/`step`/`total`/`state`/`run_id`.

Phía JS, `window.wfxHandleBackendProgress` hiện gán thẳng `updateGdnProgress`.
Đổi thành dispatcher rẽ theo `progress.method`:

- `run_gdn_dispatch` → `updateGdnProgress`
- `start_sale_asn_create`, `continue_sale_asn_create`,
  `skip_sale_asn_create_step` → `updateSaleAsnProgress`
- method lạ → bỏ qua, không ném lỗi

### Bắn progress trong `run_sale_asn_create`

Trong `wfx_panel/automation/sale_asn_create.py`, hàm nhận thêm tham số
`progress: Callable[..., None] | None = None` và gọi tại các điểm sau:

| Điểm gọi | stage | step/total | message |
|---|---|---|---|
| Trước khi chọn Buyer và mở Add Order Details | `po` | 1/4 | `Đang mở Add Order Details` |
| Mỗi vòng lặp `for index in range(first_pending, len(rows))` | `po` | 1/4 | `Thêm PO <index+1>/<len(rows)>` |
| Vào nhánh `step == "order_details"` | `order_details` | 2/4 | `Đang điền Order Details` |
| Vào nhánh `step == "style_details"` | `style_details` | 3/4 | `Đang điền Style Details` |
| Vào nhánh `step == "shipping_info"` | `shipping_info` | 4/4 | `Đang điền Shipping Info` |
| Bước bị bỏ qua theo `skipped` | stage đó | tương ứng | `Đã bỏ qua <tên bước>`, `state="skipped"` |

Tham số `progress` mặc định `None` để mọi lời gọi hiện có và toàn bộ test đang có
không phải sửa chữ ký.

Bộ đếm `step/total` luôn tính trên **bốn** bước cố định của
`SALE_ASN_STAGE_ORDER`, không tính theo số bước người dùng chọn, để dòng bước bị
bỏ tích vẫn hiện đúng vị trí trong danh sách với trạng thái `skipped`.

Progress chỉ là tín hiệu hiển thị. Nó không được đổi giá trị trả về, không được
nuốt exception, và lỗi trong chính hàm progress phải bị nuốt tại chỗ như
`_progress` hiện tại đang làm.

## Ranh giới các phần

- **HTML** khai báo cấu trúc tĩnh và các hook `data-*`; không chứa logic.
- **`panel.js`** giữ ba nhóm hàm tách bạch: `showSaleAsnView` cho điều hướng,
  `syncSaleAsnCreate` cho trạng thái form, và nhóm mới `updateSaleAsnProgress` +
  `renderSaleAsnRunResult` cho thẻ tiến độ. `renderSaleAsnRunResult` chỉ đặt
  trạng thái dòng bước, không tự dựng lại DOM.
- **`panel_api.py`** không biết gì về bố cục; nó chỉ bắn payload progress có
  `method`.
- Hàm `showSaleAsnCreateMode` bị xóa cùng tầng tab thứ hai. Hai hàm đang gọi nó,
  `exportSaleAsnContinueTemplate` và `exportSaleAsnOrderDetailsTemplate`, bỏ lời
  gọi đó; riêng hàm thứ hai và `chooseSaleAsnOrderDetailsInput` phải bung khối
  `Tùy chọn nâng cao` và cuộn tới nhóm 8 cột để kết quả không bị khuất trong khối
  đang đóng. Tương tự, `renderSaleAsnOrderResult` bung khối nâng cao thay vì
  chuyển mode.
- **`sale_asn_create.py`** không biết gì về UI; nó gọi một callback tùy chọn.

## Xử lý lỗi

- Không có mã lỗi mới. Toàn bộ mã hiện có
  (`SALE_ASN_PO_SELECTION_REQUIRED`, `SALE_ASN_FORM_COMPLETED`,
  `SALE_ASN_ORDER_DETAILS_COMPLETED`, `SALE_ASN_BUYER_REQUIRED`,
  `SALE_ASN_FILE_EMPTY`, `SALE_ASN_CREATE_STAGE_INVALID`,
  `SALE_ASN_FILE_DIALOG_CANCELLED`) giữ nguyên ý nghĩa và ánh xạ telemetry.
- Progress không được phát sinh telemetry.
- Nếu người dùng bấm `Stop`, flow trả `ACTION_CANCELLED` như cũ; thẻ tiến độ giữ
  nguyên trạng thái cuối cùng và hiện dòng đã hủy, không tự xóa.
- Mất kết nối progress (không nhận được payload nào) không được làm treo UI: thẻ
  tiến độ chỉ là hiển thị, nút bấm vẫn nhả theo result sink như quy định trong
  `CLAUDE.md`.

## Kiểm thử

**`tests/test_ui_assets.py`** — cập nhật `test_sale_asn_workspace_uses_one_flat_guided_flow`:

- Bỏ assert `'data-sale-asn-create-mode="full"'`, `'data-sale-asn-create-mode="order"'`,
  `.sale-asn-create-modes`, `.sale-asn-open-new` khỏi danh sách hook.
- Thêm assert: chỉ còn đúng hai `data-sale-asn-view`; có nút
  `data-module-action="sale-asn-list"` nằm trong `.sale-asn-toolbar`; có
  `.sale-asn-progress-card` với đủ bốn `data-sale-asn-progress-stage`; có
  `.sale-asn-advanced`; không còn `.sale-asn-pending` trong HTML.
- Assert bốn `data-sale-asn-stage` vẫn tồn tại (đã chuyển vào khối nâng cao).
- Bump `src="panel.js?v=..."` và assert theo giá trị mới.

**`tests/test_panel_js.py`** — thêm test: `wfxHandleBackendProgress` rẽ theo
`method` và có nhánh `updateSaleAsnProgress`; các test bridge hiện có giữ nguyên.

**`tests/test_sale_asn_create.py`** — thêm test: `run_sale_asn_create` gọi
callback progress đúng thứ tự `po → order_details → style_details →
shipping_info`, và bỏ qua đúng bước nằm trong `skip_stages`; chạy được khi
`progress=None`.

**`tests/test_manual.py`** — phải xanh sau khi cập nhật manual.

Cả `python -m pytest` và `ruff check .` phải xanh.

## Tài liệu phải cập nhật cùng lần sửa

- **`CLAUDE.md`**: mục Sale ASN — nêu đúng hai tab, tab mặc định `Tạo mới`, nút
  `Mở Sale ASN List` ở thanh trên, khối `Tùy chọn nâng cao` chứa chọn bước và
  form 8 cột, thẻ tiến độ bốn bước, và quy tắc bàn giao sang Invoice/PKL.
- **`wfx_panel/manual/05-don-hang/sale-asn.md`**: viết lại các bước theo bố cục
  mới, dùng đúng nhãn mới.
- **`wfx_panel/manual/whats_new.json`**: thêm mục cho lần thay đổi này.
- **`docs/USER_FEATURES.md`**: sinh lại bằng
  `python scripts/generate_user_features.py`, không sửa tay.

## Thống nhất nhãn

Ba nguồn phải dùng đúng một bộ chữ:

| Vị trí | Nhãn chốt |
|---|---|
| Tab 1 | `Tạo mới` |
| Tab 2 | `Tra cứu & Invoice/PKL` |
| Nút thanh trên | `Mở Sale ASN List` |
| Khối gấp | `Tùy chọn nâng cao` |
| Nhóm 8 cột | `Chỉ điền Order Details` |
| Nút mở New trống | `Mở Sale ASN New trống` |

## Rủi ro

- **Người dùng quen tab cũ.** Giảm nhẹ bằng mục `whats_new.json` và badge `Mới`
  trên nút Manual đã có sẵn.
- **Progress sai lệch với thực tế.** Progress chỉ hiển thị; nguồn sự thật vẫn là
  giá trị trả về của flow. `renderSaleAsnRunResult` chạy sau cùng và ghi đè trạng
  thái dòng bước, nên payload progress đến trễ không thể để lại trạng thái sai.
- **Regression cho GDN.** Việc thêm tham số `method` chạm hàm dùng chung; test
  hiện có của GDN phải giữ nguyên và xanh.
