"""Integration tests: talkingdb.helpers.job.store against a real, on-disk
SQLite database (not mocks). These exercise the persistence layer that
app.services.job_context and app.api.jobs both build on.
"""

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.helpers.job import store as job_store
from talkingdb.models.job.job import JobModel
from talkingdb.models.job.state import JobState
from talkingdb.models.job.type import JobType


def _new_job(**overrides) -> JobModel:
    job = JobModel.new(job_type=JobType.DOCUMENT, filename="report.pdf")
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


class TestInsertAndGet:
    def test_inserted_job_can_be_read_back_with_same_fields(self, initialized_db):
        job = _new_job(namespace="reports")
        with sqlite_client.sqlite_conn() as conn:
            job_store.insert(conn, job)
            fetched = job_store.get(conn, job.job_id)

        assert fetched.job_id == job.job_id
        assert fetched.namespace == "reports"
        assert fetched.filename == "report.pdf"
        assert fetched.state == JobState.QUEUED

    def test_get_unknown_job_id_returns_none(self, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            result = job_store.get(conn, "job::does-not-exist")
        assert result is None


class TestCancelRequestFlow:
    def test_is_cancel_requested_false_before_request(self, initialized_db):
        job = _new_job()
        with sqlite_client.sqlite_conn() as conn:
            job_store.insert(conn, job)
            assert job_store.is_cancel_requested(conn, job.job_id) is False

    def test_is_cancel_requested_true_after_request(self, initialized_db):
        job = _new_job()
        with sqlite_client.sqlite_conn() as conn:
            job_store.insert(conn, job)
            job_store.request_cancel(conn, job.job_id)
            assert job_store.is_cancel_requested(conn, job.job_id) is True

    def test_cancel_request_on_unknown_job_does_not_raise(self, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            job_store.request_cancel(conn, "job::does-not-exist")


class TestMarkOngoing:
    def test_mark_ongoing_transitions_state_and_sets_started_at(self, initialized_db):
        job = _new_job()
        with sqlite_client.sqlite_conn() as conn:
            job_store.insert(conn, job)
            job_store.mark_ongoing(conn, job.job_id, "2026-01-01T00:00:00+00:00")
            fetched = job_store.get(conn, job.job_id)

        assert fetched.state == JobState.ONGOING
        assert fetched.started_at == "2026-01-01T00:00:00+00:00"


class TestUpdateProgress:
    def test_update_progress_persists_stage_and_units(self, initialized_db):
        from talkingdb.models.job.stage import JobStage

        job = _new_job()
        with sqlite_client.sqlite_conn() as conn:
            job_store.insert(conn, job)
            job_store.update_progress(
                conn,
                job.job_id,
                stage=JobStage.PARSING,
                done_units=3,
                total_units=10,
                status_message="parsing document",
                heartbeat=True,
            )
            fetched = job_store.get(conn, job.job_id)

        assert fetched.stage == JobStage.PARSING
        assert fetched.done_units == 3
        assert fetched.total_units == 10
        assert fetched.status_message == "parsing document"


class TestListNamespaceDocuments:
    def test_filters_by_namespace(self, initialized_db):
        job_a = _new_job(namespace="ns-a")
        job_a.state = JobState.COMPLETED
        job_b = _new_job(namespace="ns-b")
        job_b.state = JobState.COMPLETED
        with sqlite_client.sqlite_conn() as conn:
            job_store.insert(conn, job_a)
            job_store.insert(conn, job_b)
            docs = job_store.list_namespace_documents(conn, "ns-a")

        ids = [d.job_id for d in docs]
        assert job_a.job_id in ids
        assert job_b.job_id not in ids

    def test_completed_only_defaults_to_true(self, initialized_db):
        queued_job = _new_job(namespace="ns-a")  # default state is QUEUED
        with sqlite_client.sqlite_conn() as conn:
            job_store.insert(conn, queued_job)
            docs = job_store.list_namespace_documents(conn, "ns-a")

        assert docs == []

    def test_empty_namespace_returns_empty_list(self, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            docs = job_store.list_namespace_documents(conn, "no-such-namespace")
        assert docs == []
