from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class OHLCVBase(BaseModel):
    timestamp: datetime
    ticker_id: str = Field(..., description="Ticker ID, e.g. FPT, BTC/USDT")
    resolution: str = Field(..., description="Interval, 1h or 1d")
    open: float = Field(..., ge=0)
    high: float = Field(..., ge=0)
    low: float = Field(..., ge=0)
    close: float = Field(..., ge=0)
    volume: float = Field(..., ge=0)

    @field_validator("ticker_id")
    @classmethod
    def upper_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in ("1h", "1d"):
            raise ValueError("Resolution must be '1h' or '1d'")
        return val

class OHLCVCreate(OHLCVBase):
    pass

class OHLCVResponse(OHLCVBase):
    class Config:
        from_attributes = True
