"""Dữ liệu tham chiếu được lưu và đồng bộ ngoài phiên WFX.

Article Library, danh sách tuỳ chọn Style, tham số báo cáo và kho Buyer đều
sống lâu hơn một lần chạy: chúng ghi cache xuống data dir, tự kiểm tra phiên
bản và vẫn dùng được bản gần nhất khi offline. Mọi URL máy chủ phải qua kiểm
tra HTTPS + có hostname trước khi gọi ``urlopen``.
"""
