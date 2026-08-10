"""Unit tests for app.services.job_observability."""

import json
import logging

from talkingdb.models.job.job import JobModel
from talkingdb.models.job.state import JobState
from talkingdb.models.job.type import JobType

from app.services.job_observability import _diff_ms, emit_lifecycle


class TestDiffMs:
    def test_returns_none_when_start_missing(self):
        assert _diff_ms(None, "2026-01-01T00:00:01+00:00") is None

    def test_returns_none_when_end_missing(self):
        assert _diff_ms("2026-01-01T00:00:00+00:00", None) is None

    def test_returns_none_for_unparseable_timestamp(self):
        assert _diff_ms("not-a-timestamp", "2026-01-01T00:00:01+00:00") is None

    def test_computes_positive_millisecond_delta(self):
        start = "2026-01-01T00:00:00+00:00"
        end = "2026-01-01T00:00:01.500000+00:00"
        assert _diff_ms(start, end) == 1500


class TestEmitLifecycle:
    def test_logs_one_json_record_with_expected_fields(self, caplog):
        job = JobModel.new(job_type=JobType.DOCUMENT, filename="report.pdf")
        job.state = JobState.COMPLETED
        job.created_at = "2026-01-01T00:00:00+00:00"
        job.started_at = "2026-01-01T00:00:01+00:00"
        job.completed_at = "2026-01-01T00:00:03+00:00"

        with caplog.at_level(logging.INFO, logger="talkingdb"):
            emit_lifecycle(job, rollback_ms=42)

        assert len(caplog.records) == 1
        record = json.loads(caplog.records[0].message)
        assert record["event"] == "job.lifecycle"
        assert record["job_id"] == job.job_id
        assert record["job_type"] == "document"
        assert record["state"] == "COMPLETED"
        assert record["queue_wait_ms"] == 1000
        assert record["processing_ms"] == 2000
        assert record["rollback_ms"] == 42
        assert record["filename"] == "report.pdf"

    def test_handles_missing_stage_and_error_code_gracefully(self, caplog):
        job = JobModel.new(job_type=JobType.DOCUMENT, filename="report.pdf")
        assert job.stage is None
        assert job.error_code is None

        with caplog.at_level(logging.INFO, logger="talkingdb"):
            emit_lifecycle(job)

        record = json.loads(caplog.records[0].message)
        assert record["stage"] is None
        assert record["error_code"] is None
        assert record["rollback_ms"] is None
