"""Web app: upload a photo, watch the agent work (server-sent events), download the package."""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .env import load_env

load_env(str(Path(__file__).resolve().parents[1] / ".env"))

from . import meta, pipeline  # noqa: E402  (env must be loaded first)

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "static"
SAMPLES = ROOT / "samples"
pipeline.OUT.mkdir(exist_ok=True)

app = FastAPI(title="Listing Pilot")
app.mount("/runs", StaticFiles(directory=pipeline.OUT), name="runs")
app.mount("/samples", StaticFiles(directory=SAMPLES), name="samples")
RUNS: dict[str, pipeline.Run] = {}
LOCK = threading.Semaphore(2)  # at most two live runs at once (credit budget)


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text()


@app.get("/api/status")
def status():
    return {"mock": meta.mock_mode(), "samples": sorted(p.stem for p in SAMPLES.glob("*.jpg"))}


def _start(photo: Image.Image, brand: str, notes: str) -> str:
    if not LOCK.acquire(blocking=False):
        raise HTTPException(429, "Two listings are already being built. Try again in a minute.")
    run = pipeline.new_run()
    RUNS[run.id] = run

    def work():
        try:
            pipeline.run_pipeline(run, photo, brand, notes)
        except Exception:
            pass
        finally:
            LOCK.release()

    threading.Thread(target=work, daemon=True).start()
    return run.id


@app.post("/api/run")
async def start_run(photo: UploadFile | None = File(None), sample: str = Form(""), brand: str = Form("Hearth & Clay"),
                    notes: str = Form("")):
    if photo is not None and photo.filename:
        data = await photo.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(413, "Photo is larger than 15 MB")
        import io
        img = Image.open(io.BytesIO(data))
    elif sample:
        path = SAMPLES / f"{Path(sample).name}.jpg"
        if not path.exists():
            raise HTTPException(404, "unknown sample")
        img = Image.open(path)
    else:
        raise HTTPException(400, "send a photo or pick a sample")
    img.load()
    return {"id": _start(img, brand.strip()[:60] or "Your Brand", notes.strip()[:500])}


@app.get("/api/runs/{rid}/events")
async def events(rid: str):
    run = RUNS.get(rid)
    if run is None:
        replay = pipeline.OUT / rid / "events.json"
        if not replay.exists():
            raise HTTPException(404, "unknown run")

    async def gen():
        if run is None:
            for ev in json.loads(replay.read_text()):
                yield f"data: {json.dumps(ev)}\n\n"
                await asyncio.sleep(0.6)
            yield "event: done\ndata: {}\n\n"
            return
        sent = 0
        while True:
            while sent < len(run.events):
                yield f"data: {json.dumps(run.events[sent])}\n\n"
                sent += 1
            if run.done and sent >= len(run.events):
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(0.3)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/runs/{rid}")
def run_result(rid: str):
    f = pipeline.OUT / rid / "listing.json"
    if not f.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(f)
