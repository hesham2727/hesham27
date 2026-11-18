import { useEffect, useState } from "react";
import { api, dt, type AuditEntry } from "../api";

const ACTION_AR: Record<string, string> = {
  "auth.setup": "إعداد النظام",
  "auth.login": "تسجيل دخول",
  "auth.login_failed": "محاولة دخول فاشلة",
  "auth.login_locked": "دخول لحساب مقفل",
  "auth.logout": "تسجيل خروج",
  "auth.password_changed": "تغيير كلمة المرور",
  "number.validate": "تحقق من رقم",
  "investigation.create": "إنشاء تحقيق",
  "investigation.view": "عرض تحقيق",
  "investigation.update": "تعديل تحقيق",
  "investigation.delete": "حذف تحقيق",
  "source_record.create": "إضافة سجل مصدر",
  "source_record.delete": "حذف سجل مصدر",
  "invitation.create": "إنشاء دعوة موقع",
  "invitation.opened": "فتح العميل للدعوة",
  "invitation.shared": "مشاركة الموقع بموافقة",
  "invitation.declined": "رفض العميل",
  "invitation.revoke": "إلغاء دعوة",
  "location.list": "عرض المواقع",
  "location.reverse_geocode": "طلب عنوان تقريبي",
  "report.pdf": "تصدير PDF",
  "report.xlsx": "تصدير Excel",
  "report.xlsx_all": "تصدير Excel شامل",
  "settings.update": "تعديل الإعدادات",
  "retention.run": "تنفيذ سياسة الاحتفاظ",
  "user.create": "إنشاء مستخدم",
  "user.update": "تعديل مستخدم",
  "customer.create": "إضافة عميل",
  "customer.view": "عرض عميل",
  "customer.update": "تعديل عميل",
  "customer.delete": "حذف عميل",
};

export default function AuditLog() {
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [action, setAction] = useState("");
  const [username, setUsername] = useState("");
  const [offset, setOffset] = useState(0);
  const PAGE = 100;

  useEffect(() => {
    const p = new URLSearchParams({ action, username, limit: String(PAGE), offset: String(offset) });
    api<AuditEntry[]>(`/api/audit?${p}`).then(setItems).catch(() => undefined);
  }, [action, username, offset]);

  return (
    <div className="space-y-4">
      <h1 className="h1">سجل التدقيق</h1>
      <div className="card overflow-x-auto">
        <div className="mb-3 flex flex-wrap gap-2">
          <select className="input max-w-xs" value={action} onChange={(e) => { setAction(e.target.value); setOffset(0); }}>
            <option value="">كل العمليات</option>
            {["auth.", "number.", "investigation.", "source_record.", "invitation.", "location.", "report.", "customer.", "user.", "settings.", "retention."].map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          <input className="input max-w-xs" placeholder="اسم المستخدم" value={username} onChange={(e) => { setUsername(e.target.value); setOffset(0); }} />
        </div>
        <table className="table">
          <thead><tr><th>الوقت</th><th>المستخدم</th><th>العملية</th><th>الكيان</th><th>تفاصيل</th><th>IP</th></tr></thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td className="whitespace-nowrap">{dt(a.at)}</td>
                <td>{a.username || (a.action.startsWith("invitation.") ? "العميل (رابط عام)" : "النظام")}</td>
                <td>{ACTION_AR[a.action] ?? a.action}</td>
                <td className="ltr">{a.entity_type}{a.entity_id ? `#${a.entity_id}` : ""}</td>
                <td className="ltr max-w-xs break-all text-xs text-slate-500">{a.details ? JSON.stringify(a.details) : ""}</td>
                <td className="ltr text-xs">{a.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-3 flex gap-2">
          <button className="btn-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>الأحدث</button>
          <button className="btn-secondary" disabled={items.length < PAGE} onClick={() => setOffset(offset + PAGE)}>الأقدم</button>
        </div>
      </div>
    </div>
  );
}
