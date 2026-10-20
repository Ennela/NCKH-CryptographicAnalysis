import type { Metadata } from "next";
import Navbar from "@/components/navbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hệ thống phân tích & dự báo giá cổ phiếu – tiền số | NCKH",
  description:
    "Thu thập, làm sạch, phân tích và dự báo giá cổ phiếu Việt Nam & tiền mã hóa bằng ARIMA, XGBoost, Random Forest, GRU; giải thích mô hình bằng SHAP.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="flex min-h-screen flex-col bg-page text-slate-100 antialiased">
        <Navbar />
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-5 py-6">{children}</main>
        <footer className="border-t border-line bg-panel py-4 text-center text-xs text-slate-400">
          Đồ án Nghiên cứu khoa học — Hệ thống thu thập, phân tích &amp; dự báo giá cổ phiếu VN và tiền mã hóa
        </footer>
      </body>
    </html>
  );
}
