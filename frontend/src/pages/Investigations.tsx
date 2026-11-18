import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, dt, type Customer, type Investigation } from "../api";
import { ErrorBox, Field, StatusBadge } from "../components/ui";

export default function Investigations() {
  const nav = useNavigate();
  const [items, setItems] = useState<Investigation[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [params] = useSearchParams();
  const prefill = params.get("new") ?? "";
  const [showForm, setShowForm] = useState(prefill !== "");
  const [form, setForm] = useState({ phone: prefill, title: "", purpose: "", customer_id: "", notes: "" });
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<Investigation[]>(`/api/investigations?q=${encodeURIComponent(q)}&status=${status}`).then(setItems).catch(() => undefined);
  useEffect(() => { load(); }, [q, status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api<Customer[]>("/api/customers").then(setCustomers).catch(() => undefined); }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const inv = await api<Investigation>("/api/investigations", {
        method: "POST",
        body: { ...form, customer_id: form.customer_id ? Number(form.customer_id) : null },
      });
      nav(`/investigations/${inv.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطأ");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1 mb-0">التحقيقات</h1>
        <div className="flex gap-2">
          <a className="btn-secondary" href={`/api/reports/investigations.xlsx?status=${status}`} download>تصدير Excel</a>
          <button className="btn-primary" onClick={() => setShowForm(!showForm)}>تحقيق جديد</button>
        </div>
      </div>
      {showForm && (
        <form onSubmit={create} className="card grid gap-3 md:grid-cols-2">
          <div className="md:col-span-2"><ErrorBox error={error} /></div>
          <Field label="رقم الهاتف *"><input className="input ltr" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required /></Field>
          <Field label="عنوان التحقيق *"><input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required /></Field>
          <div className="md:col-span-2">
            <Field label="الغرض المشروع من التحقيق * (يظهر في التقرير وسجل التدقيق)">
              <textarea className="input" rows={2} value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} required minLength={5} />
            </Field>
          </div>
          <Field label="العميل المرتبط (اختياري)">
            <select className="input" value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })}>
              <option value="">— بدون —</option>
              {customers.map((c) => <option key={c.id} value={c.id}>{c.full_name}</option>)}
            </select>
          </Field>
          <Field label="ملاحظات"><input className="input" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
          <div className="md:col-span-2"><button className="btn-primary">إنشاء والتحقق من الرقم</button></div>
        </form>
      )}
      <div className="card overflow-x-auto">
        <div className="mb-3 flex flex-wrap gap-2">
          <input className="input max-w-xs" placeholder="بحث بالمرجع أو العنوان أو الرقم" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="input max-w-[10rem]" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">كل الحالات</option>
            <option value="open">مفتوح</option>
            <option value="closed">مغلق</option>
          </select>
        </div>
        <table className="table">
          <thead><tr><th>المرجع</th><th>العنوان</th><th>الرقم</th><th>صالح</th><th>العميل</th><th>الحالة</th><th>تاريخ الإنشاء</th></tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id}>
                <td className="ltr whitespace-nowrap"><Link className="text-brand-600" to={`/investigations/${i.id}`}>{i.ref_code}</Link></td>
                <td>{i.title}</td>
                <td className="ltr">{i.phone_e164 || i.phone_raw}</td>
                <td>{i.validation?.is_valid ? "نعم" : "لا"}</td>
                <td>{i.customer_name || "—"}</td>
                <td><StatusBadge status={i.status} /></td>
                <td className="whitespace-nowrap">{dt(i.created_at)}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={7} className="text-slate-500">لا توجد نتائج.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
