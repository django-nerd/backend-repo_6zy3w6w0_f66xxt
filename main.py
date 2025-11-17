import os
import math
import random
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TOFY-X1 Backend", version="1.0.0")

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


@app.get("/api/telemetry")
def telemetry():
    """Return simulated real-time telemetry for the rover."""
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
    # Map surface_temp 10C..60C to hue 220..0
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


@app.get("/api/image")
def image():
    """Provide a sample camera frame (static placeholder)."""
    # Using a royalty-free placeholder image
    return {
        "url": "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=1600&auto=format&fit=crop"
    }


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
