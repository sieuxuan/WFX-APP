# WFX Catalog automation — đặc tả hành vi chuẩn

## Sản phẩm thật

Dự án này là **desktop app pywebview** (`wfx_panel/`) tự động hoá
WorldFashionExchange qua Playwright/CDP, đóng gói bằng PyInstaller
(`build-panel.ps1` → `dist/WFX-Panel/`), đóng thành bộ cài Inno Setup
(`build-installer.ps1` → `dist/installer/`) và tự cập nhật từ GitHub Release.
Mọi code sản phẩm nằm trong `wfx_panel/`. Khi sửa code, luôn sửa trong
`wfx_panel/` (nguồn), không sửa mỗi file trong `dist/`.

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
dành cho người dùng nằm trong `wfx_panel/manual/` và được sinh ra
`docs/USER_FEATURES.md` bằng `python scripts/generate_user_features.py`. Không
sửa tay `docs/USER_FEATURES.md`. `README.md` là hướng dẫn cài/chạy/build ngắn
gọn.

Thay đổi hành vi sản phẩm phải cập nhật `wfx_panel/manual/` trong cùng lần sửa:
thêm module, thêm nút thao tác, thêm công tắc cài đặt hoặc thêm mã lỗi mà chưa
có mục hướng dẫn phủ thì `tests/test_manual.py` sẽ đỏ. Cách viết nằm ở
`docs/MANUAL_AUTHORING.md`.

### Hành vi giao diện

- Launcher 48×48 logical mở panel; native bounds phải scale theo DPI của HWND
  (48/60/72/96 physical tại 100/125/150/200%), kể cả khi cửa sổ đang hidden.
  Hotkey mặc định là `Ctrl+Shift+X`.
- Bản EXE mặc định bật `Khởi động cùng Windows` cho cài đặt mới và đồng bộ
  Windows Run key sau khi giữ được single-instance lock. Nếu người dùng đã tắt
  thì phải giữ nguyên lựa chọn đó. Chạy source development không được tự đăng
  ký Python/Pythonw vào startup.
- Panel tự thu khi mất focus, kể cả khi automation đang chạy, để user có thể
  thu nhỏ UI hoặc chuyển sang Chrome theo dõi WFX mà không dừng task. Ngoài
  `window.blur`, monitor foreground Win32 là fallback bắt buộc vì WebView2 đôi
  khi bỏ lỡ blur. Trạng thái pointer của WebView phải được đồng bộ sang native;
  không được thu panel chỉ vì automation vừa đưa Chrome lên foreground khi con
  trỏ vẫn đang thao tác trong UI.
- Chuyển giữa List/module và thanh tiến trình dùng animation ngắn chỉ với
  transform/opacity; phải tôn trọng `prefers-reduced-motion`. Nút vừa kích hoạt
  giữ highlight trong khi tác vụ chạy để người dùng biết flow nào đang xử lý.
- Bootstrap bình thường do `PanelApp._startup()` inject một lần; JavaScript chỉ
  gọi `get_initial_state` sau 600 ms làm fallback nếu chưa nhận state, tránh đọc
  prefs và render module trùng lúc mở app.
- Nút Manual ở top nav mở một cửa sổ Hướng dẫn sử dụng riêng 1000×720, đọc nội
  dung đã đóng gói trong `wfx_panel/manual/`. Cửa sổ này chạy offline hoàn toàn:
  không gọi mạng, không cần Chrome, không cần phiên WFX. Bấm lần hai đưa cửa sổ
  đang mở lên trước, không tạo cửa sổ trùng. Cửa sổ Manual không tham gia logic
  tự thu của panel. Mỗi màn module có nút dấu hỏi mở đúng mục của module đó, và
  thanh trạng thái hiện nút trợ giúp khi lỗi có mục hướng dẫn. Sau khi ứng dụng
  tự cập nhật, nút Manual hiện badge `Mới` có nhãn rõ ràng và mở thẳng phần Có
  gì mới. Nút Log dùng badge cảnh báo `!` màu vàng khi có lỗi mới; không dùng
  chấm đỏ không nhãn dễ bị hiểu là lỗi render.
- Mặc định app nhớ đúng màn module người dùng đang làm. Setting `Trở về List
  sau khi thao tác` cho phép đổi sang hành vi quay về danh sách module.
- Module được ghim bằng nút ngôi sao sẽ nằm trong `Yêu thích` ở đầu vùng cuộn,
  ngay sau ô tìm kiếm cố định. Khu vực này dùng chung scrollbar với danh sách;
  module đã ghim không lặp lại trong nhóm bên dưới và luôn giữ cùng độ rộng hai
  cột để thao tác ghim không làm layout nhảy hoặc đẩy ô tìm kiếm xuống.
- Tab Tài khoản ở trạng thái đã đăng nhập chỉ hiện kết nối hiện tại và nút `Đổi
  tài khoản`; form User ID/password chỉ mở khi người dùng muốn đổi hoặc cần xác
  thực lại.
- Sau khi đã có một phiên đăng nhập thành công, app kiểm tra/duy trì phiên nền
  mỗi 4 phút khi Chrome rảnh. Nếu một flow phát hiện `NOT_LOGGED_IN`, app dùng
  credential đã lưu để login lại và retry toàn bộ flow đúng một lần; không retry
  từng bước ghi dữ liệu và không lặp vô hạn. Các probe chỉ đọc session/Division/
  quyền và ảnh chẩn đoán phải dùng `bring_to_front=False`, không được kéo user
  khỏi tab Costing.
