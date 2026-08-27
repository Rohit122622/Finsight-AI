"""
Cloudflare R2 private document storage service for FinSentry AI (Phase 2D).

Provides secure private object storage, presigned URLs, and mockable interfaces
for isolated testing without external network dependencies.
"""

import io
import logging
from typing import Any, Dict, Optional

from core.config import get_settings
from core.exceptions import StorageServiceException

logger = logging.getLogger(__name__)


class R2StorageService:
    """
    Client for interacting privately with Cloudflare R2 bucket.
    """

    def __init__(self) -> None:
        self._mock_storage: Dict[str, bytes] = {}
        self._mock_failure: bool = False

    def set_mock_failure(self, failure: bool) -> None:
        """Testing hook to simulate R2 storage outage/exception."""
        self._mock_failure = failure

    def reset_mocks(self) -> None:
        """Reset mock storage and error states."""
        self._mock_storage.clear()
        self._mock_failure = False

    def generate_storage_key(self, user_id: str, document_id: str, ext: str = ".pdf") -> str:
        """
        Generate standardized private storage key: users/{user_id}/documents/{document_id}.{ext}
        """
        clean_ext = ext if ext.startswith(".") else f".{ext}"
        return f"users/{user_id}/documents/{document_id}{clean_ext}"

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        """
        Upload binary data to private R2 storage.

        Returns:
            The storage key on success.

        Raises:
            StorageServiceException: If upload fails.
        """
        if self._mock_failure:
            logger.error("R2 storage upload failed for key %s (simulated failure)", key)
            raise StorageServiceException(f"Failed to upload document to R2 storage: key={key}")

        settings = get_settings()

                                                                     
        if settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_ENDPOINT_URL:
            try:
                import boto3
                from botocore.config import Config

                s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.get_r2_endpoint_url(),
                    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                    config=Config(signature_version="s3v4"),
                    region_name=settings.R2_REGION,
                )
                s3.put_object(
                    Bucket=settings.R2_BUCKET_NAME,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
                logger.info("Uploaded %d bytes to R2 bucket %s with key %s", len(data), settings.R2_BUCKET_NAME, key)
                return key
            except Exception as exc:
                logger.error("Boto3 R2 upload error: %s", exc)
                raise StorageServiceException(f"Cloudflare R2 upload error: {exc}")

                                                         
        self._mock_storage[key] = data
        logger.info("Stored %d bytes to in-memory private R2 store: key=%s", len(data), key)
        return key

    def get_bytes(self, key: str) -> bytes:
        """
        Retrieve object binary data from private R2 storage.
        """
        if self._mock_failure:
            raise StorageServiceException(f"Failed to retrieve document from R2 storage: key={key}")

        settings = get_settings()
        if settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_ENDPOINT_URL:
            try:
                import boto3
                from botocore.config import Config

                s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.get_r2_endpoint_url(),
                    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                    config=Config(signature_version="s3v4"),
                    region_name=settings.R2_REGION,
                )
                resp = s3.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
                return resp["Body"].read()
            except Exception as exc:
                raise StorageServiceException(f"Failed to get object from R2: {exc}")

        if key not in self._mock_storage:
            raise StorageServiceException(f"Object key '{key}' not found in R2 storage.")
        return self._mock_storage[key]

    def delete_object(self, key: str) -> bool:
        """
        Delete object from private R2 storage (e.g. for rollback or document deletion).
        """
        settings = get_settings()
        if settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_ENDPOINT_URL:
            try:
                import boto3
                s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.get_r2_endpoint_url(),
                    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                )
                s3.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
                return True
            except Exception as exc:
                logger.warning("Failed to delete object from R2: %s", exc)
                return False

        if key in self._mock_storage:
            del self._mock_storage[key]
            return True
        return False

    def object_exists(self, key: str) -> bool:
        """
        Check if object exists in R2 storage.
        """
        settings = get_settings()
        if settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_ENDPOINT_URL:
            try:
                import boto3
                s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.get_r2_endpoint_url(),
                    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                )
                s3.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
                return True
            except Exception:
                return False

        return key in self._mock_storage

    def get_object_metadata(self, key: str) -> Dict[str, Any]:
        """
        Fetch object metadata headers from private R2 storage.
        """
        if self._mock_failure:
            raise StorageServiceException(f"Failed to fetch metadata from R2: key={key}")

        settings = get_settings()
        if settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_ENDPOINT_URL:
            try:
                import boto3
                s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.get_r2_endpoint_url(),
                    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                )
                resp = s3.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
                return {
                    "content_length": resp.get("ContentLength", 0),
                    "content_type": resp.get("ContentType", "application/octet-stream"),
                    "etag": resp.get("ETag", "").strip('"'),
                    "last_modified": resp.get("LastModified"),
                }
            except Exception as exc:
                raise StorageServiceException(f"Failed to fetch R2 object metadata: {exc}")

        if key not in self._mock_storage:
            raise StorageServiceException(f"Object key '{key}' not found in R2 storage.")

        data = self._mock_storage[key]
        return {
            "content_length": len(data),
            "content_type": "application/pdf" if key.endswith(".pdf") else "application/octet-stream",
            "etag": "mock-etag-12345",
            "last_modified": None,
        }

    def generate_presigned_url(self, key: str, expires_in_seconds: int = 3600) -> str:
        """
        Generate short-lived presigned URL for private R2 object access.
        """
        if self._mock_failure:
            raise StorageServiceException(f"Failed to generate presigned URL: key={key}")

        settings = get_settings()
        if settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_ENDPOINT_URL:
            try:
                import boto3
                from botocore.config import Config

                s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.get_r2_endpoint_url(),
                    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                    config=Config(signature_version="s3v4"),
                    region_name=settings.R2_REGION,
                )
                url = s3.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
                    ExpiresIn=expires_in_seconds,
                )
                return url
            except Exception as exc:
                logger.error("Failed to generate presigned URL from boto3: %s", exc)
                raise StorageServiceException(f"Cloudflare R2 presigned URL generation error: {exc}")

                        
        if key not in self._mock_storage:
            raise StorageServiceException(f"Object key '{key}' not found in R2 storage.")
        return f"https://mock-r2.finsentry.internal/{key}?expires_in={expires_in_seconds}"


r2_storage_service = R2StorageService()
