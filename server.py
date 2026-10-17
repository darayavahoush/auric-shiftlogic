"""
FastAPI Server for ShiftLogic: Serves the Web Dashboard and Live Neuro-Symbolic API.

Endpoints:
    GET  /             -> Serves ui/index.html
    GET  /api/items    -> Returns all 60 items with ground truth and metadata
    POST /api/solve    -> Runs live Granite 4.2 8B decompilation and 720-world solver
    GET  /api/health   -> Health check
"""
import os
import json
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

from src.types import BLOCKS, STATIONS
from src.prefilter import prefilter_item
from src.decompiler import decompile_constraints
from src.solver import solve
from src.fsm_controller import FSMController

load_dotenv()
api_key = os.environ.get("OPENROUTER_API_KEY")
base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
model = os.environ.get("MODEL", "ibm-granite/granite-4.2-8b")

client = None
if api_key:
    client = OpenAI(api_key=api_key, base_url=base_url)

app = FastAPI(title="ShiftLogic API", description="Neuro-Symbolic Entity Resolution & Constraint Engine")

# Load items and key
ITEMS_PATH = os.path.join(os.path.dirname(__file__), "items.json")
KEY_PATH = os.path.join(os.path.dirname(__file__), "visible_key.json")
UI_DIR = os.path.join(os.path.dirname(__file__), "ui")

with open(ITEMS_PATH, "r", encoding="utf-8") as f:
    ALL_ITEMS = {it["id"]: it for it in json.load(f)}

with open(KEY_PATH, "r", encoding="utf-8") as f:
    KEY_DATA = json.load(f)


class SolveRequest(BaseModel):
    item_id: str
    custom_text: Optional[str] = None
    budget: str = "1x"


@app.get("/api/health")
def health():
    return {"status": "ok", "model": model, "api_configured": client is not None}


@app.get("/api/items")
def list_items():
    data = []
    for item_id, it in ALL_ITEMS.items():
        k = KEY_DATA.get(item_id, {})
        data.append({
            "id": item_id,
            "text": it["text"],
            "n_staff": it.get("n_staff", 5),
            "n_stations": it.get("n_stations", 3),
            "case": k.get("case"),
            "assignments": k.get("assignments", []),
            "assignment": k.get("assignment"),
            "conflict_line_sets": k.get("conflict_line_sets", [])
        })
    return data


@app.post("/api/solve")
def live_solve(req: SolveRequest):
    if not client:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured in .env")

    raw_text = req.custom_text
    if not raw_text:
        item = ALL_ITEMS.get(req.item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {req.item_id} not found")
        raw_text = item["text"]

    controller = FSMController(client, model)
    result = controller.run_item(req.item_id, raw_text, budget=req.budget)
    return result


# Mount UI static files
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


@app.get("/{full_path:path}")
def serve_ui(full_path: str):
    file_path = os.path.join(UI_DIR, full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(UI_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    print(f"Starting ShiftLogic Server at http://localhost:3000 ...")
    uvicorn.run(app, host="0.0.0.0", port=3000)
