import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, isSafeHttpUrl } from "../api";
import { useEnumLabel, useI18n } from "../i18n";

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "generic"));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading, reload, setData };
}

export function ErrorBox({ error }: { error: ApiError | null | undefined }) {
  const { t } = useI18n();
  if (!error) return null;
  const key = `err.${error.code}`;
  const msg = t(key) !== key ? t(key) : `${t("err.generic")} (${error.code})`;
  return <div className="alert alert-error" role="alert">{msg}</div>;
}

export function Spinner() {
  const { t } = useI18n();
  return <div className="muted" aria-busy="true">{t("common.loading")}</div>;
}

const TONE: Record<string, string> = {
  completed: "ok", verified: "ok", high: "ok", fetched: "ok", available: "ok", fact: "ok",
  partial: "warn", medium: "warn", unverified: "warn", undisclosed: "warn", running: "info", pending: "info", analytical_observation: "info",
  failed: "bad", conflicting: "bad", low: "bad", unavailable: "bad", error: "bad", blocked_policy: "bad", blocked_robots: "warn",
  not_permitted: "bad", rate_limited: "warn", not_found: "bad", not_configured: "warn", auth_error: "bad",
};

export function Badge({ prefix, value }: { prefix: string; value: string }) {
  const label = useEnumLabel();
  return <span className={`badge badge-${TONE[value] ?? "neutral"}`}>{label(prefix, value)}</span>;
}

/** Renders a URL as a link only when it is http(s); never as javascript: etc. */
export function SafeLink({ href, children }: { href: string; children?: ReactNode }) {
  if (!href) return <span className="muted">—</span>;
  if (!isSafeHttpUrl(href)) return <span className="mono">{href}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="link-break">
      {children ?? href}
    </a>
  );
}

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export function BarChart({ data, labelKey, valueKey }: { data: Record<string, unknown>[]; labelKey: string; valueKey: string }) {
  const max = Math.max(1, ...data.map((d) => Number(d[valueKey]) || 0));
  return (
    <div className="bars" role="img">
      {data.map((d, i) => {
        const v = Number(d[valueKey]) || 0;
        return (
          <div className="bar-col" key={i} title={`${String(d[labelKey])}: ${v}`}>
            <div className="bar" style={{ height: `${(v / max) * 100}%` }} />
            <div className="bar-label">{String(d[labelKey]).slice(-5)}</div>
          </div>
        );
      })}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}
