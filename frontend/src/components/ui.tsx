import type { ReactNode } from "react";
import type { Validation } from "../api";

export const CURRENT_LOCATION_UNAVAILABLE = "CURRENT LOCATION UNAVAILABLE – NO AUTHORIZED LOCATION SOURCE.";

export function ErrorBox({ error, steps }: { error?: string | null; steps?: string[] }) {
  if (!error) return null;
  return (
    <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
      <div className="font-semibold">{error}</div>
      {steps && steps.length > 0 && (
        <ol className="mt-2 list-decimal space-y-1 pr-5">
          {steps.map((s) => <li key={s}>{s}</li>)}
        </ol>
      )}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

export function NoCurrentLocation() {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      <div className="ltr text-center font-bold">{CURRENT_LOCATION_UNAVAILABLE}</div>
      <div className="mt-1 text-center">الموقع الحالي غير متاح – لا يوجد مصدر موقع مُصرَّح به. الرقم وحده لا يكشف أي موقع.</div>
    </div>
  );
}

export function ValidationView({ v }: { v: Validation }) {
  const rows: [string, ReactNode][] = [
    ["النتيجة", v.is_valid ? <span className="badge bg-green-100 text-green-800">رقم صالح</span> : <span className="badge bg-red-100 text-red-800">رقم غير صالح</span>],
    ["الصيغة الدولية (E.164)", <span className="ltr">{v.e164 || "—"}</span>],
    ["الصيغة الدولية المنسقة", <span className="ltr">{v.international_format || "—"}</span>],
    ["الصيغة المحلية", <span className="ltr">{v.national_format || "—"}</span>],
    ["الدولة", v.region_code || "—"],
    ["النوع", v.number_type_ar],
    ["المشغّل الأصلي للنطاق", v.original_operator_ar || "—"],
    ["المنطقة", v.geographic_area || "—"],
  ];
  return (
    <div className="space-y-3">
      <table className="table">
        <tbody>
          {rows.map(([k, val]) => (
            <tr key={k}><th className="w-48">{k}</th><td>{val}</td></tr>
          ))}
        </tbody>
      </table>
      {v.warnings.length > 0 && (
        <ul className="list-disc space-y-1 rounded-lg bg-amber-50 p-3 pr-6 text-sm text-amber-900">
          {v.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
      <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
        <div className="font-semibold">لا يمكن استنتاج ما يلي من الرقم وحده:</div>
        <div>{v.not_derivable.join("، ")}</div>
      </div>
      <NoCurrentLocation />
      <div className="text-xs text-slate-500">مصدر البيانات: {v.data_source} – تحليل دون اتصال بالإنترنت</div>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    open: "bg-blue-100 text-blue-800",
    closed: "bg-slate-200 text-slate-700",
    shared: "bg-green-100 text-green-800",
    declined: "bg-red-100 text-red-800",
    revoked: "bg-slate-200 text-slate-700",
    expired: "bg-slate-200 text-slate-700",
    pending: "bg-amber-100 text-amber-800",
    opened: "bg-blue-100 text-blue-800",
  };
  return <span className={`badge ${map[status] ?? "bg-slate-100"}`}>{label(status)}</span>;
}

function label(s: string): string {
  return (
    {
      open: "مفتوح",
      closed: "مغلق",
      pending: "بانتظار الفتح",
      opened: "تم فتح الرابط",
      shared: "تمت المشاركة",
      declined: "رفض",
      revoked: "ملغاة",
      expired: "منتهية",
    } as Record<string, string>
  )[s] ?? s;
}
