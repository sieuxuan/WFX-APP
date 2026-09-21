"""Đọc và sinh workbook Excel — Python thuần, không chạm Playwright.

Mỗi module ở đây biết đúng một loại chứng từ: hình dạng sheet, ô bắt buộc,
dropdown và luật validate. Chúng không biết gì về WFX, DOM hay selector — lớp
``wfx_panel/automation`` mới là nơi thao tác trình duyệt. Nhờ ranh giới đó,
toàn bộ luật nghiệp vụ của file Excel test được mà không cần Chrome.
"""
