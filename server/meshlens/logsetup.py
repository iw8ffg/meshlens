"""Log su file con rotazione (meshlens.log, 1 MB x 5)."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE = "meshlens.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 5
HANDLER_NAME = "meshlens-file"
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(log_dir: Path, level: int = logging.INFO) -> Path:
    """Installa il file di log; richiamarla di nuovo non duplica le righe."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / LOG_FILE
    root = logging.getLogger()
    for h in list(root.handlers):
        if h.get_name() == HANDLER_NAME:
            root.removeHandler(h)
            h.close()
    handler = RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS,
                                  encoding="utf-8", errors="replace")
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    logging.getLogger("meshlens").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return path


def tail_file(path: Path, max_bytes: int) -> str:
    """Ultimi max_bytes del file, a partire dalla prima riga intera."""
    try:
        with open(path, "rb") as f:
            size = f.seek(0, 2)
            f.seek(max(0, size - max_bytes))
            data = f.read()
            truncated = size > max_bytes
    except OSError:
        return ""
    if truncated:
        nl = data.find(b"\n")
        data = data[nl + 1:] if nl != -1 else b""
    return data.decode("utf-8", errors="replace")
