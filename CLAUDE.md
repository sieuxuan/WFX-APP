# WFX Catalog automation — đặc tả hành vi chuẩn

## Sản phẩm thật

Dự án này là **desktop app pywebview** (`wfx_panel/`) tự động hoá
WorldFashionExchange qua Playwright/CDP, đóng gói bằng PyInstaller
(`build-panel.ps1` → `dist/WFX-Panel/`), đóng thành bộ cài Inno Setup
(`build-installer.ps1` → `dist/installer/`) và tự cập nhật từ GitHub Release. Đây
KHÔNG phải Chrome extension; thư mục `chrome-extension/` không được dùng.
`wfx-tampermonkey.user.js` chỉ là biến thể userscript tuỳ chọn, không phải sản
phẩm chính. Khi sửa code, luôn sửa trong `wfx_panel/` (nguồn), không sửa mỗi file
trong `dist/`.

Bản đồ nhanh:

- `wfx_panel/automation/` — lớp Playwright (login/session/catalog/directory/
  modules/browser). `login.py` chỉ còn shim re-export để tương thích ngược.
- `wfx_panel/automation/runtime.py` — worker tuần tự duy nhất sở hữu Playwright
  sync + CDP connection bền vững và cờ cancel theo checkpoint.
- `wfx_panel/panel_api.py` — bridge `PanelAPI` giữa UI và automation.
- `wfx_panel/catalog_controller.py` — toàn bộ luồng Catalog (browse/prepare/find/
  Costing/BOM + cây folder), tách khỏi `PanelAPI`.
- `wfx_panel/oc_workbook.py` — tạo form OC một-header, validate workbook New/
  Revise và sinh `Sheet1` EDI 51 cột chỉ chứa giá trị.
- `wfx_panel/automation/oc.py` — mở report Revise OC và điều khiển EDI Buyer PO
  tới bước Create Transaction.
- `wfx_panel/panel_app.py` — pywebview + tray + hotkey toàn cục + lớp win32.
- `wfx_panel/prefs.py` + `wfx_panel/secret.py` — settings và mật khẩu (DPAPI).

## Trạng thái sản phẩm hiện tại

WFX Smart là panel automation desktop cho người dùng WFX. Danh sách chức năng
dành cho người dùng nằm tại [`docs/USER_FEATURES.md`](./docs/USER_FEATURES.md);
`README.md` là hướng dẫn cài/chạy/build ngắn gọn. Khi thay đổi hành vi sản phẩm,
phải cập nhật cả ba tài liệu nếu nội dung liên quan.

### Hành vi giao diện

- Launcher 48×48 logical mở panel; native bounds phải scale theo DPI của HWND
  (48/60/72/96 physical tại 100/125/150/200%), kể cả khi cửa sổ đang hidden.
  Hotkey mặc định là `Ctrl+Shift+X`.
- Bản EXE mặc định bật `Khởi động cùng Windows` cho cài đặt mới và đồng bộ
  Windows Run key sau khi giữ được single-instance lock. Nếu người dùng đã tắt
  thì phải giữ nguyên lựa chọn đó. Chạy source development không được tự đăng
  ký Python/Pythonw vào startup.
- Panel tự thu khi mất focus. Ngoài `window.blur`, monitor foreground Win32 là
  fallback bắt buộc vì WebView2 đôi khi bỏ lỡ blur. Nếu automation đang chạy,
  panel ghi nhận yêu cầu và chỉ thu khi tác vụ kết thúc **và** con trỏ không còn
  nằm trong UI. Trạng thái pointer của WebView phải được đồng bộ sang native;
  không được thu panel chỉ vì automation vừa đưa Chrome lên foreground.
- Chuyển giữa List/module và thanh tiến trình dùng animation ngắn chỉ với
  transform/opacity; phải tôn trọng `prefers-reduced-motion`. Nút vừa kích hoạt
  giữ highlight trong khi tác vụ chạy để người dùng biết flow nào đang xử lý.
- Bootstrap bình thường do `PanelApp._startup()` inject một lần; JavaScript chỉ
  gọi `get_initial_state` sau 600 ms làm fallback nếu chưa nhận state, tránh đọc
  prefs và render module trùng lúc mở app.
- Mặc định app nhớ đúng màn module người dùng đang làm. Setting `Trở về List
  sau khi thao tác` cho phép đổi sang hành vi quay về danh sách module.
- Module được ghim bằng nút ngôi sao sẽ nằm trong `Yêu thích` trước ô tìm kiếm.
  Khu vực này không có scrollbar riêng; module đã ghim không lặp lại trong nhóm
  bên dưới và favorite cuối cùng ở hàng lẻ chiếm trọn chiều ngang.
- Tab Tài khoản ở trạng thái đã đăng nhập chỉ hiện kết nối hiện tại và nút `Đổi
  tài khoản`; form User ID/password chỉ mở khi người dùng muốn đổi hoặc cần xác
  thực lại.
- Sau khi đã có một phiên đăng nhập thành công, app kiểm tra/duy trì phiên nền
  mỗi 4 phút khi Chrome rảnh. Nếu một flow phát hiện `NOT_LOGGED_IN`, app dùng
  credential đã lưu để login lại và retry toàn bộ flow đúng một lần; không retry
  từng bước ghi dữ liệu và không lặp vô hạn. Các probe chỉ đọc session/Division/
  quyền và ảnh chẩn đoán phải dùng `bring_to_front=False`, không được kéo user
  khỏi tab Costing.
- Form góp ý chỉ cho gửi từ 5 ký tự và hiển thị bộ đếm trên giới hạn 2.000 ký tự.
- Bộ chọn Division là segmented control gọn để dành thêm chiều cao cho module.
- Chỉ thanh footer dưới cùng hiển thị trạng thái tác vụ; không lặp status bên
  trong màn module.
- Result sink từ backend phải nhả trạng thái busy của UI độc lập với Promise
  pywebview. Nếu Promise bridge bị kẹt sau khi backend đã ghi kết quả, các nút
  workflow vẫn phải hoạt động lại ngay.
- Updater chờ instance hiện tại tự đóng 15 giây. Nếu pywebview/WebView2 còn giữ
  process cha, helper chỉ được force-stop đúng PID sau khi xác minh đường dẫn
  process trùng exact `WFX-Panel.exe` đang cập nhật; tuyệt đối không kill theo
  tên process. Chỉ tải/thay file sau khi PID đã biến mất.
- Release phải phát hành song song `WFX-Smart-Setup-v<version>.exe` và ZIP
  portable. Installer dùng AppId cố định, cài per-user vào
  `%LocalAppData%\Programs\WFX Smart`, không yêu cầu Admin, mặc định tạo shortcut
  Desktop/Start Menu và dùng Restart Manager để đóng app khi nâng cấp. Không
  được xóa dữ liệu `%LocalAppData%\WFX-Panel` khi cài, upgrade hoặc uninstall.
- Catalog tách `Tìm Style` và `Costing` thành hai workspace trong cùng module.
  Khi mở Costing hoặc upload/import XLSX, panel tự chuyển hẳn sang workspace
  Costing; không bắt người dùng cuộn xuống dưới form tìm kiếm. Hai workspace
  không có hero/block hướng dẫn lặp lại. Nút mở List luôn ghi `Mở Catalog`;
  vị trí Apparel mặc định được chỉnh bằng nút icon nhỏ nằm cạnh nút này.
