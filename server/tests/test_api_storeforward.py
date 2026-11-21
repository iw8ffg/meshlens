from meshlens.storeforward import SfError
from test_api import client, logged, make_ctx

JOB = {"id": "j1", "radio_id": "r1", "router_id": "!a1b2c3d4", "window_min": 240,
       "channel_index": 1, "status": "waiting", "expected": None, "received": 0,
       "duplicates": 0, "error": None, "started": 1.0, "ended": None}
ROUTER = {"id": "!a1b2c3d4", "name": "Router Vesuvio", "radio_id": "r1", "last_seen": 1.0,
          "heartbeat_period": 900, "secondary": False, "stats": None, "last_request": None}
BODY = {"radio_id": "r1", "router_id": "!a1b2c3d4", "window_min": 240, "channel_index": 1}


class FakeService:
    def __init__(self):
        self.calls = []
        self.error = None

    async def request(self, radio_id, num, window_min, channel_index):
        self.calls.append(("request", radio_id, num, window_min, channel_index))
        if self.error:
            raise self.error
        return dict(JOB)

    async def probe(self, radio_id, num, channel_index):
        self.calls.append(("probe", radio_id, num, channel_index))
        if self.error:
            raise self.error

    def routers(self):
        return [ROUTER]

    def jobs(self):
        return [JOB]


def make():
    ctx = make_ctx()
    ctx.storeforward = FakeService()
    return ctx


async def test_requires_auth():
    async with client(make()) as c:
        assert (await c.get("/api/storeforward/routers")).status_code == 401
        assert (await c.get("/api/storeforward/jobs")).status_code == 401
        assert (await c.post("/api/storeforward/request", json=BODY)).status_code == 401
        assert (await c.post("/api/storeforward/probe", json=BODY)).status_code == 401


async def test_validation():
    ctx = make()
    async with logged(ctx) as c:
        r = await c.post("/api/storeforward/request", json={**BODY, "window_min": 2})
        assert r.status_code in (400, 422)
        r = await c.post("/api/storeforward/request", json={**BODY, "channel_index": 8})
        assert r.status_code in (400, 422)
        r = await c.post("/api/storeforward/request", json={**BODY, "router_id": "xyz"})
        assert r.status_code == 400 and r.json()["detail"] == "Identificativo del nodo non valido"
        r = await c.post("/api/storeforward/probe", json={**BODY, "router_id": "xyz"})
        assert r.status_code == 400
    assert ctx.storeforward.calls == []


async def test_request_ok_and_lists():
    ctx = make()
    async with logged(ctx) as c:
        r = await c.post("/api/storeforward/request", json=BODY)
        assert r.status_code == 202 and r.json() == JOB
        assert ctx.storeforward.calls == [("request", "r1", 0xa1b2c3d4, 240, 1)]
        assert (await c.get("/api/storeforward/routers")).json() == [ROUTER]
        assert (await c.get("/api/storeforward/jobs")).json() == [JOB]
        r = await c.post("/api/storeforward/probe", json={"radio_id": "r1",
                         "router_id": "!a1b2c3d4", "channel_index": 1})
        assert r.status_code == 202 and r.json() == {}


async def test_sf_errors_mapped():
    ctx = make()
    async with logged(ctx) as c:
        ctx.storeforward.error = SfError("Attendi 12 s prima di una nuova richiesta a questo router",
                                         429, retry_after=12)
        r = await c.post("/api/storeforward/request", json=BODY)
        assert r.status_code == 429 and r.headers["Retry-After"] == "12"
        assert r.json() == {"detail": "Attendi 12 s prima di una nuova richiesta a questo router"}
        ctx.storeforward.error = SfError("Radio non connessa", 409)
        r = await c.post("/api/storeforward/request", json=BODY)
        assert r.status_code == 409 and "Retry-After" not in r.headers
        assert r.json() == {"detail": "Radio non connessa"}
        r = await c.post("/api/storeforward/probe", json=BODY)
        assert r.status_code == 409
