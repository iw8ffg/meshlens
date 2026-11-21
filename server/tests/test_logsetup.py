import logging

import pytest

from meshlens.logsetup import LOG_FILE, setup_logging, tail_file


@pytest.fixture(autouse=True)
def clean_logging():
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        if h.get_name() == "meshlens-file":
            root.removeHandler(h)
            h.close()
    logging.getLogger("meshlens").setLevel(logging.NOTSET)
    root.setLevel(logging.WARNING)


def test_setup_logging_rotates_at_1mb(tmp_path):
    path = setup_logging(tmp_path)
    assert path == tmp_path / LOG_FILE
    log = logging.getLogger("meshlens.x")
    line = "r" * 190
    for i in range(13000):  # ~2,6 MB
        log.info("%06d %s", i, line)
    names = {p.name for p in tmp_path.iterdir()}
    assert {"meshlens.log", "meshlens.log.1", "meshlens.log.2"} <= names
    for p in tmp_path.iterdir():
        assert p.stat().st_size <= 1_000_000 + 400


def test_setup_logging_is_idempotent(tmp_path):
    setup_logging(tmp_path)
    setup_logging(tmp_path)
    logging.getLogger("meshlens.y").info("una sola volta")
    text = (tmp_path / LOG_FILE).read_text(encoding="utf-8")
    assert text.count("una sola volta") == 1
    assert "INFO meshlens.y: una sola volta" in text


def test_meshlens_info_written_but_root_info_not(tmp_path):
    setup_logging(tmp_path)
    logging.getLogger("meshlens.z").info("visibile")
    logging.getLogger("altra.libreria").info("rumore")
    logging.getLogger("altra.libreria").warning("avviso")
    logging.getLogger("uvicorn.access").info("GET /")
    text = (tmp_path / LOG_FILE).read_text(encoding="utf-8")
    assert "visibile" in text and "avviso" in text
    assert "rumore" not in text and "GET /" not in text


def test_tail_file_starts_at_line_boundary(tmp_path):
    p = tmp_path / "t.log"
    p.write_bytes("".join(f"riga numero {i:03d}\n" for i in range(100)).encode())
    out = tail_file(p, 100)
    assert out.startswith("riga numero ") and out.endswith("099\n")
    assert len(out.encode()) <= 100
    assert tail_file(p, 10_000).startswith("riga numero 000")
    assert tail_file(tmp_path / "manca.log", 100) == ""


def test_tail_file_tolerates_invalid_utf8(tmp_path):
    p = tmp_path / "b.log"
    p.write_bytes(b"ok\n\xff\xfe riga\nfine\n")
    assert "fine" in tail_file(p, 1000)
