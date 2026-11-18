import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Field } from "../components/ui";

export default function Account() {
  const { user } = useAuth();
  const [f, setF] = useState({ current_password: "", new_password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setOk(false);
    if (f.new_password !== f.confirm) return setError("كلمتا المرور غير متطابقتين");
    try {
      await api("/api/auth/change-password", { method: "POST", body: { current_password: f.current_password, new_password: f.new_password } });
      setOk(true);
      setF({ current_password: "", new_password: "", confirm: "" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطأ");
    }
  };

  return (
    <div className="max-w-md space-y-4">
      <h1 className="h1">حسابي – {user?.username}</h1>
      <form onSubmit={submit} className="card space-y-3">
        <h2 className="h2">تغيير كلمة المرور</h2>
        <ErrorBox error={error} />
        {ok && <div className="text-sm text-green-700">تم تغيير كلمة المرور وإنهاء الجلسات الأخرى ✓</div>}
        <Field label="كلمة المرور الحالية"><input className="input ltr" type="password" autoComplete="current-password" value={f.current_password} onChange={(e) => setF({ ...f, current_password: e.target.value })} required /></Field>
        <Field label="كلمة المرور الجديدة"><input className="input ltr" type="password" autoComplete="new-password" value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} required /></Field>
        <Field label="تأكيد كلمة المرور الجديدة"><input className="input ltr" type="password" autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} required /></Field>
        <button className="btn-primary">تغيير</button>
      </form>
    </div>
  );
}
