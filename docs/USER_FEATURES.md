# Danh sách chức năng WFX Smart

Tài liệu này dành cho người dùng WFX Smart. Nội dung không yêu cầu kiến thức
lập trình.

## 1. Mở và điều khiển ứng dụng

- Launcher nổi 48×48 logical luôn sẵn sàng; app tự đổi sang 48/60/72/96 pixel
  vật lý ở Windows scale 100/125/150/200% để không cắt góc trên màn hình DPI cao.
- Click launcher để mở panel ngay bên cạnh.
- Kéo launcher đến vị trí thuận tiện; app nhớ vị trí cho lần mở sau.
- Chuột phải launcher để chọn **Ẩn xuống taskbar** hoặc **Thu vào system tray**;
  thoát hoàn toàn vẫn thực hiện từ menu icon trong system tray.
- System alert nghiệp vụ của WFX được giữ hiển thị trên Chrome để người dùng đọc
  và xác nhận, không còn bị automation chấp nhận ngay lập tức.
- Bubble có lớp bắt chuột phải Win32 dự phòng khi WebView nuốt sự kiện. Menu là
  tool-window riêng, không còn bị `TrackPopupMenu` đóng tức thì sai thread;
  spinner dùng chung tốc độ 1,25 giây/vòng giữa các thiết bị.
- Hotkey mặc định `Ctrl+Shift+X` để ẩn/hiện panel khi đang làm trên WFX.
- Tùy chọn `Luôn trên cùng` giữ panel phía trên các cửa sổ khác.
- Bản EXE mặc định khởi động cùng Windows. Có thể tắt `Khởi động cùng Windows`
  trong Settings; app sẽ nhớ lựa chọn này.
- Panel tự thu khi click ra ngoài. Nếu tác vụ đang chạy, panel chờ hoàn tất rồi
  mới thu.
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
- Hỗ trợ Chrome, Edge, Brave và Chromium.
- Hiển thị trạng thái browser và trạng thái phiên WFX ở cuối panel.

## 4. Division

- Chuyển nhanh giữa `WOVEN`, `KNIT` và `PSSG`.
- Bộ chọn Division được thu gọn để dành thêm không gian cho danh sách module.
- App đọc Division thật từ WFX và highlight lựa chọn hiện tại.
- Chỉ báo thành công sau khi WFX xác nhận đã chuyển Division.

## 5. Quy tắc sử dụng các workflow

Các nút `List`, `Search`, `New` và nút thao tác khác là các bước riêng:

1. Bấm `List` để mở màn danh sách.
2. Chờ List/Floating Filter tải xong.
3. Nhập nội dung rồi bấm `Tìm`, hoặc chạy bước tiếp theo.

Search không tải lại List. Nếu người dùng chưa mở đúng List, app sẽ nhắc bấm
List trước và không gửi đây là lỗi hệ thống.
Khi bấm thao tác, nút vừa chọn được đánh dấu và automation bắt đầu ngay trong
lúc Chrome được đưa lên trước, giúp giảm cảm giác chờ giữa các bước.

## 6. Catalog

- Chọn Category Catalog.
- Chọn vị trí mặc định trong cây Group/Folder của Apparel.
- Cache cây folder theo tài khoản để không phải scan lại mỗi lần mở app.
- Mở Master hoặc folder đã chọn.
- Tìm theo:
  - Style Code.
  - Buyer Reference.
- Khi chỉ có một Style Code, app tự mở Article.
- Khi có nhiều kết quả, app giữ danh sách để người dùng chọn.
- Hiển thị Season và Internal CostSheet Status khi đọc được từ grid.
- Mở Costing.
- Mở BOM.
- Xem và tải file đính kèm theo các nhóm Images/Documents.

## 7. OC List

- `List`: mở OC List hiện tại.
- `Search OC`: tìm trực tiếp trên List đã mở theo:
  - OC No.
  - Style.
- App chỉ áp dụng filter trên WFX, không sao chép danh sách kết quả về panel.

## 8. Sample List

- `List`: mở Sample List và bật Floating Filter.
- `Search Sample`: tìm trên List đã mở theo:
  - Sample Order No.
  - Style.
  - Created By.
- `New`: mở New Sample Order.

## 9. Sale ASN

- `List`: mở Sale ASN List và bật Floating Filter.
- `Search`: tìm trên List đã mở theo:
  - Invoice No.
  - Style.
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
- Tìm theo tên hoặc một phần tên công ty trên đúng Buyer List đang mở.
- Mở Edit của Buyer đầu tiên phù hợp.
- Không dùng nhầm Supplier List dù hai màn cùng có ô Company Name.

## 12. Company Setup

- Mở Company Setup bằng nút `List`.
- Đổi nơi áp dụng FOC giữa ASN và GRN.
- Bấm Save và chỉ báo thành công sau khi WFX xác nhận trạng thái đã lưu.

## 13. Module khác

Nhóm Operation:

- RMPO List: mở List và lọc đồng thời theo Supplier, RMPO No. hoặc cả hai.
- Indent List: mở List và lọc đồng thời theo Supplier, Article, Indent No.,
  Style; có thể nhập một hoặc nhiều điều kiện.
- User Indent: có cùng bộ lọc kết hợp như Indent List.
- QA List: mở List hoặc bấm `New` để tạo QA Request trên đúng màn đang mở.

Nhóm Finance:

- Advance PR List: mở List hoặc bấm `New` để tạo Advance Payment Request.
- Supplier Inv List.
- Expense Inv List: mở List hoặc bấm `New` để tạo Expense Invoice.

Với RMPO và hai màn Indent, bấm `List` trước. Nút `Tìm` chỉ điền các ô search
trên màn hiện tại, không mở lại menu. Các ô không nhập được xóa để kết quả phản
ánh đúng tổ hợp điều kiện đang thấy trên panel.

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
- Các lỗi thao tác như chưa bấm List, thiếu nội dung tìm hoặc không có kết quả
  không được gửi thành lỗi hệ thống.

## 16. Cập nhật ứng dụng

- Tự kiểm tra GitHub Release Stable định kỳ.
- Nút `Cập nhật ngay` tải và cài bản mới.
- Xác minh chữ ký certificate và SHA-256 trước khi thay file.
- Tự rollback nếu cập nhật thất bại.
- Giữ nguyên tài khoản và Settings khi build, update hoặc rollback.

## 17. Giới hạn cần biết

- WFX Smart cần một Chromium browser tương thích trên máy.
- Global hotkey có thể không nhận nếu cửa sổ đang focus chạy quyền Administrator
  cao hơn WFX Smart; khi đó dùng launcher hoặc tray.
- Automation phụ thuộc cấu trúc giao diện và quyền tài khoản WFX. Nếu WFX thay
  markup hoặc quyền, người dùng có thể cần mở Log kỹ thuật và gửi Run ID.
- Bản đóng gói là `onedir`; không được tách riêng EXE khỏi thư mục `_internal`.