- Sau khi tìm Article để mở Costing/BOM, popup phải được xác nhận bằng exact
  Article Code trong `#lblArticleNameValue`; không chờ cứng khi header đã đúng.
  Probe popup hiện tại tối đa 3–4 giây, sau đó recycle CDP không activate tab
  Catalog và recovery cuối tối đa 18 giây.
- Khi automation đang chạy, footer hiện nút `Stop`. Nút chỉ đặt cờ hủy; flow
  dừng ở checkpoint kế tiếp và trả `ACTION_CANCELLED`. Không đóng browser hoặc
  Playwright để ép dừng. Đoạn click/chờ Save phải dùng `cancellation_deferred()`
  để không trả trạng thái hủy khi WFX còn đang ghi dữ liệu.
- `Log kỹ thuật` cho phép bôi đen/copy. Log mới chỉ tự cuộn khi người dùng đang
  ở gần cuối và không chọn văn bản.

### Quy tắc flow List → thao tác

Mỗi nút trong module là một flow riêng:

1. `List` mở đúng màn danh sách và, nếu cần, bật Floating Filter.
2. `New` mặc định dùng màn List hiện tại. Riêng QA Request, Advance Payment
   Request và Expense Invoice phải click trực tiếp menu `New` tương ứng, không
   yêu cầu mở List trước. `Đổi FOC` tự mở Company Setup nếu context hiện tại đã
   đổi sang module khác, rồi mới mở Miscellaneous Settings.
3. `Search` ưu tiên đúng List hiện tại. Nếu List chưa mở hoặc context chưa sẵn
   sàng, automation phải tự click đúng menu List, chờ grid/Floating Filter ổn
   định rồi mới điền điều kiện; người dùng không cần bấm List trước.
4. Trước khi điền, automation phải xác nhận context riêng của module trong cùng
   frame. Không được dùng chỉ `#txtArticle` hoặc `#txtCompanyName`, vì OC/Sample/
   Sale ASN và Buyer/Supplier có selector trùng nhau.
5. Search và Đổi FOC không được trả `*_LIST_NOT_OPEN` hay hướng dẫn bấm List.
   Nếu đã tự mở
   nhưng List/search vẫn không sẵn sàng, trả lỗi kỹ thuật cụ thể kèm trạng thái
   tự mở thất bại. `*_LIST_NOT_OPEN` chỉ còn dùng cho các thao tác làm thay đổi
   dữ liệu như New khi người dùng chưa mở đúng List.
6. Khi chạy flow module, bridge backend phải được gọi trước; thao tác đưa Chrome
   lên foreground chạy song song và không nằm trên critical path. Poll trạng
   thái grid ở 150 ms, nhưng chỉ chấp nhận Floating Filter sau khi visible/enabled
   ổn định ít nhất 0,5 giây và đúng context để vừa nhanh vừa tránh grid cũ.
7. Mọi flow từ `PanelAPI._run()` chạy trên automation worker duy nhất. Các lời
   gọi `sync_playwright().start()/stop()` trong workflow chỉ là lease; TRONG một
   flow runtime cache một Playwright process và một CDP Browser để các sub-op
   dùng chung. Nhưng NGAY khi flow kết thúc, runtime nhả driver/CDP (không giữ
   attach giữa các flow); Chrome ngoài và phiên đăng nhập vẫn được giữ, flow sau
   tự kết nối lại. Lý do KHÔNG giữ persistent connection giữa các flow: khi CDP
   còn attach, tab người dùng tự mở trong Chrome bị auto-attach
   `waitForDebuggerOnStart` pause ("Debugger paused in another tab") và có thể
   treo Chrome khi đóng tab đó. Việc "dùng lại grid Master đang mở" vẫn chạy vì
   nó tái dùng DOM đang mở trong Chrome, không phụ thuộc Playwright có giữ kết
   nối. Không dùng object Playwright sync từ thread khác.
8. Các wait dài dùng `_wait()`/`_sleep()` theo lát tối đa 100 ms để đọc cancel;
   không thêm cơ chế terminate/close page từ thread UI.

### Giới hạn bộ nhớ

- Chrome automation chạy `--process-per-site`, tối đa 4 renderer và tắt các
  dịch vụ nền không cần cho WFX; không giới hạn V8 heap cứng vì grid lớn có thể
  cần bộ nhớ đột biến.
- WebView2 của panel/bubble/menu/notification dùng tối đa 3 renderer qua
  `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`. Dùng `setdefault` để cấu hình quản trị
  viên vẫn có quyền override.
- Bubble phải có fallback Win32 bắt chuột phải, không chỉ dựa vào sự kiện
  `contextmenu` của WebView. Menu chuột phải là tool-window pywebview riêng;
  không dùng `TrackPopupMenu` đồng bộ từ worker/WebView thread vì Windows có thể
  dismiss ngay. Poll loop phải bỏ qua click mở menu, sau đó tự đóng menu khi
  người dùng click ra ngoài. Mọi spinner UI dùng chung chu kỳ 1,25 giây/vòng.
- Tối đa một Playwright driver/CDP connection tồn tại tại một thời điểm và chỉ
  trong lúc một flow đang chạy; runtime nhả driver/CDP ngay khi flow xong (không
  giữ giữa các flow) và phải shutdown khi người dùng thoát. Tại ranh giới
  popup Article (Costing, BOM hoặc File), KHÔNG dựng lại driver/CDP vô điều
  kiện: mỗi `connect_over_cdp` mới re-attach mọi tab và làm Chrome nhấp banner
  "đang bị điều khiển", gây lag. Thay vào đó phải probe popup trên CDP hiện tại
  trước (`_open_article_destination`/`_article_page`); chỉ khi probe ngắn timeout
  mới `recycle_playwright` đúng một lần rồi thử lại, và không đóng Chrome. Khi
  driver cũ không thấy popup trong `context.pages`, vẫn phải recycle: không được
  dùng chính danh sách target stale đó để bỏ qua recovery.
  Quy tắc này cũng áp dụng ngay trong flow kết hợp Tìm → Costing/BOM: nếu người
  dùng vừa chọn một dòng sau `MULTIPLE_RESULTS` và WFX tái sử dụng popup Style,
  phải recover popup rồi mở destination, không quay lại Catalog để search lần hai.

Các workflow riêng hiện có:

- Catalog: Category/folder, Master, Article Code; Apparel dùng Buyer Reference,
  category khác dùng Article Name; Costing, BOM,
  file đính kèm và Costing file import/export XLSX.
- Costing file chỉ áp dụng cho Apparel và luôn chạy hai phase:
  1. scan live + validate file + dry-run, cache plan bằng opaque token tối đa
     15 phút, chưa ghi WFX;
  2. re-scan/chống stale, apply plan server-side, Save trong
     `cancellation_deferred()` và đọc lại field đã đổi để xác nhận.
- File Costing không được cung cấp selector cho automation. Blank giữ nguyên,
  `__CLEAR__` mới là xóa giá trị, Action trống là UPSERT; chỉ `DELETE` rõ ràng
  mới được chọn đúng row rồi dùng `#imgDelete`.
- Export được phép ở mọi Costing status. Import và Apply chỉ được bật khi
  Costing hiện tại có status chính xác là `Open`; nếu status khác `Open` hoặc
  chưa có Costing, app dừng với `COSTING_NOT_OPEN` và người dùng phải tự
  tạo/mở Costing trong WFX trước.
- Add Article chỉ dùng `#imgAdd` và Material Search: ưu tiên exact Article Code,
  fallback Article Name; 0 kết quả thì skip/báo, nhiều kết quả thì chờ user
  resolve, không tự chọn dòng đầu. Dùng Continue cho item chưa phải cuối và
  Finish cho item cuối.
