import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";

export const CURRENT_KEY = "fbo_current_inv";
export function getCurrent(): string | null {
  try {
    return localStorage.getItem(CURRENT_KEY);
  } catch {
    return null;
  }
}
export function setCurrent(id: number | string) {
  try {
    localStorage.setItem(CURRENT_KEY, String(id));
  } catch {
    /* ignore */
  }
}

const INV_SECTIONS = ["profile", "contacts", "posts", "media", "sources", "export"] as const;

export default function Layout({ children }: { children: ReactNode }) {
  const { t, lang, setLang } = useI18n();
  const { user, logout } = useAuth();
  const loc = useLocation();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const m = loc.pathname.match(/^\/investigations\/(\d+)/);
  const current = m ? m[1] : getCurrent();
  useEffect(() => {
    if (m) setCurrent(m[1]);
    setOpen(false);
  }, [loc.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const invLink = (section: string) => (current ? `/investigations/${current}/${section}` : `/history?pick=${section}`);
  const items: [string, string, string][] = [
    ["/", "nav.dashboard", "▦"],
    ["/new", "nav.new", "＋"],
    [invLink("profile"), "nav.profile", "◉"],
    [invLink("contacts"), "nav.contacts", "✆"],
    [invLink("posts"), "nav.posts", "☰"],
    [invLink("media"), "nav.media", "▣"],
    [invLink("sources"), "nav.sources", "✓"],
    ["/history", "nav.history", "⟲"],
    [invLink("export"), "nav.export", "⇩"],
    ["/settings", "nav.settings", "⚙"],
  ];
  const isActive = (to: string) => {
    if (to === "/") return loc.pathname === "/";
    const base = to.split("?")[0];
    if (to.startsWith("/history?pick=")) return false;
    return loc.pathname === base || (base !== "/history" && loc.pathname.startsWith(base));
  };

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <img src="/favicon.svg" alt="" width={34} height={34} />
          <div>
            <div className="brand-name">{t("app.name")}</div>
            <div className="brand-tag">{t("app.tagline")}</div>
          </div>
        </div>
        <nav>
          {items.map(([to, key, icon]) => (
            <NavLink key={key} to={to} className={() => `nav-item ${isActive(to) ? "active" : ""}`} data-testid={`nav-${key.split(".")[1]}`}>
              <span className="nav-icon" aria-hidden>{icon}</span>
              <span>{t(key)}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="muted small">{t("nav.current")}: {current ? <NavLink to={`/investigations/${current}/profile`}>#{current}</NavLink> : t("nav.none_selected")}</div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost menu-btn" onClick={() => setOpen((o) => !o)} aria-label="menu">☰</button>
          <div className="topbar-spacer" />
          <button className="btn btn-ghost" data-testid="lang-toggle" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{t("lang.toggle")}</button>
          <span className="user-chip" title={user?.role}>{user?.full_name || user?.username} · {t(`role.${user?.role}`)}</span>
          <button className="btn btn-ghost" data-testid="logout" onClick={async () => { await logout(); nav("/"); }}>{t("nav.logout")}</button>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}

export { INV_SECTIONS };
