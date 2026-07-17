"""
run: docker compose run --rm training python /app/gru_forecast.py
GRU vs Naive Baseline Comparison Module - Incremental Saving & Stock Priority
============================================================================
Mô hình: GRU (Gated Recurrent Unit) vs Naive Baseline (y_t = y_{t-1})
Output: Ưu tiên STOCK chạy trước, xong mã nào lưu ngay vào forecast_results.csv
"""

import os
import logging
import warnings
from pathlib import Path
from typing import Tuple, Dict, List, Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import MinMaxScaler
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings("ignore")

# ============================================================================
# LOGGER CONFIGURATION
# ============================================================================
def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

logger = setup_logger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================
class GRUConfig:
    WINDOW_SIZE: int = 30
    INPUT_SIZE: int = 2  # Close + MA7
    HIDDEN_SIZE: int = 64
    NUM_LAYERS: int = 2
    OUTPUT_SIZE: int = 1
    DROPOUT: float = 0.2
    
    EPOCHS: int = 60
    BATCH_SIZE: int = 32
    LEARNING_RATE: float = 0.0005
    WEIGHT_DECAY: float = 1e-4
    
    TRAIN_SPLIT: float = 0.8
    MIN_DATA_POINTS: int = WINDOW_SIZE + 20
    MA_WINDOW: int = 7
    TIMEFRAME: str = "1d"
    
    DEVICE: torch.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def set_random_seed(seed: int = 42) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    logger.info(f"✓ Random seed fixed to {seed}")

