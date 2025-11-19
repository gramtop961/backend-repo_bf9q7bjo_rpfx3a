"""
Database Schemas for Netra: AI-Driven Fugitive Localization & Digital Footprint Scanner

Each Pydantic model corresponds to a MongoDB collection. The collection name is the
lowercase of the class name (e.g., Suspect -> "suspect").
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Literal
from datetime import datetime

class Suspect(BaseModel):
    name: str = Field(..., description="Suspect full name")
    aliases: List[str] = Field(default_factory=list, description="Known aliases/usernames")
    notes: Optional[str] = Field(None, description="Additional info")
    photo_base64: Optional[str] = Field(
        None, description="Base64-encoded photo uploaded by police"
    )

class Source(BaseModel):
    kind: Literal["social", "camera"] = Field(..., description="Type of public source")
    name: str = Field(..., description="Platform or camera name")
    url: Optional[HttpUrl] = Field(None, description="Publicly accessible URL if any")
    country: Optional[str] = None
    city: Optional[str] = None

class MatchEvent(BaseModel):
    suspect_id: str = Field(..., description="Reference to suspect _id as string")
    source_type: Literal["instagram", "twitter", "facebook", "ip_camera", "other"]
    confidence: float = Field(..., ge=0, le=1, description="Face match confidence 0-1")
    message: str = Field(..., description="Human-readable event summary")
    latitude: float = Field(..., description="Latitude for map marker")
    longitude: float = Field(..., description="Longitude for map marker")
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    media_url: Optional[str] = Field(None, description="Link to the matched media if public")
    exif: Optional[dict] = Field(default=None, description="Parsed EXIF if available")

class TelecomNode(BaseModel):
    name: str
    latitude: float
    longitude: float
    radius_m: Optional[float] = Field(None, description="Approx. range/estimated distance in meters")

class TriangulationInput(BaseModel):
    nodes: List[TelecomNode]

class TriangulationResult(BaseModel):
    latitude: float
    longitude: float
    method: Literal["centroid", "weighted"] = "centroid"
    nodes: List[TelecomNode]
