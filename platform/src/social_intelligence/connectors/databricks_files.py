"""Minimal Databricks Files API client for external connector workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class DatabricksFilesError(RuntimeError):
    """Sanitized Files API failure that never includes bearer credentials."""

    def __init__(self, status: int | None, operation: str, path: str) -> None:
        super().__init__(
            f"Databricks Files API {operation} failed "
            f"({status or 'network'}) for {path}"
        )
        self.status = status


Opener = Callable[..., object]


@dataclass(frozen=True)
class DatabricksFilesClient:
    """Read and overwrite files in a Unity Catalog volume."""

    host: str
    token: str
    timeout_seconds: int = 30
    opener: Opener = urlopen

    def __post_init__(self) -> None:
        normalized_host = self.host.strip().rstrip("/")
        if not normalized_host.startswith("https://"):
            raise ValueError("DATABRICKS_HOST must use https://")
        if not self.token.strip():
            raise ValueError("DATABRICKS_TOKEN is required")
        if not 1 <= self.timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be between 1 and 300")
        object.__setattr__(self, "host", normalized_host)

    def download(self, path: str) -> bytes | None:
        """Return file bytes, or ``None`` when the path does not exist."""
        request = Request(
            self._url(path),
            method="GET",
            headers=self._headers("application/octet-stream"),
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                return response.read()
        except HTTPError as error:
            if error.code == 404:
                return None
            raise DatabricksFilesError(error.code, "download", path) from error
        except URLError as error:
            raise DatabricksFilesError(None, "download", path) from error

    def upload(self, path: str, content: bytes) -> None:
        """Create or atomically replace a volume file through the Files API."""
        request = Request(
            f"{self._url(path)}?overwrite=true",
            data=content,
            method="PUT",
            headers=self._headers("application/octet-stream"),
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                response.read()
        except HTTPError as error:
            raise DatabricksFilesError(error.code, "upload", path) from error
        except URLError as error:
            raise DatabricksFilesError(None, "upload", path) from error

    def create_directory(self, path: str) -> None:
        """Create a directory and missing parents using idempotent mkdir semantics."""
        request = Request(
            self._url(path, resource="directories"),
            data=b"",
            method="PUT",
            headers=self._headers("application/octet-stream"),
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                response.read()
        except HTTPError as error:
            raise DatabricksFilesError(error.code, "create directory", path) from error
        except URLError as error:
            raise DatabricksFilesError(None, "create directory", path) from error

    def _url(self, path: str, *, resource: str = "files") -> str:
        normalized_path = path.strip()
        if not normalized_path.startswith("/Volumes/"):
            raise ValueError("Files API path must start with /Volumes/")
        if any(part in {"", ".", ".."} for part in normalized_path.split("/")[1:]):
            raise ValueError("Files API path contains an unsafe segment")
        if resource not in {"files", "directories"}:
            raise ValueError(f"Unsupported Files API resource: {resource}")
        encoded_path = quote(normalized_path.lstrip("/"), safe="/")
        return f"{self.host}/api/2.0/fs/{resource}/{encoded_path}"

    def _headers(self, content_type: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": content_type,
            "User-Agent": "social-intelligence-external-collector/1.0",
        }
