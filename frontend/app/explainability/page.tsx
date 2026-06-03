"use client";

import { useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import { Cpu, AlertCircle, HelpCircle } from "lucide-react";

export default function ExplainabilityPage() {
  const [domLoaded, setDomLoaded] = useState(false);

  useEffect(() => {
    setDomLoaded(true);
  }, []);

  // Mock SHAP values data
  // Positive SHAP values indicate pushing price UP (green)
  // Negative SHAP values indicate pulling price DOWN (rose)
  const shapFeatures = ["RSI (14)", "MACD Line", "MACD Signal", "Historical Volatility", "Log Returns (1d)", "Lagged Close (t-1)"];
  const shapValues = [0.45, -0.22, 0.08, -0.35, 0.65, 1.20]; // Mock SHAP force values

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "shadow"
      },
      backgroundColor: "#151b2c",
      borderColor: "#1e293b",
      textStyle: {
        color: "#cbd5e1"
      },
      formatter: function (params: any) {
        const item = params[0];
        const val = item.value;
        const color = val >= 0 ? "#10b981" : "#f43f5e";
        return `<div className="text-xs">
                  <span className="font-semibold block">${item.name}</span>
                  <span style="color: ${color}">Tác động (SHAP): ${val >= 0 ? "+" : ""}${val}</span>
                </div>`;
      }
    },
    grid: {
      left: "3%",
      right: "10%",
      bottom: "10%",
      top: "5%",
      containLabel: true
    },
    xAxis: {
      type: "value",
      axisLine: { lineStyle: { color: "#334155" } },
      axisLabel: { color: "#94a3b8" },
      splitLine: { lineStyle: { color: "#1e293b", type: "dashed" } }
    },
    yAxis: {
      type: "category",
      data: shapFeatures,
      axisLine: { lineStyle: { color: "#334155" } },
      axisLabel: { color: "#94a3b8" },
      splitLine: { show: false }
    },
    series: [
      {
        name: "Tác động đặc trưng (SHAP value)",
        type: "bar",
        data: shapValues,
        itemStyle: {
          color: function (params: any) {
            // green if positive impact, rose if negative impact
            return params.value >= 0 ? "#10b981" : "#f43f5e";
          },
          borderRadius: [0, 4, 4, 0]
        },
        label: {
          show: true,
          position: "right",
          formatter: function (params: any) {
            const val = params.value;
            return val >= 0 ? `+${val}` : `${val}`;
          },
          textStyle: {
            color: "#cbd5e1",
            fontWeight: "bold",
            fontSize: 11
          }
        }
      }
    ]
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-200">SHAP Model Explainability</h1>
        <p className="text-slate-500 text-sm mt-1">
          Giải thích cơ chế ra quyết định của mô hình Machine Learning XGBoost sử dụng các đặc trưng tài chính kỹ thuật.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* SHAP Chart */}
        <div className="lg:col-span-2 space-y-6">
          <div className="glass-card p-6 rounded-xl border border-darkBorder">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-bold tracking-tight text-slate-200">Biểu Đồ Lực Lượng SHAP (XGBoost Regressor)</h3>
              <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-glowEmerald border border-emerald-500/20 font-semibold uppercase">SHAP Waterfall</span>
            </div>
            
            {domLoaded ? (
              <ReactECharts option={option} style={{ height: "400px", width: "100%" }} />
            ) : (
              <div className="h-[400px] w-full flex items-center justify-center bg-slate-900/50 rounded-xl">Loading SHAP visualizer...</div>
            )}
          </div>
        </div>

        {/* Explain Summary Panel */}
        <div className="lg:col-span-1 space-y-6">
          <div className="glass-panel p-6 rounded-xl border border-darkBorder space-y-4">
            <div className="flex items-center gap-2 text-glowIndigo font-semibold">
              <Cpu className="w-5 h-5" />
              <span>Phân Tích Quyết Định</span>
            </div>

            <p className="text-slate-400 text-sm leading-relaxed">
              Mô hình XGBoost sử dụng các chỉ số kỹ thuật của 14 phiên trước để dự báo giá đóng cửa của phiên tiếp theo.
              SHAP values đo lường mức độ lệch của dự báo so với giá trị trung bình cơ sở khi thêm mỗi đặc trưng.
            </p>

            <div className="space-y-3 pt-4 border-t border-darkBorder">
              <div className="flex items-start gap-2.5 text-xs">
                <div className="w-2 h-2 rounded-full bg-glowEmerald mt-1.5 shrink-0" />
                <div>
                  <span className="font-semibold text-slate-300">Yếu tố đẩy giá tăng (Positive Impact)</span>
                  <p className="text-slate-500 mt-0.5">Tỷ suất lợi nhuận Log Returns cao (`+0.65`) chứng tỏ đà tăng đang mạnh mẽ.</p>
                </div>
              </div>
              
              <div className="flex items-start gap-2.5 text-xs">
                <div className="w-2 h-2 rounded-full bg-glowRose mt-1.5 shrink-0" />
                <div>
                  <span className="font-semibold text-slate-300">Yếu tố kéo giá giảm (Negative Impact)</span>
                  <p className="text-slate-500 mt-0.5">Độ biến động lịch sử cao (`-0.35`) làm tăng mức độ rủi ro, kéo giá dự báo đi xuống.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900 border border-darkBorder flex gap-2.5 items-start">
            <AlertCircle className="w-5 h-5 text-amber-500 shrink-0" />
            <div className="text-xs space-y-1">
              <span className="font-semibold text-slate-300 block">Lưu Ý Đối Với Mô Hình Deep Learning</span>
              <p className="text-slate-500 leading-relaxed">
                Mô hình LSTM và GRU sử dụng mạng nơ-ron không có tính giải thích trực tiếp như XGBoost. 
                Do đó, SHAP values chỉ khả dụng cho mô hình dạng cây quyết định (Tree models).
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
