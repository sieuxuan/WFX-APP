## Dùng để làm gì

Tải Packing List và Buyer Invoice của một Sale ASN rồi ghép thành một file
Excel để gửi hoặc lưu trữ.

## Các bước

1. Mở module Sale ASN.
2. Chọn Invoice No. và nhập số Invoice.
3. Bấm `Tải Packing List + Buyer Invoice`.
4. Chờ ứng dụng mở đúng dòng Sale ASN và tải hai báo cáo.
5. Chọn nơi lưu file Excel.
6. Chờ thư mục chứa file tự mở. Các cửa sổ Docs/report do lượt tải vừa mở sẽ tự đóng.
7. Mở file và kiểm tra hai sheet Packing List và Buyer Invoice.

## Mẹo

> [!meo]
> Tên file mặc định là Invoice No. thực tế đọc được trên WFX.

> [!meo]
> Hai sheet giữ nguyên cách trình bày của báo cáo nguồn.

> [!meo]
> Ứng dụng tải trực tiếp đúng file Excel từ Report Viewer bằng phiên WFX đang
> đăng nhập và kiểm tra nội dung từng file trước khi ghép. Vì vậy Packing List
> không thể bị dùng nhầm làm Buyer Invoice và không tạo hai file PKL thừa trong
> thư mục Downloads.

> [!meo]
> Nếu WFX chưa trả file Excel ở lần tải đầu, ứng dụng tự chờ rồi tải lại từ cùng
> báo cáo trong giới hạn ba phút. Bạn không cần bấm nút xuất lần thứ hai.

> [!meo]
> Khi ghép, ứng dụng tăng chiều cao của các hàng có nội dung wrap để tránh bị
> cắt chữ khi mở file trong Excel.

> [!meo]
> Các cột `No of Pcs`, `Net Wt`, `Gross Wt`, `No of Carton` và `CBM` tự được nới
> đủ để thấy hết header và số liệu. Khổ in A4 cùng hướng dọc/ngang của report vẫn
> được giữ nguyên.

> [!meo]
> Mọi sheet đã ghép dùng khổ A4, giữ đúng hướng dọc/ngang từ report WFX và vừa
> một trang theo chiều ngang khi in.

> [!meo]
> Với Packing List J.Lindeberg có header `JL PO#`, các dòng liền nhau cùng PO và
> Style sẽ tự gộp dọc Net Wt, Gross Wt, No of Carton và CBM khi số liệu giống nhau.

> [!meo]
> Với Packing List CORPORATE OFFICE - TRUEWERK, cặp dòng liền nhau cùng Style có
> PO gốc và PO hậu tố `ADD` hoặc `- ADD` tự gộp dọc Net-Weight, Gross-Weight,
> Qty Cartons và CBM khi mỗi cột chỉ có một giá trị khác 0. Giá trị đó tự được đưa
> lên ô đầu vùng gộp, dù đang nằm ở dòng PO hay `ADD`; Qty/Unit được giữ riêng.
> Nếu cùng một cột có hai số khác 0 hoặc hai dòng không liền nhau, app giữ nguyên
> để không làm mất số liệu hay đổi thứ tự Packing List.

> [!meo]
> Nếu file cùng tên đang mở trong Excel, ứng dụng tự lưu thành tên kế tiếp như
> `INV-001 (2).xlsx`, không cần tải lại report.

> [!meo]
> Bạn có thể kéo cột Docs tới vị trí bất kỳ; ứng dụng sẽ tự quét ngang bảng để
> tìm cột, không yêu cầu đưa Docs về vị trí mặc định.

> [!meo]
> Nếu ô tìm kiếm để trống, hãy chọn đúng một dòng trên WFX. Ứng dụng đọc
> Invoice No. từ chính dòng đã chọn, kể cả khi cột này đang nằm ngoài màn hình.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Không tìm thấy Invoice No. | Kiểm tra số Invoice, xóa bộ lọc cũ trên WFX rồi thử lại. |
| Có nhiều dòng phù hợp | Chọn đúng một dòng trên WFX rồi bấm tải lại. |
| Đã tìm thấy Invoice nhưng không có nút Docs | Kiểm tra dòng đã chọn, trạng thái Sale ASN và quyền Documents của tài khoản trên WFX. |
| Một báo cáo chưa sẵn sàng | Chờ WFX tạo báo cáo xong rồi tải lại. |
| Không ghép hoặc lưu được file | Chọn một thư mục bạn có quyền ghi và bảo đảm file cũ không đang mở trong Excel. |
| Lượt tải bị lỗi nhưng còn popup Docs/report | App tự đóng các popup được mở từ lượt bấm Docs đó; các tab WFX đã mở sẵn vẫn được giữ. |