- Mọi editable field Minutes phải được đặt thành `1`. Save Cost Sheet chỉ dùng
  `//*[@id="titlebarCostSheet"]/tbody/tr/td[3]/span/div[1]`.
- Field Supplier và các editor WFX dùng Select2 có backing
  `select2-hidden-accessible` 1×1: không dùng Playwright `select_option()` vì
  actionability có thể timeout; gán exact option value trên backing select và
  phát native `change` để chạy nguyên onchange/xOnBlur của WFX.
- Một Article có thể chiếm nhiều dòng DOM; dòng tiếp nối hiển thị `>>`.
  Chỉ kế thừa Article khi chính `#lblArticle` của dòng `>>` đang visible; nhãn
  `>>` ẩn trên subtotal/total không phải dòng split.
  Inventory phải kế thừa Article của dòng trước nhưng tạo `item_key` riêng cho
  từng dòng. Planner ưu tiên exact `item_key`; với workbook cũ từng gộp các
  dòng, phải ánh xạ từng field về dòng live thực sự chứa field đó.
- Khi file có cùng Article trên các dòng liền nhau nhiều hơn số dòng live,
  Apply phải click đúng `#imgSplitterForUsage` của dòng Article để tạo đủ dòng
  `>>` trước khi điền field; không Add lại cùng Article cho từng dòng.
- Export phải scan Material Color/Size theo từng Article và nội dung popup
  Dependency Table. Workbook có `Color Mapping`/`Size Mapping`, mỗi dòng theo
  cú pháp `Material => Style 1 | Style 2`; Apply tự đặt `[Table]`, mở đúng
  `#lnkColorDependency`/`#lnkSizeDependency` và tick exact theo từng dòng nguồn.
  Material Color/Size có dropdown từ giá trị item đã scan; option Style nằm
  trong comment ô Mapping.
- Khi Apply gặp Material Color/Size chưa có trong option của đúng Article,
  automation phải mở editor dòng Costing rồi dùng đúng
  `#imgMaterialColorAdd`/`#imgMaterialSizeAdd`. Trong Article Color/Size List,
  giữ card hiện tại, điền Search ở vùng `form/table[3].../tr[2]`, click
  `#btnShow`, chọn exact rồi `#btnAdd`. Nếu card chưa có giá trị thì dùng link
  Search and Add tại `form/table[3].../tr[4]/td[1]/a`; riêng Size được fallback
  sang card `Sample` rồi tìm lại. Sau Add phải click Save tại
  `form/table[1].../td[2]/a`, xác nhận option đã xuất hiện lại trong editor
  Costing, và không xóa/đổi Color Card, Size Card hay mapping đang có.
- Style Name lấy từ `#lblArticleNameValue`, chính xác phần sau dấu `/` trong
  ngoặc. Form có thêm hai cột đỏ chỉ đọc `Cons. Qty. Incl. Waste` và
  `Value in (USD)`; export giá trị live nhưng import không được tạo field đổi
  cho hai cột công thức này.
- `Purchase Officer` bắt buộc không được chờ tới Save mới phát hiện. Workbook
  cung cấp dropdown từ giá trị live; dry-run dừng với
  `COSTING_REQUIRED_FIELD_MISSING` nếu cả file và dòng live vẫn trống.
- Export/Import/Apply phải tái sử dụng đúng Costing đang mở cho cùng style,
  không mở lại destination, không đưa Chrome lên foreground và không reload
  frame sau Save. Workbook có đúng hai sheet: `Hướng dẫn` và `Costing`.
  Khi có nhiều tab/popup Costing, phải ưu tiên target đang hoạt động gần nhất,
  không dùng thứ tự tạo trong `context.pages`. Trước hộp thoại export phải quét
  nhanh Style Code/Style Name/status, hiển thị ngay trong thẻ Costing và dùng
  Style Name đặt tên file. Hộp thoại nhớ thư mục export gần nhất; Settings có
  hai lựa chọn độc lập mở file hoặc mở thư mục sau export. Nút `Kiểm tra file` chỉ
  validate XLSX và trả lỗi sheet/ô, không scan WFX hoặc tạo dry-run.
  `Costing` luôn có bộ cột form chuẩn để nhập trực tiếp, chỉ round-trip field
  item `editable=true`. Cuối form có đúng 1 dòng CM Costs, 1 dòng Production
  Costs và 2 dòng Indirect Costs; scan option Article từ editor đúng block,
  Curr. CM/Indirect là USD, dòng trống không Add. Production đặt Minutes=1 ở
  parent và child, rồi Value parent trước Rate child. Không có sheet `Cost Sheet`,
  `Sections`, `_Fields`, `_Meta`; hộp thoại chỉ hỗ trợ `.xlsx`.
- Article Library là danh sách toàn cục bốn cột `Article Code`/`Article Name`/
  `Buyer Reference`/`Article Category`, mặc định phát hành từ
  `Article List.csv` kèm manifest version + SHA-256.
  App tự kiểm tra lúc mở và mỗi giờ, chỉ tải khi version đổi, ghi cache atomic
  tại data dir và tiếp tục dùng bản gần nhất khi offline. User không scan WFX,
  chọn file hoặc cập nhật thủ công. Workflow server tự tạo lại manifest khi CSV
  trên nhánh main đổi. Catalog chỉ gợi ý trong Category đang chọn: Article Code
  theo code, Apparel theo Buyer Reference, category còn lại theo Article Name.
  Costing lọc `Textiles/Fabric` + prefix F cho section Fabric và `Trims` +
  prefix T cho section Trim. Excel tạo dropdown theo cặp Code/Name và công thức
  lookup an toàn để Article Name đổi theo Article Code; khi chưa có cache vẫn
  cho nhập tay. Mọi gợi ý bắt đầu sau 2 ký tự, tối đa 20 kết quả.
- Khi user chọn một gợi ý từ Buyer Reference hoặc Article Name, UI phải lấy
  exact `Article Code` của chính dòng đó, chuyển filter sang Code và tìm bằng
  code; không lọc lại Buyer Reference/Name khiến user phải chọn Article lần hai.
  Nếu floating filter Code dạng contains vẫn render nhiều code gần giống, exact
  code duy nhất phải được mở trực tiếp.
- Costing tuyệt đối không click `#colBodyType label span`, `#imgDeleteSection`,
  `#imgEditSection` hoặc `#imgCopySection`.
- OC List: tìm theo OC No. hoặc Style; tải form `OC INPUT` một hàng header;
  Upload OC New và Revise OC qua EDI Buyer PO.
- Workspace OC gom nút mở `OC List` và Search trong cùng card. Card `Upload OC
  New` đặt `Tải file mẫu` và `Chọn file mới` cạnh nhau; Revise giữ cặp mở report
  và chọn file đã sửa.
- Form OC mới chỉ để user nhập trên sheet visible `OC INPUT`; sheet
  `REFERENCES` phải `veryHidden`, chỉ chứa nguồn dropdown. App phải tự sinh
  workbook tạm chỉ có `Sheet1` với đúng 51 header EDI, không công thức, không
  macro và không phụ thuộc phiên bản Excel. Vẫn đọc được `UPLOAD FORM.xlsx` cũ
  gồm `FORM`/`THONG TIN` để chuyển tiếp, nhưng không phát hành form cũ cho user.
