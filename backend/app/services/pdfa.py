"""Конвертация PDF в PDF/A-1b (ghostscript) — требование приказа № 235 для
документов постоянного хранения."""
import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("pdfa")


def convert_to_pdfa(pdf_bytes: bytes) -> bytes | None:
    """Вернуть PDF/A-1b версию документа или None при неудаче."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.pdf"
        dst = Path(tmp) / "out.pdf"
        src.write_bytes(pdf_bytes)
        cmd = [
            "gs", "-dPDFA=1", "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE",
            "-sColorConversionStrategy=UseDeviceIndependentColor",
            "-sDEVICE=pdfwrite", "-dPDFACompatibilityPolicy=1",
            f"-sOutputFile={dst}", str(src),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=120)
            if res.returncode == 0 and dst.exists():
                return dst.read_bytes()
            log.warning("PDF/A conversion failed: %s", res.stderr[-300:])
        except Exception as exc:  # noqa: BLE001
            log.warning("PDF/A conversion error: %s", exc)
    return None
