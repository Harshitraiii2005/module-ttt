import json
from typing import Iterable

from talkingdb.helpers.validation import content_length_over_every_cap


class UploadSizeLimitMiddleware:
    def __init__(self, app, paths: Iterable[str] = ("/v1/documents",)) -> None:
        self.app = app
        self.paths = frozenset(paths)

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in self.paths
        ):
            await self.app(scope, receive, send)
            return

        content_length = None
        for name, value in scope.get("headers", ()):
            if name == b"content-length":
                content_length = value.decode("latin-1")
                break

        cap_mb = content_length_over_every_cap(content_length)
        if cap_mb is None:
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {
                "detail": {
                    "error_code": "FILE_TOO_LARGE",
                    "message": f"File exceeds the maximum allowed size ({cap_mb}MB)",
                    "max_file_size_mb": cap_mb,
                }
            }
        ).encode()

        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