- Nếu một flow do user kích hoạt phát hiện `CHROME_CLOSED`, app phải tự mở lại
  trình duyệt làm việc, đăng nhập bằng credential đã lưu và retry toàn bộ flow
  đúng một lần. Heartbeat nền không tự mở lại Chrome khi user chủ động đóng.
- Form góp ý chỉ cho gửi từ 5 ký tự và hiển thị bộ đếm trên giới hạn 2.000 ký tự.
- Bộ chọn Division là segmented control gọn để dành thêm chiều cao cho module.
- Chỉ thanh footer dưới cùng hiển thị trạng thái tác vụ; không lặp status bên
  trong màn module.
- Result sink từ backend phải nhả trạng thái busy của UI độc lập với Promise
  pywebview. Nếu Promise bridge bị kẹt sau khi backend đã ghi kết quả, các nút
  workflow vẫn phải hoạt động lại ngay.
- Các form Search/Cancel nhiều điều kiện phải disable hành động khi toàn bộ ô
  liên quan còn trống, hiện gợi ý ngay tại form và chỉ nhận Enter khi hợp lệ;
  backend vẫn giữ validation như lớp bảo vệ cuối.
- `Lịch sử hoạt động` chỉ gồm `Tất cả tác vụ` và `Log kỹ thuật`; không tách thêm
  thẻ `Cần xử lý`. Heartbeat `maintain_session` thành công không ghi `jobs.json`,
  không thêm log RUN và không thay footer.
- Toast hoàn tất phải hiện khi foreground đang ở WFX, kể cả panel chưa kịp đổi
  cờ sang hidden; không hiện trùng khi panel thật sự đang foreground. Nếu
  tray Windows đã sẵn sàng, ưu tiên notification native để không phụ thuộc
  WebView2 hidden và vẫn lưu ở Notification Center; WebView notification là
  fallback, giữ thông báo mới nhất nếu chưa load. Settings có nút thử toast,
  toast không được lấy focus.
  Bấm vào THÂN toast phải mở lại panel qua `show_from_tray()`, vì đó là lý do
  người dùng bấm. Toast native gửi `NIN_BALLOONUSERCLICK` (`0x0405`) chứ không
  phải `WM_LBUTTONUP`, và pystray không xử lý message này, nên
  `_WfxTrayIcon._on_notify` phải tự bắt. Toast WebView bắt click trên chính
  `.notification` và gọi bridge `activate()`; nút đóng nằm bên trong nên bắt
  buộc `stopPropagation()` để bấm ✕ chỉ đóng chứ không kéo panel lên.
- Updater chờ instance hiện tại tự đóng 15 giây. Nếu pywebview/WebView2 còn giữ
  process cha, helper chỉ được force-stop đúng PID sau khi xác minh đường dẫn
  process trùng exact `WFX-Panel.exe` đang cập nhật; tuyệt đối không kill theo
  tên process. Chỉ tải/thay file sau khi PID đã biến mất.
- Release phải phát hành song song `WFX-Smart-Setup-v<version>.exe` và ZIP
  portable. Installer dùng AppId cố định, cài per-user vào
  `%LocalAppData%\Programs\WFX Smart`, không yêu cầu Admin, mặc định tạo shortcut
  Desktop/Start Menu và dùng Restart Manager để đóng app khi nâng cấp. Không
  được xóa dữ liệu `%LocalAppData%\WFX-Panel` khi cài, upgrade hoặc uninstall.
  Updater phải nhận diện kiểu cài đặt hiện tại: bản đã cài bằng Setup luôn tải,
  xác minh và chạy asset Setup để Inno Setup nâng cấp/giữ registry, shortcut và
  Uninstall; chỉ bản portable chạy `WFX-Panel.exe` trực tiếp mới tải ZIP và tự
  thay `WFX-Panel.exe`/`_internal` như luồng updater hiện tại.
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
  ở gần cuối và không chọn văn bản. App chạy cả ngày ở khay hệ thống nên `<pre>`
  log có trần dòng cứng và cắt dòng cũ nhất; `pushLog` chỉ được đụng
  `childNodes`/`firstChild`, KHÔNG đọc `pre.textContent` trên từng dòng vì getter
  đó nối lại toàn bộ text node con, làm chi phí ghi log tăng theo bình phương.
- Nội dung hiển thị cho người dùng phải là tiếng Việt Unicode NFC, dùng nhất
  quán `xóa`, `hủy`, `hóa`. Ưu tiên “bảng điều khiển”, “khay hệ thống” và
  “trình duyệt làm việc”; chỉ giữ tiếng Anh khi đó là tên nghiệp vụ hoặc nhãn
  chính thức trên WFX.

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
   Với AG Grid có Floating Filter, automation phải quét toàn bộ scroll ngang để
   tìm cột dù user đã kéo đổi thứ tự; đồng thời xóa các filter cũ ở cả cột đang
   bị virtualize trước khi điền điều kiện mới. Sau cùng giữ cột đích trong
   viewport để user thấy điều kiện đang áp dụng.
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
8. Playwright attach qua CDP là ĐỔI thư mục tải của chính Chrome sang temp
   riêng của nó (`Browser.setDownloadBehavior` = `allowAndName`), rồi xóa sạch
   thư mục đó khi ngắt. Nên trong lúc một flow chạy, file NGƯỜI DÙNG tự bấm tải
   trên WFX cũng bị nuốt vào đó và mất hẳn — Downloads rỗng, mục trong Chrome
   Download history trỏ vào đường dẫn đã chết nên bấm mở file/`Show in folder`
   đều không có tác dụng. Vì vậy runtime theo dõi mọi sự kiện `download` của
   context và, trong `_release_connections()` TRƯỚC khi nhả driver, lưu các
   download không có flow nào nhận về `%USERPROFILE%\Downloads` kèm log. Flow
   nào tự `save_as` phải gọi `claim_download()` ngay trước đó, nếu không mỗi lần
   xuất báo cáo lại sinh thêm một bản thừa trong Downloads.
