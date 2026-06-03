import type { Metadata } from "next";
import Navbar from "@/components/navbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hệ Thống Phân Tích & Dự Báo Cổ Phiếu - Tiền Số | NCKH",
  description: "Trực quan hóa chỉ số tài chính, chạy mô hình học máy LSTM, GRU, ARIMA, XGBoost và giải thích kết quả bằng SHAP cho thị trường Việt Nam & Crypto.",
  keywords: "dự báo giá cổ phiếu, vnstock, crypto forecast, lstm forecast, xgboost shap",
  authors: [{ name: "Student Agile Team" }],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className="dark">
      <body className="min-h-screen flex flex-col relative bg-darkBg text-slate-100 antialiased selection:bg-glowIndigo/30 selection:text-white">
        {/* Glow Ambient Orbs for rich aesthetics */}
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-glowIndigo/5 blur-[120px] pointer-events-none" />
        <div className="absolute bottom-[20%] right-[-5%] w-[40%] h-[40%] rounded-full bg-glowEmerald/5 blur-[120px] pointer-events-none" />
        
        <Navbar />
        
        <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 z-10">
          {children}
        </main>
        
        <footer className="w-full border-t border-darkBorder py-6 text-center text-xs text-slate-500 glass-panel">
          <p>© {new Date().getFullYear()} Đồ Án Nghiên Cứu Khoa Học - Nhóm 5 SV Agile. All rights reserved.</p>
        </footer>
      </body>
    </html>
  );
}
