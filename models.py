from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class LeadScore(str, Enum):
    HOT = "hot"          # Ready to buy, has budget, timeline < 30 days
    WARM = "warm"        # Interested, exploring options
    COLD = "cold"        # Just browsing, no urgency
    UNQUALIFIED = "unqualified"  # Not a real lead

class FinancingStatus(str, Enum):
    PRE_APPROVED = "pre_approved"
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    CASH_BUYER = "cash_buyer"
    UNKNOWN = "unknown"

class PropertyType(str, Enum):
    HOUSE = "house"
    APARTMENT = "apartment"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    LAND = "land"
    COMMERCIAL = "commercial"
    OTHER = "other"

class LeadData(BaseModel):
    # Contact Info
    phone_number: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    
    # Property Preferences
    property_type: Optional[PropertyType] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    min_budget: Optional[int] = None
    max_budget: Optional[int] = None
    preferred_locations: List[str] = []
    
    # Timeline & Status
    timeline: Optional[str] = None  # "immediately", "1-3 months", "3-6 months", etc.
    financing_status: Optional[FinancingStatus] = None
    is_first_time_buyer: Optional[bool] = None
    
    # Scoring
    lead_score: LeadScore = LeadScore.COLD
    buying_signals: List[str] = []  # e.g., "mentioned pre-approval", "urgent timeline"
    
    # Metadata
    call_sid: str
    call_duration: Optional[int] = None
    conversation_transcript: List[dict] = []
    # default_factory so each lead is timestamped at creation, not at import time
    extracted_at: datetime = Field(default_factory=datetime.now)
    
    # Agent Notes
    ai_summary: Optional[str] = None
    key_requirements: List[str] = []
    next_steps: Optional[str] = None