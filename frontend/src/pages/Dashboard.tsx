import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, dt, type InternetMode, type Investigation, type NumberCheck } from "../api";
import { StatusBadge } from "../components/ui";

export default function Dashboard() {
  const [invs, setInvs] = useState<Investigation[]>([]);
  const [checks, setChecks] = useState<NumberCheck[]>([]);
  const [mode, setMode] = useState<InternetMode | null>(null);

  useEffect(() => {
    api<Investigation[]>("/api/investigations?limit=200").then(setInvs).catch(() => undefined);
    api<NumberCheck[]>("/api/numbers/checks?limit=10").then(setChecks).catch(() => undefined);
    api<InternetMode>("/api/internet-mode").then(setMode).catch(() => undefined);
  }, []);

  const open = invs.filter((i) => i.status === "open").length;
  const stats = [
    { label: "التحقيقات المفتوحة", value: open },
    { label: "إجمالي التحقيقات", value: invs.length },
    { label: "آخر عمليات التحقق", value: checks.length },
  ];

  return (
    <div className="space-y-4">
      <h1 className="h1">لوحة المتابعة</h1>
      <div className="grid gap-3 sm:grid-cols-3">
        {stats.map((s) => (
          <div key={s.label} className="card">
            <div className="text-sm text-slate-500">{s.label}</div>
            <div className="text-2xl font-bold text-brand-800">{s.value}</div>
          </div>
        ))}
      </div>
      {mode && (
        <div className={`card text-sm ${mode.enabled ? "border-r-4 border-green-600" : "border-r-4 border-amber-500"}`}>
          <div className="font-semibold">{mode.enabled ? "وضع الإنترنت مفعّل" : "وضع الإنترنت غير مفعّل – دعوات مشاركة الموقع معطّلة"}</div>
          <div className="text-slate-600">{mode.message}</div>
          {mode.enabled && <div className="ltr mt-1 text-xs text-slate-500">{mode.public_base_url}</div>}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card overflow-x-auto">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="h2 mb-0">أحدث التحقيقات</h2>
            <Link to="/investigations" className="text-sm text-brand-600">عرض الكل</Link>
          </div>
          <table className="table">
            <thead><tr><th>المرجع</th><th>العنوان</th><th>الحالة</th></tr></thead>
            <tbody>
              {invs.slice(0, 8).map((i) => (
                <tr key={i.id}>
                  <td className="ltr"><Link className="text-brand-600" to={`/investigations/${i.id}`}>{i.ref_code}</Link></td>
                  <td>{i.title}</td>
                  <td><StatusBadge status={i.status} /></td>
                </tr>
              ))}
              {invs.length === 0 && <tr><td colSpan={3} className="text-slate-500">لا توجد تحقيقات بعد.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="card overflow-x-auto">
          <h2 className="h2">آخر عمليات التحقق</h2>
          <table className="table">
            <thead><tr><th>الوقت</th><th>الرقم</th><th>النتيجة</th></tr></thead>
            <tbody>
              {checks.map((c) => (
                <tr key={c.id}>
                  <td>{dt(c.checked_at)}</td>
                  <td className="ltr">{c.e164 || c.raw_input}</td>
                  <td>{c.is_valid ? "صالح" : "غير صالح"}</td>
                </tr>
              ))}
              {checks.length === 0 && <tr><td colSpan={3} className="text-slate-500">لا يوجد.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
