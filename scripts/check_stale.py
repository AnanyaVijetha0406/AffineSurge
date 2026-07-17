import httpx

c = httpx.Client(base_url="http://127.0.0.1:8001", timeout=120.0)
batt_v1 = c.get("/browse/search", params={"q": "Battery Life", "version": 1}).json()
print("v1 battery", batt_v1[0]["id"], batt_v1[0]["content_hash"][:12])
sel = c.post(
    "/selections",
    json={"name": "battery-v1-pin", "node_ids": [batt_v1[0]["id"]]},
)
print("sel", sel.status_code, sel.text[:300])
sel.raise_for_status()
sid = sel.json()["id"]
gen = c.post("/generate", json={"selection_id": sid, "force": True})
gen.raise_for_status()
gid = gen.json()["id"]
print("gen", gid, gen.json()["llm_status"])
stale = c.get(f"/generations/{gid}/staleness").json()
print("is_stale", stale["is_stale"], stale["changed_nodes"])
