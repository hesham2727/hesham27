import { useEffect, useState } from "react";
import { api, ApiError, type AppSettings } from "../api";
import { ErrorBox, Field } from "../components/ui";

const RETENTION_AR: Record<string, string> = {
  location_records_days: "المواقع المشاركة",
  invitations_days: "الدعوات المنتهية",
  number_checks_days: "سجل عمليات التحقق",
  audit_logs_days: "سجل التدقيق",
  closed_investigations_days: "التحقيقات المغلقة",
};

export default function SettingsPage() {
  const [s, setS] = useState<AppSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => { api<AppSettings>("/api/settings").then(setS).catch(() => undefined); }, []);
  if (!s) return <div className="text-slate-500">جارٍ التحميل…</div>;

  const save = async (body: Partial<AppSettings>) => {
    setError(null);
    setMsg(null);
    try {
      setS(await api<AppSettings>("/api/settings", { method: "PUT", body }));
      setMsg("تم الحفظ ✓");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطأ");
    }
  };
  const runRetention = async () => {
    const r = await api<Record<string, number>>("/api/retention/run", { method: "POST" });
    setMsg("تم تنفيذ الحذف: " + Object.entries(r).map(([k, v]) => `${k}=${v}`).join("، "));
  };

  const im = s.internet_mode;
  return (
    <div className="space-y-4">
      <h1 className="h1">الإعدادات</h1>
      <ErrorBox error={error} />
      {msg && <div className="rounded-lg bg-green-50 p-3 text-sm text-green-800">{msg}</div>}

      <section className="card space-y-3">
        <h2 className="h2">وضع الإنترنت (دعوات مشاركة الموقع)</h2>
        <div className={`rounded-lg p-3 text-sm ${im.enabled ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-900"}`}>
          <div className="font-semibold">{im.enabled ? "مفعّل" : "غير مفعّل"} – {im.message}</div>
          {!im.enabled && <ol className="mt-2 list-decimal space-y-1 pr-5">{im.steps.map((x) => <li key={x}>{x}</li>)}</ol>}
        </div>
        <Field label="اسم الجهة (يظهر للعميل في صفحة الموافقة)">
          <input className="input" value={s.organization_name} onChange={(e) => setS({ ...s, organization_name: e.target.value })} />
        </Field>
        <Field label="عنوان الوصول العام HTTPS (مثال: https://xxxx.trycloudflare.com)">
          <input className="input ltr" value={s.public_base_url} disabled={s.public_base_url_locked} onChange={(e) => setS({ ...s, public_base_url: e.target.value })} placeholder="https://" />
        </Field>
        {s.public_base_url_locked && <p className="text-xs text-slate-500">العنوان مضبوط من متغير البيئة TAHQIQ_PUBLIC_BASE_URL على الخادم.</p>}
        <Field label="صلاحية الدعوة الافتراضية (ساعات)">
          <input className="input max-w-[8rem]" type="number" min={1} max={168} value={s.invitation_default_hours} onChange={(e) => setS({ ...s, invitation_default_hours: Number(e.target.value) })} />
        </Field>
        <button className="btn-primary" onClick={() => save({
          organization_name: s.organization_name,
          invitation_default_hours: s.invitation_default_hours,
          ...(s.public_base_url_locked ? {} : { public_base_url: s.public_base_url }),
        })}>حفظ</button>
      </section>

      <section className="card space-y-3">
        <h2 className="h2">الخريطة</h2>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={s.map.enabled} onChange={(e) => setS({ ...s, map: { ...s.map, enabled: e.target.checked } })} /> تفعيل الخريطة التفاعلية
        </label>
        <Field label="رابط مزوّد البلاطات (متوافق مع OpenStreetMap)">
          <input className="input ltr" value={s.map.tile_url} onChange={(e) => setS({ ...s, map: { ...s.map, tile_url: e.target.value } })} />
        </Field>
        <Field label="نص الإسناد (إلزامي حسب ترخيص المزوّد)">
          <input className="input ltr" value={s.map.attribution} onChange={(e) => setS({ ...s, map: { ...s.map, attribution: e.target.value } })} />
        </Field>
        <p className="text-xs text-slate-500">خوادم OpenStreetMap الرسمية للاستخدام الخفيف فقط وفق سياسة الاستخدام. للاستخدام الكثيف استخدم مزوّداً آخر أو خادم بلاطات خاص.</p>
        <button className="btn-primary" onClick={() => save({ map: s.map })}>حفظ</button>
      </section>

      <section className="card space-y-3">
        <h2 className="h2">المحوّلات الخارجية الاختيارية (مجانية – يمكن تعطيلها)</h2>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={s.adapters.manual_share?.enabled} onChange={(e) => setS({ ...s, adapters: { ...s.adapters, manual_share: { enabled: e.target.checked } } })} />
          <span>المشاركة اليدوية: روابط واتساب (wa.me) ورسالة نصية من جهازك – لا تحتاج أي حساب.</span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={s.adapters.nominatim_reverse_geocoding?.enabled} onChange={(e) => setS({ ...s, adapters: { ...s.adapters, nominatim_reverse_geocoding: { enabled: e.target.checked } } })} />
          <span>العنوان التقريبي عبر OpenStreetMap Nominatim – عند الطلب فقط، بحد أقصى طلب/ثانية وفق سياسة الاستخدام.</span>
        </label>
        <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
          غير متاح في هذا الإصدار (يتطلب حسابات مدفوعة أو تصريحاً قانونياً – لم يُنفَّذ): إرسال SMS آلي، مزودو معلومات الاتصالات المدفوعون، تكامل MDM أو شركات الاتصالات.
        </div>
        <button className="btn-primary" onClick={() => save({ adapters: { manual_share: { enabled: !!s.adapters.manual_share?.enabled }, nominatim_reverse_geocoding: { enabled: !!s.adapters.nominatim_reverse_geocoding?.enabled } } })}>حفظ</button>
      </section>

      <section className="card space-y-3">
        <h2 className="h2">سياسة الاحتفاظ بالبيانات (بالأيام – 0 = بدون حذف تلقائي)</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(s.retention).map(([k, v]) => (
            <Field key={k} label={RETENTION_AR[k] ?? k}>
              <input className="input" type="number" min={0} max={3650} value={v} onChange={(e) => setS({ ...s, retention: { ...s.retention, [k]: Number(e.target.value) } })} />
            </Field>
          ))}
        </div>
        <p className="text-xs text-slate-500">يتم التنفيذ تلقائياً عند التشغيل وكل 24 ساعة. يُنصح بأقل مدة تحقق الغرض وفق قانون حماية البيانات الشخصية رقم 151 لسنة 2020.</p>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={() => save({ retention: s.retention })}>حفظ</button>
          <button className="btn-secondary" onClick={runRetention}>تنفيذ الحذف الآن</button>
        </div>
      </section>
    </div>
  );
}
