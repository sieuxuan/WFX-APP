# WFX Smart 1.0.18

WFX Smart là ứng dụng desktop Windows giúp mở và tự động hóa các màn thường
dùng của WorldFashionExchange (WFX). App chạy bằng pywebview và điều khiển một
Chromium browser hệ thống qua Playwright/CDP.

Xem danh sách đầy đủ dành cho người dùng tại
[`docs/USER_FEATURES.md`](./docs/USER_FEATURES.md).
Hướng dẫn file Costing nằm tại
[`docs/CATALOG_COSTING_FILES.md`](./docs/CATALOG_COSTING_FILES.md).
Benchmark RAM/tốc độ của bản này nằm tại
[`docs/PERFORMANCE_1.0.15.md`](./docs/PERFORMANCE_1.0.15.md).

## Chức năng nổi bật

- Mở panel bằng launcher nổi, taskbar, system tray hoặc hotkey `Ctrl+Shift+X`;
  chuột phải launcher để chọn nơi thu gọn.
- Launcher và menu tự scale theo DPI của từng màn hình, gồm màn 2K ở 125%.
- Alert nghiệp vụ của WFX vẫn hiện trên Chrome và chờ người dùng xác nhận.
- Bản EXE mặc định khởi động cùng Windows; người dùng có thể tắt trong Settings
  và lựa chọn này được giữ nguyên.
- Chuyển màn và phản hồi tiến trình có animation ngắn, mượt, đồng thời tự giảm
  chuyển động theo thiết lập accessibility của Windows.
- Ghim module yêu thích lên đầu, trước ô tìm kiếm; module đã ghim không bị lặp
  lại ở danh sách bên dưới.
- Nhớ màn hình đang làm; có setting `Trở về List sau khi thao tác`.
- Đổi Division WOVEN/KNIT/PSSG và chỉ xác nhận khi WFX đổi thành công.
- Catalog có workspace Costing để nhận đúng Style Code/Style Name/status từ tab
  đang mở, scan Color/Size và phối Table theo từng item trong XLSX,
  tải `.xlsx` với tên Style Name vào thư mục gần nhất, tùy chọn mở file,
  thêm CM/Production/Indirect Costs bằng danh sách quét từ WFX, rồi cập
  nhật và Save CostSheet `Open` tự động; hỗ trợ Splitter cho Article nhiều dòng,
  dropdown phối Color/Size Dependency và kiểm tra Purchase Officer bắt buộc.
  Ba danh sách chi phí dùng cache 7 ngày theo tài khoản/Division; công tắc gọn
  cùng hàng với `Clear All Dependency` ép quét lại đúng một lần rồi tự tắt. Nút này
  có xác nhận sẽ xóa phối ở mọi section của Costing đang mở và Save.
- Tạo Style dùng picker Group có tìm kiếm. Form Excel nhận dropdown dùng chung,
  Sub-Category phụ thuộc Product Group; snapshot dùng chung đọc từ GitHub Raw
  và cache chỉ quét lại WFX sau 30 ngày.
  `Tự động Save` có thể bật theo nhu cầu nhưng luôn mặc định tắt.
- Catalog tách màn tìm Article và màn Costing; mở Costing hoặc Import file tự
  chuyển sang workspace Costing. Thư viện CSV bốn cột từ server tự đồng bộ mỗi
  giờ: Category lọc gợi ý Article Code, Apparel tìm Buyer Reference, category
  khác tìm Article Name. Costing chỉ đưa mã F vào Fabric, mã T vào Trim và tự
  điền Article Name trong Excel; chọn Article Name cũng được đồng bộ ngược sang
  Article Code lúc đọc/import nếu tên là duy nhất, còn tên trùng mã sẽ được báo
  để chọn Code. User không phải scan hay chọn file. Khi Apply,
  Material Color/Size
  còn thiếu được bổ sung vào đúng Article card rồi Save trước khi điền Costing.
  Chọn một gợi ý Buyer Reference/Article Name sẽ chuyển sang exact Article Code,
  nên không phải chọn lại trong danh sách kết quả gần giống.
- OC List có form Upload OC một hàng header: app kiểm tra dữ liệu, tự sinh
  `Sheet1` 51 cột không công thức, hiện review Buyer/Season/PO/Article/Units
  trước khi xác nhận upload `StandardSalesOrder`, kiểm tra đủ ba trạng thái EDI
  rồi mới Create Transaction; hỗ trợ cả OC New và Revise OC. Chọn lại cùng file
  sau khi sửa luôn tạo snapshot mới, không dùng dữ liệu review cũ. Trạng thái
  EDI `InProgress` hoặc Fail được coi là lỗi ngay; app mở `Failed Record`, hiện
  Mapping/Doc No. cụ thể và lưu ảnh chẩn đoán trước khi dừng transaction.
  Form có thêm `SMS` và dropdown Payment Terms; tự bỏ dòng Units bằng 0, mặc
  định Zone trống thành FOB/Extra Production trống thành 0 và chặn sai thứ tự ngày.