- Mỗi file OC New/Revise chỉ được chứa một Buyer. Trước khi mở WFX phải kiểm tra
  extension/ZIP an toàn, schema/header, số dòng tối đa, ô lỗi công thức, trường
  bắt buộc, ngày, Selling Price, Units, Extra Production, dòng trùng và tự tính
  lại `Total Qty` theo PO/delivery/style. Buyer/Factory trong form là danh sách
  gợi ý có thể nhập thêm để không chặn master data mới; Buyer vẫn phải khớp
  exact trên WFX và Factory được WFX kiểm tra ở Process Package. Country phải
  có mapping Market. Revise phải giữ đủ định danh OC gốc như `DeliveryOCID`.
- Sau validate local phải hiện review và chưa được mở EDI: Buyer, Season, số PO
  distinct theo `Summary Buyer Order Ref`, số Style distinct theo `Article`,
  `Sum of Units` và số dòng. Workbook tạm dùng token một lần; chỉ nút `Xác nhận
  Upload` mới chạy EDI, còn Huỷ phải xoá review và không chạm WFX.
- EDI OC phải chọn exact Buyer từ file và package value `1`/
  `StandardSalesOrder`, upload file chuẩn hoá, bấm `Process Package` rồi đọc
  cả `Data Imported`, `Data Validated`, `Mapping Resolved`. Chỉ khi tất cả đều
  Success mới chọn transaction đầu tiên và bấm `Create Transaction`; New đi
  tab `New`, Revise đi tab `Revision`.
- `ddlBuyer` và `ddlPackage` của WFX chỉ bind đủ option sau `mousedown`; automation
  phải dispatch sự kiện này, tìm option theo label/title exact và xác nhận lại
  control sau postback trước khi đi tiếp.
- `Create Transaction` là ranh giới không idempotent. Nếu đã click nhưng không
  đọc được xác nhận, trả `OC_TRANSACTION_UNCONFIRMED` và tuyệt đối không retry
  tự động. Lỗi validate file là lỗi người dùng, không gửi telemetry hệ thống.
- Nút mở Revise phải click Reporting & Analytic `0004_0110`, tìm đúng report
  `Upload OC from OC_Sale` node `258`. User tự chọn tham số và Export Excel
  trên report WFX; app không tự động hoá bước download này. App tiếp tục từ
  file người dùng đã sửa và chọn lại ở card Revise OC.
- Sample List: List + Floating Filter, tìm theo Sample Order No./Style/
  Created By, và New Sample Order.
- Sale ASN: List + Floating Filter, tìm theo Invoice No./Buyer Order Ref/OC
  No., và New.
- Supplier List: đổi Category, mở Master, tìm trong tất cả Category.
- Buyer List: tự mở đúng Buyer List khi cần rồi mở Edit đầu tiên.
- Company Setup: Đổi FOC tự mở đúng List nếu cần, mở Miscellaneous Settings rồi
  mới đổi/lưu nơi áp dụng FOC.
- Mọi flow `List` chỉ trả thành công sau khi WFX đổi page/frame/document thật;
  một cú click menu đơn thuần không được coi là `MODULE_OPENED`.
- RMPO List: tìm kết hợp theo Supplier và RMPO No. trên đúng grid
  `gridRMPO`.
- Indent List/User Indent: tìm kết hợp theo Supplier, Article, Indent No. và
  Style trên đúng grid `gridMOLList`.
- QA List, Advance PR List và Expense Inv List: List + New; New click trực tiếp
  menu QA Inspection Request New, Advance Payment Request New hoặc Expense
  Invoice New và phải xác nhận navigation, không phụ thuộc màn List hiện tại.
- Các module generic còn lại thuộc nhóm Finance/Admin theo quyền tài khoản.

### Webhook và quyền riêng tư

- Lỗi automation gửi `method_label`, `error_title`, `error_detail`,
  `suggestion`, mã kỹ thuật, Run ID và context tài khoản gồm User ID, Company,
  Division.
- Nếu `result.message`, `module` hoặc `filter_kind` bị trống, telemetry phải suy
  ra mô tả cụ thể từ `method` và metadata request đã whitelist (`module_id`,
  `filter_kind`, `division_key`); không dùng fallback chung chung kiểu
  `Automation không trả về mô tả chi tiết`.
- Background flush phải nhận endpoint đã resolve tại thời điểm lên lịch. Không
  được resolve lại `DEFAULT_WEBHOOK_URL` bên trong thread chạy trễ, vì có thể
  làm payload test bị gửi sang production sau khi monkeypatch/config được hoàn
  nguyên.
- Pytest phải có autouse fixture tắt `DEFAULT_WEBHOOK_URL` và xoá override
  environment. Test giao nhận chỉ được bật endpoint giả; không test nào được
  phép gọi webhook production.
- Không gửi password, cookie, SessionID, LoginID, URL WFX đầy đủ hoặc nội dung
  tìm kiếm. Mọi mô tả lỗi phải qua `redact_telemetry_text`.
- Lỗi nhập liệu/trình tự như thiếu query, chưa mở List, không có kết quả hoặc
  filter không hợp lệ phải nằm trong `NON_REPORTABLE_FAILURES`.
- Mỗi error code có khả năng gửi phải có mô tả và hướng xử lý trong
  `telemetry.ERROR_CODE_INFO`; test phải bảo đảm không còn code reportable bị
  thiếu mapping.
- Code node n8n chuẩn nằm ở `n8n/wfx-app-normalize-code.js`; workflow import
  hoàn chỉnh nằm ở `n8n/wfx-app-webhook.json`. Hai file phải cùng trả
  `notification_text`, không giữ `raw_payload`, và trường `message` của lỗi
  automation cũng phải là bản đã redaction.
- Buyer/Supplier chỉ được resolve lại frame cùng PartyType với flow ban đầu.
  Search tất cả Supplier Category phải tiếp tục khi một Category lỗi, báo rõ
  kết quả một phần và đếm tổng trước khi giới hạn danh sách hiển thị.
- Crash log phải sanitize exception/stack trước khi ghi xuống ổ đĩa.

## Mục tiêu

File này là đặc tả hành vi bắt buộc cho lớp automation Catalog trong
`wfx_panel/automation/catalog.py`. Không được coi việc “đã click”, “đã tìm thấy
frame” hoặc “đã thấy input” là thành công nếu trạng thái thật trên UI chưa được
xác nhận.

## Kết luận từ log 1.7.1 lúc 23:01:30

1. `Catalog` và Category `Apparel` đã mở đúng.
2. Lần click `Master` đầu tiên làm frame `left` reload/chuyển trạng thái
   (`FromRefresh=1` thành `FromRefresh=`), nhưng chưa tạo Catalog Grid.
3. Script tiếp tục thử `img` và `li` là sai hướng. Tới lần 4, khi nó lấy lại document
   mới và click lại đúng `span` có `onclick`, `wfxcataloglist` mới được tạo.
4. Sau khi `.ag-root-wrapper` xuất hiện, log ghi:
   `rawRows=0`, `rawButtons=0`, `renderedButtons=0`.
5. Dù chưa có row và chưa có bằng chứng nút `#showfloatingfilter` đã được click,
   script vẫn báo `Code Filter đã sẵn sàng` rồi kết thúc mode `prepare`.

Vì vậy có hai lỗi độc lập:

- **Master:** giữ candidate/document cũ quá lâu và thử cả node không có action đúng.
- **Floating Filter:** chỉ kiểm tra input tồn tại/usable, không kiểm tra grid đã nạp
  dữ liệu và filter thật sự đang hiển thị trong grid mới.

