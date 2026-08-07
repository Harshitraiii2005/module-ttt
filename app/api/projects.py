import base64
import hashlib
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from talkingdb.clients.sqlite import sqlite_conn
from talkingdb.helpers.auth import verify_api_key
from talkingdb.helpers.job import store as job_store
from talkingdb.helpers.logo import validate_logo
from talkingdb.helpers.project import store as project_store
from talkingdb.models.api.response import ErrorResponse

from app.api.validators import validate_project_name, validate_project_owned
from app.core import config
from app.model.jobs import JobStatusResponse
from app.model.projects import (
    ProjectCreateRequest,
    ProjectResponse,
    ProjectTreeItem,
    ProjectTreeResponse,
)

router = APIRouter(prefix="/v1", tags=["Projects"])


# --------------------------------------------------------------------- helpers
def _logo_url(project: Dict[str, Any]) -> Optional[str]:
    if not project.get("logo"):
        return None
    return f"/v1/projects/{project['project_id']}/logo"


def _to_response(
    project: Dict[str, Any], stats: Dict[Optional[str], Dict[str, Any]]
) -> Dict[str, Any]:
    entry = stats.get(project["project_id"]) or {}
    return {
        "project_id": project["project_id"],
        "name": project["name"],
        "logo_url": _logo_url(project),
        "document_count": entry.get("document_count", 0),
        "last_interaction_at": entry.get("last_interaction_at")
        or project["created_at"],
        "created_at": project["created_at"],
    }


# --------------------------------------------------------------------- routes
@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
    description=(
        "Create a private project owned by the authenticated caller. Name and "
        "logo are supplied together in one request. The project starts with no "
        "documents; upload with ``project_id`` to fill it."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        409: {"model": ErrorResponse, "description": "Duplicate project name"},
        422: {"model": ErrorResponse, "description": "Invalid name or logo"},
    },
)
async def create_project(
    payload: ProjectCreateRequest,
    owner_email: str = Depends(verify_api_key),
) -> ProjectResponse:
    name = validate_project_name(payload.name)
    logo, logo_media_type = validate_logo(payload.logo)

    with sqlite_conn() as conn:
        try:
            project = project_store.create(
                conn,
                name=name,
                logo=logo,
                logo_media_type=logo_media_type,
                owner_email=owner_email,
            )
        except sqlite3.IntegrityError as exc:
            if exc.sqlite_errorcode != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise
            # Relies on the unique index rather than a pre-check, so two
            # concurrent creates cannot both see "available" and both insert.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "PROJECT_NAME_TAKEN",
                    "message": f"You already have a project named: {name}",
                },
            ) from exc

    return ProjectResponse(**_to_response(project, {}))


@router.get(
    "/projects",
    response_model=List[ProjectResponse],
    summary="List projects",
    description=(
        "List the projects owned by the authenticated caller, newest first, each "
        "with its document count and last-interaction timestamp. Returns an "
        "empty list -- never a 404 -- when the caller has no projects."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
    },
)
async def list_projects(
    limit: int = Query(10, ge=1, le=200, description="Max projects to return"),
    offset: int = Query(0, ge=0, description="Number of projects to skip"),
    owner_email: str = Depends(verify_api_key),
) -> List[ProjectResponse]:
    with sqlite_conn() as conn:
        projects = project_store.list_for_owner(
            conn, owner_email, limit=limit, offset=offset
        )
        stats = job_store.owner_document_stats(conn, owner_email)
    return [ProjectResponse(**_to_response(p, stats)) for p in projects]


@router.get(
    "/projects/tree",
    response_model=ProjectTreeResponse,
    summary="List the caller's documents as a hierarchy",
    description=(
        "The caller's documents in two levels: ``documents`` holds root-level "
        "documents that belong to no project, and ``projects`` holds each "
        "project with its own documents nested inside. Documents per project are "
        "capped; ``document_count`` remains the true total."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
    },
)
async def list_project_tree(
    limit: int = Query(10, ge=1, le=200, description="Max projects to return"),
    offset: int = Query(0, ge=0, description="Number of projects to skip"),
    owner_email: str = Depends(verify_api_key),
) -> ProjectTreeResponse:
    with sqlite_conn() as conn:
        projects = project_store.list_for_owner(
            conn, owner_email, limit=limit, offset=offset
        )
        stats = job_store.owner_document_stats(conn, owner_email)
        documents = job_store.list_owner_documents(
            conn, owner_email, per_project=config.TREE_DOCS_PER_PROJECT
        )

    grouped: Dict[Optional[str], List[JobStatusResponse]] = {}
    for job in documents:
        grouped.setdefault(job.project_id, []).append(
            JobStatusResponse(**job.to_status_payload())
        )

    return ProjectTreeResponse(
        documents=grouped.get(None, []),
        projects=[
            ProjectTreeItem(
                **_to_response(p, stats),
                documents=grouped.get(p["project_id"], []),
            )
            for p in projects
        ],
    )


@router.get(
    "/projects/{project_id}/logo",
    summary="Fetch a project's logo",
    description=(
        "Return the project's logo bytes with the stored media type. Served "
        "under a restrictive Content-Security-Policy so an SVG cannot execute "
        "even if it slipped past sanitisation on write."
    ),
    responses={
        200: {"content": {"image/*": {}}, "description": "Logo bytes"},
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        404: {"model": ErrorResponse, "description": "Unknown project or no logo"},
    },
)
async def get_project_logo(
    project_id: str = Path(..., description="Project id"),
    owner_email: str = Depends(verify_api_key),
) -> Response:
    project = validate_project_owned(project_id, owner_email)

    if not project["logo"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "LOGO_NOT_FOUND",
                "message": f"Project has no logo: {project_id}",
            },
        )

    raw = base64.b64decode(project["logo"])

    return Response(
        content=raw,
        media_type=project["logo_media_type"] or "application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=3600",
            "ETag": f'"{hashlib.sha256(raw).hexdigest()[:32]}"',
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
        },
    )
