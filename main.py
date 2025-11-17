import os
import math
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

try:
    # Database utilities (MongoDB)
    from database import db, create_document, get_documents
except Exception:
    db = None
    def create_document(*args, **kwargs):
        raise Exception("Database not available")
    def get_documents(*args, **kwargs):
        raise Exception("Database not available")

app = FastAPI(title="TOFY-X1 Backend", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "TOFY-X1 backend running", "time": datetime.utcnow().isoformat()}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the TOFY-X1 backend API!"}

# --- Simulation helpers ---
_start = datetime.utcnow().timestamp()

def _sim_value(base: float, amp: float, speed: float, noise: float = 0.5) -> float:
    t = datetime.utcnow().timestamp() - _start
    return base + amp * math.sin(t * speed) + random.uniform(-noise, noise)


def _make_telemetry_payload() -> Dict[str, Any]:
    # Environmental
    ambient_temp = round(_sim_value(22.0, 6.0, 0.06), 2)  # C
    surface_temp = round(ambient_temp + _sim_value(5.0, 3.0, 0.08, 0.3), 2)
    uv_index = max(0.0, round(_sim_value(4.0, 3.0, 0.05, 0.4), 2))
    ir_radiation = max(0.0, round(_sim_value(250.0, 120.0, 0.03, 5.0), 2))  # mW/m^2 approx
    light_lux = max(0.0, round(_sim_value(20000.0, 15000.0, 0.04, 500.0), 2))

    # Power
    battery_pct = min(100.0, max(0.0, round(_sim_value(78.0, 8.0, 0.01, 1.0), 1)))
    battery_voltage = round(3.0 + battery_pct / 100.0 * 1.2, 2)

    # Orientation (MPU6050)
    pitch = round(_sim_value(2.0, 10.0, 0.02, 0.8), 2)
    roll = round(_sim_value(1.0, 12.0, 0.018, 0.8), 2)
    yaw = (datetime.utcnow().timestamp() * 12) % 360

    # GPS approx
    lat = 46.0569 + _sim_value(0.0, 0.0008, 0.002, 0.0001)
    lon = 14.5058 + _sim_value(0.0, 0.0008, 0.002, 0.0001)

    # Solar panel orientation target (like sunflower)
    sun_dir = (datetime.utcnow().timestamp() * 6) % 360

    # Camouflage color based on environment (blue=cool, red=hot)
    hue = max(0, min(220, int(220 - (surface_temp - 10) * (220 / 50))))
    camo_color_hsl = f"hsl({hue}, 70%, 55%)"

    danger = "low"
    if uv_index > 7 or surface_temp > 50:
        danger = "high"
    elif uv_index > 5 or surface_temp > 40:
        danger = "medium"

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": {
            "ambient_temp_c": ambient_temp,
            "surface_temp_c": surface_temp,
            "uv_index": uv_index,
            "ir_mw_m2": ir_radiation,
            "light_lux": light_lux,
        },
        "power": {
            "battery_pct": battery_pct,
            "battery_voltage": battery_voltage,
        },
        "attitude": {
            "pitch": pitch,
            "roll": roll,
            "yaw": round(yaw, 2),
        },
        "navigation": {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "speed_mps": round(max(0.0, _sim_value(0.8, 0.6, 0.07, 0.2)), 2),
            "heading": round(yaw, 2),
        },
        "solar": {
            "target_azimuth": round(sun_dir, 2),
            "panel_azimuth": round(sun_dir + _sim_value(0.0, 5.0, 0.2, 1.5), 2),
            "light_lux": light_lux,
        },
        "camouflage": {
            "color_hsl": camo_color_hsl,
        },
        "danger_level": danger,
    }


def _active_session() -> Optional[dict]:
    if not db:
        return None
    try:
        return db["session"].find_one({"active": True})
    except Exception:
        return None


@app.get("/api/telemetry")
def telemetry():
    """Return simulated real-time telemetry for the rover and optionally persist when a session is active."""
    payload = _make_telemetry_payload()

    # Auto-attach image url for convenience
    payload["image"] = {
        "url": "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=1600&auto=format&fit=crop"
    }

    # If a recording session is active, persist this snapshot
    sess = _active_session()
    if sess:
        try:
            create_document("telemetry", payload)
        except Exception:
            pass

    return payload


@app.post("/api/session/start")
def start_session():
    """Start a recording session so that subsequent telemetry calls are stored."""
    if not db:
        return JSONResponse({"status": "error", "message": "Database not configured"}, status_code=400)

    # Deactivate previous sessions
    db["session"].update_many({"active": True}, {"$set": {"active": False, "ended_at": datetime.utcnow()}})
    sess = {
        "active": True,
        "started_at": datetime.utcnow(),
        "note": "TOFY-X1 recording session"
    }
    db["session"].insert_one(sess)
    return {"status": "ok", "active": True}