# ============================================================================
# GRU MODEL
# ============================================================================
class OptimizedGRU(nn.Module):
    def __init__(
        self,
        input_size: int = 2,
        hidden_size: int = 64,
        num_layers: int = 2,
        output_size: int = 1,
        dropout: float = 0.2
    ):
        super(OptimizedGRU, self).__init__()
        self.gru = nn.GRU(
            input_size,
            hidden_size,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc = nn.Linear(hidden_size, output_size)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h0 = torch.zeros(
            self.gru.num_layers, x.size(0), self.gru.hidden_size,
            device=x.device, dtype=x.dtype
        )
        out, _ = self.gru(x, h0)
        return self.fc(out[:, -1, :])

# ============================================================================
# DATA PROCESSING
# ============================================================================
def validate_data(df: pd.DataFrame, ticker: str, min_points: int) -> bool:
    if df.empty or len(df) < min_points:
        logger.warning(f"⚠ {ticker}: Không đủ điểm dữ liệu ({len(df)}/{min_points})")
        return False
    if df[["close"]].isnull().any().any() or (df["close"] <= 0).any():
        logger.warning(f"⚠ {ticker}: Dữ liệu giá close không hợp lệ")
        return False
    return True

def create_features(df: pd.DataFrame, ma_window: int = 7) -> pd.DataFrame:
    df = df.copy()
    df["ma7"] = df["close"].rolling(window=ma_window).mean().bfill()
    return df

def create_sequences(
    X_data: np.ndarray,
    y_data: np.ndarray,
    window_size: int = 30
) -> Tuple[np.ndarray, np.ndarray]:
    X, y = [], []
    for i in range(len(X_data) - window_size):
        X.append(X_data[i:i + window_size])
        y.append(y_data[i + window_size])
    return np.array(X), np.array(y)

# ============================================================================
# TRAINING & METRICS EVALUATION
# ============================================================================
def train_model(
    model: OptimizedGRU,
    train_loader: DataLoader,
    config: GRUConfig
) -> float:
    criterion = nn.MSELoss()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.LEARNING_RATE,
        weight_decay=config.WEIGHT_DECAY
    )
    model.train()
    last_loss = 0.0
    for epoch in range(config.EPOCHS):
        epoch_loss = 0.0
        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(config.DEVICE), batch_y.to(config.DEVICE)
            optimizer.zero_grad()
            predictions = model(batch_X)
            loss = criterion(predictions, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        last_loss = epoch_loss / len(train_loader)
    return last_loss

def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    mse = np.mean((y_true - y_pred) ** 2)
    mae = np.mean(np.abs(y_true - y_pred))
    mape = np.mean(np.abs((y_true - y_pred) / (np.abs(y_true) + 1e-8)))
    
    return {
        "mse": float(mse),
        "mae": float(mae),
        "mape": float(mape)
    }

def evaluate_and_compare(
    model: OptimizedGRU,
    X_test: np.ndarray,
    y_test: np.ndarray,
    scaler_y: MinMaxScaler,
    config: GRUConfig
) -> Dict[str, Dict[str, float]]:
    model.eval()
    with torch.no_grad():
        X_test_tensor = torch.tensor(X_test, dtype=torch.float32).to(config.DEVICE)
        test_preds_scaled = model(X_test_tensor).cpu().numpy()
    
    y_test_true = scaler_y.inverse_transform(y_test)
    
    # 1. Kết quả GRU
    y_test_gru = scaler_y.inverse_transform(test_preds_scaled)
    gru_metrics = calculate_metrics(y_test_true, y_test_gru)
    
    # 2. Kết quả Naive Baseline
    naive_scaled = X_test[:, -1, 0].reshape(-1, 1)
    y_test_naive = scaler_y.inverse_transform(naive_scaled)
    naive_metrics = calculate_metrics(y_test_true, y_test_naive)
    
    return {"gru": gru_metrics, "naive": naive_metrics}

# ============================================================================
# DATA LOADING & SYMBOL PROCESSING
# ============================================================================
def load_data(data_dir: str = "data") -> Tuple[pd.DataFrame, pd.DataFrame]:
    possible_paths = [data_dir, "data", "../../data", "/app/data", r"E:\NCKH-CryptographicAnalysis\data"]
    for path in possible_paths:
        if os.path.exists(os.path.join(path, "market_ohlcv.csv")):
            df_ohlcv = pd.read_csv(os.path.join(path, "market_ohlcv.csv"))
            df_symbol = pd.read_csv(os.path.join(path, "market_symbol.csv"))
            logger.info(f"✓ Đã tải dữ liệu từ: {path} ({len(df_ohlcv)} nến)")
            return df_ohlcv, df_symbol
    raise FileNotFoundError("❌ Không tìm thấy thư mục data!")

def process_symbol(
    ticker: str,
    symbol_id: int,
    df_ohlcv: pd.DataFrame,
    config: GRUConfig
) -> Optional[List[Dict]]:
    try:
        df_target = (
            df_ohlcv[df_ohlcv["symbol_id"] == symbol_id]
            .copy().sort_values("ts").reset_index(drop=True)
        )
        if not validate_data(df_target, ticker, config.MIN_DATA_POINTS):
            return None
        
        logger.info(f"⚡ ĐANG PHÂN TÍCH: {ticker} | {len(df_target)} nến")
        
        df_target = create_features(df_target, config.MA_WINDOW)
        X_raw = df_target[["close", "ma7"]].values
        y_raw = df_target[["close"]].values
        
        train_size = int(len(X_raw) * config.TRAIN_SPLIT)
        
        scaler_X = MinMaxScaler(feature_range=(0, 1))
        scaler_y = MinMaxScaler(feature_range=(0, 1))
        
        X_train_scaled = scaler_X.fit_transform(X_raw[:train_size])
        X_test_scaled = scaler_X.transform(X_raw[train_size:])
        y_train_scaled = scaler_y.fit_transform(y_raw[:train_size])
        y_test_scaled = scaler_y.transform(y_raw[train_size:])
        
        X_train, y_train = create_sequences(X_train_scaled, y_train_scaled, config.WINDOW_SIZE)
        X_test, y_test = create_sequences(X_test_scaled, y_test_scaled, config.WINDOW_SIZE)
        
        train_loader = DataLoader(
            TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32)),
            batch_size=config.BATCH_SIZE, shuffle=False
        )
        
        model = OptimizedGRU(
            input_size=config.INPUT_SIZE, hidden_size=config.HIDDEN_SIZE,
            num_layers=config.NUM_LAYERS, output_size=config.OUTPUT_SIZE, dropout=config.DROPOUT
        ).to(config.DEVICE)
        
        train_model(model, train_loader, config)
        
        comparison = evaluate_and_compare(model, X_test, y_test, scaler_y, config)
        
        row_gru = {
            "symbol": ticker,
            "timeframe": config.TIMEFRAME,
            "model_type": "gru",
            "mse": comparison["gru"]["mse"],
            "mae": comparison["gru"]["mae"],
            "mape": comparison["gru"]["mape"]
        }
        
        row_naive = {
            "symbol": ticker,
            "timeframe": config.TIMEFRAME,
            "model_type": "naive",
            "mse": comparison["naive"]["mse"],
            "mae": comparison["naive"]["mae"],
            "mape": comparison["naive"]["mape"]
        }
        
        logger.info(f"  + GRU   | MSE: {row_gru['mse']:.4f} | MAE: {row_gru['mae']:.4f} | MAPE: {row_gru['mape']:.4f}")
        logger.info(f"  + Naive | MSE: {row_naive['mse']:.4f} | MAE: {row_naive['mae']:.4f} | MAPE: {row_naive['mape']:.4f}")
        
        return [row_gru, row_naive]
    except Exception as e:
        logger.error(f"❌ Lỗi xử lý {ticker}: {str(e)}")
        return None

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def main():
    logger.info("=" * 80)
    logger.info("⚡ GRU vs NAIVE - INCREMENTAL EXPORT TO FORECAST_RESULTS.CSV")
    logger.info("=" * 80)
    
    set_random_seed(42)
    config = GRUConfig()
    
    try:
        df_ohlcv, df_symbol = load_data("data")
    except FileNotFoundError as e:
        logger.error(str(e))
        return

    # 1. TẠO BỘ LỌC ƯU TIÊN: Đẩy toàn bộ mã STOCK lên chạy trước
    if "asset_class" in df_symbol.columns:
        df_symbol["clean_class"] = df_symbol["asset_class"].fillna("UNKNOWN").astype(str).str.upper()
        # Gán trọng số: STOCK là 0 (lên đầu), còn lại là 1
        df_symbol["priority"] = df_symbol["clean_class"].apply(lambda x: 0 if x == "STOCK" else 1)
        df_symbol = df_symbol.sort_values(by=["priority", "ticker"]).reset_index(drop=True)
        logger.info("✓ Đã sắp xếp: Ưu tiên phân tích toàn bộ CỔ PHIẾU (STOCK) trước!\n")
    else:
        df_symbol = df_symbol.sort_values(by="ticker").reset_index(drop=True)

    # 2. CHUẨN BỊ FILE OUTPUT (Xóa file cũ nếu tồn tại để bắt đầu bản ghi mới)
    output_file = "forecast_results.csv"
    if os.path.exists(output_file):
        os.remove(output_file)
        logger.info(f"✓ Đã làm mới file đầu ra: {output_file}\n")
    
    total_symbols = len(df_symbol)
    processed_count = 0
    
    # 3. VÒNG LẶP XỬ LÝ & GHI NỐI TIẾP TỨC THÌ
    for idx, row in df_symbol.iterrows():
        ticker = row["ticker"]
        res_pair = process_symbol(ticker, row["id"], df_ohlcv, config)
        
        if res_pair:
            # Chuyển kết quả của mã hiện tại thành DataFrame
            df_temp = pd.DataFrame(res_pair)
            
            # Nếu file chưa tồn tại -> Ghi kèm Header. Nếu đã có -> Chỉ append vào đuôi file
            write_header = not os.path.exists(output_file)
            df_temp.to_csv(output_file, mode="a", index=False, header=write_header, encoding="utf-8")
            
            processed_count += 1
            logger.info(f"  --> [Đã lưu {processed_count}/{total_symbols}] Kết quả của {ticker} vào {output_file}\n")

    logger.info("=" * 80)
    logger.info(f"🎉 HOÀN TẤT! Toàn bộ kết quả đã được lưu an toàn tại: {os.path.abspath(output_file)}")
    logger.info("=" * 80)

if __name__ == "__main__":
    main()