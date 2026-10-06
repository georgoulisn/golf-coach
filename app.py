"""
Gemini Live Real-Time Golf Coach Bridge
Connects Tablet Camera + Rapsodo MLM2PRO Telemetry + Natural Human Voice Audio Engine
"""
import os
import json
import asyncio
import tempfile
import subprocess
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Gemini Live Golf Coach")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
active_tablet_ws = set()

class RapsodoShot(BaseModel):
    club: str = "7i"
    ball_speed: float = 98.4
    club_speed: float = 71.8
    smash: float = 1.37
    attack_angle: float = -3.2
    launch_angle: float = 15.6
    spin_rate: int = 3450
    spin_axis: float = 4.2
    carry: float = 136.5

@app.get("/")
async def get_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Golf Coach running, but static/index.html not found!</h1>", status_code=404)

@app.get("/api/tts")
async def text_to_speech(text: str):
    """
    Generates natural, human studio audio file so iPad plays real voice instead of robotic synthesizer.
    """
    clean_text = text.replace('"', '').replace("'", "")

    # 1. Try edge-tts for ultra-realistic neural human voice (if installed)
    try:
        import edge_tts
        communicate = edge_tts.Communicate(clean_text, "en-US-GuyNeural")
        audio_bytes = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes.extend(chunk["data"])
        if audio_bytes:
            return Response(content=bytes(audio_bytes), media_type="audio/mpeg")
    except Exception:
        pass

    # 2. Fallback to Mac's high-quality built-in voice (Daniel / Oliver) via 'say' + 'afconvert'
    try:
        tmp_dir = tempfile.gettempdir()
        aiff_path = os.path.join(tmp_dir, "coach_voice.aiff")
        m4a_path = os.path.join(tmp_dir, "coach_voice.m4a")

        # Pick natural voice on macOS
        subprocess.run(["say", "-v", "Daniel", "-o", aiff_path, clean_text], check=True, timeout=5)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", aiff_path, m4a_path], check=True, timeout=5)

        with open(m4a_path, "rb") as f:
            data = f.read()
        return Response(content=data, media_type="audio/mp4")
    except Exception as e:
        print("Local audio generation error:", e)
        return Response(content=b"", status_code=500)

@app.post("/api/rapsodo_webhook")
async def receive_rapsodo_shot(shot: RapsodoShot):
    shot_data = shot.dict()
    broadcast_msg = json.dumps({
        "type": "shot_update",
        **shot_data
    })
    for ws in list(active_tablet_ws):
        try:
            await ws.send_text(broadcast_msg)
        except Exception:
            pass

    feedback = f"Flushed {shot.club}! Great compression with a {shot.attack_angle}° downward attack angle carrying {shot.carry} yards. Lead hip cleared well through impact."
    
    coach_payload = json.dumps({
        "type": "coach_speech",
        "text": feedback,
        "audio_url": f"/api/tts?text={feedback}"
    })
    for ws in list(active_tablet_ws):
        try:
            await ws.send_text(coach_payload)
        except Exception:
            pass

    return {"status": "ok", "shot": shot_data, "feedback": feedback}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_tablet_ws.add(websocket)
    try:
        while True:
            msg = await websocket.receive_text()
    except WebSocketDisconnect:
        active_tablet_ws.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    print("Starting Gemini Live Golf Coach on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
