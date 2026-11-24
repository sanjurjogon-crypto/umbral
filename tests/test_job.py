from __future__ import annotations

import subprocess
import sys

from umbral.job import JobHandle, create_job_for_process, wait_for_job


def test_wait_for_job_without_job_is_noop() -> None:
    wait_for_job(None)


def test_job_handle_without_handle_reports_zero() -> None:
    assert JobHandle(None).active_processes() == 0


def test_create_job_for_real_process_does_not_crash() -> None:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        job = create_job_for_process(process)
        if job is not None:
            job.close()
    finally:
        process.wait()


def test_wait_for_job_with_fake_handle_returns() -> None:
    wait_for_job(JobHandle(None))
