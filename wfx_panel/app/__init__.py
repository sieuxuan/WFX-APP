"""Lớp vỏ desktop: cửa sổ panel, bubble, tray, hộp thoại file và Manual.

``panel_app.PanelApp`` là orchestrator — nó sở hữu cửa sổ pywebview, tray và
các vòng lặp nền. Từng mảng hành vi nằm ở controller riêng trong package này
và mượn lại app qua tham chiếu ``app``, giống cách ``PanelAPI`` dùng
``wfx_panel/controllers``.
"""
