# Danh sách chức năng WFX Smart

Tài liệu này dành cho người dùng WFX Smart. Nội dung không yêu cầu kiến thức
lập trình.

## 1. Mở và điều khiển ứng dụng

- Launcher nổi 48×48 logical luôn sẵn sàng; app tự đổi sang 48/60/72/96 pixel
  vật lý ở Windows scale 100/125/150/200% để không cắt góc trên màn hình DPI cao.
- Click launcher để mở panel ngay bên cạnh.
- Kéo launcher đến vị trí thuận tiện; app nhớ vị trí cho lần mở sau.
- Chuột phải launcher để chọn **Ẩn xuống taskbar** hoặc **Thu vào system tray**;
  click ra ngoài hoặc nhấn `Esc` để đóng menu; thoát hoàn toàn vẫn thực hiện từ
  menu icon trong system tray.
- System alert nghiệp vụ của WFX được giữ hiển thị trên Chrome để người dùng đọc
  và xác nhận, không còn bị automation chấp nhận ngay lập tức.
- Bubble có lớp bắt chuột phải Win32 dự phòng khi WebView nuốt sự kiện. Menu là
  tool-window riêng, không còn bị `TrackPopupMenu` đóng tức thì sai thread;
  spinner dùng chung tốc độ 1,25 giây/vòng giữa các thiết bị.
- Hotkey mặc định `Ctrl+Shift+X` để ẩn/hiện panel khi đang làm trên WFX.
- Tùy chọn `Luôn trên cùng` giữ panel phía trên các cửa sổ khác.
- Bản EXE mặc định khởi động cùng Windows. Có thể tắt `Khởi động cùng Windows`
  trong Settings; app sẽ nhớ lựa chọn này.
- Panel tự thu khi click ra ngoài, kể cả khi WebView bỏ lỡ sự kiện mất focus.
  Nếu tác vụ đang chạy, panel chờ hoàn tất rồi mới thu; nếu chuột vẫn nằm trên
  UI thì panel tiếp tục hiện dù automation vừa chuyển foreground sang Chrome.
- Chuyển giữa danh sách/module và thanh tiến trình có chuyển động ngắn để dễ
  theo dõi; app tự hạn chế animation khi Windows bật chế độ giảm chuyển động.

## 2. Cá nhân hóa danh sách module

- Tìm nhanh module bằng ô Search.
- Bấm ngôi sao ở cuối module để thêm/bỏ khỏi `Yêu thích`.
- Module yêu thích được ghim ở đầu panel, trước ô Search.
- Khu vực Yêu thích không có thanh cuộn riêng.
- Module đã ghim không lặp lại trong nhóm module bên dưới; favorite cuối cùng ở
  hàng lẻ được mở rộng để không để khoảng trống.
- App mặc định nhớ đúng màn module và nội dung người dùng đang làm.
- Bật `Trở về List sau khi thao tác` nếu muốn tự quay về danh sách module sau
  mỗi tác vụ.

## 3. Tài khoản và trình duyệt WFX

- Lưu User ID/password trong tab Tài khoản.
- Khi phiên WFX đã kết nối, tab Tài khoản chỉ hiện User ID và nút `Đổi tài
  khoản`; form mật khẩu chỉ xuất hiện khi đổi tài khoản hoặc cần đăng nhập lại.
- Password được Windows DPAPI mã hóa trên chính máy đang sử dụng.
- Nút `Mở trình duyệt` mở Chromium browser automation và đăng nhập WFX bằng tài
  khoản đã lưu.
- Sau lần đăng nhập thành công, app duy trì phiên nền định kỳ. Nếu WFX tự logout
  do để lâu, app tự login lại bằng tài khoản đã lưu; một thao tác gặp phiên hết
  hạn cũng được login lại và chạy lại đúng một lần.
- Hỗ trợ Chrome, Edge, Brave và Chromium.
- Hiển thị trạng thái browser và trạng thái phiên WFX ở cuối panel.

## 4. Division

