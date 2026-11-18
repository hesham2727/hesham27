import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  api,
  ApiError,
  dt,
  RELIABILITY_AR,
  SOURCE_TYPE_AR,
  type DataSource,
  type Investigation,
  type Invitation,
  type LocationRec,
  type NumberCheck,
  type SourceRecord,
} from "../api";
import { useAuth } from "../auth";
import LocationPanel from "../components/LocationPanel";
import { ErrorBox, Field, StatusBadge, ValidationView } from "../components/ui";

interface Detail {
  investigation: Investigation;
  sources: SourceRecord[];
  locations: LocationRec[];
  invitations: Invitation[];
  checks: NumberCheck[];
}

const nowLocal = () => {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};

export default function InvestigationDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [d, setD] = useState<Detail | null>(null);
  const [catalog, setCatalog] = useState<DataSource[]>([]);
  const [tab, setTab] = useState<"overview" | "sources" | "location" | "history">("overview");
  const [error, setError] = useState<string | null>(null);
  const emptySource = { data_source_id: "", source_name: "", source_url: "", source_type: "website", observed_at: nowLocal(), summary: "", reliability: "unverified" };
  const [src, setSrc] = useState(emptySource);

  const load = useCallback(() => {
    api<Detail>(`/api/investigations/${id}`).then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "خطأ"));
  }, [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api<DataSource[]>("/api/data-sources").then((c) => setCatalog(c.filter((x) => x.enabled))).catch(() => undefined); }, []);

  if (error && !d) return <ErrorBox error={error} />;
  if (!d) return <div className="text-slate-500">جارٍ التحميل…</div>;
  const inv = d.investigation;

  const toggleStatus = async () => {
    await api(`/api/investigations/${inv.id}`, { method: "PATCH", body: { status: inv.status === "open" ? "closed" : "open" } });
    load();
  };
  const remove = async () => {
    if (!window.confirm("حذف التحقيق وكل سجلاته نهائياً؟")) return;
    await api(`/api/investigations/${inv.id}`, { method: "DELETE" });
    nav("/investigations");
  };
  const recheck = async () => {
    await api("/api/numbers/validate", { method: "POST", body: { number: inv.phone_raw, investigation_id: inv.id } });
    load();
  };
  const addSource = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api(`/api/investigations/${inv.id}/sources`, {
        method: "POST",
        body: { ...src, data_source_id: src.data_source_id ? Number(src.data_source_id) : null, observed_at: new Date(src.observed_at).toISOString() },
      });
      setSrc({ ...emptySource, observed_at: nowLocal() });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطأ");
    }
  };
  const delSource = async (sid: number) => {
    if (!window.confirm("حذف السجل؟")) return;
    await api(`/api/sources/${sid}`, { method: "DELETE" });
    load();
  };

  const tabs = [
    ["overview", "نظرة عامة"],
    ["sources", `المصادر العامة (${d.sources.length})`],
    ["location", `الموقع (${d.locations.length})`],
    ["history", `سجل التحقق (${d.checks.length})`],
  ] as const;

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="ltr text-xs text-slate-500">{inv.ref_code}</div>
          <h1 className="text-xl font-bold text-brand-800">{inv.title}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
            <StatusBadge status={inv.status} />
            <span className="ltr font-mono">{inv.phone_e164 || inv.phone_raw}</span>
            {inv.customer_name && <span>العميل: {inv.customer_name}</span>}
            <span className="text-slate-500">أنشأه {inv.created_by_username} في {dt(inv.created_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <a className="btn-secondary" href={`/api/reports/investigations/${inv.id}.pdf`} download>تقرير PDF</a>
          <a className="btn-secondary" href={`/api/reports/investigations/${inv.id}.xlsx`} download>Excel</a>
          <button className="btn-secondary" onClick={toggleStatus}>{inv.status === "open" ? "إغلاق التحقيق" : "إعادة فتح"}</button>
          {user?.role === "admin" && <button className="btn-danger" onClick={remove}>حذف</button>}
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {tabs.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} className={`px-3 py-2 text-sm ${tab === k ? "border-b-2 border-brand-600 font-bold text-brand-800" : "text-slate-600"}`}>{label}</button>
        ))}
      </div>
      <ErrorBox error={error} />

      {tab === "overview" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card">
            <h2 className="h2">بيانات التحقيق</h2>
            <dl className="space-y-2 text-sm">
              <div><dt className="text-slate-500">الغرض المشروع</dt><dd>{inv.purpose}</dd></div>
              <div><dt className="text-slate-500">ملاحظات</dt><dd className="whitespace-pre-wrap">{inv.notes || "—"}</dd></div>
              <div><dt className="text-slate-500">آخر تحديث</dt><dd>{dt(inv.updated_at)}</dd></div>
              {inv.closed_at && <div><dt className="text-slate-500">تاريخ الإغلاق</dt><dd>{dt(inv.closed_at)}</dd></div>}
            </dl>
          </div>
          <div className="card">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="h2 mb-0">نتيجة التحقق من الرقم</h2>
              <button className="btn-secondary" onClick={recheck}>إعادة التحقق</button>
            </div>
            {inv.validation && <ValidationView v={inv.validation} />}
          </div>
        </div>
      )}

      {tab === "sources" && (
        <div className="space-y-4">
          <form onSubmit={addSource} className="card grid gap-3 md:grid-cols-2">
            <h2 className="h2 md:col-span-2">إضافة سجل من مصدر عام (إدخال يدوي – لا يوجد جمع آلي)</h2>
            <Field label="من دليل المصادر (اختياري)">
              <select className="input" value={src.data_source_id} onChange={(e) => {
                const ds = catalog.find((c) => String(c.id) === e.target.value);
                setSrc({ ...src, data_source_id: e.target.value, source_name: ds ? ds.name : src.source_name, source_url: ds?.url || src.source_url });
              }}>
                <option value="">— غير محدد —</option>
                {catalog.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="اسم المصدر *"><input className="input" value={src.source_name} onChange={(e) => setSrc({ ...src, source_name: e.target.value })} required /></Field>
            <Field label="الرابط"><input className="input ltr" type="url" value={src.source_url} onChange={(e) => setSrc({ ...src, source_url: e.target.value })} placeholder="https://" /></Field>
            <Field label="نوع المصدر">
              <select className="input" value={src.source_type} onChange={(e) => setSrc({ ...src, source_type: e.target.value })}>
                {Object.entries(SOURCE_TYPE_AR).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="تاريخ ووقت الاطلاع *"><input className="input" type="datetime-local" value={src.observed_at} onChange={(e) => setSrc({ ...src, observed_at: e.target.value })} required /></Field>
            <Field label="درجة الموثوقية">
              <select className="input" value={src.reliability} onChange={(e) => setSrc({ ...src, reliability: e.target.value })}>
                {Object.entries(RELIABILITY_AR).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <div className="md:col-span-2">
              <Field label="ملخص ما تم العثور عليه *"><textarea className="input" rows={3} value={src.summary} onChange={(e) => setSrc({ ...src, summary: e.target.value })} required /></Field>
            </div>
            <div className="md:col-span-2"><button className="btn-primary">حفظ السجل</button></div>
          </form>
          <div className="card overflow-x-auto">
            <table className="table">
              <thead><tr><th>المصدر</th><th>النوع</th><th>تاريخ الاطلاع</th><th>الموثوقية</th><th>الملخص</th><th>بواسطة</th><th></th></tr></thead>
              <tbody>
                {d.sources.map((s) => (
                  <tr key={s.id}>
                    <td>{s.source_url ? <a className="text-brand-600 underline" href={s.source_url} target="_blank" rel="noreferrer noopener">{s.source_name}</a> : s.source_name}</td>
                    <td>{SOURCE_TYPE_AR[s.source_type] ?? s.source_type}</td>
                    <td className="whitespace-nowrap">{dt(s.observed_at)}</td>
                    <td>{RELIABILITY_AR[s.reliability]}</td>
                    <td className="whitespace-pre-wrap">{s.summary}</td>
                    <td>{s.created_by_username}</td>
                    <td><button className="text-sm text-red-700 underline" onClick={() => delSource(s.id)}>حذف</button></td>
                  </tr>
                ))}
                {d.sources.length === 0 && <tr><td colSpan={7} className="text-slate-500">لا توجد سجلات.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "location" && (
        <LocationPanel investigationId={inv.id} locations={d.locations} invitations={d.invitations} reload={load} />
      )}

      {tab === "history" && (
        <div className="card overflow-x-auto">
          <table className="table">
            <thead><tr><th>الوقت</th><th>المُدخل</th><th>E.164</th><th>النتيجة</th><th>المشغّل الأصلي</th><th>بواسطة</th></tr></thead>
            <tbody>
              {d.checks.map((c) => (
                <tr key={c.id}>
                  <td className="whitespace-nowrap">{dt(c.checked_at)}</td>
                  <td className="ltr">{c.raw_input}</td>
                  <td className="ltr">{c.e164 || "—"}</td>
                  <td>{c.is_valid ? "صالح" : "غير صالح"}</td>
                  <td>{c.result.original_operator_ar || "—"}</td>
                  <td>{c.checked_by_username}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
