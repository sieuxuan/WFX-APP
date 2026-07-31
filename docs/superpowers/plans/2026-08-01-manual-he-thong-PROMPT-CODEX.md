# Prompt bàn giao cho Codex

Chép toàn bộ khối dưới đây làm tin nhắn đầu tiên gửi Codex, trong thư mục
`D:\XUAN\PROJECT\WFX-APP`.

---

Bạn đang làm việc trong repo `WFX-APP` — một ứng dụng desktop pywebview tên
**WFX Smart**, tự động hoá trang WorldFashionExchange cho nhân viên nghiệp vụ
dệt may người Việt.

## Nhiệm vụ

Triển khai đầy đủ kế hoạch tại:

```
docs/superpowers/plans/2026-08-01-manual-he-thong.md
```

Thiết kế gốc để đối chiếu khi có nghi ngờ:

```
docs/superpowers/specs/2026-08-01-manual-he-thong-design.md
```

Mục tiêu một câu: biến nút Manual trên thanh trên cùng — hiện chỉ mở một URL
ngoài — thành cửa sổ tra cứu hướng dẫn sử dụng đầy đủ, chạy offline, phủ mọi
tính năng của sản phẩm, kèm test chặn việc thêm tính năng mà quên viết manual.

## Trước khi viết dòng code đầu tiên

1. Đọc `CLAUDE.md` ở gốc repo. Đây là đặc tả hành vi bắt buộc của sản phẩm,
   ưu tiên cao hơn phán đoán của bạn.
2. Đọc trọn kế hoạch, cả 21 task, để nắm bức tranh tổng thể.
3. Chạy `python -m pytest` và `ruff check .` để xác nhận cây code đang xanh
   trước khi bạn đụng vào.
4. Xác nhận đang ở nhánh `feat/manual-he-thong`. Nếu chưa:
   `git checkout feat/manual-he-thong`.

## Cách làm việc

- Làm **tuần tự từ Task 1 tới Task 21**. Không nhảy cóc, không gộp task.
- Mỗi task theo đúng chu trình đã ghi: viết test thất bại → chạy để thấy đỏ →
  viết code tối thiểu → chạy để thấy xanh → commit.
- **Chạy `python -m pytest` và `ruff check .` sau mỗi task.** Cả hai phải xanh
  trước khi sang task kế tiếp.
- Commit sau mỗi task, message tiếng Việt như kế hoạch đã soạn sẵn.
- Không sửa file trong `dist/`. Mọi code sản phẩm nằm trong `wfx_panel/`.

## Ràng buộc không được vi phạm

- **Không thư viện JavaScript ngoài.** Cửa sổ hướng dẫn phải chạy được khi máy
  mất mạng, chưa mở trình duyệt, và chưa đăng nhập WFX.
- **Không đổi kích thước bảng điều khiển chính** (`WINDOW_WIDTH = 440`).
- **Không đụng vào bất kỳ luồng tự động hoá nào** — Playwright, Catalog,
  Costing, OC, Sample, Sale ASN đều giữ nguyên. Việc này thuần giao diện và
  tài liệu.
- **Không bịa mã lỗi.** Chỉ dùng mã có thật, lấy bằng:
  ```
  python -c "from wfx_panel import telemetry; print('\n'.join(sorted(telemetry.ERROR_CODE_INFO)))"
  ```
- **Không nới lỏng test khi nó đỏ.** Kiểm tra phủ đỏ nghĩa là sản phẩm có thứ
  mà tài liệu chưa nói tới — hãy viết mục hướng dẫn cho thứ đó.

## Giọng văn của nội dung hướng dẫn

Đây là phần chiếm nhiều công nhất (Task 7 tới Task 13) và cũng là phần dễ làm
sai nhất. Người đọc là nhân viên nghiệp vụ, không rành máy tính.

- Viết tiếng Việt, câu ngắn, ngôi thứ hai ("bạn").
- Mỗi bước một hành động. Luôn nói rõ **bấm nút nào trên màn hình nào**.
- Tên nút đặt trong dấu backtick và viết y hệt chữ hiện trên màn hình,
  ví dụ `Mở Catalog`, `Xác nhận Upload`, `Clear All Dependency`.
- **Từ cấm:** frame, selector, CDP, postback, iframe, XPath, DOM, endpoint,
  payload, token, grid. Có test chặn.
  Dùng thay: màn hình, nút, ô nhập, danh sách, file Excel, trình duyệt.
- Mỗi mục bắt buộc có `## Dùng để làm gì` và `## Các bước`.
  `## Mẹo` và `## Gặp lỗi thì sao` thêm khi có gì đáng nói.

Thử lại từng câu bằng câu hỏi: *một nhân viên merchandiser chưa từng nghe từ
"API" có hiểu câu này không?* Nếu không, viết lại.

## Khi gặp bất đồng giữa kế hoạch và code thật

Kế hoạch được viết ngày 2026-08-01 dựa trên trạng thái repo lúc đó. Nếu số đếm
hoặc số dòng bị lệch (ví dụ Task 4 kỳ vọng 16 module và 29 nút thao tác):

1. Mở file nguồn xác minh con số thật.
2. Cập nhật test theo thực tế, ghi rõ lý do trong commit message.
3. Viết bổ sung nội dung hướng dẫn cho phần mới phát sinh.

Đừng im lặng hạ chuẩn test để nó xanh.

## Khi hoàn tất

Chạy Task 21 đầy đủ, gồm cả 10 mục kiểm tra thủ công bằng `python app.py`, rồi
báo lại cho tôi:

- Kết quả `python -m pytest` và `ruff check .`
- Kết quả lệnh xác nhận không sót ở Task 21 Step 3 (phải in ra ba danh sách rỗng)
- Danh sách các mục kiểm tra thủ công nào bạn đã tự chạy được, mục nào cần tôi
  xác nhận
- Bất kỳ chỗ nào bạn phải lệch khỏi kế hoạch, kèm lý do

Bắt đầu từ Task 1.
