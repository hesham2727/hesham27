import { useState, type FormEvent } from "react";
import { api, ApiError, type User } from "../api";
import { ErrorBox, Field } from "../components/ui";

export default function Setup({ onDone }: { onDone: (u: User) => void }) {
  const [form, setForm] = useState({ username: "admin", full_name: "", password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (form.password !== form.confirm) return setError("كلمتا المرور غير متطابقتين");
    try {
      onDone(await api<User>("/api/auth/setup", { method: "POST", body: { username: form.username, full_name: form.full_name, password: form.password } }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "تعذر الإعداد");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-md space-y-4">
        <div>
          <h1 className="text-xl font-bold text-brand-800">الإعداد الأول</h1>
          <p className="text-sm text-slate-500">أنشئ حساب مدير النظام. يتم هذا مرة واحدة فقط ومن نفس الجهاز.</p>
        </div>
        <ErrorBox error={error} />
        <Field label="اسم المستخدم (حروف إنجليزية)"><input className="input ltr" value={form.username} onChange={set("username")} required /></Field>
        <Field label="الاسم الكامل"><input className="input" value={form.full_name} onChange={set("full_name")} /></Field>
        <Field label="كلمة المرور (10 أحرف على الأقل، حروف وأرقام)"><input className="input ltr" type="password" autoComplete="new-password" value={form.password} onChange={set("password")} required /></Field>
        <Field label="تأكيد كلمة المرور"><input className="input ltr" type="password" autoComplete="new-password" value={form.confirm} onChange={set("confirm")} required /></Field>
        <button className="btn-primary w-full">إنشاء حساب المدير</button>
      </form>
    </div>
  );
}