## State machine bắt buộc

```text
HOME
  -> click Catalog
  -> NEW_CATALOG_TREE_FRAME
  -> CATEGORY_CONFIRMED
  -> click exact actionable "Master"
  -> nếu left document reload: reacquire left rồi click lại exact Master
  -> NEW_CATALOG_GRID
  -> GRID_DATA_SETTLED
  -> click #showfloatingfilter nếu Code Filter chưa visible
  -> FILTER_VISIBLE
  -> fill query
  -> FILTER_VALUE_CONFIRMED
  -> FILTER_RESULTS_SETTLED
  -> 0 / 1 / nhiều unique Code
  -> chỉ click Article khi đúng 1 unique Code
```

Không được nhảy state. Mode `prepare` chỉ thành công tại `FILTER_VISIBLE` sau khi
`GRID_DATA_SETTLED`, không phải ngay khi tìm thấy một input ẩn hoặc input thuộc grid cũ.

## Điều kiện xác nhận

### Mở Master

- Trước khi click Catalog, snapshot document của frame cây (thường tên `left`) và
  Catalog Grid cũ.
- Sau khi click Catalog, nhận diện frame cây mới theo `#ddlCategory`; ưu tiên
  nhưng không phụ thuộc cứng vào tên `left`.
- Nếu sau 3 giây trang trung gian `wfx_BaseSetting.aspx` chưa tạo frame cây, lấy
  `RedirURL` từ link menu, chỉ chấp nhận URL cùng origin và đích
  `WFX_CatalogMain.aspx`, rồi điều hướng frame `body` trực tiếp tới URL đó.
- Chỉ click node có text chuẩn hóa đúng bằng `Master` và có action trực tiếp
  (`onclick`, `a`, `button`, hoặc `role=button`).
- Ưu tiên đúng node `span[onclick]` như log; không click `img` collapse và không click
  container `li` chỉ vì nó chứa text Master.
- Sau mỗi click, chờ tối đa 4–5 giây:
  - nếu grid mới xuất hiện thì sang bước kế tiếp;
  - nếu document `left` đổi thì lấy lại frame/document và click lại đúng Master;
  - nếu không đổi gì thì retry đúng Master, không chuyển sang node cha/con ngẫu nhiên.
- Chỉ log `MASTER_OPENED` khi grid mới, URL chứa `wfxcataloglist`, đã xuất hiện.
- Header và Floating Filter xuất hiện trước datasource không phải là grid ready.
  Nếu center container còn cao 1px, không có row và cũng không có no-rows thật,
  phải tiếp tục chờ. Nếu filter đã nhận value trong trạng thái rỗng giả này,
  clear/refill đúng một lần sau khi datasource bind rồi mới kết luận timeout.

### Grid mới và dữ liệu đã ổn định

Grid hợp lệ phải đồng thời thỏa:

- thuộc frame/document mới so với snapshot trước khi click Catalog;
- URL chứa `wfxcataloglist`;
- có `.ag-root-wrapper`;
- không còn loading overlay hiển thị;
- có ít nhất một row dữ liệu thật, **hoặc** no-rows overlay đang hiển thị ổn định.

Không dùng tổng số node trong DOM làm số kết quả. AG Grid giữ virtual buffer, pinned
column và có thể clone row. Chỉ lấy row cắt với viewport hiện tại rồi deduplicate theo
Code không phân biệt hoa/thường.

### Floating Filter

- Tìm Code Filter bên trong chính `.ag-root-wrapper` đã xác nhận, không quét toàn bộ
  mọi frame rồi lấy input có score cao nhất.
- Nếu Code Filter chưa visible, click `#showfloatingfilter` trong cùng grid frame.
- Sau click, resolve lại grid/frame vì Angular có thể thay document.
- Xác nhận `Code Filter Input` visible, enabled và thuộc grid mới.
- Không log thành công nếu `rawRows=0` mà cũng không có no-rows overlay.

### Lọc

- Xóa cả Code Filter và Buyer Reference Filter bằng thao tác tương đương
  Playwright `locator.fill("")`.
- Điền query bằng thao tác tương đương `locator.fill(query)`, không chỉ gán `.value`.
- Xác nhận `input.value === query`.
- Chờ debounce và chờ loading kết thúc.
- Với Code: mọi Code đang render phải chứa query.
- Với Buyer Reference: mọi Buyer Reference đang render phải chứa query.
- Đếm `unique Code`, không đếm DOM button.
- `0`: không click.
- `1`: resolve lại button của đúng Code ngay trước click rồi mới click.
- `>=2`: giữ grid mở để người dùng chọn.

## Python tham chiếu đầy đủ

Đây là mã tham chiếu độc lập cho riêng pipeline Catalog. Nó dùng Chrome CDP giống
`login.py`, không chứa mật khẩu cứng. Chrome cần được mở với
`--remote-debugging-port=9222`; nếu chưa có session thì truyền `WFX_USER_ID` và
`WFX_PASSWORD`.

