import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, dt, type Customer, type Investigation, type Invitation, type LocationRec } from "../api";
import { useAuth } from "../auth";
import LocationPanel from "../components/LocationPanel";
import { ErrorBox, Field, StatusBadge } from "../components/ui";

interface Detail {
  customer: Customer;
  investigations: Investigation[];
  locations: LocationRec[];
  invitations: Invitation[];
}

export default function CustomerDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [d, setD] = useState<Detail | null>(null);
  const [form, setForm] = useState({ full_name: "", phone: "", email: "", address: "", notes: "" });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => {
    api<Detail>(`/api/customers/${id}`).then((r) => {
      setD(r);
      setForm({ full_name: r.customer.full_name, phone: r.customer.phone_e164, email: r.customer.email, address: r.customer.address, notes: r.customer.notes });
    }).catch((e) => setError(e instanceof ApiError ? e.message : "خطأ"));
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (!d) return <ErrorBox error={error} />;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api(`/api/customers/${id}`, { method: "PATCH", body: form });
      setSaved(true);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطأ");
    }
  };
  const remove = async () => {
    if (!window.confirm("حذف العميل ومواقعه المشاركة نهائياً؟ (التحقيقات تبقى بدون ربط)")) return;
    await api(`/api/customers/${id}`, { method: "DELETE" });
    nav("/customers");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="h1 mb-0">{d.customer.full_name}</h1>
        {user?.role === "admin" && <button className="btn-danger" onClick={remove}>حذف العميل</button>}
      </div>
      <form onSubmit={save} className="card grid gap-3 md:grid-cols-2">
        <div className="md:col-span-2"><ErrorBox error={error} /></div>
        <Field label="الاسم"><input className="input" value={form.full_name} onChange={(e) => { setForm({ ...form, full_name: e.target.value }); setSaved(false); }} required /></Field>
        <Field label="الهاتف"><input className="input ltr" value={form.phone} onChange={(e) => { setForm({ ...form, phone: e.target.value }); setSaved(false); }} /></Field>
        <Field label="البريد"><input className="input ltr" value={form.email} onChange={(e) => { setForm({ ...form, email: e.target.value }); setSaved(false); }} /></Field>
        <Field label="العنوان"><input className="input" value={form.address} onChange={(e) => { setForm({ ...form, address: e.target.value }); setSaved(false); }} /></Field>
        <div className="md:col-span-2"><Field label="ملاحظات"><textarea className="input" rows={2} value={form.notes} onChange={(e) => { setForm({ ...form, notes: e.target.value }); setSaved(false); }} /></Field></div>
        <div className="md:col-span-2 flex items-center gap-3"><button className="btn-primary">حفظ التعديلات</button>{saved && <span className="text-sm text-green-700">تم الحفظ ✓</span>}</div>
      </form>
      <div className="card overflow-x-auto">
        <h2 className="h2">التحقيقات المرتبطة</h2>
        <table className="table">
          <thead><tr><th>المرجع</th><th>العنوان</th><th>الحالة</th><th>التاريخ</th></tr></thead>
          <tbody>
            {d.investigations.map((i) => (
              <tr key={i.id}>
                <td className="ltr"><Link className="text-brand-600" to={`/investigations/${i.id}`}>{i.ref_code}</Link></td>
                <td>{i.title}</td><td><StatusBadge status={i.status} /></td><td>{dt(i.created_at)}</td>
              </tr>
            ))}
            {d.investigations.length === 0 && <tr><td colSpan={4} className="text-slate-500">لا يوجد.</td></tr>}
          </tbody>
        </table>
      </div>
      <LocationPanel customerId={d.customer.id} locations={d.locations} invitations={d.invitations} reload={load} />
    </div>
  );
}