- Chuyển nhanh giữa `WOVEN`, `KNIT` và `PSSG`.
- Bộ chọn Division được thu gọn để dành thêm không gian cho danh sách module.
- App đọc Division thật từ WFX và highlight lựa chọn hiện tại.
- Chỉ báo thành công sau khi WFX xác nhận đã chuyển Division.

## 5. Quy tắc sử dụng các workflow

Các nút `List`, `Search`, `New` và nút thao tác khác là các flow riêng. App chỉ
báo `Đã mở` sau khi WFX thật sự đổi màn hình:

1. Bấm `List` để chủ động mở màn danh sách.
2. Hoặc nhập nội dung và bấm `Tìm` ngay; app tự mở đúng List, chờ
   List/Floating Filter tải xong rồi áp dụng search.
3. Với `New`, mở List trước để xác nhận đúng màn. Riêng `Đổi FOC` có thể bấm
   trực tiếp; app sẽ tự mở Company Setup nếu cần.

Nếu đúng List đã mở, Search dùng lại màn hiện tại để nhanh hơn. Nếu đang ở màn
khác, app tự điều hướng; không báo lỗi yêu cầu người dùng bấm List.
Khi bấm thao tác, nút vừa chọn được đánh dấu và automation bắt đầu ngay trong
lúc Chrome được đưa lên trước, giúp giảm cảm giác chờ giữa các bước.

## 6. Catalog

- Chọn Category Catalog.
- Chọn vị trí mặc định trong cây Group/Folder của Apparel.
- Cache cây folder theo tài khoản để không phải scan lại mỗi lần mở app.
- Bấm **Mở Catalog** để mở Master hoặc folder đã chọn. Vị trí mặc định được
  chỉnh bằng nút bút nhỏ ngay bên cạnh.
- Nếu trang trung gian của menu phản hồi chậm, app tự mở Catalog đích; frame cây
  được nhận diện theo ô Category nên vẫn hoạt động khi WFX đổi tên frame.
- Tìm theo:
  - Style Code.
  - Buyer Reference.
- Có thể nhập rồi bấm Tìm/Costing/BOM ngay; app tự mở Catalog > Category >
  Master nếu cần. Nút mở List/Master chỉ dùng khi muốn xem trước màn hình.
- Khi chỉ có một Style Code, app tự mở Article.
- Trước khi mở Costing, BOM hoặc File, app tự đồng bộ lại popup Article để
  không dùng nhầm frame cũ khi WFX reload cùng một style. Nếu driver hiện tại
  chưa nhìn thấy popup mới, app kết nối lại sớm một lần và tiếp tục ngay tại
  Article, không quay lại Master để tìm Style lần hai.
- Khi có nhiều kết quả, app giữ danh sách để người dùng chọn.
- Hiển thị Season và Internal CostSheet Status khi đọc được từ grid.
- Mở Costing.
- Trong Category Apparel, khu vực **Costing file** cho phép:
  - làm việc ở màn Costing riêng; khi mở Costing hoặc chọn file Import, panel
    tự chuyển sang màn này thay vì bắt cuộn qua phần tìm Catalog;
  - quét nhanh và hiển thị Style Code/status của đúng tab Costing hiện tại
    trước khi mở hộp thoại lưu;
  - tải Costing đang mở thành Excel `.xlsx`;
  - đặt tên file theo Style Name, nhớ thư mục gần nhất và có setting riêng để
    mở file/mở thư mục sau khi tải;
  - dùng nút **Kiểm tra file** để xem lỗi kèm sheet/ô trước khi tạo dry-run;
  - nhập trực tiếp vào form cột chuẩn trên sheet `Costing` rồi import lại;
  - Article Code/Article Name dùng thư viện CSV bốn cột tự tải từ server mỗi
    giờ, không quét hàng trăm trang và không yêu cầu user cập nhật file. Fabric
    chỉ hiện mã F, Trim chỉ hiện mã T; khi chọn Code trong Excel, Article Name
    tự lookup đúng nhưng vẫn có thể ghi đè thủ công. Khi chọn Article Name, app
    đồng bộ ngược Article Code lúc kiểm tra/import nếu tên chỉ có một mã; tên
    trùng nhiều mã sẽ yêu cầu chọn Code. Khi offline app dùng cache gần nhất;
    khi chưa có cache vẫn cho nhập tay;
  - scan Material Color/Size theo từng Article, mapping Table hiện tại và danh
    sách Style Color/Size; Material Color/Size có dropdown riêng theo item;
  - nếu Material Color/Size trong file chưa có ở Article card, app tự tìm và
    thêm đúng Color/Size trong lúc Apply, giữ nguyên card/mapping hiện có; Size
    có thể tìm lại trong card Sample trước khi Save;
  - phối trực tiếp trong `Color Mapping`/`Size Mapping` theo từng dòng
    `Material => Style 1 | Style 2`, rồi app tick exact trong popup Table;
  - lấy Style Name chuẩn từ phần sau dấu `/` của `#lblArticleNameValue`;
