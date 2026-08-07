# Báo cáo `Color Combination - Production`

Ngày: 2026-08-07

## Vấn đề

Báo cáo `Color combination cost sheet_Production` trên WFX chỉ xuất được **một
style mỗi lần view report**. Tham số lại phụ thuộc nhau nên user phải chọn lại
từ đầu cho từng style. Một mùa có hơn 50 style thì đây là công việc lặp tay
hàng giờ.

Báo cáo `Shipment Summary` hiện có không dùng lại được: nó đọc toàn bộ tham số
trong một lượt và một lần chạy ra đúng một file. Báo cáo mới phá cả hai giả
định đó.

## Mục tiêu

User chọn `OC Division` → `Buyer` → `Season` một lần, tick những
`BuyerStyleReference` cần tải, bấm một nút, rồi để app tự chạy hết: chọn style,
chọn `StyleCode`, view report, tải Excel, lưu file theo tên style, sang style
kế.

Ngoài phạm vi: không sửa dữ liệu WFX, không tự Save bất cứ thứ gì, không đổi
hành vi báo cáo `Shipment Summary`.

## Tham số của báo cáo

| Tham số | Loại | Xử lý |
| --- | --- | --- |
| `OC Division` | select | user chọn, nhớ lần sau |
| `Buyer` | select | user chọn, nhớ lần sau |
| `Season` | select | user chọn, nhớ lần sau |
| `SearchStyle` | text + checkbox NULL | bỏ qua hoàn toàn, không đụng vào |
| `BuyerStyleReference` | select | app lặp qua danh sách user tick |
| `StyleCode` | select | app tự chọn mã có số lớn nhất |
| `OCNum` | multiselect popup | giữ nguyên mặc định WFX, chỉ chờ nạp xong |
| `SizeVisibility` | select | chỉ set `Yes` nếu đang khác `Yes` |

Mỗi lần đổi một select, ReportViewer chạy async postback và nạp lại các tham số
phía dưới.

URL báo cáo:

```
https://prosports.worldfashionexchange.com/WFXBase4.0/WFXBICustomReportView.aspx
  ?BICustomReportID=0864e93b-ee5d-4dbc-840e-c83a1b44d728
  &Path=/WFXPSHLIVE/Production%20Reports/Color%20combination%20cost%20sheet_Production
  &LoginID=psh45&GUID=cc0170bb-4722-47fa-928e-8d5d6e4c6c03&ReportParams=
```

## Kiến trúc

### Chỗ đặt code

`reports.py` giữ vai trò primitive dùng chung cho mọi báo cáo ReportViewer:
`_open_report`, `_click_view_report`, `_wait_report_ready`, `_export_excel`,
`_is_report_page`. Thêm `_wait_postback_settled()` tách ra từ logic
`Sys.WebForms.PageRequestManager` đang nằm trong `_wait_report_ready`.

`wfx_panel/automation/color_combination.py` (mới) chứa phần riêng: cascade tham
số, vòng lặp batch, lưu file theo style.

Hai flow chỉ chung *cơ chế ReportViewer*, không chung *logic nghiệp vụ*. Gộp
vào một file sẽ đẩy `reports.py` lên khoảng 900 dòng với hai mô hình chạy trộn
nhau.

`REPORTS` giữ vai trò catalog, thêm entry `color_combination_production` với
khóa `kind`: `"simple"` cho Shipment Summary, `"cascade_batch"` cho báo cáo
mới. `report_catalog()` trả thêm `kind` để `panel.js` biết render form nào.

### Điều khiển tham số cascade

Không hardcode control id dạng `..._ctl03_ddValue`: sau mỗi postback
ReportViewer render lại bảng tham số và id có thể đổi.

`_resolve_controls(page) -> dict[label, control_id]` đọc
`#ParameterTable_rptCustomReportViewer_ctl04`, lấy nhãn từ
`valueCell.previousElementSibling` đúng như `_read_parameters` đang làm, và
chạy lại sau mỗi postback.

`_select_and_settle(page, label, value)`:

1. `checkpoint()`
2. `select_option(value)` trên đúng `<select>`
3. chờ `get_isInAsyncPostBack()` về false và không còn overlay `AsyncWait` hiển
   thị, ổn định 0,5 giây, trần 45 giây
4. resolve lại control map

Quá 45 giây thì trả `COLOR_REPORT_OPTIONS_NOT_READY`.

### Chọn StyleCode

Với danh sách option của `StyleCode`:

- đúng một option: dùng option đó, kể cả khi không parse được số;
- nhiều option: tách toàn bộ chữ số cuối mã (`SWV0003935` → `3935`) và lấy mã
  có số lớn nhất, tức style mới nhất;
- nhiều option mà không mã nào có chữ số: lấy option cuối và ghi cảnh báo vào
  log kỹ thuật;
- bằng nhau: lấy option xuất hiện sau.

