"""S3 Client Module - Handles all AWS S3 operations"""

import boto3
import urllib3
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path
from typing import BinaryIO, Optional
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Suppress InsecureRequestWarning when SSL verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class S3Client:
    """AWS S3 client wrapper for file operations"""

    def __init__(self):
        """Initialize S3 client with credentials from settings"""
        self.s3_client = None
        self.bucket_name = settings.s3_bucket_name

        if settings.aws_access_key_id and settings.aws_secret_access_key:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
                verify=False,
            )
            logger.info(f"S3 client initialized for region: {settings.aws_region}")
        else:
            logger.warning("S3 credentials not configured. S3 operations will fail.")

    def upload_file(
        self, file_obj: BinaryIO, s3_key: str, content_type: Optional[str] = None
    ) -> str:
        """
        Upload a file to S3.

        Args:
            file_obj: File-like object to upload
            s3_key: S3 key (path) for the uploaded file
            content_type: Optional content type for the file

        Returns:
            str: S3 URL of the uploaded file

        Raises:
            ValueError: If S3 is not configured
            Exception: If upload fails
        """
        if not self.s3_client:
            raise ValueError("S3 client not configured. Check AWS credentials.")

        if not self.bucket_name:
            raise ValueError("S3 bucket name not configured.")

        try:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type

            self.s3_client.upload_fileobj(file_obj, self.bucket_name, s3_key, ExtraArgs=extra_args if extra_args else None)

            s3_url = f"https://{self.bucket_name}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"
            logger.info(f"File uploaded successfully to S3: {s3_key}")
            return s3_url

        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise ValueError("AWS credentials not configured properly")
        except ClientError as e:
            logger.error(f"S3 upload failed: {str(e)}")
            raise Exception(f"Failed to upload file to S3: {str(e)}")

    def upload_local_file(
        self, local_path: Path, s3_key: str, content_type: Optional[str] = None
    ) -> str:
        """
        Upload a local file to S3.

        Args:
            local_path: Path to local file
            s3_key: S3 key (path) for the uploaded file
            content_type: Optional content type for the file

        Returns:
            str: S3 URL of the uploaded file
        """
        with open(local_path, "rb") as f:
            return self.upload_file(f, s3_key, content_type)

    def delete_file(self, s3_key: str) -> bool:
        """
        Delete a file from S3.

        Args:
            s3_key: S3 key (path) of the file to delete

        Returns:
            bool: True if deletion was successful
        """
        if not self.s3_client:
            raise ValueError("S3 client not configured. Check AWS credentials.")

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"File deleted from S3: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"S3 delete failed: {str(e)}")
            return False

    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL for temporary access to an S3 object.

        Args:
            s3_key: S3 key (path) of the file
            expiration: Time in seconds for the presigned URL to remain valid (default: 1 hour)

        Returns:
            Optional[str]: Presigned URL or None if generation fails
        """
        if not self.s3_client:
            raise ValueError("S3 client not configured. Check AWS credentials.")

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )
            logger.info(f"Generated presigned URL for: {s3_key}")
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            return None


# Singleton instance
_s3_client: Optional[S3Client] = None


def get_s3_client() -> S3Client:
    """Get or create the singleton S3 client instance"""
    global _s3_client
    if _s3_client is None:
        _s3_client = S3Client()
    return _s3_client
