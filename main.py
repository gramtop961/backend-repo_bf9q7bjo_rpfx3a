import os
import base64
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Suspect, MatchEvent, TriangulationInput, TriangulationResult

app = FastAPI(title="Netra: AI-Driven Fugitive Localization API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Netra backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ------------------------- Suspects -------------------------
class SuspectCreate(Suspect):
    pass


@app.post("/api/suspects")
def create_suspect(payload: SuspectCreate):
    sid = create_document("suspect", payload)
    return {"_id": sid}


@app.get("/api/suspects")
def list_suspects():
    docs = get_documents("suspect", {})
    # Convert ObjectId to string
    for d in docs:
        if "_id" in d:
            d["_id"] = str(d["_id"])
    return docs


@app.get("/api/suspects/{suspect_id}")
def get_suspect(suspect_id: str):
    from bson import ObjectId

    try:
        oid = ObjectId(suspect_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid suspect id")

    doc = db["suspect"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Suspect not found")
    doc["_id"] = str(doc["_id"])
    return doc


# ------------------------- Scanning (Simulated) -------------------------
class ScanRequest(BaseModel):
    suspect_id: str


def _seed_locations():
    # A small set of well-known public locations to simulate detections
    return [
        {"name": "Connaught Place, Delhi", "lat": 28.6315, "lng": 77.2167},
        {"name": "India Gate, Delhi", "lat": 28.6129, "lng": 77.2295},
        {"name": "Gateway of India, Mumbai", "lat": 18.9220, "lng": 72.8347},
        {"name": "Marine Drive, Mumbai", "lat": 18.9432, "lng": 72.8238},
        {"name": "MG Road, Bengaluru", "lat": 12.9738, "lng": 77.6077},
        {"name": "Charminar, Hyderabad", "lat": 17.3616, "lng": 78.4747},
    ]


def _build_event(suspect_id: str, source_type: str, location: dict, confidence: float, media_url: Optional[str] = None):
    msg = f"Suspect face matched on {source_type.capitalize()} (Location: {location['name']})."
    event = MatchEvent(
        suspect_id=suspect_id,
        source_type=source_type,  # type: ignore
        confidence=confidence,
        message=msg,
        latitude=location["lat"],
        longitude=location["lng"],
        captured_at=datetime.utcnow(),
        media_url=media_url,
    )
    eid = create_document("matchevent", event)
    payload = event.model_dump()
    payload.update({"_id": eid})
    return payload


@app.post("/api/scan/social")
def scan_social(req: ScanRequest):
    # Simulate by creating 1-3 match events based on suspect aliases/seed
    from random import random, choice

    # Validate suspect exists
    _ = get_suspect(req.suspect_id)

    locs = _seed_locations()
    results = []
    for _i in range(2):
        loc = choice(locs)
        conf = round(0.7 + random() * 0.25, 3)
        results.append(_build_event(req.suspect_id, "instagram", loc, conf))
    return {"events": results}


@app.post("/api/scan/cameras")
def scan_cameras(req: ScanRequest):
    # Simulate scanning of public IP cameras by adding events near traffic/tourist spots
    from random import random, choice

    _ = get_suspect(req.suspect_id)

    camera_spots = [
        {"name": "Traffic Cam - Connaught Circus", "lat": 28.6319, "lng": 77.2195},
        {"name": "Tourist Cam - India Gate Lawn", "lat": 28.6123, "lng": 77.2298},
        {"name": "Traffic Cam - Marine Drive", "lat": 18.9438, "lng": 72.8230},
    ]
    results: List[dict] = []
    for _i in range(1):
        loc = choice(camera_spots)
        conf = round(0.6 + random() * 0.3, 3)
        results.append(_build_event(req.suspect_id, "ip_camera", loc, conf))
    return {"events": results}


# ------------------------- EXIF Parsing -------------------------
class ExifParseRequest(BaseModel):
    image_base64: str


@app.post("/api/exif/parse")
def parse_exif(req: ExifParseRequest):
    try:
        from PIL import Image
        from io import BytesIO
        import piexif
    except Exception:
        # If Pillow/piexif not installed, return a graceful message
        return {"gps": None, "note": "EXIF parsing not available (Pillow/piexif not installed)."}

    try:
        data = base64.b64decode(req.image_base64)
        im = Image.open(BytesIO(data))
        info = im.info
        exif_bytes = info.get("exif")
        if not exif_bytes:
            return {"gps": None, "note": "No EXIF metadata found."}
        exif_dict = piexif.load(exif_bytes)
        gps = exif_dict.get("GPS", {})
        if not gps:
            return {"gps": None, "note": "No GPS tags present."}

        def _convert_to_degrees(value):
            d = float(value[0][0]) / float(value[0][1])
            m = float(value[1][0]) / float(value[1][1])
            s = float(value[2][0]) / float(value[2][1])
            return d + (m / 60.0) + (s / 3600.0)

        lat = _convert_to_degrees(gps.get(piexif.GPSIFD.GPSLatitude)) if gps.get(piexif.GPSIFD.GPSLatitude) else None
        lat_ref = gps.get(piexif.GPSIFD.GPSLatitudeRef)
        lng = _convert_to_degrees(gps.get(piexif.GPSIFD.GPSLongitude)) if gps.get(piexif.GPSIFD.GPSLongitude) else None
        lng_ref = gps.get(piexif.GPSIFD.GPSLongitudeRef)

        if lat and lat_ref and lat_ref.decode() == 'S':
            lat = -lat
        if lng and lng_ref and lng_ref.decode() == 'W':
            lng = -lng

        return {"gps": {"latitude": lat, "longitude": lng}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"EXIF parse error: {str(e)[:120]}")


# ------------------------- Events -------------------------
@app.get("/api/events/{suspect_id}")
def list_events(suspect_id: str):
    docs = get_documents("matchevent", {"suspect_id": suspect_id})
    for d in docs:
        d["_id"] = str(d["_id"]) if "_id" in d else None
        # Ensure captured_at is string
        if isinstance(d.get("captured_at"), datetime):
            d["captured_at"] = d["captured_at"].isoformat()
    # sort by captured_at desc
    docs.sort(key=lambda x: x.get("captured_at", ""), reverse=True)
    return {"events": docs}


# ------------------------- Triangulation -------------------------
@app.post("/api/triangulate", response_model=TriangulationResult)
def triangulate(payload: TriangulationInput):
    # Simple centroid method; if radius available, use inverse distance weighting
    nodes = payload.nodes
    if not nodes:
        raise HTTPException(status_code=400, detail="No nodes provided")

    # Weighted by radius if provided (smaller radius => stronger weight)
    weights = []
    for n in nodes:
        if n.radius_m and n.radius_m > 0:
            weights.append(1.0 / n.radius_m)
        else:
            weights.append(1.0)

    total_w = sum(weights)
    lat = sum(n.latitude * w for n, w in zip(nodes, weights)) / total_w
    lng = sum(n.longitude * w for n, w in zip(nodes, weights)) / total_w

    return TriangulationResult(latitude=lat, longitude=lng, method="weighted" if any(n.radius_m for n in nodes) else "centroid", nodes=nodes)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
