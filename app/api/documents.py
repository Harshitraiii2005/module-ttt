from typing import List, Optional
import mimetypes

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
    Request
)

from fastapi.responses import StreamingResponse
from talkingdb.clients.sqlite import sqlite_conn
from talkingdb.helpers import spool
from talkingdb.helpers.release_channel import get_release_channel
from talkingdb.helpers import file_store
from talkingdb.helpers.file_graph import store as file_graph_store
from talkingdb.helpers.auth import verify_api_key
from talkingdb.helpers.graph import store as graph_store
from talkingdb.helpers.graph_cache import graph_cache
from talkingdb.helpers.job import store as job_store
from talkingdb.helpers.validation import (
    validate_file_type,
    max_file_size_bytes_for,
    max_file_size_mb_for,
)
from talkingdb.models.api.response import ErrorResponse
from talkingdb.models.job.job import JobModel
from talkingdb.models.job.type import JobType
from talkingdb.models.metadata.metadata import DEFAULT_METADATA

from app.api.validators import (
    clean_optional_text,
    parse_suggested_queries,
    validate_namespace,
)
from app.core import config as job_config
from app.model.jobs import JobAcceptedResponse, JobStatusResponse
from app.services import jobs


router = APIRouter(prefix="/v1", tags=["Jobs"])


@router.post(
    "/documents",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a document for asynchronous indexing",
    description=(
        "Upload a document for asynchronous indexing. Returns immediately "
        "with a stable ``job_id`` that can be polled at "
        "``GET /v1/jobs/{job_id}`` and cancelled at "
        "``POST /v1/jobs/{job_id}/cancel``."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        413: {"model": ErrorResponse, "description": "File exceeds maximum allowed size"},
        415: {"model": ErrorResponse, "description": "Unsupported file type"},
        429: {"model": ErrorResponse, "description": "Worker queue is full"},
        503: {"model": ErrorResponse, "description": "Spool storage exhausted"},
    },
)
async def submit_document_job(
    request: Request,
    file: UploadFile = File(..., description="The document file to upload (.docx or .pdf)"),
    metadata: Optional[str] = Form(DEFAULT_METADATA, description="JSON metadata string"),
    session_id: Optional[str] = Form(
        None, description="Session to group this document with others"
    ),
    namespace: Optional[str] = Form(
        None,
        description=(
            "Curated library namespace (e.g. 'demo-library'). Omit for ordinary "
            "user uploads. Must already exist when provided."
        ),
    ),
    title: Optional[str] = Form(
        None, description="Curated document title; defaults to the filename"
    ),
    description: Optional[str] = Form(
        None, description="Short curated description shown in demo listings"
    ),
    suggested_queries: Optional[List[str]] = Form(
        None,
        description=(
            "Curated example queries for this document; add up to 5."
        ),
    ),
    api_key: str = Depends(verify_api_key),
) -> JobAcceptedResponse:
    """Submit a document ingestion job for background processing."""
    ext = validate_file_type(file)

    namespace = validate_namespace(namespace)
    parsed_queries = parse_suggested_queries(suggested_queries)
    title = clean_optional_text(title)
    description = clean_optional_text(description)

    spool.assert_spool_capacity()

    try:
        jobs.acquire_slot()
    except jobs.QueueFull:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "QUEUE_FULL",
                "error_code": "QUEUE_FULL",
                "message": "Ingestion worker pool is at capacity",
                "retry_after_seconds": job_config.RETRY_AFTER_SECONDS,
            },
            headers={"Retry-After": str(job_config.RETRY_AFTER_SECONDS)},
        )

    temp_path: Optional[str] = None
    enqueued = False
    try:
        temp_path, size_bytes = await spool.spool_upload(
            file,
            max_size_mb=max_file_size_mb_for(ext),
            max_size_bytes=max_file_size_bytes_for(ext),
        )
        
        metadata_json = metadata if metadata else DEFAULT_METADATA
        job = JobModel.new(
            job_type=JobType.DOCUMENT,
            filename=file.filename,
            session_id=session_id,
            namespace=namespace,
            title=title,
            description=description,
            suggested_queries=parsed_queries,
        )
        job.file_size_bytes = size_bytes
        job.temp_path = temp_path
        
        channel = get_release_channel(request)
        file_hash = file_store.compute_md5(temp_path)
        file_store.upload_file(channel, file_hash, temp_path)

        with sqlite_conn() as conn:
            job_store.insert(conn, job)
            file_graph_store.insert(
                conn,
                channel=channel,
                file_hash=file_hash,
                job_id=job.job_id,
                filename=file.filename,
            )

        jobs.enqueue_reserved(
            job_id=job.job_id,
            temp_path=temp_path,
            filename=file.filename or f"upload.{ext}",
            metadata_json=metadata_json,
        )
        enqueued = True

        return JobAcceptedResponse(
            job_id=job.job_id,
            job_type=job.job_type.value,
            session_id=job.session_id,
            state=job.state.value,
        )

    finally:
        if not enqueued:
            spool.discard(temp_path)
            jobs.release_slot()