- Catalog lọc thư viện theo Category và đưa tối đa 20 gợi ý: Article Code tìm
  theo code; Apparel có Buyer Reference; các Category còn lại dùng Article
  Name. Kết quả cuối vẫn được xác nhận trong Category đang chọn.
  - hiển thị hai cột công thức màu đỏ chỉ đọc `Cons. Qty. Incl. Waste` và
    `Value in (USD)`; hai cột này không được import ngược;
  - có 1 dòng CM, 1 dòng Production và 2 dòng Indirect Costs; danh sách nhà
    máy/quy trình/chi phí được quét từ WFX rồi dùng lại 7 ngày theo tài khoản và
    Division. Công tắc quét lại cạnh Thư viện Article mặc định tắt, chỉ áp dụng
    cho lần Costing kế tiếp và tự tắt sau khi scan thành công; dòng chưa chọn tên
    được bỏ qua;
  - với Production, điền Minutes ở hai dòng trước, Value tổng trước Rate;
  - xem trước số ô cập nhật, Article thêm/xóa và cảnh báo trước
    khi WFX bị thay đổi;
  - export Costing ở mọi status; chỉ import/apply khi CostSheet đang `Open`;
    nếu chưa có Costing, người dùng tự tạo trong WFX trước;
  - tự đặt mọi field Minutes thành `1`, Save một lần và đọc lại để xác nhận.
  - nút **Clear All Dependency** dưới Import hỏi xác nhận, bấm mọi nút Clear
    Dependency của Costing `Open` đang chọn rồi Save một lần.
- Export và Import luôn chỉ dùng tab Costing đang hiển thị, kể cả khi có nhiều
  tab Costing, không phụ thuộc ô Style Code và không bắt người dùng tìm lại
  style. Apply tiếp tục khóa vào đúng
  tab/style đã dry-run, không tự chuyển tab hoặc reload màn hình. Workbook có
  đúng hai sheet `Hướng dẫn` và `Costing`, không có sheet `Cost Sheet`. Form
  chuẩn chỉ hiển thị hai cột công thức cần thiết dưới dạng cột đỏ, giữ sáu
  section nguyên vật liệu/trims và thêm CM/Production/Indirect Costs ở cuối.
- Action để trống nghĩa là thêm/cập nhật. Ô trống nghĩa là giữ nguyên; nhập
  `__CLEAR__` để chủ động xóa giá trị. Chỉ dòng có Action `DELETE` mới được xóa
  Article và app luôn yêu cầu chọn đúng item trước khi xóa.
- Khi Material Search không có Article, app bỏ qua và báo lại. Nếu có nhiều kết
  quả, app dừng để người dùng chọn, không tự lấy dòng đầu tiên.
- Có thể tải một style đã có Costing, sửa file rồi import lại để làm nhanh cho
  cùng style. Style Code trong file phải khớp style đang mở.
- Nếu cùng một Article Code xuất hiện trên nhiều dòng Costing, file Excel giữ
  nguyên từng dòng riêng để Material Color và các thông số không bị gộp nhầm.
  Nếu file thêm các dòng cùng Article liền nhau, app tự dùng nút Splitter để tạo
  đủ dòng `>>`. Dòng subtotal/total có nhãn `>>` ẩn không được tính là split.
