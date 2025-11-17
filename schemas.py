"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Telemetry schema for persisted rover data
class TelemetryEnvironment(BaseModel):
    ambient_temp_c: float
    surface_temp_c: float
    uv_index: float
    ir_mw_m2: float
    light_lux: float

class TelemetryPower(BaseModel):
    battery_pct: float
    battery_voltage: float

class TelemetryAttitude(BaseModel):
    pitch: float
    roll: float
    yaw: float

class TelemetryNavigation(BaseModel):
    lat: float
    lon: float
    speed_mps: float
    heading: float

class TelemetrySolar(BaseModel):
    target_azimuth: float
    panel_azimuth: float
    light_lux: float

class TelemetryCamouflage(BaseModel):
    color_hsl: str

class Telemetry(BaseModel):
    timestamp: str
    environment: TelemetryEnvironment
    power: TelemetryPower
    attitude: TelemetryAttitude
    navigation: TelemetryNavigation
    solar: TelemetrySolar
    camouflage: TelemetryCamouflage
    danger_level: str

# Add your own schemas here:
# --------------------------------------------------

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints!
