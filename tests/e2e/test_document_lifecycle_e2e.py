"""End-to-end tests exercising multi-step user flows through the (partial)
API app - signup through querying an indexed document - the way a real
client would use them, against a real temp SQLite database.

These complement, rather than duplicate, the single-endpoint tests in
tests/api/: each test here chains several requests together and asserts on
the flow as a whole.
"""

import uuid

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.helpers.graph_cache import graph_cache
from talkingdb.helpers.job import store as job_store
from talkingdb.helpers.namespace import store as namespace_store
from talkingdb.models.graph.graph import GraphModel
from talkingdb.models.job.job import JobModel
from talkingdb.models.job.state import JobState
from talkingdb.models.job.type import JobType


def test_signup_login_create_api_key_then_use_it(client, initialized_db):
    """A brand new user can sign up, log in, mint an API key, and
    immediately use that key to call an authenticated endpoint."""
    signup = client.post(
        "/auth/signup",
        json={"email": "e2e-user@example.com", "password": "Correct-Pass1!"},
    )
    assert signup.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": "e2e-user@example.com", "password": "Correct-Pass1!"},
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    key_response = client.post(
        "/auth/api-keys", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert key_response.status_code == 200
    api_key = key_response.json()["api_key"]

    namespaces = client.get(
        "/v1/namespaces", headers={"Authorization": f"Bearer {api_key}"}
    )
    assert namespaces.status_code == 200
    assert any(ns["namespace"] == "demo-library" for ns in namespaces.json())


def test_publish_a_namespace_document_then_find_it_via_public_and_authenticated_routes(
    client, initialized_db
):
    """A document that completes processing in a public namespace shows up
    both through the authenticated /v1 routes and the anonymous /public
    routes, with matching content."""
    with sqlite_client.sqlite_conn() as conn:
        namespace_store.upsert_namespace(
            conn, "public-reports", title="Public Reports", public_read=True
        )
    job = JobModel.new(
        job_type=JobType.DOCUMENT, namespace="public-reports", filename="q1.pdf"
    )
    job.state = JobState.COMPLETED
    with sqlite_client.sqlite_conn() as conn:
        job_store.insert(conn, job)

    client.post(
        "/auth/signup",
        json={"email": "publisher@example.com", "password": "Correct-Pass1!"},
    )
    login = client.post(
        "/auth/login",
        json={"email": "publisher@example.com", "password": "Correct-Pass1!"},
    )
    api_key = client.post(
        "/auth/api-keys",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    ).json()["api_key"]

    authed = client.get(
        "/v1/namespaces/public-reports/documents",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    public = client.get("/public/namespaces/public-reports/documents")

    assert authed.status_code == public.status_code == 200
    assert [d["id"] for d in authed.json()] == [d["id"] for d in public.json()] == [job.job_id]


def test_index_a_document_then_query_and_view_its_tree(
    client, initialized_db, fake_spacy_backend
):
    """Simulates the intended end-user flow: index a document's elements,
    then both query it and view its tree via the API, using the graph_id
    the indexer produced."""
    document_payload = {
        "metadata": {"scope": "org"},
        "document": {
            "id": "doc::0",
            "filename": "quarterly-report.pdf",
            "layouts": [
                {
                    "orientation": "PORTRAIT",
                    "elements": [
                        {
                            "type": "Paragraph",
                            "id": "doc::0:layout::0:para::0",
                            "runs": [
                                {"text": "Total revenue grew twelve percent."}
                            ],
                        }
                    ],
                }
            ],
        },
    }

    index_response = client.post("/index/document/elements", json=document_payload)
    assert index_response.status_code == 200
    graph_id = index_response.json()["graph_id"]
    graph_cache.invalidate(graph_id)

    client.post(
        "/auth/signup",
        json={"email": "reader@example.com", "password": "Correct-Pass1!"},
    )
    login = client.post(
        "/auth/login",
        json={"email": "reader@example.com", "password": "Correct-Pass1!"},
    )
    api_key = client.post(
        "/auth/api-keys",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    ).json()["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}

    tree_response = client.get(
        "/v1/tree/json", params={"graph_id": graph_id}, headers=auth_headers
    )
    assert tree_response.status_code == 200
    assert len(tree_response.json()["nodes"]) > 0

    query_response = client.post(
        "/v1/queries",
        json={"graph_ids": [graph_id], "text": "revenue"},
        headers=auth_headers,
    )
    assert query_response.status_code == 200
    assert query_response.json()["total_results"] >= 1


def test_cancel_a_running_job_and_confirm_it_stays_cancelled(client, initialized_db):
    """A job that's picked up (ONGOING) and then cancelled reports
    CANCELLING via the status endpoint, and a second cancel call stays
    idempotent."""
    client.post(
        "/auth/signup",
        json={"email": "canceller@example.com", "password": "Correct-Pass1!"},
    )
    login = client.post(
        "/auth/login",
        json={"email": "canceller@example.com", "password": "Correct-Pass1!"},
    )
    api_key = client.post(
        "/auth/api-keys",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    ).json()["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}

    job = JobModel.new(job_type=JobType.DOCUMENT, filename="slow.pdf")
    with sqlite_client.sqlite_conn() as conn:
        job_store.insert(conn, job)
        job_store.mark_ongoing(conn, job.job_id, "2026-01-01T00:00:00+00:00")

    status_before = client.get(f"/v1/jobs/{job.job_id}", headers=auth_headers)
    assert status_before.json()["state"] == "ONGOING"

    cancel_response = client.post(
        f"/v1/jobs/{job.job_id}/cancel", headers=auth_headers
    )
    assert cancel_response.status_code == 202
    assert cancel_response.json()["state"] == "CANCELLING"

    status_after = client.get(f"/v1/jobs/{job.job_id}", headers=auth_headers)
    assert status_after.json()["state"] == "CANCELLING"

    second_cancel = client.post(f"/v1/jobs/{job.job_id}/cancel", headers=auth_headers)
    assert second_cancel.status_code == 202
    assert second_cancel.json()["state"] == "CANCELLING"
