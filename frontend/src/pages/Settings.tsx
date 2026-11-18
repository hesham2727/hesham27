import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError, type AuditEntry, type Role, type User } from "../api";
import { useAuth } from "../auth";
import { Badge, Card, ErrorBox, Field, Spinner, useAsync } from "../components/ui";
import { useI18n } from "../i18n";

interface SettingsResp {
  general: { retention_days: number; graph_version: string; default_language: string; backup_keep: number; duplicate_threshold: number };
  meta: { app_id: string; app_secret_set: boolean; access_token_set: boolean; access_token_masked: string; redirect_uri: string; graph_version: string; oauth_ready: boolean; user_connected: boolean; user_connection: Record<string, unknown> };
  system: { version: string; mode: string; database: string; data_dir: string; tls: boolean; session_idle_minutes: number; session_ttl_hours: number };
}

function useAction() {
  const [err, setErr] = useState<ApiError | null>(null);
  const [ok, setOk] = useState("");
  const run = async (fn: () => Promise<unknown>, okMsg = "") => {
    setErr(null);
    setOk("");
    try {
      await fn();
      setOk(okMsg);
      return true;
    } catch (e) {
      setErr(e instanceof ApiError ? e : new ApiError(0, "generic"));
      return false;
    }
  };
  return { err, ok, run };
}

export default function Settings() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [params] = useSearchParams();
  const { data, error, reload } = useAsync(() => api<SettingsResp>("/api/settings"), []);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner />;
  const admin = user?.role === "admin";
  const meta = params.get("meta");
  return (
    <div className="stack">
      <h1>{t("settings.title")}</h1>
      {meta && <div className={`alert ${meta === "connected" ? "alert-ok" : "alert-error"}`}>Facebook: {meta}</div>}
      <GeneralCard data={data} admin={admin} onSaved={reload} />
      <MetaCard data={data} admin={admin} onSaved={reload} />
      {user?.role !== "viewer" && <ConnectionCard data={data} onChange={reload} />}
      {admin && <UsersCard />}
      {admin && <BackupsCard />}
      {admin && <AuditCard />}
      <PasswordCard />
      <Card title={t("settings.system")}>
        <div className="kv-grid">{Object.entries(data.system).map(([k, v]) => <div key={k}><span className="muted">{k}:</span> <span className="ltr-text">{String(v)}</span></div>)}</div>
      </Card>
    </div>
  );
}

function GeneralCard({ data, admin, onSaved }: { data: SettingsResp; admin: boolean; onSaved: () => void }) {
  const { t } = useI18n();
  const [g, setG] = useState(data.general);
  const a = useAction();
  const save = (e: FormEvent) => {
    e.preventDefault();
    void a.run(() => api("/api/settings", { method: "PUT", body: g }), t("common.saved")).then((ok) => ok && onSaved());
  };
  return (
    <Card title={t("settings.general")}>
      <form className="grid-3" onSubmit={save}>
        <Field label={t("settings.retention_days")}><input type="number" min={0} max={3650} value={g.retention_days} disabled={!admin} onChange={(e) => setG({ ...g, retention_days: Number(e.target.value) })} /></Field>
        <Field label={t("settings.graph_version")}><input dir="ltr" value={g.graph_version} disabled={!admin} pattern="v\d{1,2}\.\d" onChange={(e) => setG({ ...g, graph_version: e.target.value })} /></Field>
        <Field label={t("settings.default_language")}>
          <select value={g.default_language} disabled={!admin} onChange={(e) => setG({ ...g, default_language: e.target.value })}><option value="ar">العربية</option><option value="en">English</option></select>
        </Field>
        <Field label={t("settings.backup_keep")}><input type="number" min={1} max={365} value={g.backup_keep} disabled={!admin} onChange={(e) => setG({ ...g, backup_keep: Number(e.target.value) })} /></Field>
        <Field label={t("settings.duplicate_threshold")}><input type="number" min={0} max={20} value={g.duplicate_threshold} disabled={!admin} onChange={(e) => setG({ ...g, duplicate_threshold: Number(e.target.value) })} /></Field>
        {admin && <div><button className="btn btn-primary" type="submit">{t("common.save")}</button></div>}
      </form>
      <ErrorBox error={a.err} />
      {a.ok && <div className="alert alert-ok">{a.ok}</div>}
    </Card>
  );
}

