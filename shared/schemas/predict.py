from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

# Các model nằm trong phạm vi đề tài (LSTM đã bị loại — xem AGENTS.md §4)
ALLOWED_MODELS = ("arima", "xgboost", "random_forest", "gru")
ALLOWED_TIMEFRAMES = ("1d", "1h")


class PredictRequest(BaseModel):
    ticker_id: str = Field(..., description="Mã tài sản, ví dụ: FPT hoặc BTCUSDT")
    model_name: str = Field(
        ..., description="Tên mô hình: arima, xgboost, random_forest, gru"
    )
    steps: int = Field(5, ge=1, le=30, description="Số bước cần dự báo về tương lai")
    timeframe: Optional[str] = Field(
        None,
        description="Khung thời gian ('1d', '1h'); mặc định suy ra từ asset_class",
    )

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        name = v.strip().lower()
        if name not in ALLOWED_MODELS:
            raise ValueError(f"Model name must be one of {ALLOWED_MODELS}")
        return name

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        tf = v.strip().lower()
        if tf not in ALLOWED_TIMEFRAMES:
            raise ValueError(f"Timeframe must be one of {ALLOWED_TIMEFRAMES}")
        return tf


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
    # Naive baseline (y_hat = close hiện tại) trên cùng tập test — AGENTS.md §6
    naive_mae: Optional[float] = None
    naive_rmse: Optional[float] = None
    naive_mape: Optional[float] = None
    directional_accuracy: Optional[float] = None


class ModelInfoResponse(BaseModel):
    model_name: str
    version: str
    status: str
    metrics: Optional[ModelMetrics] = None
    last_updated: Optional[datetime] = None


class ExplainFeature(BaseModel):
    """Một feature (hoặc tham số ARIMA) trong kết quả giải thích mô hình.

    Ý nghĩa của ``importance`` phụ thuộc ``ExplainResponse.method``:
    - ``shap_tree_explainer`` (xgboost, random_forest): độ quan trọng của cây,
      kèm ``mean_abs_shap``.
    - ``permutation_importance`` (gru): RMSE tăng thêm (đơn vị giá) khi xáo
      trộn feature, kèm độ lệch chuẩn ``importance_std`` qua các lần lặp.
    - ``arima_coefficients`` (arima): |hệ số|, kèm ``coefficient`` có dấu,
      ``std_error`` và ``p_value``.
    """

    feature: str
    importance: float
    mean_abs_shap: Optional[float] = None
    importance_std: Optional[float] = None
    coefficient: Optional[float] = None
    std_error: Optional[float] = None
    p_value: Optional[float] = None


class ExplainResponse(BaseModel):
    """Kết quả giải thích mô hình lấy từ artifact đã log lúc train."""

    ticker: str
    timeframe: str
    model_name: str
    method: str
    features: List[ExplainFeature]
    generated_at: Optional[datetime] = None
    n_samples: Optional[int] = None
    baseline_rmse: Optional[float] = None
    n_repeats: Optional[int] = None
    order: Optional[List[int]] = None
    n_observations: Optional[int] = None
