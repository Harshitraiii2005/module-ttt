from fastapi import HTTPException, status
from talkingdb.models.graph.graph import GraphModel
from talkingdb.clients.sqlite import sqlite_conn

def graph_or_404(graph_id: str) -> GraphModel:
    """Load a graph or raise HTTP 404 if it does not exist."""
    with sqlite_conn() as conn:
        graph = GraphModel.load(conn, graph_id, True)

    if graph.graph.number_of_nodes() == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "GRAPH_NOT_FOUND",
                "message": f"Unknown graph id: {graph_id}",
            },
        )

    return graph