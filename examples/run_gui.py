"""启动图形界面。

用法:
    python examples/run_gui.py
"""
from __future__ import annotations

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ethercat_scan.gui import ScanApp


def main():
    root = tk.Tk()
    ScanApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
