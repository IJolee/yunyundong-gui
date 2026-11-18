"""Shared paths and subprocess commands for source and frozen builds."""
from pathlib import Path
import sys

def app_root():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

def script_command(script, *args):
    if getattr(sys, 'frozen', False):
        flag = '--worker' if Path(script).name == 'desktop_worker.py' else '--cli'
        return [sys.executable, flag, *map(str, args)]
    return [sys.executable, '-u', str(script), *map(str, args)]