```python
from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Frame,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


HOME_URL = "https://prosports.worldfashionexchange.com/wfx_Home.aspx"
CDP_URL = os.getenv("WFX_CDP_URL", "http://127.0.0.1:9222")
COMPANY_ID = os.getenv("WFX_COMPANY_ID", "psh")
CATALOG_XPATH = '//*[@id="0003_6200"]/a'
TIMEOUT_MS = 20_000


def emit(stage: str, message: str, **data: Any) -> None:
    payload = {
        "time": time.strftime("%H:%M:%S"),
        "stage": stage,
        "message": message,
    }
    if data:
        payload["data"] = data
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def result(ok: bool, code: str, message: str, **data: Any) -> dict[str, Any]:
    return {"ok": ok, "code": code, "message": message, **data}


def normalize(value: str | None) -> str:
    return " ".join((value or "").split())


def connect(playwright: Playwright) -> tuple[Browser, BrowserContext, Page]:
    browser = playwright.chromium.connect_over_cdp(CDP_URL)
    if not browser.contexts:
        raise RuntimeError("CDP_NO_CONTEXT")
    context = browser.contexts[0]
    context.set_default_timeout(TIMEOUT_MS)
    page = next(
        (p for p in context.pages if "/wfx/default.aspx" in p.url.lower()),
        None,
    )
    page = page or next(
        (p for p in context.pages if "worldfashionexchange.com" in p.url.lower()),
        None,
    )
    page = page or context.new_page()
    page.bring_to_front()
    return browser, context, page


def click(locator: Any) -> None:
    locator.wait_for(state="attached")
    try:
        locator.click(timeout=3_000)
    except PlaywrightTimeoutError:
        locator.evaluate("element => element.click()")


def session_active(page: Page) -> bool:
    try:
        return page.locator(f"xpath={CATALOG_XPATH}").count() > 0
    except PlaywrightError:
        return False


def login_if_needed(page: Page) -> None:
    if session_active(page):
        emit("SESSION", "Dùng lại phiên WFX đang đăng nhập")
        return
    user_id = os.getenv("WFX_USER_ID", "").strip()
    password = os.getenv("WFX_PASSWORD", "")
    if not user_id or not password:
        raise RuntimeError("MISSING_CREDENTIALS")
    page.goto(HOME_URL, wait_until="domcontentloaded")
    page.locator("#txtUserID").fill(user_id)
    page.locator("#txtCompany").fill(COMPANY_ID)
    click(page.locator("#btlLogin[value='Next']"))
    page.locator("#txtPassword").fill(password)
    click(page.locator("#btlLogin[value='Log In']"))
    page.locator(f"xpath={CATALOG_XPATH}").wait_for(state="attached")
    emit("SESSION", "Đăng nhập thành công")


@dataclass
class DocumentSnapshot:
    frame: Frame | None
    url: str
    marker: str


def mark_document(frame: Frame | None, prefix: str) -> DocumentSnapshot:
    marker = f"{prefix}-{time.monotonic_ns()}"
    if frame is None:
        return DocumentSnapshot(None, "", marker)
    try:
        frame.evaluate(
            "(marker) => { window.__wfxAutomationDocumentMarker = marker; }",
            marker,
        )
    except PlaywrightError:
        pass
    return DocumentSnapshot(frame, frame.url, marker)


def document_is_new(frame: Frame, old: DocumentSnapshot | None) -> bool:
    if old is None or old.frame is None:
        return True
    if frame != old.frame:
        return True
    try:
        marker = frame.evaluate("() => window.__wfxAutomationDocumentMarker || ''")
        return marker != old.marker
    except PlaywrightError:
        return True


def current_grid_frame(page: Page) -> Frame | None:
    for frame in page.frames:
        if "wfxcataloglist" not in frame.url.lower():
            continue
        try:
            if frame.locator(".ag-root-wrapper").count() > 0:
                return frame
        except PlaywrightError:
            continue
    return None


def wait_new_left(page: Page, old: DocumentSnapshot, timeout_s: float = 15) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = page.frame(name="left")
        if frame is not None:
            try:
                if (
                    document_is_new(frame, old)
                    and frame.locator("#ddlCategory").count() > 0
                ):
                    emit("LEFT_READY", "Đã nhận frame left mới", url=frame.url)
                    return frame
            except PlaywrightError:
                pass
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError("CATALOG_LEFT_NOT_FOUND")


def select_category(
    page: Page,
    frame: Frame,
    category_name: str,
    category_value: str,
) -> None:
    selector = frame.locator("#ddlCategory")
    if selector.input_value() != category_value:
        selector.dispatch_event("mousedown")
        selector.locator(f'option[value="{category_value}"]').wait_for(
            state="attached",
            timeout=5_000,
        )
        selector.select_option(value=category_value, timeout=5_000)

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        current = page.frame(name="left")
        try:
            if (
                current is not None
                and current.locator("#ddlCategory").input_value(timeout=500)
                == category_value
            ):
                emit(
                    "CATEGORY_CONFIRMED",
                    f"Đã chọn {category_name}",
                    value=category_value,
                )
                return
        except PlaywrightError:
            pass
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError("CATEGORY_NOT_CONFIRMED")


def exact_actionable_master(frame: Frame):
    # WFX hiện dùng span text Master có onclick. Chỉ fallback sang action trực tiếp
    # khác; tuyệt đối không click img collapse hoặc li/div container.
    direct = frame.locator(
        'span[onclick], a, button, [role="button"], input[type="button"]'
    ).filter(has_text=re.compile(r"^\s*Master\s*$", re.IGNORECASE))
    for index in range(direct.count()):
        node = direct.nth(index)
        try:
            text = normalize(node.inner_text(timeout=500))
            if text.casefold() == "master":
                return node
        except PlaywrightError:
            continue
    return None


def wait_new_grid(
    page: Page,
    old_grid: DocumentSnapshot,
    timeout_s: float,
) -> Frame | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            if "wfxcataloglist" not in frame.url.lower():
                continue
            try:
                if (
                    document_is_new(frame, old_grid)
                    and frame.locator(".ag-root-wrapper").count() > 0
                ):
                    return frame
            except PlaywrightError:
                continue
        page.wait_for_timeout(200)
    return None


def click_master_until_grid(
    page: Page,
    old_grid: DocumentSnapshot,
    timeout_s: float = 50,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    attempt = 0
    last_left_marker = ""

    while time.monotonic() < deadline:
        frame = page.frame(name="left")
        if frame is None:
            page.wait_for_timeout(200)
            continue
        try:
            if frame.locator("#ddlCategory").count() == 0:
                page.wait_for_timeout(200)
                continue
            marker = frame.evaluate(
                """() => {
                    if (!window.__wfxMasterAttemptMarker) {
                        window.__wfxMasterAttemptMarker =
                            'left-' + Date.now() + '-' + Math.random();
                    }
                    return window.__wfxMasterAttemptMarker;
                }"""
            )
            if marker != last_left_marker:
                last_left_marker = marker
                emit("MASTER_FRAME", "Đã resolve document left", url=frame.url)

            master = exact_actionable_master(frame)
            if master is None:
                page.wait_for_timeout(250)
                continue

            attempt += 1
            emit(
                "MASTER_CLICK",
                "Click exact actionable Master",
                attempt=attempt,
                tag=master.evaluate("e => e.tagName"),
                onclick=bool(master.get_attribute("onclick")),
                left_marker=marker,
            )
            master.evaluate("element => element.click()")

            # Click đầu có thể chỉ reload left. Khi đó vòng sau sẽ resolve document
            # mới và click lại đúng Master. Không thử IMG/LI.
            grid = wait_new_grid(
                page,
                old_grid,
                timeout_s=min(4.5, max(0.2, deadline - time.monotonic())),
            )
            if grid is not None:
                emit(
                    "MASTER_OPENED",
                    "Master đã tạo Catalog Grid mới",
                    attempt=attempt,
                    grid_url=grid.url,
                )
                return grid
        except PlaywrightError as exc:
            emit("MASTER_RETRY", "Frame/node đổi trong lúc click", error=str(exc))
        page.wait_for_timeout(250)

    raise PlaywrightTimeoutError("MASTER_CLICK_NO_NAVIGATION")


def visible(locator: Any) -> bool:
    try:
        return locator.count() > 0 and locator.first.is_visible()
    except PlaywrightError:
        return False


def grid_state(grid: Frame) -> dict[str, Any]:
    return grid.locator(".ag-root-wrapper").first.evaluate(
        """root => {
            const shown = element => {
                if (!element || !element.isConnected) return false;
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    Number(style.opacity || 1) !== 0 &&
                    rect.width > 0 && rect.height > 0;
            };
            const loadingSelectors = [
                '.ag-overlay-loading-wrapper',
                '.ag-loading',
                '.ag-row-loading'
            ];
            const noRowSelectors = [
                '.ag-overlay-no-rows-wrapper',
                '.ag-overlay-no-rows-center'
            ];
            const loading = loadingSelectors.some(selector =>
                [...root.querySelectorAll(selector)].some(shown)
            );
            const noRows = noRowSelectors.some(selector =>
                [...root.querySelectorAll(selector)].some(shown)
            );
            const rows = [...root.querySelectorAll(
                '.ag-center-cols-container .ag-row[row-index], ' +
                '.ag-center-cols-container [role="row"][row-index]'
            )].filter(row => {
                if (!shown(row)) return false;
                if (row.classList.contains('ag-row-loading') ||
                    row.classList.contains('ag-row-ghost') ||
                    row.getAttribute('aria-hidden') === 'true') return false;
                const viewport = row.closest(
                    '.ag-center-cols-viewport, .ag-body-viewport'
                );
                if (!viewport) return true;
                const r = row.getBoundingClientRect();
                const v = viewport.getBoundingClientRect();
                return r.bottom > v.top + 0.5 && r.top < v.bottom - 0.5;
            });
            return {loading, noRows, renderedRows: rows.length};
        }"""
    )


def wait_grid_settled(grid: Frame, timeout_s: float = 35) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    stable_key = None
    stable_since = 0.0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last = grid_state(grid)
            ready = (
                not last["loading"]
                and (last["renderedRows"] > 0 or last["noRows"])
            )
            key = (
                last["loading"],
                last["noRows"],
                last["renderedRows"],
            )
            if ready and key == stable_key:
                if time.monotonic() - stable_since >= 0.7:
                    emit("GRID_SETTLED", "Grid đã ổn định", **last)
                    return last
            else:
                stable_key = key
                stable_since = time.monotonic()
        except PlaywrightError:
            pass
        grid.wait_for_timeout(200)
    emit("GRID_TIMEOUT", "Grid chưa ổn định", **last)
    raise PlaywrightTimeoutError("CATALOG_DATA_NOT_READY")


def ensure_floating_filter(page: Page, grid: Frame) -> Frame:
    deadline = time.monotonic() + 25
    last_click = 0.0
    while time.monotonic() < deadline:
        try:
            code_input = grid.locator('input[aria-label="Code Filter Input"]')
            if visible(code_input) and code_input.first.is_enabled():
                emit("FILTER_VISIBLE", "Code Filter hiển thị và enabled")
                return grid

            button = grid.locator("#showfloatingfilter")
            if visible(button) and time.monotonic() - last_click >= 2:
                last_click = time.monotonic()
                emit("FILTER_CLICK", "Click Show Floating Filters")
                button.first.click(timeout=3_000)
        except PlaywrightError:
            # Angular có thể thay document sau click. Chỉ nhận lại đúng Catalog Grid.
            candidate = current_grid_frame(page)
            if candidate is not None:
                grid = candidate
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError("FLOATING_FILTER_NOT_READY")


READ_RESULTS_JS = """(root, filterKind) => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            Number(style.opacity || 1) !== 0 &&
            rect.width > 0 && rect.height > 0;
    };
    const rendered = element => {
        if (!shown(element)) return false;
        const row = element.closest('.ag-row, [role="row"]');
        if (!row || row.classList.contains('ag-row-loading') ||
            row.classList.contains('ag-row-ghost') ||
            row.getAttribute('aria-hidden') === 'true') return false;
        const viewport = row.closest(
            '.ag-center-cols-viewport, .ag-body-viewport, ' +
            '.ag-pinned-left-cols-viewport, .ag-pinned-right-cols-viewport'
        );
        if (!viewport) return true;
        const r = row.getBoundingClientRect();
        const v = viewport.getBoundingClientRect();
        return r.bottom > v.top + 0.5 && r.top < v.bottom - 0.5;
    };
    const valueColumn =
        filterKind === 'buyer_reference' ? 'lblBuyerReference' : 'lnkArticleCode';
    const valueNodes = [...root.querySelectorAll(
        `[role="gridcell"][col-id="${valueColumn}"]`
    )].filter(rendered);
    const buttonNodes = [...root.querySelectorAll(
        '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
    )].filter(rendered);
    const values = valueNodes.map(cell => {
        if (valueColumn === 'lnkArticleCode') {
            return (cell.querySelector('input[type="button"]')?.value || '').trim();
        }
        return (cell.textContent || '').trim();
    }).filter(Boolean);
    const codes = buttonNodes.map(button => (button.value || '').trim()).filter(Boolean);
    const unique = values => [...new Map(
        values.map(value => [value.toLocaleLowerCase('vi'), value])
    ).values()];
    return {
        values: unique(values),
        codes: unique(codes),
        rawValueNodes: valueNodes.length,
        rawButtonNodes: buttonNodes.length
    };
}"""


def read_results(grid: Frame, filter_kind: str) -> dict[str, Any]:
    root = grid.locator(".ag-root-wrapper").first
    return root.evaluate(READ_RESULTS_JS, filter_kind)


def filter_catalog(
    grid: Frame,
    filter_kind: str,
    query: str,
) -> dict[str, Any]:
    definitions = {
        "code": ("Code", 'input[aria-label="Code Filter Input"]'),
        "buyer_reference": (
            "Buyer Reference",
            'input[aria-label="Buyer Reference Filter Input"]',
        ),
    }
    if filter_kind not in definitions:
        return result(False, "INVALID_FILTER", f"Filter không hỗ trợ: {filter_kind}")
    label, selector = definitions[filter_kind]

    for field_selector in (
        'input[aria-label="Code Filter Input"]',
        'input[aria-label="Buyer Reference Filter Input"]',
    ):
        field = grid.locator(field_selector)
        if visible(field):
            field.first.fill("")

    field = grid.locator(selector).first
    field.wait_for(state="visible")
    field.fill(query)
    if field.input_value() != query:
        raise RuntimeError("FILTER_VALUE_NOT_CONFIRMED")
    emit("FILTER_FILLED", f"Đã điền {label}", query=query)

    grid.wait_for_timeout(1_000)
    deadline = time.monotonic() + 25
    last: dict[str, Any] = {}
    query_folded = query.casefold()
    while time.monotonic() < deadline:
        state = grid_state(grid)
        last = read_results(grid, filter_kind)
        values = last["values"]
        applied = bool(values) and all(
            query_folded in value.casefold() for value in values
        )
        if not state["loading"] and (applied or state["noRows"]):
            break
        grid.wait_for_timeout(250)
    else:
        emit("FILTER_TIMEOUT", "Kết quả filter chưa ổn định", results=last)
        raise PlaywrightTimeoutError("FILTER_RESULTS_NOT_READY")

    codes = last["codes"]
    emit(
        "FILTER_RESULTS",
        "Đã đọc kết quả đang render",
        unique_count=len(codes),
        codes=codes,
        diagnostics=last,
    )
    if not codes:
        return result(False, "NO_RESULTS", f"Không tìm thấy {label}: {query}", codes=[])
    if len(codes) > 1:
        return result(
            True,
            "MULTIPLE_RESULTS",
            f"Có {len(codes)} kết quả; giữ grid để người dùng chọn.",
            codes=codes,
        )

    target_code = codes[0]
    buttons = grid.locator(
        '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
    )
    for index in range(buttons.count()):
        button = buttons.nth(index)
        try:
            if (
                button.is_visible()
                and normalize(button.input_value(timeout=500)).casefold()
                == target_code.casefold()
            ):
                button.click(timeout=5_000)
                emit("ARTICLE_CLICK", "Đã click unique Code", code=target_code)
                return result(
                    True,
                    "RESULT_OPENED",
                    f"Đã mở style {target_code}.",
                    article_code=target_code,
                    codes=codes,
                )
        except PlaywrightError:
            continue
    return result(False, "RESULT_DETACHED", "Row đổi trước thời điểm click.")


def open_destination(
    context: BrowserContext,
    destination: str,
    old_states: list[tuple[Page, str, str]],
) -> str:
    label, selector = {
        "costsheet": ("Costsheet", "#CostSheet"),
        "bom": ("BOM", "#BOMMaster"),
    }[destination]
    started = time.monotonic()
    deadline = started + 40
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            top = page.frame(name="ArticleTop")
            if top is None:
                continue
            old = next((item for item in old_states if item[0] is page), None)
            changed = old is None or page.url != old[1] or top.url != old[2]
            if not changed and time.monotonic() - started < 4:
                continue
            target = top.locator(selector)
            try:
                if target.count() > 0:
                    target.wait_for(state="attached", timeout=1_000)
                    page.bring_to_front()
                    target.evaluate("element => element.click()")
                    emit("DESTINATION_OPENED", f"Đã mở {label}")
                    return label
            except PlaywrightError:
                continue
        time.sleep(0.25)
    raise PlaywrightTimeoutError("ARTICLE_DESTINATION_NOT_FOUND")


def run_catalog(
    category_name: str,
    category_value: str,
    filter_kind: str | None = None,
    query: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    with sync_playwright() as playwright:
        _browser, context, page = connect(playwright)
        # Alert nghiệp vụ phải còn hiển thị trên Chrome để người dùng đọc và
        # xác nhận; không auto accept/dismiss mọi dialog.
        page.on(
            "dialog",
            lambda dialog: emit(
                "DIALOG",
                "Chờ người dùng xác nhận",
                text=dialog.message[:120],
            ),
        )
        login_if_needed(page)

        old_left = mark_document(page.frame(name="left"), "old-left")
        old_grid = mark_document(current_grid_frame(page), "old-grid")
        old_article_states = [
            (p, p.url, p.frame(name="ArticleTop").url)
            for p in context.pages
            if p.frame(name="ArticleTop") is not None
        ]

        catalog = page.locator(f"xpath={CATALOG_XPATH}")
        catalog.wait_for(state="attached", timeout=8_000)
        click(catalog)
        emit("CATALOG_CLICK", "Đã click Catalog")

        left = wait_new_left(page, old_left)
        select_category(page, left, category_name, category_value)
        grid = click_master_until_grid(page, old_grid)
        wait_grid_settled(grid)
        grid = ensure_floating_filter(page, grid)

        if not query:
            return result(
                True,
                "CATALOG_PREPARED",
                "Catalog, Master, grid data và Floating Filter đã sẵn sàng.",
            )

        filtered = filter_catalog(grid, filter_kind or "code", query.strip())
        if destination and filtered.get("code") == "RESULT_OPENED":
            label = open_destination(context, destination, old_article_states)
            filtered["destination"] = destination
            filtered["message"] = (
                f"Đã mở style {filtered['article_code']} → {label}."
            )
        return filtered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category-name", default="Apparel")
    parser.add_argument("--category-value", default="01")
    parser.add_argument("--filter", choices=["code", "buyer_reference"])
    parser.add_argument("--query")
    parser.add_argument("--destination", choices=["costsheet", "bom"])
    args = parser.parse_args()
    output = run_catalog(
        category_name=args.category_name,
        category_value=args.category_value,
        filter_kind=args.filter,
        query=args.query,
        destination=args.destination,
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(0 if output["ok"] else 1)


if __name__ == "__main__":
    main()
```