@router.get(
    "/documents",
    response_model=List[JobStatusResponse],
    summary="List documents",
    description="List documents, newest first, optionally filtered by session. Paginated.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
    },
)
async def list_documents(
    session_id: Optional[str] = Query(None, description="Filter by session"),
    limit: int = Query(50, ge=1, le=500, description="Max documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
    api_key: str = Depends(verify_api_key),
) -> List[JobStatusResponse]:
    with sqlite_conn() as conn:
        items = job_store.list_documents(conn, session_id, limit=limit, offset=offset)
    return [JobStatusResponse(**job.to_status_payload()) for job in items]


@router.delete(
    "/documents/{job_id}",
    response_model=JobStatusResponse,
    summary="Remove a document",
    description="Remove a single document. Cancels it first if still processing.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        404: {"model": ErrorResponse, "description": "Unknown job id"},
    },
)
async def remove_document(
    job_id: str = Path(..., description="Document (job) id to remove"),
    api_key: str = Depends(verify_api_key),
) -> JobStatusResponse:
    deleted = False
    graph_id: Optional[str] = None

    file_to_delete: Optional[tuple[str, str]] = None

    with sqlite_conn() as conn:
        job = job_store.get(conn, job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "JOB_NOT_FOUND", "message": f"Unknown job id: {job_id}"},
            )

        # Cancel first if still running; decide what to delete from the
        # *post-cancel* state so the response and cleanup never race the worker.
        final = job if job.is_terminal() else (job_store.request_cancel(conn, job_id) or job)

        if final.is_terminal():
            graph_id = final.result_graph_id
            if graph_id:
                graph_store.delete(conn, graph_id)
            job_store.delete(conn, job_id)

            mapping = file_graph_store.get_by_job_id(conn, job_id)
            if mapping is not None:
                file_graph_store.delete_by_job_id(conn, job_id)
                remaining = file_graph_store.get_by_channel_hash(
                    conn, mapping.channel, mapping.file_hash)
                if not remaining:
                    file_to_delete = (mapping.channel, mapping.file_hash)

            deleted = True

    if deleted:
        if graph_id:
            graph_cache.invalidate(graph_id)
        spool.discard(job.temp_path)
        if file_to_delete is not None:
            file_store.delete_file(*file_to_delete)

    return JobStatusResponse(**final.to_status_payload())


@router.get(
    "/documents/{graph_id}/file",
    summary="Download the original uploaded file",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        404: {"model": ErrorResponse, "description": "No file found for this graph"},
    },
)
async def get_document_file(
    graph_id: str = Path(..., description="Graph id returned from a completed job"),
    api_key: str = Depends(verify_api_key),
) -> StreamingResponse:
    with sqlite_conn() as conn:
        mapping = file_graph_store.get_by_graph_id(conn, graph_id)

    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "FILE_NOT_FOUND",
                "message": f"No file found for graph_id: {graph_id}",
            },
        )

    stream = file_store.get_file_stream(mapping.channel, mapping.file_hash)
    if stream is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "FILE_NOT_FOUND", "message": "File missing from storage"},
        )

    filename = mapping.filename or mapping.file_hash
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    def _iter_and_close():
        try:
            for chunk in stream.stream(32 * 1024):
                yield chunk
        finally:
            stream.close()
            stream.release_conn()

    return StreamingResponse(
        _iter_and_close(),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )