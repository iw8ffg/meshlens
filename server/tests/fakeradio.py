"""Helper di test per la radio simulata (WP7): carica gli script di tools/ e costruisce pacchetti."""
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from meshtastic.protobuf import mesh_pb2, portnums_pb2

TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def load():
    """Importa (in ritardo) replay_record e fake_radio da tools/."""
    import fake_radio
    import replay_record
    return replay_record, fake_radio


def wait_until(cond, timeout: float = 3.0, step: float = 0.01) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return bool(cond())


def _base(frm: int, to: int, pid: int, channel: int, snr: float, hop_start: int,
          hop_limit: int) -> mesh_pb2.MeshPacket:
    pkt = mesh_pb2.MeshPacket()
    setattr(pkt, "from", frm)
    pkt.to = to
    pkt.id = pid
    pkt.channel = channel
    pkt.rx_snr = snr
    pkt.hop_start = hop_start
    pkt.hop_limit = hop_limit
    pkt.rx_time = 1_700_000_000
    return pkt


def text_packet(frm, to, text, pid, channel=0, snr=5.5, hop_start=3, hop_limit=2):
    pkt = _base(frm, to, pid, channel, snr, hop_start, hop_limit)
    pkt.decoded.portnum = portnums_pb2.PortNum.TEXT_MESSAGE_APP
    pkt.decoded.payload = text.encode("utf-8")
    return pkt


def position_packet(frm, lat, lon, pid, to=0xFFFFFFFF, channel=0):
    pkt = _base(frm, to, pid, channel, 4.0, 3, 3)
    pkt.decoded.portnum = portnums_pb2.PortNum.POSITION_APP
    pos = mesh_pb2.Position()
    pos.latitude_i = int(lat * 1e7)
    pos.longitude_i = int(lon * 1e7)
    pos.time = 1_700_000_000
    pkt.decoded.payload = pos.SerializeToString()
    return pkt


def nodeinfo_packet(frm, long_name, short_name, pid, to=0xFFFFFFFF, channel=0):
    pkt = _base(frm, to, pid, channel, 3.0, 3, 3)
    pkt.decoded.portnum = portnums_pb2.PortNum.NODEINFO_APP
    user = mesh_pb2.User()
    user.id = f"!{frm:08x}"
    user.long_name = long_name
    user.short_name = short_name
    pkt.decoded.payload = user.SerializeToString()
    return pkt


@contextmanager
def running_fake_radio(session=None, **cfg_overrides):
    """Avvia una radio finta su porta effimera e la ferma sempre."""
    _, fr = load()
    cfg = fr.FakeRadioConfig(port=0, **cfg_overrides)
    server = fr.FakeRadioServer(cfg, session)
    server.start()
    try:
        yield server
    finally:
        server.stop()
