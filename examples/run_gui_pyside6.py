"""启动 PySide6 图形界面。

用法:
    pip install PySide6
    python examples/run_gui_pyside6.py

功能与 Tkinter 版 (run_gui.py / gui.py) 一致，只是控件换成 PySide6。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as e:
        sys.stderr.write("缺少 PySide6，请先安装: pip install PySide6\n")
        sys.exit(1)

    from ethercat_scan.gui_pyside6 import ScanAppQt

    app = QApplication(sys.argv)
    win = ScanAppQt()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