Không có option nào: lỗi ở mức từng style, ghi `COLOR_REPORT_STYLECODE_MISSING`
vào `failed[]` và chạy tiếp style kế.

### Lưu file

Thư mục đích do user chọn một lần, nhớ vào `prefs.report_export_dir` theo đúng
pattern `costing_export_dir` / `sale_asn_import_dir` đang có.

Tên file: `<BuyerStyleReference> - <StyleCode>.xlsx`, ví dụ
`GWSD15176 - SWV0003935.xlsx`. Ký tự Windows cấm (`\/:*?"<>|`) được thay bằng
`_`. Trùng tên thì thêm ` (2)`, ` (3)`…

Theo `CLAUDE.md`, download đi qua Chrome native: chụp `snapshot_downloads()`
trước khi click export, rồi copy file native sang đường dẫn nghiệp vụ. Không
dùng `download.save_as()`.

## API backend

Ba method mới trên `PanelAPI`, đều qua `self._run()` vì đều chạm Playwright.

### `load_color_report_options(values)`

Nhận `{division, buyer, season}`, có thể thiếu hoặc rỗng. App mở report, áp lần
lượt các giá trị hợp lệ, trả về:

```
{levels: {division: {options, value},
          buyer:    {options, value},
          season:   {options, value},
          style_ref:{options, value}}}
```

Một method duy nhất dùng cho cả lần mở đầu lẫn mỗi lần user đổi một cấp: UI chỉ
gửi state hiện tại. Nếu một giá trị đã lưu không còn trong option, app bỏ qua
từ cấp đó trở xuống và trả về option mới.

Mùa không có style nào: `COLOR_REPORT_STYLE_LIST_EMPTY`.

### `run_color_report_batch(selection, style_refs, output_dir, progress=None)`

Với mỗi `style_ref` theo đúng thứ tự UI gửi lên:

1. `checkpoint()`
2. đặt `BuyerStyleReference`, chờ postback
3. đọc option `StyleCode`, chọn theo quy tắc trên, đặt, chờ postback
4. `snapshot_downloads()` → `_click_view_report` → `_wait_report_ready`
   (trần 5 phút, dùng `REPORT_READY_TIMEOUT_SECONDS` sẵn có)
5. `_export_excel` → copy file native sang `output_dir`
6. bắn progress, message kết thúc bằng `n/m`
7. lỗi bất kỳ ở bước 2–5: ghi `{style_ref, code, message}` vào `failed[]` rồi
   `continue`

Trả `ok=True`, code `COLOR_REPORT_BATCH_DONE`,
`{saved: [...], failed: [...], output_dir}` — kể cả khi có style lỗi, vì bản
thân lượt chạy đã hoàn tất.

Bắt `AutomationCancelled` để nút Stop vẫn trả về danh sách file đã lưu với code
`COLOR_REPORT_CANCELLED`, thay vì mất trắng cả lượt.

Thành công thì mở Explorer tại `output_dir`, đúng quy tắc "thư mục chứa file
luôn tự mở sau mọi download/export thành công".

### `choose_report_export_dir()`

Hộp thoại chọn thư mục, nhớ vào `prefs.report_export_dir`.

### Nhớ lựa chọn

`Division` / `Buyer` / `Season` dùng lại `report-parameters.json` sẵn có (key
theo `user_id` + `report_id`) qua `save_report_parameters` /
`_saved_report_parameters`. Không thêm file lưu trữ mới. Danh sách style đã tick
không được nhớ.

## Giao diện

Panel rộng 440px nên bố cục là một cột dọc.

`reports-list` thêm nút thứ hai `Color Combination - Production`. Bấm vào mở
section mới `.color-report-workspace`. Section `.report-parameters` hiện tại
vẫn dành riêng cho Shipment Summary, không đụng tới.

```
 OC Division          [ PRO SPORTS - WOVEN HANOI ▾ ]
 Buyer                [ J.LINDEBERG              ▾ ]
 Season               [ WH25                     ▾ ]
 ─────────────────────────────────────────────────
 [✓] Tải hàng loạt
 Style                                      48/48
 [ Chọn tất cả ] [ Bỏ chọn ]   [ lọc style…     ]
 ┌───────────────────────────────────────────────┐
 │ [✓] GWSD15176                                 │
 │ [✓] GWSD15177                                 │
 └───────────────────────────────────────────────┘
 Thư mục lưu   D:\…\Color Combination   [ Chọn… ]
 [           Tải báo cáo                        ]
```

- **Ba select cascade.** Đổi một cấp thì các cấp dưới chuyển `disabled` kèm
  nhãn `Đang tải…` cho tới khi `load_color_report_options` trả về. Bắt buộc, vì
  mỗi postback mất vài giây và nếu không khóa thì user thao tác trên dữ liệu cũ.
- **Toggle `Tải hàng loạt`, mặc định bật.** Bật thì hiện danh sách tick, mặc
  định tick hết. Tắt thì khối tick thu về đúng một `<select>`
  `BuyerStyleReference`. Cả hai trạng thái dùng chung nút `Tải báo cáo`.
