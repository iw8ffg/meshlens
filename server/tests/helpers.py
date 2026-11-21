from meshtastic.protobuf import mesh_pb2, mqtt_pb2

from meshlens.crypto import DEFAULT_KEY, decrypt


def channel_hash(name: str, key: bytes) -> int:
    h = 0
    for b in name.encode("utf-8") + key:
        h ^= b
    return h


def make_envelope(portnum: int, payload_msg, from_node=0xa1b2c3d4, packet_id=1,
                  channel_id="LongFast", gateway="!00000001", key=DEFAULT_KEY,
                  encrypted=True, hop_start=3, hop_limit=1, rx_snr=-5.0,
                  channel_hash_value=None, reply_id=0, emoji=0, pki=False) -> bytes:
    raw = payload_msg if isinstance(payload_msg, bytes) else payload_msg.SerializeToString()
    data = mesh_pb2.Data(portnum=portnum, payload=raw, reply_id=reply_id, emoji=emoji)
    packet = mesh_pb2.MeshPacket(
        **{"from": from_node}, to=0xFFFFFFFF, id=packet_id,
        hop_start=hop_start, hop_limit=hop_limit, rx_snr=rx_snr, pki_encrypted=pki,
    )
    if encrypted:
        packet.channel = (channel_hash(channel_id, key) if channel_hash_value is None
                          else channel_hash_value)
        packet.encrypted = decrypt(key, packet_id, from_node, data.SerializeToString())
    else:
        packet.decoded.CopyFrom(data)
    env = mqtt_pb2.ServiceEnvelope(packet=packet, channel_id=channel_id, gateway_id=gateway)
    return env.SerializeToString()