function MetaCard({ data, admin, onSaved }: { data: SettingsResp; admin: boolean; onSaved: () => void }) {
  const { t } = useI18n();
  const m = data.meta;
  const [f, setF] = useState({ app_id: m.app_id, app_secret: "", access_token: "", redirect_uri: m.redirect_uri || `${window.location.origin}/api/meta/oauth/callback` });
  const [test, setTest] = useState<string>("");
  const a = useAction();
  const save = (e: FormEvent) => {
    e.preventDefault();
    const body: Record<string, string> = { app_id: f.app_id, redirect_uri: f.redirect_uri };
    if (f.app_secret) body.app_secret = f.app_secret;
    if (f.access_token) body.access_token = f.access_token;
    void a.run(() => api("/api/settings/meta", { method: "PUT", body }), t("common.saved")).then((ok) => { if (ok) { setF({ ...f, app_secret: "", access_token: "" }); onSaved(); } });
  };
  const runTest = () => void a.run(async () => { const r = await api<{ ok: boolean; info?: unknown; error?: unknown }>("/api/settings/meta/test", { method: "POST" }); setTest(JSON.stringify(r.ok ? r.info : r.error, null, 1)); });
  return (
    <Card title={t("settings.meta")}>
      <p className="muted small">{t("settings.meta_note")}</p>
      <div className="chips">
        <span>{t("settings.access_token")}: <Badge prefix="st" value={m.access_token_set ? "fetched" : "not_configured"} /> <span className="mono">{m.access_token_masked}</span></span>
        <span>{t("settings.app_secret")}: {m.app_secret_set ? t("settings.configured") : t("settings.not_configured")}</span>
      </div>
      {admin && (
        <form className="grid-2" onSubmit={save}>
          <Field label={t("settings.app_id")}><input dir="ltr" value={f.app_id} pattern="\d*" onChange={(e) => setF({ ...f, app_id: e.target.value })} /></Field>
          <Field label={t("settings.app_secret")}><input dir="ltr" type="password" autoComplete="off" value={f.app_secret} onChange={(e) => setF({ ...f, app_secret: e.target.value })} placeholder={m.app_secret_set ? "••••••" : ""} /></Field>
          <Field label={t("settings.access_token")}><input dir="ltr" type="password" autoComplete="off" value={f.access_token} onChange={(e) => setF({ ...f, access_token: e.target.value })} placeholder={m.access_token_masked} /></Field>
          <Field label={t("settings.redirect_uri")}><input dir="ltr" value={f.redirect_uri} onChange={(e) => setF({ ...f, redirect_uri: e.target.value })} /></Field>
          <div className="toolbar">
            <button className="btn btn-primary" type="submit">{t("common.save")}</button>
            <button className="btn" type="button" disabled={!m.access_token_set} onClick={runTest}>{t("settings.test")}</button>
          </div>
        </form>
      )}
      {test && <pre className="small pre-box">{test}</pre>}
      <ErrorBox error={a.err} />
      {a.ok && <div className="alert alert-ok">{a.ok}</div>}
    </Card>
  );
}

function ConnectionCard({ data, onChange }: { data: SettingsResp; onChange: () => void }) {
  const { t } = useI18n();
  const a = useAction();
  const connect = () => void a.run(async () => { const r = await api<{ url: string }>("/api/meta/oauth/start", { method: "POST" }); window.location.assign(r.url); });
  return (
    <Card title={t("settings.connection")}>
      {data.meta.user_connected ? (
        <div className="toolbar"><Badge prefix="st" value="fetched" /> {t("settings.connected")}
          <button className="btn btn-danger" onClick={() => void a.run(() => api("/api/meta/connection", { method: "DELETE" })).then(onChange)}>{t("settings.disconnect")}</button>
        </div>
      ) : (
        <button className="btn btn-primary" disabled={!data.meta.oauth_ready} onClick={connect}>{t("settings.connect")}</button>
      )}
      <ErrorBox error={a.err} />
    </Card>
  );
}

