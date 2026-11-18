import { useEffect, useState, type FormEvent } from "react";
import { NavLink, useParams } from "react-router-dom";
import { api, ApiError, type CollectionEvent, type DataPoint, type Investigation as Inv, type Media, type Post, type Source } from "../api";
import { useAuth } from "../auth";
import { Badge, BarChart, Card, ErrorBox, Field, SafeLink, Spinner, useAsync } from "../components/ui";
import { useEnumLabel, useI18n } from "../i18n";

type Section = "profile" | "contacts" | "posts" | "media" | "sources" | "export";
const SECTIONS: Section[] = ["profile", "contacts", "posts", "media", "sources", "export"];

export default function Investigation() {
  const { id = "", section = "profile" } = useParams();
  const { t, fmtDate } = useI18n();
  const { user } = useAuth();
  const { data: inv, error, reload } = useAsync(() => api<Inv>(`/api/investigations/${id}`), [id]);
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [newUrls, setNewUrls] = useState("");
  const [version, setVersion] = useState(0);
  const running = inv && (inv.status === "running" || inv.status === "pending");

  useEffect(() => {
    if (!running) return;
    const h = window.setInterval(() => void reload().then(() => setVersion((v) => v + 1)), 2000);
    return () => window.clearInterval(h);
  }, [running, reload]);

  if (error) return <ErrorBox error={error} />;
  if (!inv) return <Spinner />;
  const canEdit = user?.role === "admin" || (user?.role === "investigator" && inv.created_by_id === user.id);

  const act = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await fn();
      await reload();
      setVersion((v) => v + 1);
    } catch (e) {
      setActionError(e instanceof ApiError ? e : new ApiError(0, "generic"));
    }
  };

  return (
    <div className="stack">
      <Card>
        <div className="inv-head">
          <div>
            <div className="mono muted">{inv.reference}</div>
            <h1 className="ltr-text">{inv.title || inv.identifier}</h1>
            <div className="muted small ltr-text"><SafeLink href={inv.normalized_url}>{inv.normalized_url || inv.target_input}</SafeLink></div>
          </div>
          <div className="inv-meta">
            <Badge prefix="status" value={inv.status} />
            <span className="pill">{t(`obj.${inv.object_type}`)}</span>
            {canEdit && <button className="btn btn-small" disabled={!!running} data-testid="rerun" onClick={() => act(() => api(`/api/investigations/${inv.id}/run`, { method: "POST" }))}>{t("inv.rerun")}</button>}
          </div>
        </div>
        <div className="kv-grid">
          <div><span className="muted">{t("inv.purpose")}:</span> {inv.purpose}</div>
          <div><span className="muted">{t("inv.created_by")}:</span> <bdi>{inv.created_by_username}</bdi> · <bdi>{fmtDate(inv.created_at)}</bdi></div>
          <div><span className="muted">{t("inv.counts")}:</span> {Object.entries(inv.counts).map(([k, v]) => <span key={k} className="count-chip">{t(`count.${k}`)}: <strong>{v}</strong></span>)}</div>
        </div>
        {running && <div className="alert alert-info" data-testid="running">{t("inv.running")}</div>}
        {inv.limitations.length > 0 && (
          <details className="limitations" open>
            <summary>{t("inv.limitations")} ({inv.limitations.length})</summary>
            <ul>{inv.limitations.map((l) => <li key={l.code}><code>{l.code}</code> — {l.message}</li>)}</ul>
          </details>
        )}
        {canEdit && (
          <form className="toolbar" onSubmit={(e: FormEvent) => { e.preventDefault(); const urls = newUrls.split(/\s+/).filter(Boolean); if (urls.length) void act(() => api(`/api/investigations/${inv.id}/urls`, { method: "POST", body: { urls } })).then(() => setNewUrls("")); }}>
            <input dir="ltr" placeholder="https://example.com/contact" value={newUrls} onChange={(e) => setNewUrls(e.target.value)} />
            <button className="btn btn-small" type="submit" disabled={!!running}>{t("inv.add_urls")}</button>
          </form>
        )}
        <ErrorBox error={actionError} />
      </Card>
      <nav className="tabs">
        {SECTIONS.map((s) => (
          <NavLink key={s} to={`/investigations/${inv.id}/${s}`} className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>{t(`nav.${s}`)}</NavLink>
        ))}
      </nav>
      {section === "profile" && <ProfileTab inv={inv} canEdit={canEdit} version={version} />}
      {section === "contacts" && <ContactsTab inv={inv} canEdit={canEdit} version={version} />}
      {section === "posts" && <PostsTab inv={inv} version={version} />}
      {section === "media" && <MediaTab inv={inv} canEdit={canEdit} version={version} />}
      {section === "sources" && <SourcesTab inv={inv} version={version} />}
      {section === "export" && <ExportTab inv={inv} />}
    </div>
  );
}

