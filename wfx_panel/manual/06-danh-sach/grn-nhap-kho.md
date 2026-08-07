## Dùng để làm gì

Tạo GRN nhập nguyên phụ liệu theo một RMPO hoặc tìm và mở GRN đã có. Bạn có
thể mở module trực tiếp, hoặc chọn RMPO trong RMPO List rồi bấm `Nhập kho` để
chuyển sẵn RMPO và Supplier sang đây.

Nếu chưa biết số RMPO, bấm `RMPO List` ngay trong module này để sang màn tìm,
chọn đúng dòng rồi bấm `Nhập kho`.

Bạn có thể chỉ nhập phần số cuối, ví dụ `2345`. Nếu RMPO List chỉ trả đúng một
dòng như `PSW-TRM-23-2345`, ứng dụng tự dùng Order No. đầy đủ cho các bước sau.
Nếu có nhiều dòng chứa phần số đó, ứng dụng yêu cầu nhập rõ hơn.

> [!luuy]
> RMPO có Status `Received` đã nhập kho hết. Ứng dụng sẽ báo và không cho bắt
> đầu thêm Sourcing ASN hoặc GRN mới.

## Các bước

### Nhập đơn hàng nước ngoài

1. Nhập RMPO No., hoặc chuyển RMPO từ RMPO List.
2. Bấm `Đơn hàng nước ngoài`.
3. Ứng dụng mở Sourcing ASN New, chọn Order Type là RMPO, điền đúng Supplier,
   Add RMPO và bấm Add & Close.
4. Trên WFX, tự nhập đủ thông tin và số lượng cần nhận, sau đó bấm Confirm.
5. Quay lại ứng dụng và bấm `Tiếp tục làm GRN`. Chỉ xác nhận hộp hỏi khi bạn
   đã Confirm Sourcing ASN trên WFX.
6. Ứng dụng mở GRN Pending, chọn Receipt Type `ASN from Supplier - Against
   ASN`, Supplier, Imported và Search.
7. Chọn Site trong danh sách ứng dụng rồi bấm `Next — mở New GRN`.
8. Ứng dụng chọn đúng dòng theo cột PO No. và bấm New. Kiểm tra rồi hoàn tất
   phiếu GRN trên WFX.

> [!canhbao]
> Ứng dụng không tự điền số lượng và không tự Confirm Sourcing ASN. Hãy kiểm tra
> kỹ thông tin nhận hàng trước khi bấm `Tiếp tục làm GRN`.

### Nhập đơn hàng trong nước

1. Nhập hoặc chuyển RMPO vào module.
2. Bấm `Đơn hàng trong nước`.
3. Nếu chưa có Supplier từ RMPO List, ứng dụng tự tra đúng RMPO để lấy Supplier.
4. Ứng dụng mở GRN Pending, chọn Receipt Type `ASN from Supplier - Against PO`,
   chọn Supplier và Search. Luồng này không chọn Imported.
5. Chọn Site rồi bấm `Next — mở New GRN`.
6. Ứng dụng chọn đúng PO No. và mở New GRN để bạn kiểm tra, hoàn tất trên WFX.

### Tìm GRN

1. Chọn `Số Invoice` hoặc `RMPO / Order No.`.
2. Nhập đúng giá trị và bấm `Tìm và mở GRN`.
3. Ứng dụng mở bảng `#ctrlRpt`, bỏ tích Date ở dòng `row_txtFromGRNDate`,
   điền Document No. hoặc Order No. rồi Search.
4. Khi có kết quả, ứng dụng bấm đúng số GRN của dòng dữ liệu (link PrintGRN),
   không bấm tiêu đề `No.`, rồi chờ cửa sổ GRN mở.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Chưa chuẩn bị được nhập kho | Kiểm tra RMPO còn tồn tại, Supplier đúng và WFX đã tải xong. |
| Đã tìm thấy RMPO nhưng chưa đọc được Supplier | Mở lại RMPO List, tìm lại dòng đó rồi thử lại. |
| Không thể tiếp tục sau Sourcing ASN | Kiểm tra Sourcing ASN đã được Confirm rồi thử lại. |
| Không có Site | Kiểm tra Receipt Type, Supplier và kết quả Search trên GRN Pending. |
| Không mở được New GRN | Kiểm tra Site và dòng có PO No. đúng RMPO trên WFX. |
| Không tìm thấy GRN | Đổi đúng kiểu Invoice/RMPO, kiểm tra giá trị rồi tìm lại. |