9. Các wait dài dùng `_wait()`/`_sleep()` theo lát tối đa 100 ms để đọc cancel;
   không thêm cơ chế terminate/close page từ thread UI.
10. Chỉ tác vụ thật sự chạm Playwright/Chrome mới được bọc `_run()`. Các lời gọi
   HTTP thuần như `sync_reference_data`/`sync_article_library` phải chạy ngoài
   `_run()`: `_run()` giữ `_run_lock` và chiếm automation worker suốt cả timeout
   mạng, nên vòng lặp nền sẽ trả `ACTION_IN_PROGRESS` cho mọi cú bấm của người
   dùng, còn ở lúc khởi động thì auto-login giữ lock khiến chính lượt sync bị bỏ
   qua tới lần poll sau. Chúng cũng không được đẩy dòng nền vào `job_history`,
   vì trần 200 dòng phải dành cho job thật.

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
- Catalog có workspace `Tạo Style` riêng cho Apparel. User phải quét/chọn một
  node đúng loại Group rồi mới Import form XLSX. Form gồm Type New/Copy, Style
  copy và các trường Style; mã copy bắt đầu SWN/SKN tìm bằng Article Code, mã
  khác tìm bằng Buyer Reference. Copy mặc định chọn CostSheet và Copy as
  Variant; nhiều kết quả phải để user chọn trong app. Mỗi lần chỉ chuẩn bị một
  dòng, đặt Purchase UOM=Pcs, Price Per=Article và Color Definition=Single
  Colors. Toggle `Tự động Save` luôn mặc định off: khi off, app dừng trước Save
  và chỉ sang dòng kế sau khi user xác nhận đã tự kiểm tra/Save trên WFX; khi on,
  automation click đúng Save một lần sau khi điền xong rồi chuyển sang dòng kế.
  Group dùng picker có tìm kiếm theo tên/đường dẫn thay cho select dài; nút quét
  Group là icon nhỏ nằm cùng hàng. Form Excel có dropdown từ snapshot GitHub/cache
  30 ngày cho Material Type, Buyer, Division, Product Group, Color Card, Size
  Range và Season; Sub-Category phụ thuộc Product Group. Khi snapshot hết hạn,
  app quét read-only form WFX trong Group đã chọn, không Save, lưu local và ghi
  `data/style-options.json` qua GitHub Contents API khi máy quản trị có token.
  Bản phát hành thường chỉ có quyền đọc GitHub Raw, không nhúng token ghi.
  `Tải form Excel` phải hỏi nơi lưu TRƯỚC khi lấy dropdown, vì bước lấy dropdown
  có thể gọi GitHub hoặc chạy nguyên một lượt quét WFX. Lượt quét để lại một form
  New Style điền dở nên phải đóng đúng những popup chính nó mở (so với snapshot
  `context.pages`), kể cả khi lỗi hoặc bị Stop; popup của `prepare_style_row` thì
  giữ nguyên vì đó là kết quả user cần kiểm tra và tự Save.
  Không dùng `expect_page` chờ blocking khi mở New: WFX đặt tên cửa sổ
  `CatalogDetail` nên từ dòng thứ hai trở đi `window.open` tái dùng cửa sổ đang
  mở và Chromium không phát page event, làm mỗi dòng mất trọn timeout. Frame scan
  là nguồn xác nhận và nhận được cả hai trường hợp.
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
  Style Name đặt tên file. Hộp thoại nhớ thư mục export gần nhất; Settings
  chỉ cho chọn có mở file Costing sau export hay không. Thư mục chứa file
  luôn tự mở sau mọi download/export thành công. Nút `Kiểm tra file` chỉ
  validate XLSX và trả lỗi sheet/ô, không scan WFX hoặc tạo dry-run.
  `Costing` luôn có bộ cột form chuẩn để nhập trực tiếp, chỉ round-trip field
  item `editable=true`. Cuối form có đúng 1 dòng CM Costs, 1 dòng Production
  Costs và 2 dòng Indirect Costs; scan option Article từ editor đúng block,
  Curr. CM/Indirect là USD, dòng trống không Add. Production đặt Minutes=1 ở
  parent và child, rồi Value parent trước Rate child. Không có sheet `Cost Sheet`,
  `Sections`, `_Fields`, `_Meta`; hộp thoại chỉ hỗ trợ `.xlsx`.
