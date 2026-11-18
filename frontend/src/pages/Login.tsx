import { useState, type FormEvent } from "react";
import { api, ApiError, type User } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Field } from "../components/ui";

export default function Login() {
  const { setUser } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setUser(await api<User>("/api/auth/login", { method: "POST", body: { username, password } }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "تعذر تسجيل الدخول");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-bold text-brand-800">تحقيق</h1>
          <p className="text-sm text-slate-500">تسجيل الدخول إلى منصة التحقق من الأرقام</p>
        </div>
        <ErrorBox error={error} />
        <Field label="اسم المستخدم">
          <input className="input ltr" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </Field>
        <Field label="كلمة المرور">
          <input className="input ltr" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <button className="btn-primary w-full" disabled={busy}>{busy ? "جارٍ الدخول…" : "دخول"}</button>
      </form>
    </div>
  );
}
