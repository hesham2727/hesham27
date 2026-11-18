import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, dt, type Customer } from "../api";
import { ErrorBox, Field } from "../components/ui";

export default function Customers() {
  const [items, setItems] = useState<Customer[]>([]);
  const [q, setQ] = useState("");
  const [form, setForm] = useState({ full_name: "", phone: "", email: "", address: "", notes: "" });
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => api<Customer[]>(`/api/customers?q=${encodeURIComponent(q)}`).then(setItems).catch(() => undefined);
  useEffect(() => { load(); }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/api/customers", { method: "POST", body: form });
      setForm({ full_name: "", phone: "", email: "", address: "", notes: "" });
      setShow(false);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطأ");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="h1 mb-0">العملاء</h1>
        <button className="btn-primary" onClick={() => setShow(!show)}>عميل جديد</button>
      </div>
      {show && (
        <form onSubmit={create} className="card grid gap-3 md:grid-cols-2">
          <div className="md:col-span-2"><ErrorBox error={error} /></div>
          <Field label="الاسم *"><input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required /></Field>
          <Field label="الهاتف"><input className="input ltr" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
          <Field label="البريد الإلكتروني"><input className="input ltr" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="العنوان"><input className="input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field>
          <div className="md:col-span-2"><Field label="ملاحظات"><textarea className="input" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field></div>
          <div className="md:col-span-2"><button className="btn-primary">حفظ</button></div>
        </form>
      )}
      <div className="card overflow-x-auto">
        <input className="input mb-3 max-w-xs" placeholder="بحث بالاسم أو الرقم" value={q} onChange={(e) => setQ(e.target.value)} />
        <table className="table">
          <thead><tr><th>الاسم</th><th>الهاتف</th><th>البريد</th><th>أُضيف</th></tr></thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id}>
                <td><Link className="text-brand-600" to={`/customers/${c.id}`}>{c.full_name}</Link></td>
                <td className="ltr">{c.phone_e164 || "—"}</td>
                <td className="ltr">{c.email || "—"}</td>
                <td>{dt(c.created_at)}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={4} className="text-slate-500">لا يوجد عملاء.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
