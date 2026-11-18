"""运行时抑制 Windows 空闲睡眠，不修改系统电源或合盖设置。"""
from contextlib import contextmanager
import ctypes
import sys
import time

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def wait_between_batches(seconds, clock=None, sleep=None):
    clock = clock or time.time
    sleep = sleep or time.sleep
    started = clock()
    sleep(seconds)
    paused = clock()-started-seconds
    if paused > 60:
        raise RuntimeError(
            f'等待期间额外暂停了约 {paused:.0f} 秒，可能发生休眠或系统暂停。'
            '已停止发送，请先在 App 核对未完成记录。'
        )


def _set_execution_state(flags):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    call = kernel.SetThreadExecutionState
    call.argtypes = [ctypes.c_uint]
    call.restype = ctypes.c_uint
    result = call(flags)
    if not result:
        raise OSError(ctypes.get_last_error(), '无法设置运行期间的空闲睡眠保护')
    return result


@contextmanager
def prevent_idle_sleep():
    if sys.platform != 'win32':
        yield
        return
    previous = _set_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        _set_execution_state(previous | ES_CONTINUOUS)
