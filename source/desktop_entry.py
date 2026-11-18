"""Executable entry point; worker mode shares the bundled Python runtime."""
import os
import sys
from runtime_paths import app_root

def launch():
    os.chdir(app_root())
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode in ('--worker', '--cli'):
        del sys.argv[1]
        if mode == '--worker':
            from desktop_worker import main
        else:
            from main import main
        return main()
    if mode == '--smoke-test':
        import ssl, ctypes
        from desktop import Desktop
        app = Desktop(app_root())
        app.withdraw()
        assert len(app.tabs.tabs()) == 6
        app.destroy()
        print('GUI_SMOKE_OK', flush=True)
        return 0
    if os.name == 'nt':
        import ctypes
        window = ctypes.windll.kernel32.GetConsoleWindow()
        if window:
            ctypes.windll.user32.ShowWindow(window, 0)
    from desktop import Desktop
    Desktop(app_root()).mainloop()
    return 0

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(launch())
