"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { TrendingUp, BarChart3, HelpCircle, LayoutDashboard, Cpu } from "lucide-react";

export default function Navbar() {
  const pathname = usePathname();

  const links = [
    { href: "/", label: "Dashboard", icon: LayoutDashboard },
    { href: "/symbols", label: "Symbols", icon: BarChart3 },
    { href: "/forecast", label: "Forecast Model", icon: TrendingUp },
    { href: "/explainability", label: "SHAP Explain", icon: Cpu },
  ];

  return (
    <nav className="sticky top-0 z-50 w-full glass-panel border-b border-darkBorder py-4 px-6 md:px-12 flex justify-between items-center">
      <Link href="/" className="flex items-center gap-2 text-glowIndigo font-bold text-xl tracking-tight">
        <TrendingUp className="w-6 h-6 animate-pulse" />
        <span>NCKH Forecast <span className="text-glowEmerald text-xs font-semibold px-2 py-0.5 rounded-full bg-glowEmerald/10 border border-glowEmerald/20">Active</span></span>
      </Link>
      
      <div className="flex gap-1 md:gap-4">
        {links.map((link) => {
          const Icon = link.icon;
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-300 ${
                isActive
                  ? "bg-glowIndigo/15 text-glowIndigo border border-glowIndigo/20"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{link.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
