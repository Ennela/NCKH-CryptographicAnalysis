"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LineChart } from "lucide-react";

/** Header from the team mockup: slate bar, links with a growing blue underline. */
const LINKS = [
  { href: "/", label: "Tổng quan" },
  { href: "/analysis", label: "Dữ liệu & Phân tích" },
  { href: "/forecast", label: "Dự báo AI" },
  { href: "/explainability", label: "Giải thích mô hình" },
  { href: "/pipeline", label: "Thu thập & Làm sạch" },
];

export default function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-line bg-panel">
      <div className="mx-auto flex max-w-[1400px] items-center gap-6 overflow-x-auto px-5">
        <Link href="/" className="flex shrink-0 items-center gap-2 py-4 text-lg font-bold text-white">
          <LineChart className="h-6 w-6 text-accentSoft" />
          <span>Tiền số &amp; Cổ phiếu</span>
        </Link>
        <nav className="flex items-center gap-1">
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="nav-link" data-active={pathname === link.href}>
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
