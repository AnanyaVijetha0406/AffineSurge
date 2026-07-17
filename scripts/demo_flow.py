"""End-to-end demo: ingest v1 → select → generate → ingest v2 → show staleness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8001"
ROOT = Path(__file__).resolve().parents[1]


def pretty(label: str, data) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(data, indent=2, default=str)[:4000])


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=120.0)

    health = client.get("/health").json()
    pretty("health", health)

    r1 = client.post(
        "/documents/ingest",
        json={"pdf_path": str(ROOT / "data" / "ct200_manual.pdf"), "version_number": 1},
    )
    if r1.status_code == 409:
        pretty("v1 already present", r1.json())
    else:
        r1.raise_for_status()
        pretty("ingest v1", r1.json())

    sections = client.get("/browse/sections", params={"version": 1}).json()
    pretty("top sections v1", sections[:5])

    # Find overpressure + error codes nodes
    search = client.get("/browse/search", params={"q": "Overpressure", "version": 1}).json()
    pretty("search Overpressure", search)
    if not search:
        print("Could not find Overpressure node", file=sys.stderr)
        return 1

    node_ids = [search[0]["id"]]
    err = client.get("/browse/search", params={"q": "Error Codes", "version": 1}).json()
    if err:
        node_ids.append(err[0]["id"])

    sel_name = "safety-alarms-v1"
    sel = client.post("/selections", json={"name": sel_name, "node_ids": node_ids})
    if sel.status_code == 409:
        # already exists — list won't work; use search via generate cache path
        print("Selection exists; looking up via re-create skip — fetch by regenerating name conflict")
        # Try alternate name
        sel_name = "safety-alarms-v1-demo"
        sel = client.post("/selections", json={"name": sel_name, "node_ids": node_ids})
    sel.raise_for_status()
    selection = sel.json()
    pretty("selection", selection)

    gen = client.post("/generate", json={"selection_id": selection["id"], "force": False})
    gen.raise_for_status()
    generation = gen.json()
    pretty("generation", generation)

    r2 = client.post(
        "/documents/ingest",
        json={"pdf_path": str(ROOT / "data" / "ct200_manual_v2.pdf"), "version_number": 2},
    )
    if r2.status_code == 409:
        pretty("v2 already present", r2.json())
    else:
        r2.raise_for_status()
        pretty("ingest v2", r2.json())

    # Node change for battery section
    batt = client.get("/browse/search", params={"q": "Battery Life", "version": 2}).json()
    if batt:
        ch = client.get(f"/browse/nodes/{batt[0]['id']}/changes").json()
        pretty("battery change v1→v2", ch)

    stale = client.get(f"/generations/{generation['id']}/staleness").json()
    pretty("staleness after v2", stale)

    cached = client.post("/generate", json={"selection_id": selection["id"], "force": False}).json()
    pretty("second generate (cache policy)", {"id": cached["id"], "same": cached["id"] == generation["id"]})

    print("\nDemo complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
