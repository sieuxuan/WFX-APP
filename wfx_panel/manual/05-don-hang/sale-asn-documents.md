## Dùng để làm gì

Tải Packing List và Buyer Invoice của một Sale ASN rồi ghép thành một file
Excel để gửi hoặc lưu trữ.

## Các bước

1. Mở module Sale ASN.
2. Chọn Invoice No. và nhập số Invoice.
3. Bấm `Tải Packing List + Buyer Invoice`.
4. Chờ ứng dụng mở đúng dòng Sale ASN và tải hai báo cáo.
5. Chọn nơi lưu file Excel.
6. Chờ thư mục chứa file tự mở.
7. Mở file và kiểm tra hai sheet Packing List và Buyer Invoice.

## Mẹo

> [!meo]
> Tên file mặc định là Invoice No. thực tế đọc được trên WFX.

> [!meo]
> Hai sheet giữ nguyên cách trình bày của báo cáo nguồn.

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
