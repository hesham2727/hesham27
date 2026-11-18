import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, dt, type User } from "../api";
import { ErrorBox, Field } from "../components/ui";

export default function Users() {
  const [items, setItems] = useState<User[]>([]);
  const [form, setForm] = useState({ username: "", full_name: "", password: "", role: "operator" });
  const [error, setError] = useState<string | null>(null);
  const load = () => api<User[]>("/api/users").then(setItems).catch(() => undefined);
  useEffect(() => { load(); }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/api/users", { method: "POST", body: form });
      setForm({ username: "", full_name: "", password: "", role: "operator" });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطأ");
    }
  };
  const update = async (u: User, body: Record<string, unknown>) => {
    setError(null);
    try {
      await api(`/api/users/${u.id}`, { method: "PATCH", body });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطأ");
    }
  };
  const resetPw = (u: User) => {
    const pw = window.prompt(`كلمة مرور جديدة للمستخدم ${u.username} (10 أحرف على الأقل)`);
    if (pw) update(u, { password: pw });
  };

  return (
    <div className="space-y-4">
      <h1 className="h1">المستخدمون</h1>
      <ErrorBox error={error} />
      <form onSubmit={create} className="card grid gap-3 md:grid-cols-5 md:items-end">
        <Field label="اسم المستخدم"><input className="input ltr" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required /></Field>
        <Field label="الاسم الكامل"><input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
        <Field label="كلمة المرور"><input className="input ltr" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></Field>
        <Field label="الدور">
          <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="operator">مشغّل</option>
            <option value="admin">مدير</option>
          </select>
        </Field>
        <button className="btn-primary">إضافة</button>
      </form>
      <div className="card overflow-x-auto">
        <table className="table">
          <thead><tr><th>المستخدم</th><th>الاسم</th><th>الدور</th><th>الحالة</th><th>آخر دخول</th><th>إجراءات</th></tr></thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td className="ltr">{u.username}</td>
                <td>{u.full_name}</td>
                <td>{u.role === "admin" ? "مدير" : "مشغّل"}</td>
                <td>{u.is_active ? "نشط" : "موقوف"}</td>
                <td>{dt(u.last_login_at)}</td>
                <td className="space-x-2 space-x-reverse whitespace-nowrap text-sm">
                  <button className="text-brand-600 underline" onClick={() => update(u, { role: u.role === "admin" ? "operator" : "admin" })}>تغيير الدور</button>
                  <button className="text-brand-600 underline" onClick={() => update(u, { is_active: !u.is_active })}>{u.is_active ? "إيقاف" : "تفعيل"}</button>
                  <button className="text-brand-600 underline" onClick={() => resetPw(u)}>إعادة تعيين كلمة المرور</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