Ví dụ:

```powershell
python wfx_catalog_reference.py
python wfx_catalog_reference.py --filter code --query "ABC123"
python wfx_catalog_reference.py --filter buyer_reference --query "PO-99"
python wfx_catalog_reference.py --filter code --query "ABC123" --destination bom
```

## Yêu cầu log của Chrome Extension

Mỗi run phải có `runId`. Mỗi event ghi tối thiểu:

- timestamp, version, runId, stage, elapsedMs;
- frame name và URL đã loại query nhạy cảm;
- document generation/marker;
- selector/action đã dùng;
- Master attempt và lý do retry;
- grid loading/noRows/renderedRows;
- filter visible/enabled/value;
- raw node count, rendered node count, unique Code count;
- danh sách unique Code tối đa 20 item;
- error code riêng cho từng state.

Không ghi password, cookie, SessionID, LoginID, IP hoặc toàn bộ URL có query nhạy cảm.

Các error code tối thiểu:

```text
CATALOG_MENU_NOT_FOUND
CATALOG_LEFT_NOT_FOUND
CATEGORY_OPTION_NOT_FOUND
CATEGORY_NOT_CONFIRMED
MASTER_NOT_FOUND
MASTER_CLICK_NO_NAVIGATION
CATALOG_GRID_NOT_FOUND
CATALOG_DATA_NOT_READY
FLOATING_FILTER_NOT_READY
FILTER_VALUE_NOT_CONFIRMED
FILTER_RESULTS_NOT_READY
RESULT_DETACHED
ARTICLE_OPEN_NOT_CONFIRMED
ARTICLE_DESTINATION_NOT_FOUND
```