- Ba danh sách dùng chung của CM Costs/Production Costs/Indirect Costs chỉ scan
  một lần trong 7 ngày, cache theo User ID + Division. Công tắc `Quét lại danh
  sách chi phí` nằm cùng hàng với `Clear All Dependency`, mặc định off, chỉ ép lần Export/Import
  Costing kế tiếp và tự off sau khi scan + lưu cache thành công. Việc này không
  được bỏ qua scan Color/Size, dependency mapping hoặc field riêng của Style.
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
  cho nhập tay. Khi người dùng chọn Article Name trong workbook, lúc đọc/import
  app phải đồng bộ ngược Article Code nếu tên chỉ khớp đúng một mã; tên trùng
  nhiều mã phải báo chọn Article Code, không tự đoán. Mọi gợi ý bắt đầu sau 2 ký
  tự, tối đa 20 kết quả. Typeahead không được quét lại cả kho trên từng ký tự:
  chuẩn hóa và khử trùng đúng một lần cho mỗi cặp (Category, field) qua
  `article_library.suggestion_index`, gắn vào chính document trong cache để index
  tự mất hiệu lực khi file cache đổi.
- Khi user chọn một gợi ý từ Buyer Reference hoặc Article Name, UI phải lấy
  exact `Article Code` của chính dòng đó, chuyển filter sang Code và tìm bằng
  code; không lọc lại Buyer Reference/Name khiến user phải chọn Article lần hai.
  Nếu floating filter Code dạng contains vẫn render nhiều code gần giống, exact
  code duy nhất phải được mở trực tiếp.
- Costing tuyệt đối không click `#colBodyType label span`, `#imgDeleteSection`,
  `#imgEditSection` hoặc `#imgCopySection`.
- Nút `Clear All Dependency` nằm dưới nhóm Import Costing, chỉ chạy với tab
  CostSheet `Open`, phải hỏi xác nhận ở UI, click toàn bộ link trùng id
  `#lnkClearDependency` trong đúng frame Costing rồi Save một lần. Không tự chạy
  khi người dùng chỉ Export/Import bình thường.
- OC List: tìm theo OC No. hoặc Style; tải form `OC INPUT` một hàng header;
  Upload OC New và Revise OC qua EDI Buyer PO.
- Workspace OC gom nút mở `OC List` và Search trong cùng card; selector OC
  No./Style, ô nhập và nút Tìm nằm trên một hàng gọn. Hai card `Upload OC New`
  và `Revise OC` cân bằng hai cột, chữ/nút không nhỏ hơn phần thao tác chính của
  panel; New giữ cặp tải mẫu/chọn file và Revise giữ cặp mở report/chọn file.
  Hai nút action trong mỗi card xếp dọc để nhãn không tràn ở chiều rộng panel.
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
- Mỗi lần user chọn workbook, kể cả chọn lại cùng tên/đường dẫn sau khi Huỷ,
  backend phải snapshot lại bytes hiện tại vào thư mục review mới và tính
  SHA-256; không dùng lại workbook đã chuẩn hoá hoặc kết quả review trước. UI
  dùng selection revision để kết quả bất đồng bộ cũ không render đè lần mới.
- Form OC có dropdown Order Type `Confirmed`/`Forecast`/`SMS` và Payment Terms
  theo danh sách WFX chuẩn. Dòng `Units = 0` được bỏ khỏi Sheet1 và review;
  Units âm/không nguyên vẫn là lỗi. Zone trống mặc định `FOB`, Extra Production
  trống mặc định `0`. New và Revise đều phải kiểm tra nghiêm ngặt
  `Buyer Order Date < Raw Material ETA < Buyer Delivery Date = OC Delivery Date`.
- EDI OC phải chọn exact Buyer từ file và package value `1`/
  `StandardSalesOrder`, upload file chuẩn hoá, bấm `Process Package` rồi đọc
  cả `Data Imported`, `Data Validated`, `Mapping Resolved`. Chỉ khi tất cả đều
  Success mới chọn transaction đầu tiên và bấm `Create Transaction`; New đi
  tab `New`, Revise đi tab `Revision`.
- Chỉ đọc package mới nhất trong Error Resolution. Bất kỳ trạng thái `InProgress`/
  `In Progress` hoặc Fail nào ở Imported/Validated/Mapping đều được coi là lỗi
  ngay, không chờ timeout. Automation click đúng link trạng thái, đọc popup
  `Failed Record` (Mapping Code, Doc No., Mapping Details, InActive), trả chi
  tiết cho UI, giữ popup để chụp ảnh vào Lịch sử và không click Create Transaction.
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
  Created By, và New Sample Order. Nút `Check File` chạy đúng flow Search trước;
  nếu chỉ có một dòng thì tự click Style Code, quét bốn mục file giống Catalog
  và trả danh sách tải trực tiếp. Nếu có nhiều dòng, panel hiển thị lựa chọn
  Sample; sau khi user chọn, app tiếp tục từ grid đang mở, không tìm lại.