function UsersCard() {
  const { t, fmtDate } = useI18n();
  const { data, reload } = useAsync(() => api<User[]>("/api/admin/users"), []);
  const [f, setF] = useState({ username: "", full_name: "", password: "", role: "investigator" as Role });
  const a = useAction();
  const create = (e: FormEvent) => {
    e.preventDefault();
    void a.run(() => api("/api/admin/users", { method: "POST", body: f }), t("common.saved")).then((ok) => { if (ok) { setF({ username: "", full_name: "", password: "", role: "investigator" }); void reload(); } });
  };
  const patch = (id: number, body: Record<string, unknown>) => void a.run(() => api(`/api/admin/users/${id}`, { method: "PATCH", body }), t("common.saved")).then(() => reload());
  const detail = (a.err?.details as { detail?: unknown } | undefined)?.detail;
  return (
    <Card title={t("settings.users")}>
      <div className="table-wrap">
        <table>
          <thead><tr><th>{t("auth.username")}</th><th>{t("auth.full_name")}</th><th>{t("settings.role")}</th><th>{t("settings.active")}</th><th>{t("audit.time")}</th><th>{t("common.actions")}</th></tr></thead>
          <tbody>
            {data?.map((u) => (
              <tr key={u.id}>
                <td className="mono">{u.username}</td>
                <td>{u.full_name}</td>
                <td><select value={u.role} onChange={(e) => patch(u.id, { role: e.target.value })}>{["admin", "investigator", "viewer"].map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}</select></td>
                <td><input type="checkbox" checked={u.is_active} onChange={(e) => patch(u.id, { is_active: e.target.checked })} /></td>
                <td className="nowrap">{fmtDate(u.last_login_at)}</td>
                <td><button className="btn btn-small" onClick={() => { const p = window.prompt(t("settings.new_password")); if (p) patch(u.id, { password: p }); }}>{t("settings.reset_password")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>{t("settings.new_user")}</h3>
      <form className="grid-3" onSubmit={create}>
        <Field label={t("auth.username")}><input dir="ltr" required minLength={3} maxLength={64} pattern="[A-Za-z0-9_.\-]{3,64}" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
        <Field label={t("auth.full_name")}><input value={f.full_name} maxLength={128} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
        <Field label={t("auth.password")} hint={t("auth.password_hint")}><input type="password" autoComplete="new-password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <Field label={t("settings.role")}><select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>{["admin", "investigator", "viewer"].map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}</select></Field>
        <div><button className="btn btn-primary" type="submit">{t("dp.add")}</button></div>
      </form>
      <ErrorBox error={a.err} />
      {Array.isArray(detail) && <div className="alert alert-error">{detail.join(", ")}</div>}
      {a.ok && <div className="alert alert-ok">{a.ok}</div>}
    </Card>
  );
}

function BackupsCard() {
  const { t, fmtDate } = useI18n();
  const { data, reload } = useAsync(() => api<{ name: string; size_bytes: number; created_at: string }[]>("/api/admin/backups"), []);
  const a = useAction();
  return (
    <Card title={t("settings.backups")} actions={<>
      <button className="btn" onClick={() => void a.run(() => api("/api/admin/backups", { method: "POST" })).then(() => reload())}>{t("settings.backup_now")}</button>
      <button className="btn" onClick={() => void a.run(async () => { const r = await api<{ deleted: number }>("/api/admin/retention/run", { method: "POST" }); window.alert(`${r.deleted}`); })}>{t("settings.retention_run")}</button>
    </>}>
      <ErrorBox error={a.err} />
      <ul className="plain-list">
        {data?.map((b) => <li key={b.name}><a href={`/api/admin/backups/${encodeURIComponent(b.name)}`} className="mono">{b.name}</a> · {(b.size_bytes / 1024).toFixed(1)} KB · {fmtDate(b.created_at)}</li>)}
      </ul>
    </Card>
  );
}

function AuditCard() {
  const { t, fmtDate } = useI18n();
  const [page, setPage] = useState(1);
  const { data } = useAsync(() => api<{ total: number; items: AuditEntry[] }>("/api/admin/audit", { query: { page, page_size: 25 } }), [page]);
  const pages = data ? Math.max(1, Math.ceil(data.total / 25)) : 1;
  return (
    <Card title={t("settings.audit")}>
      <div className="table-wrap">
        <table>
          <thead><tr><th>{t("audit.time")}</th><th>{t("audit.user")}</th><th>{t("audit.action")}</th><th>{t("audit.target")}</th><th>{t("audit.ip")}</th><th>{t("audit.result")}</th></tr></thead>
          <tbody>
            {data?.items.map((e) => (
              <tr key={e.id}>
                <td className="nowrap">{fmtDate(e.created_at)}</td><td className="mono">{e.username}</td><td><code>{e.action}</code></td>
                <td className="mono small">{e.target_type} {e.target_id}</td><td className="mono small">{e.ip_address}</td>
                <td>{e.success ? "✓" : "✗"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button className="btn btn-small" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("common.prev")}</button>
        <span>{t("common.page")} {page} {t("common.of")} {pages}</span>
        <button className="btn btn-small" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t("common.next")}</button>
      </div>
    </Card>
  );
}

function PasswordCard() {
  const { t } = useI18n();
  const { refresh } = useAuth();
  const [f, setF] = useState({ current_password: "", new_password: "" });
  const a = useAction();
  return (
    <Card title={t("settings.password")}>
      <form className="grid-3" onSubmit={(e) => { e.preventDefault(); void a.run(() => api("/api/auth/change-password", { method: "POST", body: f })).then((ok) => { if (ok) void refresh(); }); }}>
        <Field label={t("settings.current_password")}><input type="password" autoComplete="current-password" required value={f.current_password} onChange={(e) => setF({ ...f, current_password: e.target.value })} /></Field>
        <Field label={t("settings.new_password")} hint={t("auth.password_hint")}><input type="password" autoComplete="new-password" required value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} /></Field>
        <div><button className="btn btn-primary" type="submit">{t("common.save")}</button></div>
      </form>
      <ErrorBox error={a.err} />
    </Card>
  );
}
