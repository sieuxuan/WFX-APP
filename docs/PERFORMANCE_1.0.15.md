# Benchmark bộ nhớ WFX Smart 1.0.15

Đây là phép đo cục bộ dùng để so sánh cùng một chuỗi thao tác giữa source
1.0.14 (`8c12cb1`) và 1.0.15. Số liệu có thể thay đổi theo máy, mạng và dữ liệu
WFX; mục tiêu là kiểm tra xu hướng, không phải cam kết dung lượng tuyệt đối.

## Phương pháp

- Windows 11, Python 3.14, cùng tài khoản và Chrome automation profile.
- Restart toàn bộ Chrome automation trước mỗi lượt để nhận đúng flags của phiên
  bản đang đo.
- Chạy lần lượt: mở Chrome/đăng nhập, mở OC List, mở RMPO List.
- Cả sáu thao tác của hai phiên bản đều trả thành công.
- Lấy mẫu Working Set mỗi 50 ms cho Python/app, Playwright driver và mọi process
  Chrome có `WFX-Automation/ChromeProfile`.
- Không gửi telemetry; kết quả chỉ lưu tên task, result code, thời gian và RAM.

## Kết quả một lượt đo

| Chỉ số | 1.0.14 | 1.0.15 | Thay đổi |
|---|---:|---:|---:|
| Tổng peak app + Chrome | 894,3 MB | 738,8 MB | −17,4% |
| Chrome peak | 722,0 MB | 590,3 MB | −18,2% |
| Tổng thời gian 3 task | 18,73 s | 14,44 s | −22,9% |
| Tổng idle ngay sau task | 771,5 MB | 739,1 MB | −4,2% |

App-only idle ngay sau task tăng do 1.0.15 chủ động giữ Playwright/CDP để flow
kế tiếp không reconnect. Runtime tự nhả connection sau 60 giây không có flow;
Chrome ngoài và phiên WFX vẫn được giữ. Trong lượt kiểm tra 1.0.15, Chrome có 7
process tổng cộng, gồm 2 renderer — dưới giới hạn 4 renderer đã cấu hình.

Kiểm tra riêng cơ chế idle bằng một lần mở OC List thật: Working Set app giảm từ
173,2 MB ngay sau task xuống 45,3 MB sau 65 giây, tức trả lại khoảng 127,9 MB;
task trả `MODULE_OPENED` và Chrome không bị đóng.