@app.post("/api/session/stop")
def stop_session():
    if not db:
        return JSONResponse({"status": "error", "message": "Database not configured"}, status_code=400)
    db["session"].update_many({"active": True}, {"$set": {"active": False, "ended_at": datetime.utcnow()}})
    return {"status": "ok", "active": False}


@app.get("/api/telemetry/history")
def telemetry_history(
    limit: int = Query(300, ge=1, le=5000),
    minutes: Optional[int] = Query(None, ge=1, le=1440),
):
    """Return recent telemetry documents, optionally limited to last N minutes."""
    if not db:
        return JSONResponse({"status": "error", "message": "Database not configured"}, status_code=400)

    q: Dict[str, Any] = {}
    if minutes is not None:
        since = datetime.utcnow() - timedelta(minutes=minutes)
        q = {"created_at": {"$gte": since}}

    docs = list(db["telemetry"].find(q).sort("created_at", -1).limit(limit))
    for d in docs:
        d["_id"] = str(d["_id"])  # make JSON serializable
        if "created_at" in d:
            d["created_at"] = d["created_at"].isoformat()
        if "updated_at" in d:
            d["updated_at"] = d["updated_at"].isoformat()
    return {"items": list(reversed(docs))}


@app.get("/api/export/csv")
def export_csv(
    minutes: Optional[int] = Query(None, ge=1, le=1440),
    limit: int = Query(2000, ge=10, le=20000),
):
    """Export telemetry history as CSV."""
    if not db:
        return JSONResponse({"status": "error", "message": "Database not configured"}, status_code=400)

    q: Dict[str, Any] = {}
    if minutes is not None:
        since = datetime.utcnow() - timedelta(minutes=minutes)
        q = {"created_at": {"$gte": since}}

    docs = list(db["telemetry"].find(q).sort("created_at", -1).limit(limit))

    # CSV header
    headers = [
        "timestamp",
        "ambient_temp_c","surface_temp_c","uv_index","ir_mw_m2","light_lux",
        "battery_pct","battery_voltage",
        "pitch","roll","yaw",
        "lat","lon","speed_mps","heading",
        "target_azimuth","panel_azimuth",
        "camo_color_hsl",
        "danger_level",
        "created_at"
    ]

    def row(d: Dict[str, Any]) -> List[str]:
        env = d.get("environment", {})
        powr = d.get("power", {})
        att = d.get("attitude", {})
        nav = d.get("navigation", {})
        sol = d.get("solar", {})
        cam = d.get("camouflage", {})
        return [
            d.get("timestamp", ""),
            str(env.get("ambient_temp_c", "")), str(env.get("surface_temp_c", "")), str(env.get("uv_index", "")), str(env.get("ir_mw_m2", "")), str(env.get("light_lux", "")),
            str(powr.get("battery_pct", "")), str(powr.get("battery_voltage", "")),
            str(att.get("pitch", "")), str(att.get("roll", "")), str(att.get("yaw", "")),
            str(nav.get("lat", "")), str(nav.get("lon", "")), str(nav.get("speed_mps", "")), str(nav.get("heading", "")),
            str(sol.get("target_azimuth", "")), str(sol.get("panel_azimuth", "")),
            cam.get("color_hsl", ""),
            d.get("danger_level", ""),
            d.get("created_at").isoformat() if isinstance(d.get("created_at"), datetime) else str(d.get("created_at", "")),
        ]

    def generate():
        yield ",".join(headers) + "\n"
        for d in reversed(docs):
            yield ",".join(row(d)) + "\n"

    return StreamingResponse(generate(), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=tofy_telemetry.csv"
    })


@app.get("/api/metrics/summary")
def metrics_summary(minutes: int = Query(60, ge=1, le=1440)):
    """Compute min/max/avg for key metrics in a time window."""
    if not db:
        return JSONResponse({"status": "error", "message": "Database not configured"}, status_code=400)
    since = datetime.utcnow() - timedelta(minutes=minutes)
    q = {"created_at": {"$gte": since}}
    docs = list(db["telemetry"].find(q))
    if not docs:
        return {"items": 0, "summary": {}}

    def agg(path: List[str]):
        vals = []
        for d in docs:
            cur = d
            for p in path:
                cur = cur.get(p, {}) if isinstance(cur, dict) else {}
            try:
                vals.append(float(cur))
            except Exception:
                pass
        if not vals:
            return {"min": None, "max": None, "avg": None}
        return {"min": min(vals), "max": max(vals), "avg": sum(vals) / len(vals)}

    return {
        "items": len(docs),
        "summary": {
            "ambient_temp_c": agg(["environment", "ambient_temp_c"]),
            "surface_temp_c": agg(["environment", "surface_temp_c"]),
            "uv_index": agg(["environment", "uv_index"]),
            "light_lux": agg(["environment", "light_lux"]),
            "battery_pct": agg(["power", "battery_pct"]),
            "speed_mps": agg(["navigation", "speed_mps"]),
        },
    }


@app.get("/api/image")
def image():
    """Provide a sample camera frame (static placeholder)."""
    return {
        "url": "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=1600&auto=format&fit=crop"
    }


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
