## Dùng để làm gì

Tìm Sale ASN cũ hoặc tạo Sale ASN mới từ một file Excel có nhiều PO.

## Các bước

### Tạo Sale ASN từ Excel

1. Mở module `Sale ASN`.
2. Chọn thẻ `Tạo New`.
3. Bấm `↻` nếu danh sách Buyer chưa có hoặc cần cập nhật.
4. Gõ vài chữ và chọn đúng Buyer trong danh sách.
5. Bấm `Tải form Excel` nếu bạn chưa có form 19 cột.
6. Điền dữ liệu theo thứ tự từ trên xuống dưới trong file.
7. Bấm `Chọn file & kiểm tra`.
8. Kiểm tra Invoice No., số PO, số Style và Destination trong phần review.
9. Bấm `Bắt đầu tạo Sale ASN`.
10. Khi ứng dụng báo cần chọn, chọn đúng dòng PO trên WFX rồi bấm `Add & Continue`.
11. Đánh dấu xác nhận trong ứng dụng và bấm `Tiếp tục dòng kế`.
12. Sau khi ứng dụng điền xong, kiểm tra toàn bộ Sale ASN trên WFX rồi tự bấm `Save`.

> [!luuy]
> Ứng dụng không tự bấm Save. Bạn luôn có bước kiểm tra cuối trên WFX.

> [!meo]
> Ứng dụng bấm `Add & Continue` cho cả PO cuối để WFX ghi đủ dòng, sau đó mới
> bấm `OK` để đóng cửa sổ Add Order Details.

## Quy tắc của file Excel

- Mỗi file chỉ chứa một Invoice No. và một FTY.
- Chỉ dòng có `PO No` mới được tính và xử lý; dòng tổng hoặc ghi chú không có PO sẽ được bỏ qua.
- Với mỗi dòng có PO, `Style No`, `Destination` và `FTY` là dữ liệu bắt buộc.
- `SEASON`, `DESCRIPTION`, `HS CODE`, `Qty`, `Carton`, `NW`, `GW`, `CBM`, `FOB Price` và `Service Price` có thể để trống.
- Nếu một ngày bị trống, ứng dụng lấy ngày có dữ liệu đầu tiên trong file. Nếu cả file không có ngày, ứng dụng dùng ngày hiện tại.
- Nếu Shipping Bill No. bị trống, ứng dụng dùng Invoice No.
- PO luôn được xử lý đúng thứ tự dòng trong file.

## Tìm Sale ASN và tải Documents

1. Chọn thẻ `Tra cứu & Invoice/PKL`.
2. Chọn `Invoice No.` hoặc `Buyer Order Ref/OC`.
3. Nhập nội dung rồi bấm `Tìm`.
4. Bấm `Xuất Buyer Invoice + Packing List` để lấy hai báo cáo trong cùng một file Excel.

> [!luuy]
> Report WFX có thể tải chậm. Ứng dụng chờ tối đa ba phút cho từng Packing List
> hoặc Buyer Invoice; không bấm xuất lại khi trạng thái vẫn đang chạy.

> [!meo]
> Khi gộp file, ứng dụng giữ nguyên tên sheet do WFX xuất. Chỉ khi hai report có
> sheet trùng tên, chúng được đổi theo dạng `PKL 1083.26.PS.PSHK_7` và
> `INVOICE 1083.26.PS.PSHK_7` để Excel chấp nhận. Nếu report có nhiều sheet,
> ứng dụng xếp xen kẽ `Invoice 1`, `PKL 1`, `Invoice 2`, `PKL 2` cho đến hết;
> Invoice luôn đứng trước PKL. Sau khi lưu thành công, Explorer sẽ tự mở và chọn
> đúng file vừa lưu. Khung, rich text, merged cell và định dạng gốc của cả
> Invoice lẫn PKL được giữ nguyên khi ghép.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Không có Buyer để chọn | Mở đúng phiên WFX rồi bấm `↻` để quét lại. |
| File có lỗi | Đọc vị trí ô hoặc dòng trong thông báo, sửa file rồi chọn lại. |
| Có nhiều dòng PO giống nhau | Chọn đúng Style hoặc Qty trên WFX, bấm `Add & Continue`, rồi tiếp tục trong ứng dụng. |
| Không tìm thấy PO | Kiểm tra PO No., Destination và Style trong file; bạn có thể tìm và chọn thủ công trên cửa sổ đang mở. |
| Đã đóng cửa sổ Add PO | Hủy phiên đang chuẩn bị và chạy lại từ file để tránh bỏ sót dòng. |
