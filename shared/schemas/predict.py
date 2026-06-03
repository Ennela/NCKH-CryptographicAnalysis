from datetime import datetime
from typing import List
from pydantic import BaseModel, Field, field_validator

class PredictRequest(BaseModel):
    ticker_id: str = Field(..., description="Mã tài sản, ví dụ: FPT hoặc BTC/USDT")
    model_name: str = Field(..., description="Tên mô hình: arima, xgboost, lstm, gru")
    steps: int = Field(5, ge=1, le=30, description="Số bước cần dự báo về tương lai")

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        name = v.strip().lower()
        allowed = ("arima", "xgboost", "lstm", "gru")
        if name not in allowed:
            raise ValueError(f"Model name must be one of {allowed}")
        return name

class PredictionItem(BaseModel):
    target_time: datetime
    predicted_value: float

class PredictResponse(BaseModel):
    ticker_id: str
    model_name: str
    prediction_time: datetime
    predictions: List[PredictionItem]

    class Config:
        from_attributes = True

class ModelMetrics(BaseModel):
    mae: float
    rmse: float
    mape: float

class ModelInfoResponse(BaseModel):
    model_name: str
    version: str
    status: str
    metrics: ModelMetrics
    last_updated: datetime
