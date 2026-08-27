"""
Storage service for FinSentry AI (Phase 2B).

Provides file system management with multi-tenant directory isolation,
filename sanitization, and size/format validation.
"""

import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Optional

from core.config import get_settings
from core.exceptions import InvalidDocumentException

logger = logging.getLogger(__name__)


class StorageService:
    """
    Manages physical storage of uploaded research documents.
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        settings = get_settings()
                                                         
        if base_dir:
            self.base_path = Path(base_dir).resolve()
        else:
            backend_root = Path(__file__).resolve().parent.parent
            self.base_path = (backend_root / settings.STORAGE_DIR).resolve()

        self.base_path.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = settings.MAX_DOCUMENT_SIZE_BYTES
        self.allowed_extensions = {ext.lower() for ext in settings.ALLOWED_DOCUMENT_EXTENSIONS}

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize an uploaded filename to prevent directory traversal and illegal characters.
        """
        clean = os.path.basename(filename).strip()
                                                       
        clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', clean)
                                     
        if not clean or clean.startswith('.'):
            clean = f"document_{clean.lstrip('.')}"
        return clean

    def validate_file(self, filename: str, content: bytes) -> None:
        """
        Validate file extension and size constraints.
        """
        ext = Path(filename).suffix.lower()
        if ext not in self.allowed_extensions:
            raise InvalidDocumentException(
                f"File extension '{ext}' is not supported. "
                f"Allowed formats: {', '.join(sorted(self.allowed_extensions))}"
            )

        if len(content) == 0:
            raise InvalidDocumentException("Cannot upload an empty file.")

        if len(content) > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            raise InvalidDocumentException(
                f"File exceeds maximum allowed size of {max_mb:.0f} MB."
            )

    def detect_mime_type(self, filename: str) -> str:
        """Detect MIME type from filename extension with explicit standard mappings."""
        ext = Path(filename).suffix.lower()
        mapping = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".json": "application/json",
        }
        if ext in mapping:
            return mapping[ext]
        mime, _ = mimetypes.guess_type(filename)
        return mime or "application/octet-stream"

    def get_document_path(
        self, user_id: str, session_id: str, document_id: str, filename: str
    ) -> Path:
        """
        Generate tenant-isolated target path:
        uploads/{user_id}/{session_id}/{document_id}_{sanitized_filename}
        """
        safe_user = self.sanitize_filename(user_id)
        safe_session = self.sanitize_filename(session_id)
        safe_name = self.sanitize_filename(filename)

        dir_path = self.base_path / safe_user / safe_session
        dir_path.mkdir(parents=True, exist_ok=True)

        return dir_path / f"{document_id}_{safe_name}"

    def save_file(
        self, user_id: str, session_id: str, document_id: str, filename: str, content: bytes
    ) -> str:
        """
        Validate and save uploaded file to isolated storage path.

        Returns the string path relative to the storage base directory.
        """
        self.validate_file(filename, content)
        target_path = self.get_document_path(user_id, session_id, document_id, filename)

        with open(target_path, "wb") as f:
            f.write(content)

        logger.info(
            "Saved document %s (%d bytes) to %s",
            document_id,
            len(content),
            target_path,
        )
        return str(target_path)

    def read_file(self, storage_path: str) -> bytes:
        """
        Read file contents from storage path (handles absolute paths, relative paths,
        and Windows/POSIX separator differences).
        """
        if not storage_path:
            raise InvalidDocumentException("File not found on storage disk.")

        path = Path(storage_path)
        if not path.is_absolute():
                                                  
            candidate1 = (self.base_path / storage_path).resolve()
            if candidate1.exists() and candidate1.is_file():
                path = candidate1
            else:
                                                                                            
                candidate2 = (self.base_path.parent / storage_path).resolve()
                if candidate2.exists() and candidate2.is_file():
                    path = candidate2

        if not path.exists() or not path.is_file():
            raise InvalidDocumentException("File not found on storage disk.")

        with open(path, "rb") as f:
            return f.read()

    def get_document_bytes_by_id(
        self, user_id: str, session_id: str, document_id: str, filename: str
    ) -> Optional[bytes]:
        """
        Retrieve document binary content by tenant parameters if present on disk.
        """
        target_path = self.get_document_path(user_id, session_id, document_id, filename)
        if target_path.exists() and target_path.is_file():
            with open(target_path, "rb") as f:
                return f.read()

                                                                                  
        safe_user = self.sanitize_filename(user_id)
        safe_session = self.sanitize_filename(session_id)
        dir_path = self.base_path / safe_user / safe_session
        if dir_path.exists() and dir_path.is_dir():
            for child in dir_path.iterdir():
                if child.is_file() and child.name.startswith(f"{document_id}_"):
                    with open(child, "rb") as f:
                        return f.read()

        return None

    def delete_file(self, storage_path: str) -> bool:
        """
        Delete file from disk if it exists.
        """
        try:
            path = Path(storage_path)
            if not path.is_absolute():
                candidate = (self.base_path / storage_path).resolve()
                if candidate.exists():
                    path = candidate
                else:
                    candidate2 = (self.base_path.parent / storage_path).resolve()
                    if candidate2.exists():
                        path = candidate2

            if path.exists() and path.is_file():
                path.unlink()
                logger.info("Deleted document file at %s", path)
                return True
        except Exception as exc:
            logger.warning("Failed to delete file at %s: %s", storage_path, exc)
        return False

    def file_exists(self, storage_path: str) -> bool:
        """Check if file exists on disk."""
        if not storage_path:
            return False
        path = Path(storage_path)
        if path.is_absolute() and path.is_file():
            return True
        candidate1 = (self.base_path / storage_path).resolve()
        if candidate1.exists() and candidate1.is_file():
            return True
        candidate2 = (self.base_path.parent / storage_path).resolve()
        return candidate2.exists() and candidate2.is_file()


storage_service = StorageService()
