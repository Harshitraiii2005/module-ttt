"""Unit tests for app.services.indexer.IndexerService.

Uses small, real (not mocked) talkingdb document/graph model instances so
the graph-building logic - node/edge shapes, symbol generation, threading,
persistence - is exercised end to end against a real temp SQLite file.
Table indexing (_process_table / _process_table_row) involves nontrivial
header-detection machinery upstream in talkingdb.models.document; those
paths are intentionally out of scope here and covered indirectly through
the paragraph + key/value-line paths, which share the same node/edge
plumbing.
"""

import pytest

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.models.document.document import DocumentModel
from talkingdb.models.document.elements.base.base import RunModel
from talkingdb.models.document.elements.primitive.paragraph import ParagraphModel
from talkingdb.models.document.indexes.index import FileIndexModel, IndexItem, IndexType
from talkingdb.models.document.layouts.layout import LayoutModel

from app.services.indexer import IndexerService


def _paragraph(text: str, *, is_heading: bool = False, heading_level: int | None = None) -> ParagraphModel:
    return ParagraphModel(
        runs=[RunModel(text=text)],
        is_heading=is_heading,
        heading_level=heading_level,
    )


def _document(*paragraphs: ParagraphModel, filename: str = "report.pdf") -> DocumentModel:
    layout = LayoutModel(orientation="PORTRAIT", elements=list(paragraphs))
    doc = DocumentModel(layouts=[layout], filename=filename)
    doc.assign_ids()
    return doc


@pytest.fixture
def indexer(initialized_db, fake_spacy_backend):
    return IndexerService(max_workers=2)


class TestGraphFileIndex:
    def test_builds_tree_with_root_and_children(self, indexer, initialized_db):
        child = IndexItem(id="idx-2", label="Section 1.1", index=IndexType.PARA)
        top = IndexItem(id="idx-1", label="Section 1", index=IndexType.OUTLINE, child=[child])
        file_index = FileIndexModel(id="idx-root", filename="report.pdf", nodes=[top])

        result = indexer.graph_file_index(file_index)

        node_ids = set(result.graph.nodes)
        assert node_ids == {"idx-root", "idx-1", "idx-2"}
        assert result.graph.has_edge("idx-root", "idx-1")
        assert result.graph.has_edge("idx-1", "idx-2")

    def test_reports_progress_for_every_node(self, indexer, initialized_db):
        top = IndexItem(id="idx-1", label="Section 1", index=IndexType.OUTLINE)
        file_index = FileIndexModel(id="idx-root", filename="report.pdf", nodes=[top])
        calls = []

        indexer.graph_file_index(file_index, progress=lambda done, total: calls.append((done, total)))

        assert calls[0] == (0, 1)
        assert calls[-1] == (1, 1)

    def test_persists_graph_to_sqlite(self, indexer, initialized_db):
        from talkingdb.models.graph.graph import GraphModel

        top = IndexItem(id="idx-1", label="Section 1", index=IndexType.OUTLINE)
        file_index = FileIndexModel(id="idx-root", filename="report.pdf", nodes=[top])

        result = indexer.graph_file_index(file_index)

        with sqlite_client.sqlite_conn() as conn:
            reloaded = GraphModel.load(conn, result.graph_id)
        assert set(reloaded.graph.nodes) == {"idx-root", "idx-1"}


class TestIndexDocumentParagraphs:
    def test_paragraph_becomes_a_node_with_text_and_metadata(self, indexer, initialized_db):
        doc = _document(_paragraph("The quarterly revenue grew significantly."))
        [para] = list(doc.iter_elements())

        result = indexer.index_document(doc)

        with sqlite_client.sqlite_conn() as conn:
            from talkingdb.models.graph.graph import GraphModel
            reloaded = GraphModel.load(conn, result.graph_id)
        assert reloaded.graph.nodes[para.id]["type"] == "paragraph"
        assert "revenue" in reloaded.graph.nodes[para.id]["text"].lower()

    def test_paragraph_text_produces_symbol_nodes_linked_to_it(self, indexer, initialized_db):
        doc = _document(_paragraph("Total revenue was strong."))
        [para] = list(doc.iter_elements())

        result = indexer.index_document(doc)

        with sqlite_client.sqlite_conn() as conn:
            from talkingdb.models.graph.graph import GraphModel
            reloaded = GraphModel.load(conn, result.graph_id)
        successors = list(reloaded.graph.neighbors(para.id))
        assert len(successors) > 0
        for symbol in successors:
            assert reloaded.graph.nodes[symbol]["type"] in {"unigram", "bigram", "trigram", "key", "value"}

    def test_key_value_line_creates_key_and_value_nodes(self, indexer, initialized_db):
        doc = _document(_paragraph("Author: Jane Doe"))
        [para] = list(doc.iter_elements())

        result = indexer.index_document(doc)

        with sqlite_client.sqlite_conn() as conn:
            from talkingdb.models.graph.graph import GraphModel
            reloaded = GraphModel.load(conn, result.graph_id)
        node_types = {n: d.get("type") for n, d in reloaded.graph.nodes(data=True)}
        key_nodes = [n for n, t in node_types.items() if t == "key"]
        value_nodes = [n for n, t in node_types.items() if t == "value"]
        assert key_nodes and value_nodes
        assert reloaded.graph.has_edge(para.id, key_nodes[0])
        assert reloaded.graph.has_edge(key_nodes[0], value_nodes[0])

    def test_multiple_paragraphs_are_all_indexed(self, indexer, initialized_db):
        doc = _document(
            _paragraph("First paragraph about apples."),
            _paragraph("Second paragraph about oranges."),
        )
        paragraphs = list(doc.iter_elements())

        result = indexer.index_document(doc)

        with sqlite_client.sqlite_conn() as conn:
            from talkingdb.models.graph.graph import GraphModel
            reloaded = GraphModel.load(conn, result.graph_id)
        for para in paragraphs:
            assert para.id in reloaded.graph.nodes

    def test_progress_callback_reaches_total_at_completion(self, indexer, initialized_db):
        doc = _document(_paragraph("Just one paragraph."))
        calls = []

        indexer.index_document(doc, progress=lambda done, total: calls.append((done, total)))

        assert calls[0][0] == 0
        assert calls[-1][0] == calls[-1][1]

    def test_empty_document_produces_empty_graph_without_error(self, indexer, initialized_db):
        doc = _document()

        result = indexer.index_document(doc)

        assert len(result.graph.nodes) == 0

    def test_clears_in_memory_graph_after_persisting(self, indexer, initialized_db):
        doc = _document(_paragraph("Some text."))

        indexer.index_document(doc)

        assert len(indexer.gm.graph.nodes) == 0