- Dry-run chặn sớm nếu dòng bắt buộc còn thiếu `Purchase Officer`, tránh điền
  xong nhiều field rồi mới bị WFX từ chối ở bước Save.
- Mở BOM.
- Xem và tải file đính kèm theo các nhóm Images/Documents.

## 7. OC List

- `List`: mở OC List hiện tại.
- `Search OC`: tự mở List nếu cần rồi tìm theo:
  - OC No.
  - Style.
- App chỉ áp dụng filter trên WFX, không sao chép danh sách kết quả về panel.
- `Tải form mới`: tạo file `.xlsx` có một sheet nhập liệu tên `OC INPUT` và chỉ
  một hàng header. Các cột bắt buộc được tô vàng, `Buyer Lot No.` là cột tuỳ
  chọn; dropdown Buyer/Factory/Country/... nằm ngay trong form. Buyer/Factory
  là danh sách gợi ý và vẫn cho nhập master data mới đang có trên WFX; Country
  phải chọn giá trị đã có mapping Market. Sheet danh mục kỹ thuật được ẩn để
  người dùng không phải sửa hoặc sao chép công thức.
- `Upload OC New`: người dùng điền dữ liệu dưới header của `OC INPUT`, chọn lại
  file trong app. App kiểm tra kiểu dữ liệu, trường bắt buộc, Buyer, ngày, số
  lượng, giá, dòng trùng và tự tính `Total Qty`; sau đó hiện review gồm Buyer,
  Season, số PO, số Style/Article, Sum of Units và số dòng. Chỉ khi người dùng
  bấm `Xác nhận Upload`, app mới đưa `Sheet1` 51 cột chỉ chứa giá trị vào
  `EDI Buyer PO` với package `StandardSalesOrder`.
- Trong workspace OC, `OC List` và Search nằm cùng một card gọn: chọn OC No./
  Style, nhập nội dung và bấm Tìm trên một hàng. Upload New và Revise nằm ở hai
  card cân bằng, chữ và số liệu review đủ lớn để đọc nhanh.
- Sau khi Huỷ review, nếu người dùng sửa rồi chọn lại đúng file cũ, app luôn đọc
  lại nội dung hiện tại trên ổ đĩa; kết quả review cũ không được tái sử dụng hoặc
  hiển thị đè lên lần chọn mới.
- App chỉ bấm `Create Transaction` khi cả ba trạng thái `Data Imported`, `Data
  Validated` và `Mapping Resolved` đều thành công. Nếu WFX báo fail, app giữ
  thông tin dòng lỗi để người dùng sửa file. Nếu đã bấm Create Transaction
  nhưng chưa đọc được xác nhận, app không tự retry để tránh tạo OC trùng.
- Nếu bất kỳ bước EDI nào hiện `InProgress`/`In Progress` hoặc Fail, app coi là
  lỗi ngay, không tiếp tục chờ và không Create Transaction. App click trạng thái,
  đọc popup `Failed Record`, hiện Mapping Code/Doc No./Mapping Details cho người
  dùng và lưu ảnh popup trong Lịch sử tác vụ.
- File `UPLOAD FORM.xlsx` cũ vẫn được hỗ trợ để chuyển đổi trong giai đoạn thay
  form; người dùng mới nên dùng form một-header tải trực tiếp từ app.
- Form một-header có dropdown Order Type gồm Confirmed/Forecast/SMS và danh sách
  Payment Terms chuẩn. Khi chuẩn hoá, app bỏ qua dòng Units bằng 0, mặc định
  Zone trống thành FOB và Extra Production trống thành 0. App chặn upload nếu
  ngày không theo `Buyer Order Date < Raw Material ETA < Buyer Delivery Date`;
  trong Sheet1, Buyer Delivery Date phải bằng OC Delivery Date.
