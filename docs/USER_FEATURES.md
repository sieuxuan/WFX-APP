# Danh sách chức năng WFX Smart

Tài liệu này dành cho người dùng WFX Smart. Nội dung không yêu cầu kiến thức
lập trình.

## 1. Mở và điều khiển ứng dụng

- Launcher nổi 48×48 luôn sẵn sàng trên màn hình.
- Click launcher để mở panel ngay bên cạnh.
- Kéo launcher đến vị trí thuận tiện; app nhớ vị trí cho lần mở sau.
- Chuột phải launcher để ẩn xuống system tray.
- Hotkey mặc định `Ctrl+Shift+X` để ẩn/hiện panel khi đang làm trên WFX.
- Tùy chọn `Luôn trên cùng` giữ panel phía trên các cửa sổ khác.
- Panel tự thu khi click ra ngoài. Nếu tác vụ đang chạy, panel chờ hoàn tất rồi
  mới thu.

## 2. Cá nhân hóa danh sách module

- Tìm nhanh module bằng ô Search.
- Bấm ngôi sao ở cuối module để thêm/bỏ khỏi `Yêu thích`.
- Module yêu thích được ghim ở đầu panel, trước ô Search.
- Khu vực Yêu thích không có thanh cuộn riêng.
- App mặc định nhớ đúng màn module và nội dung người dùng đang làm.
- Bật `Trở về List sau khi thao tác` nếu muốn tự quay về danh sách module sau
  mỗi tác vụ.

## 3. Tài khoản và trình duyệt WFX

- Lưu User ID/password trong tab Tài khoản.
- Password được Windows DPAPI mã hóa trên chính máy đang sử dụng.
- Nút `Mở trình duyệt` mở Chromium browser automation và đăng nhập WFX bằng tài
  khoản đã lưu.
- Hỗ trợ Chrome, Edge, Brave và Chromium.
- Hiển thị trạng thái browser và trạng thái phiên WFX ở cuối panel.

## 4. Division

- Chuyển nhanh giữa `WOVEN`, `KNIT` và `PSSG`.
- App đọc Division thật từ WFX và highlight lựa chọn hiện tại.
- Chỉ báo thành công sau khi WFX xác nhận đã chuyển Division.

## 5. Quy tắc sử dụng các workflow

Các nút `List`, `Search`, `New` và nút thao tác khác là các bước riêng:

1. Bấm `List` để mở màn danh sách.
2. Chờ List/Floating Filter tải xong.
3. Nhập nội dung rồi bấm `Tìm`, hoặc chạy bước tiếp theo.

Search không tải lại List. Nếu người dùng chưa mở đúng List, app sẽ nhắc bấm
List trước và không gửi đây là lỗi hệ thống.

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

- RMPO List.
- Indent List.
- User Indent.
- QA List.

Nhóm Finance:

- Advance PR List.
- Supplier Inv List.
- Expense Inv List.

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

## 15. Góp ý và báo lỗi

- Gửi báo lỗi hoặc góp ý tính năng từ panel.
- Báo lỗi automation gửi:
  - Tên tác vụ dễ hiểu.
  - Mô tả lỗi.
  - Hướng xử lý.
  - Mã kỹ thuật và Run ID.
  - User ID, Company và Division để hỗ trợ.
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
