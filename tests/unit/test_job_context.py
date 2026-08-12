"""Unit tests for app.services.job_context.JobContext.

JobContext writes progress via talkingdb.helpers.job.store against a real
SQLite row, so these use the ``initialized_db`` fixture plus a manually
inserted JobModel rather than mocking the store.
"""

import time

import pytest

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.helpers.job import store as job_store
from talkingdb.models.job.job import JobModel
from talkingdb.models.job.stage import JobStage
from talkingdb.models.job.type import JobType

from app.core import config
from app.services.job_context import JobCancelled, JobContext, JobTimeout


@pytest.fixture
def inserted_job(initialized_db):
    job = JobModel.new(job_type=JobType.DOCUMENT, filename="report.pdf")
    with sqlite_client.sqlite_conn() as conn:
        job_store.insert(conn, job)
    return job


def test_elapsed_seconds_increases_over_time():
    ctx = JobContext(job_id="job::x")
    first = ctx.elapsed_seconds()
    time.sleep(0.01)
    second = ctx.elapsed_seconds()
    assert second > first >= 0


def test_set_stage_persists_stage_and_updates_heartbeat_timestamp(inserted_job):
    ctx = JobContext(job_id=inserted_job.job_id)

    ctx.set_stage(JobStage.PARSING, status_message="parsing now")

    assert ctx._stage == JobStage.PARSING
    assert ctx._last_heartbeat_monotonic > 0
    with sqlite_client.sqlite_conn() as conn:
        row = conn.execute(
            "SELECT stage, status_message FROM jobs WHERE job_id = ?",
            (inserted_job.job_id,),
        ).fetchone()
    assert row["stage"] == JobStage.PARSING.value
    assert row["status_message"] == "parsing now"


def test_checkpoint_raises_job_cancelled_when_cancel_requested(inserted_job):
    with sqlite_client.sqlite_conn() as conn:
        job_store.request_cancel(conn, inserted_job.job_id)
    ctx = JobContext(job_id=inserted_job.job_id)

    with pytest.raises(JobCancelled):
        ctx.checkpoint(done_units=1, total_units=10)


def test_checkpoint_raises_job_timeout_when_duration_exceeded(inserted_job, monkeypatch):
    monkeypatch.setattr(config, "MAX_JOB_DURATION_SECONDS", 0)
    ctx = JobContext(job_id=inserted_job.job_id)
    time.sleep(0.01)

    with pytest.raises(JobTimeout):
        ctx.checkpoint(done_units=1, total_units=10)


def test_checkpoint_writes_heartbeat_when_forced_by_elapsed_gap(inserted_job, monkeypatch):
    monkeypatch.setattr(config, "HEARTBEAT_MIN_GAP_SECONDS", 0)
    ctx = JobContext(job_id=inserted_job.job_id)

    ctx.checkpoint(done_units=3, total_units=10, status_message="working")

    with sqlite_client.sqlite_conn() as conn:
        row = conn.execute(
            "SELECT done_units, total_units, status_message FROM jobs WHERE job_id = ?",
            (inserted_job.job_id,),
        ).fetchone()
    assert row["done_units"] == 3
    assert row["total_units"] == 10
    assert row["status_message"] == "working"


def test_checkpoint_skips_write_when_heartbeat_gap_not_elapsed(inserted_job, monkeypatch):
    monkeypatch.setattr(config, "HEARTBEAT_MIN_GAP_SECONDS", 10_000)
    ctx = JobContext(job_id=inserted_job.job_id)
    ctx._last_heartbeat_monotonic = time.monotonic()

    # Should return without error and without touching the row again.
    ctx.checkpoint(done_units=1, total_units=10)


def test_best_effort_progress_swallows_operational_errors(inserted_job, monkeypatch):
    """A locked/corrupt DB during a progress write must not crash the job."""
    import sqlite3

    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    ctx = JobContext(job_id=inserted_job.job_id)
    monkeypatch.setattr(job_store, "update_progress", _boom)

    # Must not raise.
    ctx._best_effort_progress(heartbeat=True)


def test_start_and_stop_background_heartbeat_is_idempotent(inserted_job, monkeypatch):
    monkeypatch.setattr(config, "BACKGROUND_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    ctx = JobContext(job_id=inserted_job.job_id)

    ctx.start_background_heartbeat()
    ctx.start_background_heartbeat()  # second call is a no-op (thread already running)
    time.sleep(0.05)
    ctx.stop_background_heartbeat()
    ctx.stop_background_heartbeat()  # idempotent

    assert ctx._hb_thread is None
