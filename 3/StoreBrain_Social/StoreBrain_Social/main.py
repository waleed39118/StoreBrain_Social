"""
main.py — نقطة انطلاق StoreBrain Social الوحيدة
التشغيل: python main.py
"""
from __future__ import annotations
import sys
import tkinter as tk

# إعداد الترميز
if sys.stdout is not None:
    try:
        if getattr(sys.stdout, "encoding", None) and \
                sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    from core.logger import setup_logging, get_logger
    setup_logging()
    log = get_logger("main")
    log.info("StoreBrain Social starting...")

    try:
        from gui.app import StoreBrainApp
        root = tk.Tk()
        StoreBrainApp(root)
        root.mainloop()
        log.info("StoreBrain Social closed.")
    except Exception as fatal:
        log.critical("Fatal: %s", fatal, exc_info=True)
        try:
            import tkinter.messagebox as mb
            mb.showerror("خطأ قاتل",
                         f"فشل التشغيل:\n{fatal}\n\n"
                         f"راجع السجل في: ~/.storebrain_social/logs/app.log")
        except Exception:
            print(f"[FATAL] {fatal}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
