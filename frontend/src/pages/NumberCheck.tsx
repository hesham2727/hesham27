import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, dt, type NumberCheck } from "../api";
import { ErrorBox, Field, ValidationView } from "../components/ui";

export default function NumberCheckPage() {
  const nav = useNavigate();
  const [number, setNumber] = useState("");
  const [region, setRegion] = useState("EG");
  const [result, setResult] = useState<NumberCheck | null>(null);
  const [history, setHistory] = useState<NumberCheck[]>([]);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadHistory = (query = q) =>
    api<NumberCheck[]>(`/api/numbers/checks?limit=200&q=${encodeURIComponent(query)}`).then(setHistory).catch(() => undefined);
  useEffect(() => { loadHistory(""); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setResult(await api<NumberCheck>("/api/numbers/validate", { method: "POST", body: { number, region } }));
      loadHistory();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطأ");
    }
  };

  const openInvestigation = () => {
    if (result) nav(`/investigations?new=${encodeURIComponent(result.raw_input)}`);
  };

  return (
    <div className="space-y-4">
      <h1 className="h1">التحقق من رقم هاتف</h1>
      <form onSubmit={submit} className="card grid gap-3 sm:grid-cols-[1fr_8rem_auto] sm:items-end">
        <Field label="رقم الهاتف (مثال: 01001234567 أو +201001234567)">
          <input className="input ltr" value={number} onChange={(e) => setNumber(e.target.value)} required maxLength={40} />
        </Field>
        <Field label="الدولة الافتراضية">
          <input className="input ltr uppercase" value={region} onChange={(e) => setRegion(e.target.value.toUpperCase())} maxLength={2} />
        </Field>
        <button className="btn-primary">تحقق</button>
      </form>
      <ErrorBox error={error} />
      {result && (
        <div className="card">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="h2 mb-0">نتيجة التحقق</h2>
            <button className="btn-secondary" onClick={openInvestigation}>فتح تحقيق لهذا الرقم</button>
          </div>
          <ValidationView v={result.result} />
        </div>
      )}
      <div className="card overflow-x-auto">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="h2 mb-0">سجل عمليات التحقق</h2>
          <input className="input max-w-xs" placeholder="بحث بالرقم…" value={q} onChange={(e) => { setQ(e.target.value); loadHistory(e.target.value); }} />
        </div>
        <table className="table">
          <thead><tr><th>الوقت</th><th>المُدخل</th><th>E.164</th><th>النتيجة</th><th>النوع</th><th>بواسطة</th></tr></thead>
          <tbody>
            {history.map((c) => (
              <tr key={c.id}>
                <td>{dt(c.checked_at)}</td>
                <td className="ltr">{c.raw_input}</td>
                <td className="ltr">{c.e164 || "—"}</td>
                <td>{c.is_valid ? "صالح" : "غير صالح"}</td>
                <td>{c.result.number_type_ar}</td>
                <td>{c.checked_by_username}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