- **Ô lọc style.** Lọc client-side trên danh sách đã nạp, không gọi backend.
  `Chọn tất cả` chỉ tác động lên các dòng đang hiện sau khi lọc.
- **Bộ đếm `n/m`** cạnh nhãn Style, cập nhật theo số tick.

### Thẻ tiến độ

```
 Đang tải báo cáo                            7/48
 GWSD15182 · SWV0003935
 ▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░
```

Backend bắn progress qua callback `progress`; `PanelAPI._progress` đã mang
`method` nên `wfxHandleBackendProgress` thêm nhánh cho `run_color_report_batch`.
Message kết thúc bằng `n/m` đúng định dạng UI đang đọc.

Cờ `colorReportRunActive` bao quanh đúng lời gọi và bỏ qua mọi payload ngoài
lúc đó. Thiếu cờ này thì một payload đến trễ sẽ xóa thẻ kết quả và kéo bộ đếm
lùi lại, đúng như đã xảy ra với Sale ASN.

Trong lúc chạy, khối setup bị disable. Dừng bằng nút `Stop` ở footer đã có sẵn.

### Thẻ kết quả

```
 [ 45 thành công ]  [ 3 lỗi ]      D:\…\Color Combination
 GWSD15190   Report Viewer chưa tải xong sau 5 phút
 GWSD15201   Không tìm thấy StyleCode
 ▸ 45 style đã tải
 [ Chạy lại 3 style lỗi ]        [ Mở thư mục ]
```

Dòng lỗi hiện sẵn, dòng thành công gấp trong `<details>`. Thẻ tự scroll vào
viewport khi hiện, và bị xóa trong hàm reset để lần mở module sau không còn nút
`Mở thư mục` trỏ vào lượt chạy cũ.

`Chạy lại style lỗi` tick lại đúng các style đó rồi chạy tiếp.

## Mã lỗi và telemetry

| Mã | Reportable |
| --- | --- |
| `COLOR_REPORT_OPTIONS_NOT_READY` — postback cascade quá 45 giây | có |
| `COLOR_REPORT_SAVE_FAILED` — không copy được file sang thư mục đích | có |
| `COLOR_REPORT_STYLE_LIST_EMPTY` — mùa không có style nào | không |
| `COLOR_REPORT_NO_STYLE_SELECTED` — user chưa tick style nào | không |
| `COLOR_REPORT_OUTPUT_DIR_REQUIRED` — chưa chọn thư mục | không |
| `COLOR_REPORT_CANCELLED` — user bấm Stop, kèm file đã lưu | không |

Mã reportable phải có mục trong `telemetry.ERROR_CODE_INFO`; mã không
reportable phải nằm trong `NON_REPORTABLE_FAILURES`.

`COLOR_REPORT_STYLECODE_MISSING` chỉ tồn tại ở mức từng dòng trong `failed[]`,
không phải mã trả về của flow.

Lỗi từng style không gửi telemetry: chúng phần lớn là vấn đề dữ liệu của style
đó, và 50 style một lượt sẽ làm ngập webhook. Chỉ lỗi ở mức flow mới gửi.

Tên thư mục và tên style đi qua `redact_telemetry_text` như mọi mô tả lỗi khác.

## Test

`tests/test_color_combination.py` mới:

- chọn StyleCode: nhiều option lấy số đuôi lớn nhất; đúng một option thì dùng
  luôn dù không parse được số; nhiều option không có chữ số thì lấy option cuối
  và ghi cảnh báo;
- đặt tên file `GWSD15176 - SWV0003935.xlsx`, trùng tên thành ` (2)`, ký tự
  Windows cấm bị thay;
- một style lỗi thì các style sau vẫn chạy và lỗi đó nằm trong `failed[]`;
- Stop giữa lượt trả `COLOR_REPORT_CANCELLED` kèm danh sách file đã lưu;
- giá trị cascade đã lưu không còn trong option thì bị xóa từ cấp đó xuống;
- `OCNum` và `SearchStyle` không bị đụng vào; `SizeVisibility` chỉ set khi đang
  khác `Yes`.

Test có sẵn cần cập nhật: `test_panel_js.py` và `test_ui_assets.py` (đăng ký
`data-module-action` mới), `test_constants.py` và `test_panel_api.py` (mã lỗi,
`NON_REPORTABLE_FAILURES`), `test_prefs.py` (`report_export_dir`),
`test_manual.py`.

## Tài liệu

Bổ sung `wfx_panel/manual/06-danh-sach/reports.md` một mục cho báo cáo mới —
cùng module nên cùng file, không tạo file mới. Thêm keyword và `covers.errors`
vào `wfx_panel/manual/manifest.json`. Chạy
`python scripts/generate_user_features.py` để sinh lại `docs/USER_FEATURES.md`;
không sửa tay file đó.
