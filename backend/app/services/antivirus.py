"""ClamAV scanning at ingest time."""
import clamd

from ..config import settings


class ScannerUnavailable(Exception):
    """Raised when ClamAV cannot be reached — the caller should retry, not treat
    the file as infected."""


def _client() -> clamd.ClamdNetworkSocket:
    return clamd.ClamdNetworkSocket(
        host=settings.CLAMAV_HOST, port=settings.CLAMAV_PORT, timeout=120
    )


def scan_bytes(data: bytes) -> tuple[bool, str]:
    """Return (clean, detail). clean=False means malware was found.
    Raises ScannerUnavailable if the scanner itself could not run (fail closed,
    but distinct from a positive detection)."""
    import io

    try:
        cd = _client()
        result = cd.instream(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - report scanner unavailability
        raise ScannerUnavailable(str(exc)) from exc

    status = result.get("stream", ("ERROR", None))
    verdict, signature = status[0], status[1]
    if verdict == "OK":
        return True, "Чисто"
    if verdict == "FOUND":
        return False, f"Обнаружена угроза: {signature}"
    raise ScannerUnavailable(f"Ошибка сканирования: {verdict}")