- Workflow riêng cho Catalog, OC List, Sample List, Sale ASN, RMPO,
  Indent/User Indent, QA/Advance PR/Expense Invoice, Supplier List, Buyer List
  và Company Setup. Nút New của QA, Advance Payment Request và Expense Invoice
  mở thẳng màn tạo mới, không yêu cầu vào List trước.
- Sample List có `Check File`: app tìm theo filter hiện tại, tự mở Style Code
  khi chỉ có một kết quả; nếu có nhiều kết quả thì cho chọn đúng Sample, sau đó
  liệt kê file đính kèm và cho tải trực tiếp như Catalog.
- Sale ASN có `Tải Packing List + Buyer Invoice`: dùng Invoice No. đang
  nhập hoặc dòng đang chọn, tự mở Docs, chờ từng Report Viewer,
  export Excel cả hai báo cáo, ghép thành workbook hai sheet mà không
  dựng lại format Packing List, rồi mở Save As với tên Invoice No.
- Sau mọi lần tải/export file thành công, app tự mở đúng thư mục
  chứa file vừa lưu.
- Panel có fallback Win32 để tự thu ổn định khi click ra ngoài; backend hoàn tất
  cũng tự giải phóng trạng thái bận nếu Promise WebView phản hồi chậm. Panel
  không tự thu sau flow khi chuột vẫn nằm trên UI.
- Phiên WFX được duy trì nền mỗi 4 phút sau lần login đầu tiên; nếu timeout,
  app tự đăng nhập lại và retry thao tác đúng một lần. Keepalive chỉ đọc nền,
  không kéo Chrome khỏi tab Costing. Popup Article được xác nhận bằng exact
  Article Code và đồng bộ CDP sớm để mở Costing mà không chờ cứng hoặc quay
  lại tìm Article lần hai.
- Mọi flow `List` xác nhận WFX đã đổi màn hình trước khi báo thành công; `Đổi
  FOC` tự mở lại đúng Company Setup khi context hiện tại đã cũ.
- Search ưu tiên đúng List đã mở; nếu chưa mở, app tự vào đúng List, chờ
  grid/Floating Filter rồi mới tìm.
- Flow module bắt đầu automation ngay trong lúc app đưa Chrome lên foreground;
  nhận diện Floating Filter phản hồi nhanh hơn nhưng vẫn xác nhận đúng grid.
- Playwright/CDP chạy trên một worker tuần tự và được dùng lại giữa các bước
  trong cùng flow. Driver được nhả ngay khi flow kết thúc để Chrome không bị
  pause tab; phiên đăng nhập WFX và DOM đang mở vẫn được giữ cho flow sau.
- Nút `Stop` nằm ngay dòng trạng thái dưới cùng, dừng ở checkpoint an toàn và
  không cắt ngang bước Save của WFX.
- Chrome/WebView2 được giới hạn số renderer và tắt dịch vụ nền không cần thiết,
  tối ưu cho máy Windows RAM 8 GB.
- Lịch sử tác vụ, Run ID, ảnh lỗi cục bộ, retry có kiểm soát và Log kỹ thuật có
  thể bôi đen/copy.
- Webhook lỗi có mô tả tiếng Việt, hướng xử lý và context tài khoản; không gửi
  password, cookie, URL WFX hoặc nội dung tìm kiếm. Nếu nhánh automation cũ
  không trả message, app vẫn suy ra module/trường tìm/Division từ metadata an
  toàn thay vì gửi mô tả trống.
- Endpoint webhook được chốt trước khi tạo background thread; môi trường test
  đã tắt reporting không thể gửi trễ payload giả sang production.
- Tự kiểm tra và cài GitHub Release có xác minh checksum/chữ ký, rollback và
  cơ chế đóng đúng PID/path khi WebView2 giữ process quá lâu.

## Hướng dẫn sử dụng trong ứng dụng

Bấm biểu tượng quyển sách ở thanh trên để mở WFX Manual trong một cửa sổ riêng.
Manual chứa đủ hướng dẫn theo module, tìm kiếm và bảng tra mã lỗi; toàn bộ nội
dung được đóng gói cùng ứng dụng nên dùng được khi không có mạng, không cần mở
Chrome hoặc đăng nhập WFX. Nút dấu hỏi trong từng module mở thẳng mục liên quan.

Cách bổ sung nội dung khi có tính năng mới nằm tại
[`docs/MANUAL_AUTHORING.md`](./docs/MANUAL_AUTHORING.md).

## Cách sử dụng nhanh

1. Mở WFX Smart và lưu User ID/password trong Settings. Khi đã kết nối, tab Tài
   khoản chỉ hiện trạng thái và nút `Đổi tài khoản`.
2. Bấm `Mở trình duyệt` để app mở browser automation và đăng nhập WFX.
3. Chọn Division nếu cần.
4. Chọn module. Có thể Search hoặc Đổi FOC ngay; app tự mở List khi cần. Nút
   New của QA, Advance PR và Expense Invoice mở thẳng màn tạo mới; các module
   New khác vẫn cần đúng màn List khi workflow yêu cầu.
5. Dùng ngôi sao để ghim module thường dùng.

