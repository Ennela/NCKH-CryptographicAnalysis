import Link from "next/link";
import { ArrowUpRight, ShieldCheck, Database, Brain, Activity } from "lucide-react";

export default function Dashboard() {
  const stats = [
    { label: "Mã Theo Dõi", value: "5", description: "3 Cổ phiếu VN + 2 Crypto", icon: Database, color: "text-glowIndigo" },
    { label: "Mô Hình Hoạt Động", value: "4", description: "ARIMA, XGBoost, LSTM, GRU", icon: Brain, color: "text-glowEmerald" },
    { label: "Số Bản Ghi Giá (Candles)", value: "50,000+", description: "Cập nhật mỗi 1 giờ / 1 ngày", icon: Activity, color: "text-amber-400" },
    { label: "Độ Đo MAPE Trung Bình", value: "1.25%", description: "Đánh giá trên tập kiểm thử", icon: ShieldCheck, color: "text-glowRose" },
  ];

  const symbols = [
    { id: "BTC/USDT", name: "Bitcoin / Tether", type: "Crypto", exchange: "Binance", price: "$68,250.00", change: "+2.4%" },
    { id: "FPT", name: "Công ty Cổ phần FPT", type: "Stock", exchange: "HOSE", price: "135,200 đ", change: "+1.8%" },
    { id: "ETH/USDT", name: "Ethereum / Tether", type: "Crypto", exchange: "Binance", price: "$3,780.00", change: "-0.5%" },
    { id: "VCB", name: "Ngân hàng Vietcombank", type: "Stock", exchange: "HOSE", price: "96,100 đ", change: "+0.2%" },
  ];

  return (
    <div className="space-y-10 animate-fade-in">
      {/* Hero Welcome banner */}
      <section className="glass-panel p-8 md:p-12 rounded-2xl border border-darkBorder flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
        <div className="space-y-4 max-w-2xl">
          <h1 className="text-3xl md:text-5xl font-extrabold tracking-tight bg-gradient-to-r from-glowIndigo to-glowEmerald bg-clip-text text-transparent">
            Hệ Thống Phân Tích & Dự Báo Giá
          </h1>
          <p className="text-slate-400 text-sm md:text-base leading-relaxed">
            Dự án nghiên cứu xây dựng pipeline tự động thu thập dữ liệu giá OHLCV thị trường Tài chính & Crypto, 
            huấn luyện mô hình học sâu chuỗi thời gian, và giải thích quyết định dự báo dựa trên SHAP.
          </p>
        </div>
        <div className="flex gap-4">
          <Link href="/forecast" className="px-6 py-3 rounded-xl bg-glowIndigo text-white font-semibold shadow-lg shadow-glowIndigo/20 hover:bg-glowIndigo/80 hover:shadow-glowIndigo/35 transition-all">
            Chạy Dự Báo
          </Link>
          <Link href="/symbols" className="px-6 py-3 rounded-xl bg-slate-800 border border-slate-700 hover:bg-slate-700/50 transition-all text-slate-300 font-semibold">
            Xem Bảng Giá
          </Link>
        </div>
      </section>

      {/* Stats Cards Section */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, idx) => {
          const Icon = stat.icon;
          return (
            <div key={idx} className="glass-card p-6 rounded-xl border border-darkBorder flex flex-col justify-between h-36">
              <div className="flex justify-between items-start">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{stat.label}</span>
                <Icon className={`w-5 h-5 ${stat.color}`} />
              </div>
              <div className="mt-2">
                <span className="text-3xl font-bold tracking-tight text-slate-100">{stat.value}</span>
                <p className="text-slate-500 text-xs mt-1">{stat.description}</p>
              </div>
            </div>
          );
        })}
      </section>

      {/* Symbols Table list */}
      <section className="space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-xl md:text-2xl font-bold tracking-tight text-slate-200">Danh Sách Mã Giá Giám Sát</h2>
          <Link href="/symbols" className="text-glowIndigo hover:text-glowIndigo/80 text-sm flex items-center gap-1">
            Xem tất cả <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>

        <div className="glass-panel rounded-xl border border-darkBorder overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-darkBorder bg-slate-900/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                <th className="py-4 px-6">Mã Tài Sản</th>
                <th className="py-4 px-6">Tên</th>
                <th className="py-4 px-6">Loại</th>
                <th className="py-4 px-6">Sàn Giao Dịch</th>
                <th className="py-4 px-6">Giá Gần Nhất</th>
                <th className="py-4 px-6 text-right">Biến động 24h</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-darkBorder/40">
              {symbols.map((sym) => (
                <tr key={sym.id} className="hover:bg-slate-800/25 transition-all text-sm text-slate-300">
                  <td className="py-4 px-6 font-bold text-glowIndigo">{sym.id}</td>
                  <td className="py-4 px-6 text-slate-400">{sym.name}</td>
                  <td className="py-4 px-6">
                    <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                      sym.type === "Crypto" ? "bg-purple-500/10 text-purple-400 border border-purple-500/20" : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                    }`}>
                      {sym.type}
                    </span>
                  </td>
                  <td className="py-4 px-6 text-xs text-slate-500">{sym.exchange}</td>
                  <td className="py-4 px-6 font-semibold">{sym.price}</td>
                  <td className={`py-4 px-6 text-right font-semibold ${sym.change.startsWith("+") ? "text-glowEmerald" : "text-glowRose"}`}>
                    {sym.change}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
