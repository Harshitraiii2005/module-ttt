"""Unit-level tests for app.api.index route handlers.

``POST /index/document/elements`` accepts a full ``DocumentModel`` as its
JSON body, which - because ``DocumentModel`` is a nested dataclass with
custom (de)serialization behavior - is impractical to hand-build as a raw
JSON payload for an HTTP-level test (see tests/api/test_index_api.py for
what *is* covered there: request validation and GET /index/html). Here we
call the route coroutines directly with small, real, in-memory model
instances, which exercises the same code the route body runs without
fighting FastAPI's request parsing.
"""

import asyncio

import pytest

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.models.document.document import DocumentModel
from talkingdb.models.document.elements.base.base import RunModel
from talkingdb.models.document.elements.primitive.paragraph import ParagraphModel
from talkingdb.models.document.layouts.layout import LayoutModel
from talkingdb.models.graph.graph import GraphModel
from talkingdb.models.metadata.metadata import Metadata

from app.api.index import parse_element, view_graph
from app.model.index import IndexElementRequest


def _document_with_one_paragraph() -> DocumentModel:
    layout = LayoutModel(
        orientation="PORTRAIT",
        elements=[ParagraphModel(runs=[RunModel(text="Quarterly revenue rose sharply.")])],
    )
    doc = DocumentModel(layouts=[layout], filename="report.pdf")
    doc.assign_ids()
    return doc


def test_parse_element_indexes_document_and_returns_graph_id(
    initialized_db, fake_spacy_backend
):
    request = IndexElementRequest(
        metadata=Metadata(), document=_document_with_one_paragraph()
    )

    response = asyncio.run(parse_element(request))

    assert response["graph_id"].startswith("graph::")
    with sqlite_client.sqlite_conn() as conn:
        reloaded = GraphModel.load(conn, response["graph_id"])
    assert len(reloaded.graph.nodes) > 0


def test_parse_element_defaults_metadata_when_absent(initialized_db, fake_spacy_backend):
    """metadata is a required field on the request model, but the handler
    still runs Metadata.ensure_metadata() on it - covering the explicit
    None branch would require bypassing validation, so this confirms the
    normal (already-populated) path is a no-op passthrough."""
    request = IndexElementRequest(
        metadata=Metadata(scope="org"), document=_document_with_one_paragraph()
    )

    response = asyncio.run(parse_element(request))

    assert "graph_id" in response


def test_view_graph_returns_html_for_existing_graph(initialized_db):
    gm = GraphModel.create("graph::direct-call", directed=True)
    gm.graph.add_node("n1", type="paragraph", text="hello")
    with sqlite_client.sqlite_conn() as conn:
        gm.save(conn)

    html = asyncio.run(view_graph("graph::direct-call"))

    assert "<!DOCTYPE html>" in html
    assert '"n1"' in html


def test_view_graph_raises_404_for_unknown_graph(initialized_db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(view_graph("graph::does-not-exist"))
    assert exc_info.value.status_code == 404
