"""Danh tính certificate dùng để xác minh bản cập nhật production.

Workflow release ghi đè hằng số này bằng SHA-1 thumbprint của certificate ký
Windows trước khi PyInstaller đóng gói. Source/dev cố ý để trống: bản chạy từ
source không được phép tự cài update.
"""

EXPECTED_SIGNER_THUMBPRINT = ""
