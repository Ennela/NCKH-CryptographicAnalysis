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
          Đồ án Nghiên cứu khoa học — Hệ thống thu thập, phân tích &amp; dự báo giá cổ phiếu VN và tiền mã hóa - Khoa CNS - Trường Đại học Điện lực<br />
          Bản quyền thuộc về nhóm phát triển đề tài: Nghiên cứu quy trình phát triển phần mềm Agile và các kỹ thuật học máy hiện đại ứng dụng trong phát triển thử nghiệm hệ thống thông tin hỗ trợ thu thập, phân tích và dự báo giá cổ phiếu và tiền số<br />
          Giảng viên hướng dẫn: ThS. Nguyễn Đình Thái<br />
          Gồm các thành viên: Đỗ Quang Hà (Chủ nhiệm), Nguyễn Văn Kiên, Khiếu Đình Trung Nguyên, Nguyễn Trọng Đại, Lê Hải Nam, Nguyễn Trọng Hiếu
        </footer>
      </body>
    </html>
  );
}