- Sale ASN: List + Floating Filter, tìm theo Invoice No./Buyer Order Ref/OC
  No., New từ Excel, và tải Documents. Workspace có đúng MỘT tầng tab gồm
  `Tạo mới` (mặc định) và `Tra cứu`; nút mở `Sale ASN List` là icon nằm trên
  thanh trên nên dùng được ở cả hai thẻ. Không được thêm tầng tab thứ hai bên
  trong thẻ Tạo mới. Thẻ `Tạo mới` là một cột dọc Buyer → file → review → chạy.
  Buyer được quét từ `#Cell_Buyer`, cache lại, và dùng listbox gợi ý (không dùng
  `<datalist>`): gõ từ 2 ký tự thì lọc tối đa 20 kết quả; nút dropdown mở toàn bộ
  Buyer đã cache; khớp exact thì hiện dấu ✓ và chưa khớp thì viền cảnh báo ngay
  tại ô. Chọn bước chạy, tiêu chí tìm PO và nút `Mở Sale ASN New trống` nằm
  trong khối gấp `Tùy chọn nâng cao`, mặc định đóng và tự bung khi có bước đang
  bỏ tích. KHÔNG có luồng `Chỉ điền Order Details` 8 cột: form 8 cột, hai nút
  `Xuất form từ WFX`/`Chọn file 8 cột` và các API
  `read/write_sale_asn_order_details_*`, `prepare/start/cancel_sale_asn_order_details`,
  `run_sale_asn_order_details` đã bị gỡ. Chứng từ đã có sẵn PO thì bỏ tích bước
  `Thêm PO`, bấm `Xuất PO đang mở` để lấy form 22 cột đã điền sẵn PO rồi chạy
  các bước còn lại. Nút đó chạy `scan_sale_asn_order_details` (chỉ đọc grid
  Order Details đang mở) rồi `save_sale_asn_continue_template` (ghi form 22 cột);
  hai hàm này phải được giữ lại.
  Thẻ `Tạo mới` chỉ hiện đúng phần của giai đoạn hiện tại qua
  `data-stage-view` (`idle`/`review`/`running`/`done`) do `setSaleAsnStageView`
  đặt: từ `review` trở đi, hàng Buyer, nút chọn file và `Tùy chọn nâng cao` thu
  về một dòng ngữ cảnh `Buyer · tên file` kèm nút `Đổi`. Mở lại module phải suy
  giai đoạn từ `saleAsnReviewToken`, không được để kẹt ở `done` làm mất hẳn hàng
  Buyer/chọn file. `.sale-asn-inline-status` nằm TRONG khối setup nên chỉ sống ở
  `idle`: nó là hướng dẫn chọn Buyer/file, không phải trạng thái tác vụ (footer
  mới là nơi đó). Không được ghi lại vào nó câu mà thẻ review/kết quả đã in.
  Thông điệp khi lượt chạy dừng đi vào `.sale-asn-review-note` cạnh nút Bắt đầu.
  Thẻ `Tra cứu` gom bộ lọc Search và nút xuất
  Buyer Invoice + Packing List trong cùng một bề mặt, không tách thêm card.
  Trong lúc chạy, panel hiện thẻ tiến độ năm bước theo `SALE_ASN_STAGE_ORDER`;
  `run_sale_asn_create` bắn progress qua callback tùy chọn `progress` và
  `PanelAPI._progress` phải mang `method` của flow đang chạy để
  `wfxHandleBackendProgress` rẽ đúng thẻ, không đè thẻ GDN. Mọi bước chạy theo
  vòng lặp từng dòng (`po`, `order_details`, `style_details`) phải kết thúc
  message bằng `n/m`; UI đọc đúng hậu tố đó để hiện bộ đếm, nên không được đổi
  định dạng này khi thêm bước mới.
  Lựa chọn bước được nhớ qua `prefs.sale_asn_stages`; `_clean_sale_asn_stages`
  luôn trả về đủ bốn bước khi danh sách rỗng hoặc hỏng, vì lưu trạng thái rỗng
  sẽ khiến user mở app ra mà không chạy được gì. Hộp thoại chọn file nhớ thư mục
  gần nhất qua `prefs.sale_asn_import_dir`.
  Tuyệt đối KHÔNG tự chạy `scan_sale_asn_buyers` khi user mở module: hàm này mở
  hoặc refresh hẳn form Sale ASN New trên Chrome, tức kéo user khỏi tab đang làm.
  Khi kho Buyer còn rỗng, chỉ được làm nút quét nổi bật để user tự bấm. Progress chỉ để hiển
  thị: giá trị trả về của flow vẫn là nguồn sự thật và ghi đè trạng thái dòng
  bước. Vì progress đi bằng `evaluate_js` còn kết quả flow về đường khác, UI
  phải có cờ `saleAsnRunActive` bao quanh đúng từng lời gọi và bỏ qua mọi
  payload ngoài lúc đó; không có cờ thì một payload đến trễ sẽ xóa thẻ kết quả
  và kéo bộ đếm lùi lại. Thẻ kết quả cũ phải bị ẩn trong `resetSaleAsnProgress`
  để lần mở module sau không còn nút handoff trỏ vào Invoice của lượt trước.
  Trạng thái chờ chọn PO và lỗi từng bước phải hiện trong đúng dòng bước
  của thẻ tiến độ, không dùng thẻ pending rời. Vì bước `po` không cho `Bỏ qua`,
  thẻ hành động luôn phải có lối thoát `Bỏ lượt này và chọn file khác`; nếu
  không, người dùng kẹt ở trạng thái chờ chọn PO mà chỉ còn nút Tiếp tục. Khi flow trả
  `SALE_ASN_FORM_COMPLETED`, thẻ kết quả liệt kê cảnh báo Shipping Info và có nút
  chuyển sang thẻ `Tra cứu` với Invoice No. điền sẵn; nút đó không được tự chạy
  xuất báo cáo vì user còn phải Save trên WFX. Ngay khi thẻ kết quả hiện, UI phải
  tự scroll thẻ đó vào viewport của module để user không phải kéo xuống tìm.
  Form Excel có đúng 22 cột theo thứ tự `Style No`, `PO No`, `Qty`, `Price`, `Carton`,
  `NW`, `GW`, `CBM`, `FOB Price`, `Service Price`, `Cargo Ready Date`,
  `HS CODE`, `Goods Description`, `Invoice No`, `Invoice Date`, `Shipping Bill No`, `Shipping Bill Date`,
  `Destination`, `FTY`, `Consignee Address`, `Ship To`, `Shipping Mode`; bỏ
  `SEASON`/cột `DESCRIPTION` cũ. Mỗi file chỉ chứa một Invoice No. và một FTY, xử lý PO
  đúng thứ tự dòng. Một PO có thể có nhiều Style; chỉ cặp PO No. + Style No. trùng
  hoàn toàn là lỗi. Style No./PO No./FTY bắt buộc, Destination là tùy chọn;
  Shipping Mode chỉ
  bắt buộc và chỉ được đọc ở dòng dữ liệu đầu tiên khi chạy Shipping Info, chỉ
  nhận AIR/SEA/COURIER; các dòng sau không cần điền và không được ghi đè mode đầu;
  HS Code/Goods Description/Qty/Price/Carton/NW/GW/CBM/FOB Price/Service Price/Cargo Ready Date/
  Consignee Address/Ship To được phép trống. Nếu cả file không có Cargo Ready
  Date thì giữ trống và không dùng ngày hiện tại; nếu có ngày ở một dòng thì
  dùng ngày có dữ liệu đầu tiên để điền mọi dòng còn trống. Ba cột Cargo
  Ready Date/Invoice Date/Shipping Bill Date phải có date validation trong form
  Excel và cho phép để trống. Invoice Date/Shipping Bill Date vẫn kế thừa ngày
  đầu tiên, không có nữa mới dùng ngày hiện tại; Shipping Bill No. trống thì dùng
  Invoice No.
  Automation chọn Buyer, mở Add Order Details và tìm tuần tự theo các tiêu chí
  đang bật trong `prefs.sale_asn_po_search_fields`, thứ tự cố định PO → Style →
  Destination. Mặc định bật đủ ba; dữ liệu hỏng hoặc danh sách rỗng phải quay về
  đủ ba. Destination trống phải tự bỏ qua tiêu chí này cho đúng dòng đó, đồng
  thời không làm thay đổi cặp Country Of Destination/Final Destination mặc định.
  Style từ file là từ khóa gần đúng (ví dụ `M Acel Jacket` phải khớp được
  `JLD-SMOW17905-M ACEL JACKET-MEN` trên WFX), không phải mã exact. Sau mỗi lần
  thêm điều kiện, nếu chỉ còn một dòng thì chọn và add ngay;
  nếu dùng hết tiêu chí mà vẫn còn nhiều dòng thì select all rồi Add & Continue/
  OK đúng một lần. Không dùng Dispatched Qty để tự quyết định PO, nhưng nếu popup
  trả số này thì phải so sánh với Qty file trước khi Add/OK và dừng khi lệch. Nếu 0 kết quả, giữ
  cửa sổ cho user xử lý thủ công; app dùng review token để tiếp tục từ dòng kế,
  không đọc lại hay đảo thứ tự file. Bộ tiêu chí phải được snapshot vào review
  token để thay đổi Settings giữa lượt không đổi hành vi của lượt đang chạy.
  Trước một lượt tạo mới, nếu
  frame Sale ASN New đang mở — kể
  cả đang trống hoặc đã chọn Buyer — phải reload chính frame `WFXSalesASN.aspx`
  rồi mới chọn Buyer để không dùng datasource PO stale.
  Các PO trước dùng
  `Add & Continue`; ở PO cuối phải giữ checkbox đang chọn và click đúng link
  `OK` bên trong cell action để WFX vừa add PO cuối vừa đóng popup. Không click
  theo tọa độ/viewport: Search, Add và action popup phải hoạt động khi WFX bị
  scroll hoặc Chrome không ở foreground. Nếu WFX tự đóng popup giữa hai PO,
  automation phải xác nhận các dòng vừa thêm trong Order Details, mở lại Add
  Order Details và tiếp tục đúng dòng kế, không thêm lại dòng đã có. Không click
  cell `td` bao ngoài, và không bấm `Add & Continue` trước `OK` vì thao tác đó
  xóa selection khiến WFX báo `Please select a record`. Sau click `OK`, popup
  có thể đóng/dispose frame ngay; không wait trên frame popup nữa mà resolve lại
  trang Sale ASN chính rồi điền 7 cột Order Details, map Style gần đúng để điền
  HS Code, rồi điền Shipping Info với Consignor Address `BILL-ADD - PSHK`,
  Factory theo FTY bằng lựa chọn gần đúng tốt nhất, không phân biệt hoa/thường,
  và bỏ qua mọi option Factory có dấu chấm ở cuối. Không tự điền Notify 1.
  Shipment Mode phải
  điền exact vào `#ddlShipmentMode` trước Port of Loading; Port of Loading phải
  thử điền cả `#Cell_AWBLoadingPort` và `#Cell_BLMotherLoadingPort`; chỉ cần một
  host tồn tại và nhận giá trị là thành công. Consignee Address và Ship To
  lấy option gần đúng tốt nhất duy nhất trong dropdown; không có hoặc đồng hạng
  thì bỏ qua có warning. Shipping Mode sinh Port of Loading/Delivery Terms:
  AIR → `HAN - Hanoi`/`FCA HANOI, VIET NAM`; SEA → `HPH - Haiphong`/
  `FOB HAIPHONG, VIETNAM`; COURIER → `HAN - Hanoi`/`EXW`. Field Shipping Info
  không có option tương ứng được bỏ qua có warning. Nếu Country Of Destination
  không khớp vì WFX dùng tên quốc gia đầy đủ, phải giữ nguyên Final Destination
  theo giá trị mặc định ban đầu; không được đổi riêng Final Destination. Luồng
  luôn dừng trước Save để user kiểm tra trên WFX.
  Sau bốn bước tạo, task cuối `Check giá / Qty` tự mở Shipment Details rồi map
  PO No.+Style No. theo PO tách từ Order No. dạng mã hệ thống/PO + Article, so
  sánh Shipping Qty và Price (USD) từng dòng. Đồng thời tổng Qty và Qty×Price
  file phải được so với Total Quantity, Value In Doc Currency và Net Value In
  Doc Currency ở Summary Total; có nút xuất workbook kết quả và không sửa dữ
  liệu WFX. Panel chỉ rộng 440px nên kết quả trong app phải rút gọn: một hàng
  chip `n khớp`/`n lệch`/`Summary ✓|✕`, chỉ dòng `status != "ok"` và các
  Summary lệch hiện sẵn dạng `File → WFX`, dòng khớp nằm trong `<details>`.
  Dòng không so được Qty/Price (`shipment_not_found`, `file_value_missing`,
  `system_value_missing`, `system_price_ambiguous`) chỉ hiện `message`, không in
  cặp giá trị rỗng. Workbook xuất vẫn giữ đầy đủ mọi dòng.
  Nhãn nút `Xuất Invoice + PKL` là cố định; Invoice No. hiện ở đầu thẻ kết quả,
  tuyệt đối không nhét vào nhãn nút vì `.special-primary-button` là
  `white-space: nowrap` nên số invoice dài sẽ tràn khỏi thẻ.
  Luồng Documents nhận Invoice No. đang nhập
  hoặc đúng một dòng đang chọn; xác nhận invoice độc lập với cột Docs rồi quét
  ngang AG Grid để tìm/click Docs theo metadata vì mỗi user có thể kéo cột tới
  vị trí khác nhau; tải lần lượt Packing
  List và Buyer Invoice bằng Report Viewer `EXCELOPENXML`, ghép thành một
  workbook giữ nguyên format report nguồn; nếu mỗi report có nhiều sheet thì xếp
  xen kẽ Invoice 1, PKL 1, Invoice 2, PKL 2 cho đến hết, Invoice luôn đứng trước
  PKL. Sau đó mới mở Save As với tên mặc định là Invoice No. thực tế và tự mở
  Explorer, chọn đúng file khi lưu thành công. Sau khi bấm Docs, luôn tự đóng mọi
  popup Docs/report được tạo từ lượt này, kể cả khi download/ghép gặp lỗi, nhưng
  giữ nguyên các Page đã có trước đó. Khi ghép, tăng chiều cao các hàng wrap text
  theo nội dung và độ rộng cột để không cắt dòng trong Excel; riêng No of Pcs,
  Net Wt, Gross Wt, No of Carton và CBM được nới đủ để thấy trọn header/số liệu.
  Mọi sheet đặt A4, giữ hướng dọc/ngang từ report WFX, fit vừa một trang theo
  chiều ngang và tự phân trang theo chiều dọc. Khi copy sheet giữa hai workbook,
  Với Packing List J.Lindeberg (nhận diện bằng header `JL PO#`), gộp dọc Net Wt,
  Gross Wt, No of Carton và CBM cho các dòng liền nhau có cùng JL PO# + Style No;
  chỉ gộp khi giá trị cột đó giống nhau để không làm mất số liệu.
  Với Packing List CORPORATE OFFICE - TRUEWERK, các cặp dòng liền nhau cùng Style
  và PO gốc/PO hậu tố `ADD` hoặc `- ADD` tự gộp dọc Net-Weight, Gross-Weight,
  Qty Cartons và CBM khi mỗi cột chỉ có một giá trị khác 0; app chuyển giá trị đó
  lên ô đầu vùng gộp dù nó nằm ở dòng PO hay dòng `ADD`. Qty/Unit vẫn giữ riêng.
  Nếu cùng một cột có hai số khác 0 hoặc hai dòng bị tách xa nhau thì giữ nguyên
  để không làm mất số liệu/đổi thứ tự Packing List.
  Nếu file đích cùng tên đang mở/khóa trong Excel, không báo lỗi hoặc bắt tải lại:
  tự lưu sibling kế tiếp theo dạng `Invoice (2).xlsx` và trả đúng tên đã lưu.
  phải tạo merged range trước rồi mới phục hồi style từng ô để không mất border/
  khung report do WFX xuất; style của row/column dimension phải được ánh xạ lại
  theo thuộc tính, không được mang nguyên style index từ workbook nguồn sang.
