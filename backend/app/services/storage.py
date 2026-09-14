"""MinIO / S3 object storage with WORM (Object Lock) retention for originals."""
import datetime as dt
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from ..config import settings

_session = boto3.session.Session()
_client = _session.client(
    "s3",
    endpoint_url=f"{'https' if settings.MINIO_SECURE else 'http'}://{settings.MINIO_ENDPOINT}",
    aws_access_key_id=settings.MINIO_ROOT_USER,
    aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)


def ping() -> bool:
    """Доступно ли объектное хранилище (для пробы готовности сервиса)."""
    try:
        _client.head_bucket(Bucket=settings.MINIO_BUCKET)
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_bucket() -> None:
    """Create the archive bucket with Object Lock (WORM) enabled if missing."""
    bucket = settings.MINIO_BUCKET
    try:
        _client.head_bucket(Bucket=bucket)
        return
    except ClientError:
        pass
    # ObjectLockEnabledForBucket can only be set at creation time.
    _client.create_bucket(
        Bucket=bucket, ObjectLockEnabledForBucket=True
    )


def put_original(key: str, data: bytes, content_type: str) -> None:
    """Store an original under a compliance-mode retention lock (WORM)."""
    retain_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        days=settings.MINIO_RETENTION_DAYS
    )
    _client.put_object(
        Bucket=settings.MINIO_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
        ObjectLockMode="COMPLIANCE",
        ObjectLockRetainUntilDate=retain_until,
    )


def put_object(key: str, data: bytes, content_type: str) -> None:
    """Обычный объект без WORM-блокировки: вложения карточек и служебные файлы.

    Блокировка хранения применяется только к принятым на хранение документам —
    вложение (скан подписанного акта, письмо заявителя) допускает замену."""
    _client.put_object(
        Bucket=settings.MINIO_BUCKET, Key=key, Body=data, ContentType=content_type,
    )


def delete_object(key: str) -> bool:
    """Удаляет объект. Оригиналы документов защищены WORM — для них операция
    не проходит, и это ожидаемо; вызывающий код не должен из-за этого падать."""
    try:
        _client.delete_object(Bucket=settings.MINIO_BUCKET, Key=key)
        return True
    except Exception:  # noqa: BLE001
        return False


def get_object(key: str) -> bytes:
    resp = _client.get_object(Bucket=settings.MINIO_BUCKET, Key=key)
    return resp["Body"].read()


def presigned_url(key: str, filename: str, expires: int = 900) -> str:
    return _client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.MINIO_BUCKET,
            "Key": key,
            "ResponseContentDisposition": f'inline; filename="{filename}"',
        },
        ExpiresIn=expires,
    )
