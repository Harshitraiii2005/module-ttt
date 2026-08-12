"""API-level tests for /v1/jobs/{job_id} (app.api.jobs)."""

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.helpers.job import store as job_store
from talkingdb.models.job.job import JobModel
from talkingdb.models.job.state import JobState
from talkingdb.models.job.type import JobType


def _insert_job(**overrides) -> JobModel:
    job = JobModel.new(job_type=JobType.DOCUMENT, filename="report.pdf")
    for key, value in overrides.items():
        setattr(job, key, value)
    with sqlite_client.sqlite_conn() as conn:
        job_store.insert(conn, job)
    return job


class TestGetJobStatus:
    def test_unknown_job_id_returns_404(self, client, auth_headers):
        response = client.get("/v1/jobs/does-not-exist", headers=auth_headers)
        assert response.status_code == 404
        assert response.json()["detail"]["error_code"] == "JOB_NOT_FOUND"

    def test_known_job_returns_its_status(self, client, auth_headers, initialized_db):
        job = _insert_job()

        response = client.get(f"/v1/jobs/{job.job_id}", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == job.job_id
        assert body["state"] == JobState.QUEUED.value
        assert body["job_type"] == "document"

    def test_response_has_no_store_cache_control_header(
        self, client, auth_headers, initialized_db
    ):
        job = _insert_job()
        response = client.get(f"/v1/jobs/{job.job_id}", headers=auth_headers)
        assert response.headers["cache-control"] == "no-store"

    def test_missing_auth_header_returns_401_or_403(self, client, initialized_db):
        job = _insert_job()
        response = client.get(f"/v1/jobs/{job.job_id}")
        assert response.status_code in (401, 403)

    def test_invalid_api_key_returns_401(self, client, initialized_db):
        job = _insert_job()
        response = client.get(
            f"/v1/jobs/{job.job_id}",
            headers={"Authorization": "Bearer sk_not-a-real-key"},
        )
        assert response.status_code == 401


class TestCancelJob:
    def test_cancel_unknown_job_returns_404(self, client, auth_headers):
        response = client.post(
            "/v1/jobs/does-not-exist/cancel", headers=auth_headers
        )
        assert response.status_code == 404

    def test_cancel_queued_job_transitions_to_cancelled(
        self, client, auth_headers, initialized_db
    ):
        job = _insert_job()

        response = client.post(
            f"/v1/jobs/{job.job_id}/cancel", headers=auth_headers
        )

        assert response.status_code == 202
        assert response.json()["state"] == JobState.CANCELLED.value

    def test_cancelling_an_already_cancelled_job_is_idempotent(
        self, client, auth_headers, initialized_db
    ):
        job = _insert_job()
        first = client.post(f"/v1/jobs/{job.job_id}/cancel", headers=auth_headers)
        second = client.post(f"/v1/jobs/{job.job_id}/cancel", headers=auth_headers)

        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["state"] == second.json()["state"] == JobState.CANCELLED.value

    def test_cancelling_an_ongoing_job_sets_cancelling_state(
        self, client, auth_headers, initialized_db
    ):
        job = _insert_job()
        with sqlite_client.sqlite_conn() as conn:
            job_store.mark_ongoing(conn, job.job_id, "2026-01-01T00:00:00+00:00")

        response = client.post(f"/v1/jobs/{job.job_id}/cancel", headers=auth_headers)

        assert response.status_code == 202
        assert response.json()["state"] == JobState.CANCELLING.value
