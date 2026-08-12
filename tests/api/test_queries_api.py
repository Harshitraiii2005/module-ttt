"""API-level tests for /v1/queries (app.api.queries).

ExtractorService builds a real TextTokenizer, so these tests use the
``fake_spacy_backend`` fixture (see tests/conftest.py) to avoid depending on
a downloaded spaCy language model.

``talkingdb.helpers.graph_cache.graph_cache`` is a process-wide singleton
that caches GraphModel instances by graph_id across tests, so every test
here uses a fresh, randomly-suffixed graph_id to avoid cross-test leakage.
"""

import uuid

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.helpers.graph_cache import graph_cache
from talkingdb.models.graph.graph import GraphModel


def _unique_graph_id(label: str) -> str:
    return f"graph::{label}-{uuid.uuid4().hex}"


def _save_graph_with_symbol(graph_id: str, symbol: str, element_text: str) -> None:
    """Build a minimal graph: one unigram symbol node connected to one paragraph."""
    gm = GraphModel.create(graph_id, directed=True)
    gm.graph.add_node(
        "elem-1", type="paragraph", text=element_text, metadata={}
    )
    gm.graph.add_node(symbol, type="unigram")
    gm.graph.add_edge(symbol, "elem-1", type="contains")
    with sqlite_client.sqlite_conn() as conn:
        gm.save(conn)
    graph_cache.invalidate(graph_id)


class TestQueryDocuments:
    def test_requires_auth(self, client, initialized_db):
        response = client.post(
            "/v1/queries", json={"graph_ids": ["graph::x"], "text": "revenue"}
        )
        assert response.status_code in (401, 403)

    def test_validation_error_on_empty_text(self, client, auth_headers):
        response = client.post(
            "/v1/queries",
            json={"graph_ids": ["graph::x"], "text": ""},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_validation_error_on_empty_graph_ids(self, client, auth_headers):
        response = client.post(
            "/v1/queries",
            json={"graph_ids": [], "text": "revenue"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_unknown_graph_id_yields_no_matches_rather_than_erroring(
        self, client, auth_headers, initialized_db, fake_spacy_backend
    ):
        """GraphModel.load() returns an empty graph for an unknown id rather
        than raising, so ExtractorService treats it as "nothing indexed
        yet" (0 results) instead of a 404. Documents actual behavior."""
        response = client.post(
            "/v1/queries",
            json={"graph_ids": [_unique_graph_id("missing")], "text": "revenue"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["total_results"] == 0

    def test_matching_query_returns_scored_elements(
        self, client, auth_headers, initialized_db, fake_spacy_backend
    ):
        graph_id = _unique_graph_id("revenue-doc")
        _save_graph_with_symbol(graph_id, "revenue", "Total revenue was $4.2M this quarter.")

        response = client.post(
            "/v1/queries",
            json={"graph_ids": [graph_id], "text": "revenue"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "revenue"
        assert body["graph_ids"] == [graph_id]
        assert body["total_results"] == 1
        assert body["elements"][0]["id"] == "elem-1"
        assert body["elements"][0]["graph_id"] == graph_id
        assert body["elements"][0]["score"] > 0

    def test_non_matching_query_returns_no_results(
        self, client, auth_headers, initialized_db, fake_spacy_backend
    ):
        graph_id = _unique_graph_id("revenue-doc")
        _save_graph_with_symbol(graph_id, "revenue", "Total revenue was $4.2M this quarter.")

        response = client.post(
            "/v1/queries",
            json={"graph_ids": [graph_id], "text": "zzzznomatch"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["total_results"] == 0

    def test_max_results_caps_returned_elements(
        self, client, auth_headers, initialized_db, fake_spacy_backend
    ):
        graph_id = _unique_graph_id("multi-doc")
        gm = GraphModel.create(graph_id, directed=True)
        for i in range(5):
            gm.graph.add_node(f"elem-{i}", type="paragraph", text=f"revenue figure {i}", metadata={})
            gm.graph.add_edge("revenue", f"elem-{i}", type="contains")
        gm.graph.add_node("revenue", type="unigram")
        with sqlite_client.sqlite_conn() as conn:
            gm.save(conn)
        graph_cache.invalidate(graph_id)

        response = client.post(
            "/v1/queries",
            json={"graph_ids": [graph_id], "text": "revenue", "max_results": 2},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert len(response.json()["elements"]) == 2


class TestQueryErrorHandling:
    """Exercise the three except branches in app.api.queries.query_documents
    by making ExtractorService.extract raise each exception type."""

    def test_key_error_from_extractor_becomes_404(
        self, client, auth_headers, initialized_db, monkeypatch
    ):
        import app.services.extractor as extractor_module

        def _boom(self, query):
            raise KeyError("graph::missing")

        monkeypatch.setattr(extractor_module.ExtractorService, "extract", _boom)

        response = client.post(
            "/v1/queries",
            json={"graph_ids": ["graph::x"], "text": "revenue"},
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["error_code"] == "GRAPH_NOT_FOUND"

    def test_file_not_found_from_extractor_becomes_404(
        self, client, auth_headers, initialized_db, monkeypatch
    ):
        import app.services.extractor as extractor_module

        def _boom(self, query):
            raise FileNotFoundError("graph::x")

        monkeypatch.setattr(extractor_module.ExtractorService, "extract", _boom)

        response = client.post(
            "/v1/queries",
            json={"graph_ids": ["graph::x"], "text": "revenue"},
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["error_code"] == "GRAPH_NOT_FOUND"

    def test_unexpected_exception_from_extractor_becomes_500(
        self, client, auth_headers, initialized_db, monkeypatch
    ):
        import app.services.extractor as extractor_module

        def _boom(self, query):
            raise RuntimeError("something unexpected")

        monkeypatch.setattr(extractor_module.ExtractorService, "extract", _boom)

        response = client.post(
            "/v1/queries",
            json={"graph_ids": ["graph::x"], "text": "revenue"},
            headers=auth_headers,
        )

        assert response.status_code == 500
        assert response.json()["detail"]["error_code"] == "QUERY_ERROR"