function fieldName(lang: string, f: string) {
  return lang === "ar" ? f : f.replace(/_/g, " ");
}

function DataTable({ items, canEdit, invId, onChange, withAvailability = false }: { items: DataPoint[]; canEdit: boolean; invId: number; onChange: () => void; withAvailability?: boolean }) {
  const { t, lang, fmtDate } = useI18n();
  const label = useEnumLabel();
  const [reviewing, setReviewing] = useState<number | null>(null);
  const [rv, setRv] = useState({ verification_status: "verified", confidence: "high", notes: "" });
  const [err, setErr] = useState<ApiError | null>(null);
  if (items.length === 0) return <p className="muted">{t("common.none")}</p>;
  const save = async (dp: DataPoint) => {
    try {
      await api(`/api/investigations/${invId}/datapoints/${dp.id}/review`, { method: "PATCH", body: rv });
      setReviewing(null);
      onChange();
    } catch (e) {
      setErr(e instanceof ApiError ? e : new ApiError(0, "generic"));
    }
  };
  return (
    <div className="table-wrap">
      <ErrorBox error={err} />
      <table>
        <thead>
          <tr>
            <th>{t("dp.field")}</th><th>{t("dp.value")}</th><th>{t("dp.source")}</th><th>{t("dp.collected")}</th>
            {withAvailability ? <th>{t("dp.availability")}</th> : <><th>{t("dp.verification")}</th><th>{t("dp.confidence")}</th></>}
            {canEdit && !withAvailability && <th>{t("common.actions")}</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.id}>
              <td><strong>{fieldName(lang, d.field)}</strong><div className="muted small">{label("cat", d.category)} · {label("src", d.source_type)}{d.extraction_method ? ` · ${d.extraction_method}` : ""}</div></td>
              <td className="ltr-text value-cell">{d.value || <span className="muted">—</span>}{d.notes && <div className="muted small pre">{d.notes}</div>}</td>
              <td className="ltr-text"><SafeLink href={d.source_url} /></td>
              <td className="nowrap">{fmtDate(d.collected_at)}</td>
              {withAvailability ? <td><Badge prefix="avail" value={d.availability} /></td> : <>
                <td><Badge prefix="ver" value={d.verification_status} />{d.manually_reviewed && <div className="muted small">{t("dp.reviewed")}</div>}</td>
                <td><Badge prefix="conf" value={d.confidence} /></td>
              </>}
              {canEdit && !withAvailability && (
                <td className="nowrap">
                  {reviewing === d.id ? (
                    <div className="review-box">
                      <select value={rv.verification_status} onChange={(e) => setRv({ ...rv, verification_status: e.target.value })}>
                        {["verified", "unverified", "conflicting"].map((v) => <option key={v} value={v}>{t(`ver.${v}`)}</option>)}
                      </select>
                      <select value={rv.confidence} onChange={(e) => setRv({ ...rv, confidence: e.target.value })}>
                        {["high", "medium", "low"].map((v) => <option key={v} value={v}>{t(`conf.${v}`)}</option>)}
                      </select>
                      <input placeholder={t("dp.notes")} value={rv.notes} onChange={(e) => setRv({ ...rv, notes: e.target.value })} maxLength={2000} />
                      <button className="btn btn-small btn-primary" onClick={() => save(d)}>{t("common.save")}</button>
                      <button className="btn btn-small" onClick={() => setReviewing(null)}>{t("common.cancel")}</button>
                    </div>
                  ) : (
                    <>
                      <button className="btn btn-small" onClick={() => { setReviewing(d.id); setRv({ verification_status: d.verification_status, confidence: d.confidence, notes: "" }); }}>{t("dp.review")}</button>
                      {d.source_type === "manual" && <button className="btn btn-small btn-danger" onClick={async () => { if (window.confirm(t("common.confirm_delete"))) { await api(`/api/investigations/${invId}/datapoints/${d.id}`, { method: "DELETE" }); onChange(); } }}>{t("common.delete")}</button>}
                    </>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ManualEntry({ invId, onAdded, defaultCategory = "observation" }: { invId: number; onAdded: () => void; defaultCategory?: string }) {
  const { t } = useI18n();
  const [f, setF] = useState({ category: defaultCategory, field: "", value: "", source_url: "", notes: "", classification: "unverified" });
  const [err, setErr] = useState<ApiError | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api(`/api/investigations/${invId}/datapoints`, { method: "POST", body: f });
      setF({ ...f, field: "", value: "", source_url: "", notes: "" });
      setErr(null);
      onAdded();
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex : new ApiError(0, "generic"));
    }
  };
  return (
    <details className="manual">
      <summary>{t("dp.add_manual")}</summary>
      <form className="grid-3" onSubmit={submit}>
        <Field label={t("dp.category")}>
          <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
            {["profile", "contact", "business", "identifier", "link", "observation"].map((c) => <option key={c} value={c}>{t(`cat.${c}`)}</option>)}
          </select>
        </Field>
        <Field label={t("dp.field_key")}><input dir="ltr" value={f.field} pattern="[a-z0-9_]+" required maxLength={64} onChange={(e) => setF({ ...f, field: e.target.value.toLowerCase() })} /></Field>
        <Field label={t("dp.classification")}>
          <select value={f.classification} onChange={(e) => setF({ ...f, classification: e.target.value })}>
            <option value="unverified">{t("cls.unverified")}</option>
            <option value="analytical_observation">{t("cls.analytical_observation")}</option>
          </select>
        </Field>
        <Field label={t("dp.value")}><input value={f.value} required maxLength={5000} onChange={(e) => setF({ ...f, value: e.target.value })} /></Field>
        <Field label={t("dp.source_url")}><input dir="ltr" type="url" value={f.source_url} required maxLength={1000} onChange={(e) => setF({ ...f, source_url: e.target.value })} /></Field>
        <Field label={t("dp.notes")}><input value={f.notes} maxLength={2000} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        <div><button className="btn btn-primary" type="submit">{t("dp.add")}</button></div>
      </form>
      <ErrorBox error={err} />
    </details>
  );
}

function ProfileTab({ inv, canEdit, version }: { inv: Inv; canEdit: boolean; version: number }) {
  const { t } = useI18n();
  const { data, error, reload } = useAsync(() => api<DataPoint[]>(`/api/investigations/${inv.id}/datapoints`), [inv.id, version]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner />;
  const available = data.filter((d) => d.availability === "available" && d.classification !== "analytical_observation" && d.category !== "contact");
  const missing = data.filter((d) => d.availability !== "available");
  const obs = data.filter((d) => d.classification === "analytical_observation");
  return (
    <div className="stack">
      <Card title={t("profile.available")}>
        <DataTable items={available} canEdit={canEdit} invId={inv.id} onChange={reload} />
        {canEdit && <ManualEntry invId={inv.id} onAdded={reload} />}
      </Card>
      <Card title={t("profile.observations")}><DataTable items={obs} canEdit={canEdit} invId={inv.id} onChange={reload} /></Card>
      <Card title={t("profile.unavailable")}><DataTable items={missing} canEdit={false} invId={inv.id} onChange={reload} withAvailability /></Card>
      <EventsCard invId={inv.id} version={version} />
    </div>
  );
}

function EventsCard({ invId, version }: { invId: number; version: number }) {
  const { t, fmtDate } = useI18n();
  const { data } = useAsync(() => api<CollectionEvent[]>(`/api/investigations/${invId}/events`), [invId, version]);
  return (
    <Card title={t("inv.events")}>
      <ul className="events">
        {(data || []).map((e) => <li key={e.id} className={`ev-${e.level}`}><span className="muted small nowrap">{fmtDate(e.created_at)}</span> <code>{e.step}</code> <span className="ltr-text">{e.message}</span></li>)}
      </ul>
    </Card>
  );
}

function ContactsTab({ inv, canEdit, version }: { inv: Inv; canEdit: boolean; version: number }) {
  const { t } = useI18n();
  const { data, error, reload } = useAsync(() => api<DataPoint[]>(`/api/investigations/${inv.id}/datapoints`, { query: { category: "contact" } }), [inv.id, version]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner />;
  return (
    <Card title={t("contacts.title")}>
      <div className="alert alert-info">{t("contacts.note")}</div>
      <DataTable items={data.filter((d) => d.availability === "available")} canEdit={canEdit} invId={inv.id} onChange={reload} />
      {canEdit && <ManualEntry invId={inv.id} onAdded={reload} defaultCategory="contact" />}
    </Card>
  );
}

function PostsTab({ inv, version }: { inv: Inv; version: number }) {
  const { t, fmtDate } = useI18n();
  const [form, setForm] = useState({ q: "", date_from: "", date_to: "", kind: "", order: "desc" });
  const [query, setQuery] = useState(form);
  const [offset, setOffset] = useState(0);
  const posts = useAsync(() => api<{ total: number; items: Post[] }>(`/api/investigations/${inv.id}/posts`, { query: { ...query, limit: 50, offset } }), [inv.id, query, offset, version]);
  const tl = useAsync(() => api<{ months: { month: string; count: number }[]; first: string | null; last: string | null }>(`/api/investigations/${inv.id}/timeline`), [inv.id, version]);
  return (
    <div className="stack">
      <Card title={t("posts.timeline")}>
        {tl.data && tl.data.months.length > 0 ? <BarChart data={tl.data.months} labelKey="month" valueKey="count" /> : <p className="muted">{t("posts.empty")}</p>}
      </Card>
      <Card title={t("posts.title")}>
        <form className="toolbar" onSubmit={(e) => { e.preventDefault(); setOffset(0); setQuery(form); }}>
          <input data-testid="posts-search" placeholder={t("posts.search")} value={form.q} onChange={(e) => setForm({ ...form, q: e.target.value })} maxLength={200} />
          <label className="check">{t("common.from")} <input type="date" value={form.date_from} onChange={(e) => setForm({ ...form, date_from: e.target.value })} /></label>
          <label className="check">{t("common.to")} <input type="date" value={form.date_to} onChange={(e) => setForm({ ...form, date_to: e.target.value })} /></label>
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            <option value="">{t("common.all")}</option><option value="post">{t("posts.post")}</option><option value="comment">{t("posts.comment")}</option>
          </select>
          <select value={form.order} onChange={(e) => setForm({ ...form, order: e.target.value })}>
            <option value="desc">{t("posts.order_desc")}</option><option value="asc">{t("posts.order_asc")}</option>
          </select>
          <button className="btn" type="submit">{t("common.search")}</button>
        </form>
        <ErrorBox error={posts.error} />
        {posts.data && posts.data.items.length === 0 && <p className="muted">{t("posts.empty")}</p>}
        <ol className="timeline">
          {posts.data?.items.map((p) => (
            <li key={p.id} className={`post post-${p.kind}`}>
              <div className="post-meta"><span className="pill">{t(`posts.${p.kind}`)}</span> <span className="muted">{fmtDate(p.created_time)}</span></div>
              <div className="post-msg" dir="auto">{p.message || <span className="muted">—</span>}</div>
              <div className="small">
                {p.permalink && <SafeLink href={p.permalink}>{t("posts.permalink")}</SafeLink>}
                {p.shared_link && <> · {t("posts.shared_link")}: <SafeLink href={p.shared_link} /></>}
              </div>
            </li>
          ))}
        </ol>
        {posts.data && posts.data.total > 50 && (
          <div className="pager">
            <button className="btn btn-small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>{t("common.prev")}</button>
            <span>{offset + 1}–{Math.min(offset + 50, posts.data.total)} / {posts.data.total}</span>
            <button className="btn btn-small" disabled={offset + 50 >= posts.data.total} onClick={() => setOffset(offset + 50)}>{t("common.next")}</button>
          </div>
        )}
      </Card>
    </div>
  );
}

function MediaTab({ inv, canEdit, version }: { inv: Inv; canEdit: boolean; version: number }) {
  const { t, fmtDate } = useI18n();
  const label = useEnumLabel();
  const { data, error, reload } = useAsync(() => api<Media[]>(`/api/investigations/${inv.id}/media`), [inv.id, version]);
  const [file, setFile] = useState<File | null>(null);
  const [src, setSrc] = useState("");
  const [caption, setCaption] = useState("");
  const [err, setErr] = useState<ApiError | null>(null);
  const upload = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api(`/api/investigations/${inv.id}/media/upload`, { method: "POST", form: fd, query: { source_url: src, caption } });
      setFile(null);
      setErr(null);
      (e.target as HTMLFormElement).reset();
      void reload();
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex : new ApiError(0, "generic"));
    }
  };
  return (
    <div className="stack">
      <div className="alert alert-info">{t("media.policy")}</div>
      {canEdit && (
        <Card title={t("media.upload")}>
          <form className="toolbar" onSubmit={upload}>
            <input type="file" accept="image/png,image/jpeg,image/gif,image/webp,image/bmp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="media-file" />
            <input dir="ltr" placeholder={t("media.upload_source")} value={src} onChange={(e) => setSrc(e.target.value)} />
            <input placeholder={t("media.caption")} value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={500} />
            <button className="btn btn-primary" type="submit" disabled={!file}>{t("dp.add")}</button>
          </form>
          <ErrorBox error={err} />
        </Card>
      )}
      <ErrorBox error={error} />
      {data && data.length === 0 && <p className="muted">{t("media.empty")}</p>}
      <div className="media-grid">
        {data?.map((m) => (
          <figure key={m.id} className={`media-card ${m.duplicate_group ? "dup" : ""}`}>
            {m.status === "stored" ? (
              <a href={`/api/investigations/${inv.id}/media/${m.id}/file`} target="_blank" rel="noopener noreferrer">
                <img src={`/api/investigations/${inv.id}/media/${m.id}/file`} alt={m.caption || m.kind} loading="lazy" />
              </a>
            ) : <div className="media-placeholder">{t("media.not_downloaded")}<div className="small">{m.error_message}</div></div>}
            <figcaption>
              <div><span className="pill">{label("src", m.source_type)}</span> <strong>{m.kind}</strong></div>
              {m.duplicate_group && <div className="badge badge-warn">{t("media.duplicate_group")} #{m.duplicate_group}</div>}
              {m.caption && <div dir="auto">{m.caption}</div>}
              <div className="small ltr-text"><SafeLink href={m.source_url} /></div>
              {m.sha256 && <div className="mono small">pHash {m.phash} · {m.width}×{m.height}</div>}
              <div className="muted small">{fmtDate(m.created_time || m.collected_at)}</div>
              {Object.keys(m.metadata_json || {}).length > 0 && (
                <details><summary className="small">{t("media.metadata")}</summary><pre className="small">{JSON.stringify(m.metadata_json, null, 1)}</pre></details>
              )}
            </figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}

function SourcesTab({ inv, version }: { inv: Inv; version: number }) {
  const { t, fmtDate } = useI18n();
  const label = useEnumLabel();
  const { data, error } = useAsync(() => api<{ items: Source[]; verification: Record<string, number>; confidence: Record<string, number> }>(`/api/investigations/${inv.id}/sources`), [inv.id, version]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner />;
  return (
    <div className="stack">
      <Card title={t("sources.summary")}>
        <div className="chips">
          {Object.entries(data.verification).map(([k, v]) => <span key={k}><Badge prefix="ver" value={k} /> {v}</span>)}
          {Object.entries(data.confidence).map(([k, v]) => <span key={k}><Badge prefix="conf" value={k} /> {v}</span>)}
        </div>
      </Card>
      <Card title={t("sources.title")}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("sources.url")}</th><th>{t("sources.type")}</th><th>{t("sources.status")}</th><th>{t("sources.http")}</th><th>{t("sources.points")}</th><th>{t("sources.fetched")}</th><th>{t("sources.hash")}</th></tr></thead>
            <tbody>
              {data.items.map((s) => (
                <tr key={s.id}>
                  <td className="ltr-text"><SafeLink href={s.url} />{s.title && <div className="muted small">{s.title}</div>}{s.error_message && <div className="small error-text">{s.error_message}</div>}</td>
                  <td>{label("src", s.source_type)}</td>
                  <td><Badge prefix="st" value={s.status} /></td>
                  <td>{s.http_status ?? "—"}</td>
                  <td>{s.data_points}</td>
                  <td className="nowrap">{fmtDate(s.fetched_at)}</td>
                  <td className="mono small">{s.content_sha256 ? s.content_sha256.slice(0, 16) + "…" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function ExportTab({ inv }: { inv: Inv }) {
  const { t, lang } = useI18n();
  const [rlang, setRlang] = useState(lang);
  const ready = !["pending", "running"].includes(inv.status);
  const href = (fmt: string) => `/api/investigations/${inv.id}/report?format=${fmt}&lang=${rlang}`;
  return (
    <Card title={t("export.title")}>
      <p>{t("export.note")}</p>
      <div className="toolbar">
        <label className="check">{t("export.lang")}
          <select value={rlang} onChange={(e) => setRlang(e.target.value as "ar" | "en")}>
            <option value="ar">العربية</option><option value="en">English</option>
          </select>
        </label>
      </div>
      {ready ? (
        <div className="export-buttons">
          <a className="btn btn-primary" href={href("pdf")} download data-testid="export-pdf">⇩ {t("export.pdf")}</a>
          <a className="btn btn-primary" href={href("xlsx")} download data-testid="export-xlsx">⇩ {t("export.xlsx")}</a>
        </div>
      ) : <div className="alert alert-info">{t("export.not_ready")}</div>}
    </Card>
  );
}
