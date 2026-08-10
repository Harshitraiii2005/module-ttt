
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from talkingdb.models.metadata.metadata import Metadata
from app.services.indexer import IndexerService
from app.services.graph import graph_or_404
from app.services.graph_html import render_graph_html
from app.model.index import IndexElementRequest
router = APIRouter(prefix="/index", tags=["Indexer"])


@router.post("/document/elements")
async def parse_element(request: IndexElementRequest):

    metadata = request.metadata
    metadata = Metadata.ensure_metadata(metadata)
    file_index = request.document.build_index()

    indexer = IndexerService()
    index = indexer.graph_file_index(file_index)
    index = indexer.index_document(request.document)

    return {"graph_id": index.graph_id}


@router.get("/html", response_class=HTMLResponse)
async def view_graph(graph_id: str):
    gm = graph_or_404(graph_id)
    html = render_graph_html(gm.g_json())
    return html
