// Thin fetch wrapper. All mutating calls carry the CSRF header expected by the API.

export class ApiError extends Error {
  status: number;
  steps: string[];
  constructor(status: number, message: string, steps: string[] = []) {
    super(message);
    this.status = status;
    this.steps = steps;
  }
}

function extractMessage(body: unknown, status: number): { message: string; steps: string[] } {
  const b = body as { detail?: unknown; errors?: { field: string; message: string }[] } | null;
  if (b && typeof b.detail === "object" && b.detail !== null) {
    const d = b.detail as { message?: string; steps?: string[] };
    return { message: d.message ?? "خطأ", steps: d.steps ?? [] };
  }
  if (b && typeof b.detail === "string") {
    const extra = b.errors?.map((e) => `${e.field}: ${e.message}`).join(" | ");
    return { message: extra ? `${b.detail} – ${extra}` : b.detail, steps: [] };
  }
  return { message: `خطأ غير متوقع (${status})`, steps: [] };
}

export async function api<T = unknown>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-Requested-With"] = "tahqiq";
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const { message, steps } = extractMessage(data, res.status);
    if (res.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event("tahqiq:unauthorized"));
    throw new ApiError(res.status, message, steps);
  }
  return data as T;
}

// ---------------------------------------------------------------- types
export interface User {
  id: number;
  username: string;
  full_name: string;
  role: "admin" | "operator";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Validation {
  input: string;
  is_valid: boolean;
  is_possible: boolean;
  e164: string;
  international_format: string;
  national_format: string;
  region_code: string;
  number_type: string;
  number_type_ar: string;
  original_operator: string;
  original_operator_ar: string;
  geographic_area: string;
  time_zones: string[];
  warnings: string[];
  not_derivable: string[];
  current_location: string;
  current_location_ar: string;
  data_source: string;
  analyzed_at: string;
}

export interface NumberCheck {
  id: number;
  raw_input: string;
  e164: string;
  is_valid: boolean;
  investigation_id: number | null;
  checked_at: string;
  checked_by_username: string;
  result: Validation;
}

export interface Investigation {
  id: number;
  ref_code: string;
  phone_raw: string;
  phone_e164: string;
  title: string;
  purpose: string;
  status: "open" | "closed";
  customer_id: number | null;
  customer_name: string;
  notes: string;
  validation: Validation | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  created_by_username: string;
}

export interface SourceRecord {
  id: number;
  investigation_id: number;
  data_source_id: number | null;
  source_name: string;
  source_url: string;
  source_type: string;
  observed_at: string;
  summary: string;
  reliability: "confirmed" | "likely" | "unverified";
  created_at: string;
  created_by_username: string;
}

export interface DataSource {
  id: number;
  key: string;
  name: string;
  url: string;
  information: string;
  limitations: string;
  update_frequency: string;
  license: string;
  access_method: string;
  is_builtin: boolean;
  enabled: boolean;
}

export interface LocationRec {
  id: number;
  latitude: number;
  longitude: number;
  accuracy_m: number | null;
  collected_at: string;
  consent_given_at: string;
  device_timestamp: string | null;
  address_text: string;
  is_current: false;
  label: string;
}

export interface Invitation {
  id: number;
  investigation_id: number | null;
  customer_id: number | null;
  phone_e164: string;
  purpose: string;
  status: string;
  effective_status: string;
  created_at: string;
  expires_at: string;
  opened_at: string | null;
  responded_at: string | null;
}

export interface InvitationCreated extends Invitation {
  link: string;
  message_text: string;
  whatsapp_url: string;
  sms_uri: string;
}

export interface Customer {
  id: number;
  full_name: string;
  phone_e164: string;
  email: string;
  address: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface InternetMode {
  enabled: boolean;
  public_base_url: string;
  configured_from: string;
  message: string;
  steps: string[];
}

export interface AppSettings {
  organization_name: string;
  public_base_url: string;
  public_base_url_locked: boolean;
  invitation_default_hours: number;
  map: { enabled: boolean; tile_url: string; attribution: string; max_zoom: number };
  adapters: Record<string, { enabled: boolean; endpoint?: string }>;
  retention: Record<string, number>;
  internet_mode: InternetMode;
}

export interface AuditEntry {
  id: number;
  at: string;
  username: string;
  action: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown> | null;
  ip: string;
}

// ---------------------------------------------------------------- formatting
const fmt = new Intl.DateTimeFormat("ar-EG", {
  timeZone: "Africa/Cairo",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function dt(value: string | null | undefined): string {
  if (!value) return "—";
  return fmt.format(new Date(value));
}

export function ageAr(value: string): string {
  const secs = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (secs < 60) return "منذ أقل من دقيقة";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `منذ ${mins} دقيقة`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `منذ ${hours} ساعة`;
  return `منذ ${Math.floor(hours / 24)} يوم`;
}

export const RELIABILITY_AR: Record<string, string> = { confirmed: "مؤكد", likely: "مرجّح", unverified: "غير متحقق" };
export const INVITE_STATUS_AR: Record<string, string> = {
  pending: "بانتظار الفتح",
  opened: "تم فتح الرابط",
  shared: "تمت المشاركة",
  declined: "رفض العميل",
  revoked: "ملغاة",
  expired: "منتهية",
};
export const SOURCE_TYPE_AR: Record<string, string> = {
  official_registry: "سجل رسمي",
  website: "موقع ويب",
  social_media: "وسائل تواصل",
  document: "مستند",
  other: "أخرى",
};