- `(GDN) Dispatch`: UI phải cảnh báo và bắt user xác nhận GRN nhập kho thành
  phẩm đã hoàn tất ít nhất 15 phút trước khi Submit. Flow nhận một Invoice GRN,
  mở report `BuyerDispatchOrder_Invoice`, điền `Doc No.`, chờ report load thật,
  export Excel Open XML rồi reload/save lại thành XLSX. Sau đó mở EDI Production
  Order, chọn `PackageType=Import` và package
  `DecisionOne_BuyerOrderDispatch`, upload và `Process Package`. Chỉ chọn dòng
  package MỚI của lượt chạy hiện tại có `Transaction Detail=Pending`; nếu dòng
  đầu đang `InProgress` phải bỏ qua và chọn Pending mới nhất theo `Processed ON`.
  `Create Transaction` là ranh giới không idempotent: sau khi click không tự
  retry, phải chờ WFX xác nhận thành công/lỗi; nếu mất xác nhận trả mã
  `GDN_TRANSACTION_UNCONFIRMED` và hướng dẫn kiểm tra WFX để tránh tạo trùng.
  Backend phải stream sáu bước `report`/`download`/`workbook`/`edi`/`package`/
  `transaction` tới UI. Lỗi từ bước Process Package trở đi là checkpoint cần
  kiểm tra EDI, không gợi ý Submit lại; thẻ tiến độ cung cấp hành động read-only
  mở đúng `DecisionOne_BuyerOrderDispatch` mà không tạo transaction.