## Hotkey

**Desktop app (chính):** hotkey toàn cục mặc định `Ctrl+Shift+X` do
`wfx_panel/hotkey.py` + thư viện `keyboard` bắt ở cấp hệ điều hành, nên nhận được
kể cả khi focus nằm trong iframe của WFX trên Chrome. Đổi được trong Settings. Giới
hạn: nếu cửa sổ đang focus chạy quyền Administrator cao hơn app thì global hook có
thể không nhận phím — khi đó dùng launcher/tray để mở panel.

**Biến thể extension/userscript (tuỳ chọn, tham khảo):** Hotkey mặc định
`Ctrl+Shift+X` (khác `Ctrl+Alt+X` cũ — tổ hợp `Ctrl+Alt` bị Chrome
từ chối trong `suggested_key` vì trùng `AltGr`). `Ctrl+Shift+X` là tổ hợp hợp lệ nên
manifest command `toggle-panel` KHAI BÁO `suggested_key.default = "Ctrl+Shift+X"` để Chrome
tự bind sẵn, người dùng không phải gán tay tại `chrome://extensions/shortcuts`.

Lý do dùng Chrome command thay vì bắt keydown in-page: WFX chạy nội dung trong iframe, mà
content script chỉ chạy ở top frame (`all_frames:false`) nên keydown khi focus trong iframe
không tới được listener top → hotkey "không phản hồi trên màn WFX". `chrome.commands` bắt phím
ở cấp trình duyệt, độc lập với frame nào đang focus. Background service worker nhận
`chrome.commands.onCommand` và gửi message toggle tới tab WFX đang active; nếu chưa có tab WFX
thì mở/focus WFX trước.

Vì command đã là nguồn hotkey duy nhất của bản extension: bridge.js KHÔNG bắt keydown nữa và
core `handleKeydown` bỏ nhánh toggle khi `window.__wfxSmartChromeExtensionLoaded` (tránh
double-toggle mở-rồi-đóng khi focus ở top frame). Tampermonkey không có command API nên vẫn dùng
hotkey in-page cấu hình được trong panel.

## Tiêu chí nghiệm thu

1. Master có thể cần click lại sau frame reload, nhưng không click IMG/LI và không báo
   lỗi trước timeout tổng.
2. Mode prepare không báo thành công khi `rawRows=0`, trừ khi no-rows overlay thật sự
   visible và ổn định.
3. Nếu filter chưa mở, UI/log phải nói đang click `#showfloatingfilter`; chỉ báo xong
   khi input visible + enabled.
4. UI hiển thị 1 Code thì kết quả phải là 1, dù DOM giữ 32 node clone/buffer.
5. Code và Buyer Reference đều fill được và có xác nhận giá trị.
6. Một unique Code tự mở Article; nhiều Code không tự mở.
7. Costsheet/BOM chờ đúng popup `ArticleTop`.
8. `Ctrl+Shift+X` (suggested_key trong manifest) mở/đóng panel được ngay cả khi focus đang
   nằm trong iframe của WFX, không cần gán tay ở `chrome://extensions/shortcuts`.
9. Sửa code trong `wfx_panel/` (nguồn) và build lại bằng `build-panel.ps1`; không
   chỉnh trực tiếp file trong `dist/`. `python -m pytest` và `ruff check .` phải xanh.
