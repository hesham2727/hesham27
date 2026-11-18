import { useEffect, useState } from "react";
import { api, type DataSource } from "../api";
import { useAuth } from "../auth";

const ACCESS_AR: Record<string, string> = { manual: "مراجعة يدوية", bundled: "مضمّن دون اتصال", api: "اتصال خارجي" };

export default function DataSources() {
  const { user } = useAuth();
  const [items, setItems] = useState<DataSource[]>([]);
  const load = () => api<DataSource[]>("/api/data-sources").then(setItems).catch(() => undefined);
  useEffect(() => { load(); }, []);

  const toggle = async (d: DataSource) => {
    await api(`/api/data-sources/${d.id}?enabled=${!d.enabled}`, { method: "PATCH" });
    load();
  };

  return (
    <div className="space-y-4">
      <h1 className="h1">دليل المصادر العامة المجانية</h1>
      <p className="text-sm text-slate-600">
        كل مصدر بيانات يستخدمه التطبيق أو يُرشد إليه موثّق هنا. لا يقوم التطبيق بأي جمع آلي (Scraping) من مواقع الويب؛ أي معلومة من موقع عام تُسجَّل يدوياً مع الرابط وتاريخ الاطلاع.
      </p>
      <div className="grid gap-3 lg:grid-cols-2">
        {items.map((d) => (
          <div key={d.id} className={`card space-y-2 text-sm ${d.enabled ? "" : "opacity-60"}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="font-bold text-brand-800">{d.name}</div>
              <span className="badge bg-slate-100 text-slate-700">{ACCESS_AR[d.access_method] ?? d.access_method}</span>
            </div>
            {d.url && <a className="ltr block break-all text-xs text-brand-600 underline" href={d.url} target="_blank" rel="noreferrer noopener">{d.url}</a>}
            <div><span className="font-semibold">المعلومات المتاحة: </span>{d.information}</div>
            <div><span className="font-semibold">القيود: </span>{d.limitations}</div>
            <div><span className="font-semibold">التحديث: </span>{d.update_frequency || "غير معروف"}</div>
            <div><span className="font-semibold">الترخيص والإسناد: </span>{d.license}</div>
            {user?.role === "admin" && (
              <button className="text-xs text-brand-600 underline" onClick={() => toggle(d)}>{d.enabled ? "تعطيل من قائمة الاختيار" : "تفعيل"}</button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
