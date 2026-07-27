"""Entrypoint tương thích cho WFX Smart Panel.

UI Tkinter cũ đã được loại bỏ để mọi cách khởi động (`python app.py`,
`start_app.bat`, executable) đều dùng chung UI pywebview trong
`wfx_panel/ui/index.html`.
"""

from wfx_panel.panel_app import main

if __name__ == "__main__":
    main()