- `Revise OC`:
  1. `Mở report` đưa Chrome tới `Reporting & Analytic` và mở đúng
     `Upload OC from OC_Sale`.
  2. Người dùng chọn điều kiện và xuất Excel trên WFX, sửa các cột cho phép.
  3. Chọn file đã sửa tại app; app kiểm tra schema 51 cột, dữ liệu OC gốc và
     tính lại `Total Qty`, hiện review để xác nhận, rồi chạy cùng kiểm tra EDI
     và tạo transaction vào tab `Revision`.
- Mỗi file chỉ được chứa một Buyer để app chọn đúng Buyer tại EDI Buyer PO.

## 8. Sample List

- `List`: mở Sample List và bật Floating Filter.
- `Search Sample`: tự mở List nếu cần rồi tìm theo:
  - Sample Order No.
  - Style.
  - Created By.
- `Check File`: tìm theo đúng điều kiện đang chọn. Một kết quả sẽ tự mở Style
  Code và liệt kê file đính kèm; nhiều kết quả sẽ cho chọn Sample cần dùng rồi
  tiếp tục. Bấm vào tên file trong danh sách để tải ngay.
- `New`: mở New Sample Order.

## 9. Sale ASN

- `List`: mở Sale ASN List và bật Floating Filter.
- `Search`: tự mở List nếu cần rồi tìm theo:
  - Invoice No.
  - Buyer Order Ref/OC No.
- `New`: mở Sale ASN mới với `With GDN` và `Buyer Order Dispatch`.

## 10. Supplier List

- Mở Supplier List.
- Chọn Category và mở Master.
- Tìm Supplier trong tất cả Category:
  - Apparel.
  - Fixed Asset.
  - Miscellaneous.
  - Services.
  - Textiles/Fabric.
  - Trims.
- App báo Category nào có Supplier phù hợp.
- Nếu một Category tạm thời lỗi, app tiếp tục tìm các Category còn lại và báo
  rõ phần chưa kiểm tra được.

## 11. Buyer List

- Mở Buyers List.
- Tự mở Buyer List nếu cần rồi tìm theo tên hoặc một phần tên công ty.
- Mở Edit của Buyer đầu tiên phù hợp.
- Không dùng nhầm Supplier List dù hai màn cùng có ô Company Name.

## 12. Company Setup

- Mở Company Setup bằng nút `List`.
- Đổi nơi áp dụng FOC giữa ASN và GRN; nút này tự mở lại đúng Company Setup và
  `12. Miscellaneous Settings` nếu người dùng vừa làm ở module khác.
- Bấm Save và chỉ báo thành công sau khi WFX xác nhận trạng thái đã lưu.

## 13. Module khác

Nhóm Operation:

- RMPO List: mở List và lọc đồng thời theo Supplier, RMPO No. hoặc cả hai.
- Indent List: mở List và lọc đồng thời theo Supplier, Article, Indent No.,
  Style; có thể nhập một hoặc nhiều điều kiện.
- User Indent: có cùng bộ lọc kết hợp như Indent List.
- QA List: mở List hoặc bấm `New` để vào thẳng QA Request New, không cần mở
  List trước.

Nhóm Finance:

- Advance PR List: mở List hoặc bấm `New` để vào thẳng Advance Payment Request
  New, không cần mở List trước.
- Supplier Inv List.
- Expense Inv List: mở List hoặc bấm `New` để vào thẳng Expense Invoice New,
  không cần mở List trước.

Với RMPO và hai màn Indent, có thể bấm `Tìm` ngay. App tự mở đúng List nếu cần
và phân biệt `Indent List` với `User Indent` bằng context trang, dù hai màn dùng
chung selector. Các ô không nhập được xóa để kết quả phản ánh đúng tổ hợp điều
kiện đang thấy trên panel.

Nhóm Admin hiển thị theo quyền của tài khoản:

- Org Structure.
- System Coding.
- Company Setup.
- Buyer List.
- Supplier List.

## 14. Trạng thái, lịch sử và log