Mật khẩu được DPAPI mã hóa thành `WFX_PASSWORD_ENC`. Bản Windows từ chối lưu
mật khẩu nếu DPAPI không hoạt động. Settings của bản đóng gói nằm tại
`%LOCALAPPDATA%\WFX-Panel`, tách khỏi thư mục cài đặt.

## Chạy bản development

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m wfx_panel.panel_app
```

Browser không được bundle trong ứng dụng. WFX Smart hỗ trợ Chrome Stable/Beta/
Dev/Canary, Edge, Brave hoặc Chromium. Có thể đặt `WFX_CHROME_PATH` nếu browser
nằm ở đường dẫn riêng.

## Kiến trúc chính

- `wfx_panel/automation/`: Playwright/CDP và các workflow WFX.
- `wfx_panel/panel_api.py`: bridge giữa UI và automation.
- `wfx_panel/catalog_controller.py`: state/context của Catalog.
- `wfx_panel/oc_workbook.py`: form một-header, validate và sinh `Sheet1` EDI.
- `wfx_panel/automation/oc.py`: mở report Revise và workflow EDI Buyer PO.
- `wfx_panel/panel_app.py`: pywebview, launcher, tray và hotkey.
- `wfx_panel/ui/`: HTML/CSS/JavaScript của panel.
- `wfx_panel/telemetry.py`: webhook, outbox và redaction dữ liệu nhạy cảm.
- `n8n/`: workflow webhook có thể import; xem `WFX_SYNC_SETUP.md` để cài API
  đồng bộ Article/Style qua PostgreSQL.
- App User tự lấy snapshot Article/Style từ n8n tối đa một lần mỗi 30 ngày và
  có nút `Đồng bộ ngay` trong Cài đặt > Tài khoản. Admin key được lưu bằng
  Windows DPAPI và chỉ dùng khi xác nhận publish cache hiện tại.
- `CLAUDE.md`: đặc tả kỹ thuật chuẩn bắt buộc.

## Đóng gói EXE

```powershell
powershell -ExecutionPolicy Bypass -File build-panel.ps1
```

Kết quả:

```text
dist/WFX-Panel/WFX-Panel.exe
```

Đây là bản `onedir`; cần giữ cả `WFX-Panel.exe` và thư mục `_internal`.

## Kiểm thử

```powershell
python -m pytest
ruff check .
node --check wfx_panel/ui/panel.js
```

Visual-regression chạy trên pywebview/WebView2 thật với light/dark và DPI
100/125/150/200%, chụp năm trạng thái
Home/tooltip/Catalog/Sale ASN/Settings:

```powershell
python scripts/visual_regression_panel.py --suite baseline
python scripts/visual_regression_panel.py --suite current
python scripts/visual_regression_panel.py --compare
```

Ảnh và `report.json` nằm trong `build/visual-regression/` (không đưa vào Git).

Test tích hợp WFX thật sử dụng tài khoản trong `.env`:

```powershell
$env:WFX_LIVE_TEST = "1"
python -m pytest tests/test_wfx_live.py tests/test_wfx_live_module_contexts.py -v
```

Test không được in credential hoặc nội dung tìm kiếm ra output.

## Release và cập nhật

Mỗi release Windows có hai lựa chọn, đều kèm checksum `.sha256` và chữ ký
detached `.sha256.p7s`:

- `WFX-Smart-Setup-v1.0.18.exe` — bản khuyên dùng. Cài theo user, không cần
  quyền Administrator, tự tạo shortcut Desktop và Start Menu, có Uninstall và
  nâng cấp tại chỗ.
- `WFX-Smart-v1.0.18-win64.zip` — bản portable. Giải nén nguyên thư mục rồi mở
  `WFX-Panel.exe`; không được tách EXE khỏi `_internal`.

Khi cập nhật, bản cài bằng Setup tiếp tục nâng cấp qua bộ cài để giữ đúng
shortcut, registry và Uninstall. Bản portable tiếp tục cập nhật trực tiếp bằng
gói ZIP trong thư mục đang chạy.

Build bộ cài tại máy Windows (cần Inno Setup 6 hoặc 7):

```powershell
.\build-installer.ps1
```

Nếu đã có `dist/WFX-Panel`, dùng `-SkipAppBuild` để chỉ đóng gói installer.
Bộ cài được tạo trong `dist/installer/`.

GitHub Actions cần hai secrets:

- `WFX_SIGNING_CERTIFICATE_BASE64`
- `WFX_SIGNING_CERTIFICATE_PASSWORD`

Updater xác minh chữ ký certificate đã ghim và SHA-256. Bản portable chỉ thay
`WFX-Panel.exe` cùng `_internal` và rollback hai thành phần này nếu lỗi; bản
Setup chạy installer nâng cấp tại chỗ. Cả hai giữ nguyên tài khoản/settings tại
`%LocalAppData%\WFX-Panel` khi cài mới, nâng cấp hoặc uninstall.

Windows 11 thường có sẵn WebView2. Windows 10 cần Microsoft Edge WebView2
Runtime nếu UI không mở.
