"""API-level tests for /v1/namespaces (app.api.namespaces)."""

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.helpers.job import store as job_store
from talkingdb.helpers.namespace import store as namespace_store
from talkingdb.models.job.job import JobModel
from talkingdb.models.job.state import JobState
from talkingdb.models.job.type import JobType


def _insert_job(namespace: str, state: JobState = JobState.COMPLETED) -> JobModel:
    job = JobModel.new(job_type=JobType.DOCUMENT, namespace=namespace, filename="a.pdf")
    job.state = state
    with sqlite_client.sqlite_conn() as conn:
        job_store.insert(conn, job)
    return job


class TestListNamespaces:
    def test_requires_auth(self, client, initialized_db):
        response = client.get("/v1/namespaces")
        assert response.status_code in (401, 403)

    def test_includes_the_reserved_demo_namespace(self, client, auth_headers):
        response = client.get("/v1/namespaces", headers=auth_headers)
        assert response.status_code == 200
        names = {ns["namespace"] for ns in response.json()}
        assert "demo-library" in names

    def test_newly_created_namespace_is_listed(self, client, auth_headers, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            namespace_store.upsert_namespace(
                conn, "acme-reports", title="Acme Reports", public_read=False
            )

        response = client.get("/v1/namespaces", headers=auth_headers)

        by_name = {ns["namespace"]: ns for ns in response.json()}
        assert by_name["acme-reports"]["title"] == "Acme Reports"
        assert by_name["acme-reports"]["public_read"] is False


class TestListNamespaceDocuments:
    def test_unknown_namespace_returns_404(self, client, auth_headers):
        response = client.get(
            "/v1/namespaces/does-not-exist/documents", headers=auth_headers
        )
        assert response.status_code == 404
        assert response.json()["detail"]["error_code"] == "NAMESPACE_NOT_FOUND"

    def test_default_lists_documents_in_any_state(
        self, client, auth_headers, initialized_db
    ):
        """completed_only defaults to False, so QUEUED/FAILED/etc. are included."""
        with sqlite_client.sqlite_conn() as conn:
            namespace_store.upsert_namespace(conn, "reports", public_read=False)
        _insert_job("reports", state=JobState.COMPLETED)
        _insert_job("reports", state=JobState.FAILED)

        response = client.get("/v1/namespaces/reports/documents", headers=auth_headers)

        assert response.status_code == 200
        states = {doc["state"] for doc in response.json()}
        assert states == {"COMPLETED", "FAILED"}

    def test_completed_only_true_filters_to_completed(
        self, client, auth_headers, initialized_db
    ):
        with sqlite_client.sqlite_conn() as conn:
            namespace_store.upsert_namespace(conn, "reports", public_read=False)
        completed = _insert_job("reports", state=JobState.COMPLETED)
        _insert_job("reports", state=JobState.FAILED)

        response = client.get(
            "/v1/namespaces/reports/documents",
            params={"completed_only": "true"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        ids = [doc["id"] for doc in response.json()]
        assert ids == [completed.job_id]

    def test_limit_bounds_result_count(self, client, auth_headers, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            namespace_store.upsert_namespace(conn, "reports", public_read=False)
        for _ in range(3):
            _insert_job("reports", state=JobState.COMPLETED)

        response = client.get(
            "/v1/namespaces/reports/documents",
            params={"limit": 2},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_limit_out_of_range_returns_422(self, client, auth_headers, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            namespace_store.upsert_namespace(conn, "reports", public_read=False)

        response = client.get(
            "/v1/namespaces/reports/documents",
            params={"limit": 0},
            headers=auth_headers,
        )
        assert response.status_code == 422
