import json
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8001"
c = httpx.Client(base_url=BASE, timeout=180.0)

r = c.post("/generate", json={"selection_id": 1, "force": False})
print("GEN", r.status_code)
r.raise_for_status()
gen = r.json()
print("generation_id", gen["id"], "llm_status", gen["llm_status"], "cases", len(gen["test_cases"]))

r2 = c.post(
    "/documents/ingest",
    json={"pdf_path": r"data\ct200_manual_v2.pdf", "version_number": 2},
)
print("V2", r2.status_code)
if r2.status_code == 409:
    print("v2 already exists")
else:
    r2.raise_for_status()
    print(r2.json())

batt = c.get("/browse/search", params={"q": "Battery Life", "version": 2}).json()
print("BATT_FOUND", bool(batt), batt[0]["id"] if batt else None)
if batt:
    ch = c.get(f"/browse/nodes/{batt[0]['id']}/changes").json()
    print("CHANGE_TYPE", ch.get("change_type"), "changed", ch.get("changed"))

stale = c.get(f"/generations/{gen['id']}/staleness").json()
print("STALE", stale.get("is_stale"), "changed_nodes", len(stale.get("changed_nodes") or []))
print("DONE")