- Supplier List: đổi Category, mở Master, tìm trong tất cả Category. Cả hai thao
  tác đều tự mở Supplier List khi WFX chưa mở, nên UI không được đánh số bước hay
  bắt người dùng bấm List trước; nút List chỉ là lối tắt và chỉ có một nút chính
  duy nhất trong màn.
- Trong cùng một màn module, không được có hai nút trùng nhãn. Riêng OC, hai nút
  chọn file phải ghi rõ `Chọn file OC mới` và `Chọn file Revise`: chúng đi vào
  hai tab EDI khác nhau và `Create Transaction` không idempotent, nên bấm nhầm
  là tạo sai chứng từ.
- Buyer List: tự mở đúng Buyer List khi cần rồi mở Edit đầu tiên.
- Company Setup: Đổi FOC tự mở đúng List nếu cần, mở Miscellaneous Settings rồi
  mới đổi/lưu nơi áp dụng FOC.
- Mọi flow `List` chỉ trả thành công sau khi WFX đổi page/frame/document thật;
  một cú click menu đơn thuần không được coi là `MODULE_OPENED`. Nếu link WFX
  có `target=body` nhưng click không navigation sau 5 giây, app được phép mở
  chính `href` đã đọc từ menu trong đúng frame `body`, chờ tối đa 12 giây rồi
  mới báo thành công/thất bại và phải log rõ đang ở bước fallback.
  Nếu một module đã phải dùng fallback này, app được cache route trong bộ nhớ
  của đúng phiên để lần sau bỏ qua 5 giây chờ click không phản hồi. Cache chỉ
  nhận URL cùng origin, tự xóa khi login/session/Division thay đổi và phải
  fallback về click bình thường ngay nếu route cache không còn hợp lệ.
