from typing import List

from pydantic import BaseModel, Field


class SupportedUploadType(BaseModel):
    extension: str = Field(..., description="Lowercase extension, without the dot (e.g. 'pdf')")
    mime_type: str = Field(..., description="Canonical MIME type, for a file picker's accept list")
    max_file_size_mb: int = Field(
        ..., description="Largest accepted file of this type, in MB"
    )


class UploadConstraintsResponse(BaseModel):
    supported_types: List[SupportedUploadType] = Field(
        ..., description="Accepted file types, each with its own size cap"
    )
    max_file_size_mb: int = Field(
        ...,
        description=(
            "Largest cap across all types. An upper bound only - a file within "
            "it can still be rejected by its own type's lower cap, so show the "
            "per-type values rather than this alone."
        ),
    )
