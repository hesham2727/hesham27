import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  ApiError,
  dt,
  ageAr,
  type AppSettings,
  type InternetMode,
  type Invitation,
  type InvitationCreated,
  type LocationRec,
} from "../api";
import MapView from "./MapView";
import { ErrorBox, Field, NoCurrentLocation, StatusBadge } from "./ui";

interface Props {
  investigationId?: number;
  customerId?: number;
  locations: LocationRec[];
  invitations: Invitation[];
  reload: () => void;
}

export default function LocationPanel({ investigationId, customerId, locations, invitations, reload }: Props) {
  const [mode, setMode] = useState<InternetMode | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [purpose, setPurpose] = useState("");
  const [phone, setPhone] = useState("");
  const [hours, setHours] = useState(24);
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const [error, setError] = useState<{ msg: string; steps: string[] } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api<InternetMode>("/api/internet-mode").then(setMode).catch(() => undefined);
    api<AppSettings>("/api/settings").then((s) => { setSettings(s); setHours(s.invitation_default_hours); }).catch(() => undefined);
  }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setCopied(false);
    try {
      const r = await api<InvitationCreated>("/api/invitations", {
        method: "POST",
        body: { investigation_id: investigationId ?? null, customer_id: customerId ?? null, phone, purpose, hours },
      });
      setCreated(r);
      reload();
    } catch (err) {
      if (err instanceof ApiError) setError({ msg: err.message, steps: err.steps });
    }
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      window.prompt("انسخ النص:", text);
    }
  };

  const revoke = async (id: number) => {
    await api(`/api/invitations/${id}/revoke`, { method: "POST" });
    reload();
  };

  const geocode = async (id: number) => {
    try {
      await api(`/api/locations/${id}/reverse-geocode`, { method: "POST" });
      reload();
    } catch (err) {
      if (err instanceof ApiError) setError({ msg: err.message, steps: [] });
    }
  };

  const geocodeEnabled = settings?.adapters?.nominatim_reverse_geocoding?.enabled;

  return (
    <div className="space-y-4">
      <NoCurrentLocation />

      <div className="card space-y-3">
        <h3 className="h2">طلب مشاركة الموقع بموافقة صاحب الجهاز</h3>
        {mode && !mode.enabled ? (
          <ErrorBox error={`دعوات العملاء الخارجية معطّلة: ${mode.message}`} steps={mode.steps} />
        ) : (
          <>
            <p className="text-sm text-slate-600">
              يتم إنشاء رابط HTTPS يُستخدم مرة واحدة. يفتحه العميل، ويقرأ الغرض، ثم يوافق أو يرفض. لا يوجد أي تتبع مستمر.
              أرسل الرابط يدوياً (نسخ / واتساب / رسالة نصية من هاتفك) – لا توجد خدمة SMS مدفوعة.
            </p>
            <form onSubmit={create} className="grid gap-3 md:grid-cols-[1fr_12rem_8rem_auto] md:items-end">
              <Field label="الغرض الذي سيظهر للعميل *">
                <input className="input" value={purpose} onChange={(e) => setPurpose(e.target.value)} required minLength={5} placeholder="مثال: تأكيد عنوان التسليم" />
              </Field>
              <Field label="رقم العميل (اختياري)">
                <input className="input ltr" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="من التحقيق افتراضياً" />
              </Field>
              <Field label="الصلاحية (ساعات)">
                <input className="input" type="number" min={1} max={168} value={hours} onChange={(e) => setHours(Number(e.target.value))} />
              </Field>
              <button className="btn-primary">إنشاء رابط الدعوة</button>
            </form>
          </>
        )}
        <ErrorBox error={error?.msg} steps={error?.steps} />
        {created && (
          <div className="space-y-2 rounded-lg border border-green-200 bg-green-50 p-3 text-sm">
            <div className="font-semibold text-green-800">تم إنشاء الدعوة – يظهر الرابط مرة واحدة فقط، احفظه أو أرسله الآن.</div>
            <div data-testid="invite-link" className="ltr break-all rounded bg-white p-2 font-mono text-xs">{created.link}</div>
            <textarea className="input text-xs" rows={4} readOnly value={created.message_text} />
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary" onClick={() => copy(created.message_text)}>نسخ الرسالة</button>
              <button type="button" className="btn-secondary" onClick={() => copy(created.link)}>نسخ الرابط فقط</button>
              {created.whatsapp_url && <a className="btn-secondary" href={created.whatsapp_url} target="_blank" rel="noreferrer">فتح واتساب</a>}
              {created.sms_uri && <a className="btn-secondary" href={created.sms_uri}>رسالة نصية</a>}
              {copied && <span className="self-center text-green-700">تم النسخ ✓</span>}
            </div>
          </div>
        )}
      </div>

      {invitations.length > 0 && (
        <div className="card overflow-x-auto">
          <h3 className="h2">الدعوات</h3>
          <table className="table">
            <thead><tr><th>أُنشئت</th><th>تنتهي</th><th>الغرض</th><th>الحالة</th><th></th></tr></thead>
            <tbody>
              {invitations.map((i) => (
                <tr key={i.id}>
                  <td className="whitespace-nowrap">{dt(i.created_at)}</td>
                  <td className="whitespace-nowrap">{dt(i.expires_at)}</td>
                  <td>{i.purpose}</td>
                  <td><StatusBadge status={i.effective_status} /></td>
                  <td>
                    {(i.effective_status === "pending" || i.effective_status === "opened") && (
                      <button className="text-sm text-red-700 underline" onClick={() => revoke(i.id)}>إلغاء</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card space-y-3 overflow-x-auto">
        <h3 className="h2">مواقع تمت مشاركتها سابقاً (بيانات تاريخية – ليست الموقع الحالي)</h3>
        {locations.length === 0 ? (
          <p className="text-sm text-slate-500">لا توجد مواقع مُشاركة.</p>
        ) : (
          <>
            <MapView locations={locations} />
            <table className="table">
              <thead><tr><th>وقت الجمع</th><th>العمر</th><th>الإحداثيات</th><th>الدقة</th><th>العنوان التقريبي</th></tr></thead>
              <tbody>
                {locations.map((l) => (
                  <tr key={l.id}>
                    <td className="whitespace-nowrap">{dt(l.collected_at)}</td>
                    <td className="whitespace-nowrap font-semibold text-amber-800">{ageAr(l.collected_at)}</td>
                    <td className="ltr whitespace-nowrap">{l.latitude.toFixed(6)}, {l.longitude.toFixed(6)}</td>
                    <td>{l.accuracy_m != null ? `±${Math.round(l.accuracy_m)} م` : "—"}</td>
                    <td>
                      {l.address_text ||
                        (geocodeEnabled ? (
                          <button className="text-sm text-brand-600 underline" onClick={() => geocode(l.id)}>عرض العنوان (OSM)</button>
                        ) : (
                          "—"
                        ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