- Thanh trạng thái dưới cùng hiển thị tác vụ đang chạy và kết quả cuối.
- Không lặp lại status bên trong màn module.
- Mỗi automation có Run ID và thời gian chạy.
- Lịch sử tác vụ tự xóa sau 7 ngày.
- Tác vụ phù hợp có nút chạy lại.
- Lỗi automation có thể lưu ảnh chụp cục bộ để kiểm tra.
- `Log kỹ thuật` cho phép bôi đen và copy.
- Khi người dùng đang chọn nội dung log, log mới không ép cuộn xuống cuối.
- Khi tác vụ đang chạy, nút `Stop` xuất hiện ngay trên dòng trạng thái cuối
  panel. App sẽ dừng ở bước kiểm tra an toàn kế tiếp; nếu WFX đang Save, app chờ
  Save được xác nhận rồi mới kết thúc flow.
- App dùng chung một kết nối Playwright/Chrome giữa các thao tác và giới hạn số
  tiến trình renderer để chạy ổn hơn trên máy RAM 8 GB. Nếu không có thao tác
  trong 1 phút, app tự nhả driver nền nhưng vẫn giữ Chrome và phiên đăng nhập.

## 15. Góp ý và báo lỗi

- Gửi báo lỗi hoặc góp ý tính năng từ panel.
- Nút gửi chỉ bật khi mô tả có ít nhất 5 ký tự; bộ đếm hiển thị giới hạn 2.000
  ký tự.
- Báo lỗi automation gửi:
  - Tên tác vụ dễ hiểu.
  - Mô tả lỗi.
  - Hướng xử lý.
  - Mã kỹ thuật và Run ID.
  - User ID, Company và Division để hỗ trợ.
- Nếu WFX lỗi trước khi automation tạo được message, app vẫn ghi rõ module,
  trường tìm hoặc Division đích dựa trên metadata không nhạy cảm.
- Báo cáo nền dùng đúng endpoint tại thời điểm lỗi xảy ra; dữ liệu test khi
  reporting bị tắt không thể bị gửi trễ lên webhook thật.
- Không gửi password, cookie, SessionID, LoginID, URL WFX đầy đủ hoặc nội dung
  tìm kiếm.
- Search tự mở đúng List và Floating Filter khi cần; người dùng có thể nhập điều
  kiện rồi bấm Tìm ngay, không cần bấm List trước.
- Các lỗi nhập liệu như thiếu nội dung tìm hoặc không có kết quả không được gửi
  thành lỗi hệ thống.

## 16. Cập nhật ứng dụng

- Bản cài `Setup.exe` được khuyên dùng: chỉ cần mở file để cài trực tiếp vào
  Windows, không cần quyền Administrator; shortcut Desktop được tạo mặc định,
  đồng thời có Start Menu và Uninstall.
- Khi chạy Setup phiên bản mới, bộ cài tự đóng đúng WFX Smart đang dùng file và
  nâng cấp tại chỗ. Tài khoản, Settings và dữ liệu làm việc vẫn được giữ nguyên.
- Bản portable `.zip` vẫn được phát hành cho người không muốn cài; phải giải nén
  và giữ `WFX-Panel.exe` cạnh thư mục `_internal`.
- Tự kiểm tra GitHub Release Stable định kỳ.
- Nút `Cập nhật ngay` tải và cài bản mới.
- Xác minh chữ ký certificate và SHA-256 trước khi thay file.
- Tự rollback nếu cập nhật thất bại.
- Nếu WebView2 làm app đóng chậm, updater xác minh đúng PID và đường dẫn bản
  đang cài rồi mới hoàn tất việc đóng; không tắt các bản WFX Smart khác theo tên.
- Giữ nguyên tài khoản và Settings khi build, update hoặc rollback.

## 17. Giới hạn cần biết

- WFX Smart cần một Chromium browser tương thích trên máy.
- Global hotkey có thể không nhận nếu cửa sổ đang focus chạy quyền Administrator
  cao hơn WFX Smart; khi đó dùng launcher hoặc tray.
- Automation phụ thuộc cấu trúc giao diện và quyền tài khoản WFX. Nếu WFX thay
  markup hoặc quyền, người dùng có thể cần mở Log kỹ thuật và gửi Run ID.
- Bản đóng gói là `onedir`; không được tách riêng EXE khỏi thư mục `_internal`.
