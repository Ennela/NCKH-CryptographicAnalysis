"use client";

import TechnicalChart from "@/components/chart";

export default function ForecastPage() {
  //  DỮ LIỆU GIẢ TẠM THỜI — xóa khi có API thật 
  const rmse = 123.45;
  const mae = 98.76;
  const r2 = 0.87;

  const history = [
    { time: "2026-08-01", open: 60000, high: 61000, low: 59500, close: 60800 },
    { time: "2026-08-02", open: 60800, high: 62000, low: 60500, close: 61500 },
    { time: "2026-08-03", open: 61500, high: 61800, low: 60900, close: 61200 },
    { time: "2026-08-04", open: 61200, high: 62500, low: 61000, close: 62300 },
    { time: "2026-08-05", open: 62300, high: 63000, low: 62000, close: 62800 },
  ];

  const forecasts = [
    { time: "2026-08-06", value: 63200 },
    { time: "2026-08-07", value: 63800 },
    { time: "2026-08-08", value: 64100 },
  ];
  // =======================================================

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-100">Phân tích &amp; Dự báo</h1>

      {/* ... phần filter giữ nguyên như cũ ... */}

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        <div className="xl:col-span-3">
          <TechnicalChart symbol="BTC/USDT" history={history} forecasts={forecasts} />
        </div>

        <div className="xl:col-span-1 space-y-6">
          <div className="glass-panel rounded-xl p-6 text-center space-y-3">
            <h2 className="text-lg font-bold text-slate-200">Đánh giá Mô hình</h2>
            <p className="text-xs text-slate-500">Trên tập dữ liệu kiểm thử (Test set)</p>
            <div className="glass-card rounded-lg p-3 text-sm">
              Root Mean Sq Error (RMSE): {rmse}
            </div>
            <div className="glass-card rounded-lg p-3 text-sm">
              Mean Absolute Error (MAE): {mae}
            </div>
            <div className="glass-card rounded-lg p-3 text-sm">
              R² Score (Độ khớp): {r2}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}