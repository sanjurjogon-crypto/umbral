from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes
from typing import Optional

if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _BasicAccounting(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", wintypes.LARGE_INTEGER),
            ("TotalKernelTime", wintypes.LARGE_INTEGER),
            ("ThisPeriodTotalUserTime", wintypes.LARGE_INTEGER),
            ("ThisPeriodTotalKernelTime", wintypes.LARGE_INTEGER),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    _kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
    ]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_QUERY_INFORMATION = 0x0400


class JobHandle:
    def __init__(self, handle: int) -> None:
        self._handle: Optional[int] = handle

    def active_processes(self) -> int:
        if not self._handle:
            return 0
        info = _BasicAccounting()
        ok = _kernel32.QueryInformationJobObject(
            self._handle,
            _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
            None,
        )
        if not ok:
            return 0
        return int(info.ActiveProcesses)

    def close(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


def create_job_for_process(process: subprocess.Popen) -> JobHandle | None:
    if os.name != "nt":
        return None
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    handle = _kernel32.OpenProcess(
        _PROCESS_TERMINATE | _PROCESS_SET_QUOTA | _PROCESS_QUERY_INFORMATION,
        False,
        process.pid,
    )
    if not handle:
        _kernel32.CloseHandle(job)
        return None
    try:
        if not _kernel32.AssignProcessToJobObject(job, handle):
            _kernel32.CloseHandle(job)
            return None
    finally:
        _kernel32.CloseHandle(handle)
    return JobHandle(job)


def wait_for_job(job: JobHandle | None, timeout: float = 12 * 3600) -> None:
    if job is None:
        return
    import time

    started = time.monotonic()
    try:
        while job.active_processes() > 0:
            if time.monotonic() - started > timeout:
                break
            time.sleep(0.5)
    finally:
        job.close()