- RMPO List: tìm kết hợp theo Supplier và RMPO No. trên đúng grid
  `gridRMPO`.
- Indent List/User Indent: tìm kết hợp theo Supplier, Article, Indent No. và
  Style trên đúng grid `gridMOLList`.
- QA List, Advance PR List và Expense Inv List: List + New; New click trực tiếp
  menu QA Inspection Request New, Advance Payment Request New hoặc Expense
  Invoice New và phải xác nhận navigation, không phụ thuộc màn List hiện tại.
  Advance PR hỗ trợ tìm kết hợp theo Buyer Name, Supplier, Invoice Number và
  Order No. trên `gridAdvancePaymentRequestList`.
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
- Mọi URL máy chủ do cấu hình cung cấp (`article_library`, `style_options`,
  `reference_sync`) phải qua kiểm tra scheme HTTPS + có hostname trước khi gọi
  `urlopen`. Read key và admin key nằm trong header nên một cấu hình nhầm
  `http://` đủ để đẩy chúng qua mạng dưới dạng rõ, còn `file://` biến chính hàm
  đọc JSON thành trình đọc file cục bộ.
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
- Không giả định Code/Buyer Reference/Article Name đang ở viewport đầu tiên:
  quét các vị trí scroll ngang của grid vì layout cột được lưu riêng theo user.
- Nếu Code Filter chưa visible, click `#showfloatingfilter` trong cùng grid frame.
- Sau click, resolve lại grid/frame vì Angular có thể thay document.
- Xác nhận `Code Filter Input` visible, enabled và thuộc grid mới.
- Không log thành công nếu `rawRows=0` mà cũng không có no-rows overlay.

### Lọc

- Xóa cả Code Filter và Buyer Reference Filter bằng thao tác tương đương
  Playwright `locator.fill("")`; phải quét ngang để xóa cả filter đang bị
  AG Grid virtualize ngoài viewport.
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

## Yêu cầu log automation Catalog

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

Hotkey toàn cục mặc định `Ctrl+Shift+X` do
`wfx_panel/hotkey.py` + thư viện `keyboard` bắt ở cấp hệ điều hành, nên nhận được
kể cả khi focus nằm trong iframe của WFX trên Chrome. Đổi được trong Settings. Giới
hạn: nếu cửa sổ đang focus chạy quyền Administrator cao hơn app thì global hook có
thể không nhận phím — khi đó dùng launcher/tray để mở panel.

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
8. `Ctrl+Shift+X` mở/đóng desktop panel ngay cả khi focus đang nằm trong iframe
   của WFX.
9. Sửa code trong `wfx_panel/` (nguồn) và build lại bằng `build-panel.ps1`; không
   chỉnh trực tiếp file trong `dist/`. `python -m pytest` và `ruff check .` phải xanh.
