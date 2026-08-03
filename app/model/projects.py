from typing import List, Optional

from pydantic import BaseModel, Field

from app.model.jobs import JobStatusResponse


class ProjectCreateRequest(BaseModel):
    name: str = Field(
        ...,
        description="Project name.",
    )
    logo: str = Field(
        ...,
        description=(
            "Logo as a base64 data URI."
        ),
    )


class ProjectResponse(BaseModel):
    project_id: str = Field(..., description="Stable project id")
    name: str = Field(..., description="Project name")
    logo_url: Optional[str] = Field(
        None,
        description=(
            "Path to this project's logo bytes; null when the project has no "
            "logo. Fetch rather than expecting inline image data."
        ),
    )
    document_count: int = Field(
        ...,
        description="Documents filed under this project. 0 for a new project.",
    )
    last_interaction_at: Optional[str] = Field(
        None,
        description=(
            "Newest document timestamp for this project, falling back to the "
            "project's creation time while it is still empty."
        ),
    )
    created_at: str = Field(..., description="When the project was created")


class ProjectTreeItem(ProjectResponse):
    documents: List[JobStatusResponse] = Field(
        default_factory=list,
        description=(
            "Newest documents in this project, capped per project. "
            "``document_count`` remains the true total."
        ),
    )


class ProjectTreeResponse(BaseModel):
    documents: List[JobStatusResponse] = Field(
        default_factory=list,
        description="Root-level documents: owned by the caller, in no project.",
    )
    projects: List[ProjectTreeItem] = Field(
        default_factory=list,
        description="The caller's projects, each with its documents nested.",
    )
