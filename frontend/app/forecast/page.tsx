"use client";

import { useState } from "react";
import TechnicalChart from "@/components/chart";
import { Play, Sparkles, Server, Info } from "lucide-react";

export default function ForecastPage() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [modelName, setModelName] = useState("xgboost");
  const [steps, setSteps] = useState(5);
  const [loading, setLoading] = useState(false);

  // States to keep the chart input
  const [chartHistory, setChartHistory] = useState([
    { time: "05-28", open: 66500, high: 67200, low: 66100, close: 67100 },
    { time: "05-29", open: 67100, high: 68100, low: 66800, close: 67800 },
    { time: "05-30", open: 67800, high: 69200, low: 67400, close: 68500 },
    { time: "05-31", open: 68500, high: 68800, low: 67100, close: 67500 },
    { time: "06-01", open: 67500, high: 68300, low: 67200, close: 68100 },
    { time: "06-02", open: 68100, high: 68900, low: 67800, close: 68250 },
  ]);

  const [chartForecasts, setChartForecasts] = useState([
    { time: "06-03", value: 68450 },
    { time: "06-04", value: 68710 },
    { time: "06-05", value: 68590 },
    { time: "06-06", value: 68900 },
    { time: "06-07", value: 69150 },
  ]);

  const modelMetadata = {
    arima: { name: "ARIMA Baseline", type: "Statistical", valError: "MAPE: 2.4%" },
    xgboost: { name: "XGBoost Regressor", type: "Machine Learning", valError: "MAPE: 1.5%" },
    lstm: { name: "PyTorch LSTM", type: "Deep Learning (Recurrent)", valError: "MAPE: 1.2%" },
    gru: { name: "PyTorch GRU", type: "Deep Learning (Recurrent)", valError: "MAPE: 1.25%" },
  };

  const handleRunForecast = () => {
    setLoading(true);
    // Simulate API request to backend POST /api/v1/predict
    setTimeout(() => {
      // Mock new predictions based on selections
      const startPrice = chartHistory[chartHistory.length - 1].close;
      const factor = modelName === "lstm" || modelName === "gru" ? 1.002 : 0.999;
      
      const newForecasts = [];
      let lastVal = startPrice;
      for (let i = 1; i <= steps; i++) {
        lastVal = lastVal * (factor + (Math.random() * 0.01 - 0.005));
        newForecasts.push({
          time: `Forecast T+${i}`,
          value: Math.round(lastVal * 100) / 100
        });
      }

      setChartForecasts(newForecasts);
      setLoading(false);
    }, 800);
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-200">Mô Phỏng Dự Báo Chuỗi Thời Gian</h1>
        <p className="text-slate-500 text-sm mt-1">
          Chạy các mô hình Deep Learning hoặc Machine Learning trên dữ liệu lịch sử để phác họa xu hướng giá tương lai.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">
        {/* Controls Panel */}
        <div className="xl:col-span-1 glass-panel p-6 rounded-xl border border-darkBorder space-y-6">
          <div className="flex items-center gap-2 text-glowIndigo font-semibold">
            <Sparkles className="w-5 h-5" />
            <span>Tham Số Mô Hình</span>
          </div>

          <div className="space-y-4">
            {/* Symbol Selection */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Mã Tài Sản</label>
              <select 
                value={symbol} 
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-slate-900 border border-darkBorder rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-glowIndigo"
              >
                <option value="BTC/USDT">BTC/USDT (Crypto)</option>
                <option value="ETH/USDT">ETH/USDT (Crypto)</option>
                <option value="FPT">FPT (Stock VN)</option>
                <option value="VCB">VCB (Stock VN)</option>
                <option value="MSN">MSN (Stock VN)</option>
              </select>
            </div>

            {/* Model Selection */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Chọn Mô Hình</label>
              <select 
                value={modelName} 
                onChange={(e) => setModelName(e.target.value)}
                className="w-full bg-slate-900 border border-darkBorder rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-glowIndigo"
              >
                <option value="arima">ARIMA Baseline</option>
                <option value="xgboost">XGBoost Regressor</option>
                <option value="lstm">LSTM (PyTorch Deep Learning)</option>
                <option value="gru">GRU (PyTorch Deep Learning)</option>
              </select>
            </div>

            {/* Steps (Sliders) */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-semibold text-slate-400 uppercase tracking-wider">
                <span>Số Bước Dự Báo</span>
                <span className="text-glowIndigo font-bold">{steps} bước</span>
              </div>
              <input 
                type="range" 
                min="1" 
                max="10" 
                value={steps} 
                onChange={(e) => setSteps(parseInt(e.target.value))}
                className="w-full accent-glowIndigo"
              />
              <span className="text-[10px] text-slate-500 block">
                {symbol.includes("/") ? "Khung 1 giờ / bước" : "Khung 1 ngày / bước"}
              </span>
            </div>

            {/* Action button */}
            <button
              onClick={handleRunForecast}
              disabled={loading}
              className="w-full py-3 rounded-lg bg-glowIndigo hover:bg-glowIndigo/85 disabled:bg-slate-800 disabled:text-slate-600 transition-all font-bold text-sm text-white flex items-center justify-center gap-2 border border-glowIndigo/20 shadow-lg shadow-glowIndigo/15"
            >
              {loading ? (
                <span>Đang xử lý mô hình...</span>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-white" />
                  <span>Kích Hoạt Dự Báo</span>
                </>
              )}
            </button>
          </div>

          <div className="pt-4 border-t border-darkBorder space-y-3">
            <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold">
              <Info className="w-4 h-4 text-slate-500" />
              <span>Thông Tin Thuật Toán</span>
            </div>
            
            <div className="bg-slate-900/50 rounded-lg p-3 border border-darkBorder/40 space-y-2 text-xs">
              <div>
                <span className="text-slate-500 block">Tên hiển thị:</span>
                <span className="font-semibold text-slate-300">{modelMetadata[modelName as keyof typeof modelMetadata].name}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Phân loại:</span>
                <span className="font-semibold text-slate-300">{modelMetadata[modelName as keyof typeof modelMetadata].type}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Sai số Test:</span>
                <span className="font-semibold text-glowEmerald">{modelMetadata[modelName as keyof typeof modelMetadata].valError}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Chart View */}
        <div className="xl:col-span-3 space-y-6">
          <TechnicalChart 
            symbol={symbol} 
            history={chartHistory} 
            forecasts={chartForecasts} 
          />
          
          <div className="glass-panel p-4 rounded-xl border border-darkBorder flex items-center gap-3">
            <div className="p-2 rounded bg-glowIndigo/10 text-glowIndigo border border-glowIndigo/20">
              <Server className="w-5 h-5" />
            </div>
            <div className="text-xs">
              <span className="font-semibold block text-slate-300">Kết nối MLflow Registry / Redis Cache</span>
              <p className="text-slate-500">Mô hình sẽ tự động được caching trên Redis để giảm tải và phục vụ cực nhanh cho các client khác.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
