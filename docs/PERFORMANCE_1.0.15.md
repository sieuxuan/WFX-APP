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

Ghi chú cập nhật: bản đo trên dùng cơ chế giữ Playwright/CDP giữa các flow
(persistent connection + nhả sau 60 giây idle). Cơ chế đó đã được BỎ: runtime
nhả driver/CDP ngay sau mỗi flow, không giữ attach giữa các flow. Lý do là khi
CDP còn attach, tab người dùng tự mở trong Chrome bị auto-attach pause
("Debugger paused in another tab") và có thể treo Chrome khi đóng tab đó. Đổi
lại mỗi flow tự reconnect (chậm hơn chút so với số liệu −22,9% ở trên) nhưng
người dùng thao tác tay trong WFX không còn bị đứt/treo. Chrome ngoài và phiên
WFX vẫn được giữ giữa các flow.
