import mimetypes
import os
import uuid
import logging
from io import BytesIO
from typing import IO, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings


class S3UploadError(Exception):
    """Raised when the application fails to upload a file to S3."""


logger = logging.getLogger(__name__)


def _build_s3_base_url() -> str:
    if settings.AWS_S3_BASE_URL:
        return settings.AWS_S3_BASE_URL.rstrip("/")

    bucket = settings.AWS_S3_BUCKET_NAME
    region = settings.AWS_REGION or "us-east-1"

    if region == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com"
    return f"https://{bucket}.s3.{region}.amazonaws.com"


def _get_s3_client():
    missing = [
        name
        for name, value in (
            ("AWS_S3_BUCKET_NAME", settings.AWS_S3_BUCKET_NAME),
            ("AWS_ACCESS_KEY_ID", settings.AWS_ACCESS_KEY_ID),
            ("AWS_SECRET_ACCESS_KEY", settings.AWS_SECRET_ACCESS_KEY),
        )
        if not value
    ]
    if missing:
        joined = ", ".join(missing)
        raise S3UploadError(f"Configuracion AWS incompleta: {joined}.")

    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION or "us-east-1",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def upload_product_image(upload: IO[bytes], filename: Optional[str] = None) -> str:
    """
    Uploads a product image to S3 and returns its public URL.

    Args:
        upload: A file-like object coming from Django's uploaded file.
        filename: Optional original filename (used only for extension extraction).
    """
    client = _get_s3_client()
    bucket = settings.AWS_S3_BUCKET_NAME
    base_url = _build_s3_base_url()

    original_name = filename or getattr(upload, "name", None) or "producto"
    _, ext = os.path.splitext(original_name)
    if not ext:
        guessed = mimetypes.guess_extension(getattr(upload, "content_type", "") or "")
        ext = guessed or ""

    key = f"productos/{uuid.uuid4().hex}{ext}"

    extra_args = {}
    if settings.AWS_S3_OBJECT_ACL:
        extra_args["ACL"] = settings.AWS_S3_OBJECT_ACL
    content_type = getattr(upload, "content_type", None)
    if content_type:
        extra_args["ContentType"] = content_type

    def _read_upload_bytes() -> bytes:
        open_callable = getattr(upload, "open", None)

        if getattr(upload, "closed", False) and callable(open_callable):
            open_callable()

        try:
            upload.seek(0)
        except (AttributeError, OSError, ValueError):
            if callable(open_callable):
                open_callable()
                upload.seek(0)
            else:
                raise S3UploadError("No pudimos preparar la imagen para subirla en S3.")

        data = upload.read()
        if not data:
            raise S3UploadError("El archivo de imagen esta vacio o no se pudo leer.")

        # Volvemos a dejar el stream al inicio en caso de que Django quiera reutilizarlo
        try:
            upload.seek(0)
        except (AttributeError, OSError, ValueError):
            pass

        return data

    upload_bytes = _read_upload_bytes()

    def _do_upload(args: Optional[dict]):
        fileobj = BytesIO(upload_bytes)
        if args:
            client.upload_fileobj(fileobj, bucket, key, ExtraArgs=args)
        else:
            client.upload_fileobj(fileobj, bucket, key)

    try:
        _do_upload(extra_args or None)
    except (BotoCoreError, ClientError) as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"AccessControlListNotSupported", "InvalidRequest"} and "ACL" in extra_args:
            logger.warning(
                "Bucket %s no admite ACL (%s). Reintentando subida sin ACL.", bucket, error_code
            )
            try:
                extra_args_without_acl = {k: v for k, v in extra_args.items() if k != "ACL"}
                _do_upload(extra_args_without_acl or None)
            except (BotoCoreError, ClientError) as retry_exc:
                logger.exception(
                    "Reintento fallido al subir imagen %s a S3 bucket %s",
                    filename or getattr(upload, "name", ""),
                    bucket,
                )
                raise S3UploadError("No pudimos cargar la imagen en S3.") from retry_exc
        else:
            logger.exception(
                "Error al subir imagen %s a S3 bucket %s",
                filename or getattr(upload, "name", ""),
                bucket,
            )
            raise S3UploadError("No pudimos cargar la imagen en S3.") from exc

    return f"{base_url}/{key}"
