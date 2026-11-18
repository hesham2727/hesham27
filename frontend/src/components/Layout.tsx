import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

const links = [
  { to: "/", label: "لوحة المتابعة", end: true },
  { to: "/check", label: "التحقق من رقم" },
  { to: "/investigations", label: "التحقيقات" },
  { to: "/customers", label: "العملاء" },
  { to: "/sources", label: "دليل المصادر العامة" },
];
const adminLinks = [
  { to: "/audit", label: "سجل التدقيق" },
  { to: "/users", label: "المستخدمون" },
  { to: "/settings", label: "الإعدادات" },
];

export default function Layout({ children, version, mode }: { children: ReactNode; version: string; mode: string }) {
  const { user, setUser } = useAuth();
  const [open, setOpen] = useState(false);
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
  };
  const item = (l: { to: string; label: string; end?: boolean }) => (
    <NavLink
      key={l.to}
      to={l.to}
      end={l.end}
      onClick={() => setOpen(false)}
      className={({ isActive }) =>
        `block rounded-lg px-3 py-2 text-sm ${isActive ? "bg-white/15 font-bold text-white" : "text-brand-100 hover:bg-white/10"}`
      }
    >
      {l.label}
    </NavLink>
  );
  return (
    <div className="min-h-screen md:flex">
      <header className="flex items-center justify-between bg-brand-800 px-4 py-3 text-white md:hidden">
        <span className="font-bold">تحقيق</span>
        <button className="btn-secondary" onClick={() => setOpen(!open)} aria-label="القائمة">☰</button>
      </header>
      <aside className={`${open ? "block" : "hidden"} w-full bg-brand-800 p-4 md:block md:min-h-screen md:w-60 md:shrink-0`}>
        <div className="mb-6 hidden md:block">
          <div className="text-lg font-bold text-white">تحقيق</div>
          <div className="text-xs text-brand-100">منصة التحقق من الأرقام</div>
        </div>
        <nav className="space-y-1">
          {links.map(item)}
          {user?.role === "admin" && <div className="my-3 border-t border-white/15" />}
          {user?.role === "admin" && adminLinks.map(item)}
          <div className="my-3 border-t border-white/15" />
          {item({ to: "/account", label: "حسابي" })}
        </nav>
        <div className="mt-6 text-xs text-brand-100">
          <div>{user?.full_name || user?.username} ({user?.role === "admin" ? "مدير" : "مشغّل"})</div>
          <button className="mt-2 text-white underline" onClick={logout}>تسجيل الخروج</button>
          <div className="mt-4 opacity-70">الإصدار {version} – {mode === "desktop" ? "سطح المكتب" : "خادم"}</div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
    </div>
  );
}
