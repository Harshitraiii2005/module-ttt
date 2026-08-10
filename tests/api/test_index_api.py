"""API-level tests for /index (app.api.index).

``POST /index/document/elements`` accepts a full ``DocumentModel`` (a
dataclass with nested layouts/elements) as JSON, which is impractical to
hand-build as a request body in an API-level test - that scenario is
exercised at the unit level instead (see
tests/unit/test_index_route_handlers.py), calling the route coroutine
directly with real, small in-memory model instances. Here we cover request
validation and the GET /index/html route, which only needs a graph_id.
"""

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.models.graph.graph import GraphModel


class TestParseElementValidation:
    def test_missing_body_returns_422(self, client):
        response = client.post("/index/document/elements")
        assert response.status_code == 422

    def test_missing_document_field_returns_422(self, client):
        response = client.post(
            "/index/document/elements",
            json={"metadata": {"scope": "org"}},
        )
        assert response.status_code == 422


class TestViewGraphHtml:
    def test_unknown_graph_id_returns_404(self, client, initialized_db):
        response = client.get("/index/html", params={"graph_id": "graph::nope"})
        assert response.status_code == 404

    def test_known_graph_returns_html_page(self, client, initialized_db):
        gm = GraphModel.create("graph::html-view", directed=True)
        gm.graph.add_node("n1", type="paragraph", text="hello")
        with sqlite_client.sqlite_conn() as conn:
            gm.save(conn)

        response = client.get("/index/html", params={"graph_id": "graph::html-view"})

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "<!DOCTYPE html>" in response.text
        assert '"n1"' in response.text
