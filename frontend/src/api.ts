// REST client for the FBOSINT backend. Uses the HttpOnly session cookie and the
// double-submit CSRF token (cookie `fbo_csrf` -> header `X-CSRF-Token`).

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, details?: unknown) {
    super(code);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function readCookie(name: string): string {
  const m = document.cookie.split("; ").find((c) => c.startsWith(name + "="));
  return m ? decodeURIComponent(m.slice(name.length + 1)) : "";
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown; form?: FormData; query?: Record<string, string | number | boolean | undefined | null> } = {}): Promise<T> {
  const method = (opts.method || "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (UNSAFE.has(method)) headers["X-CSRF-Token"] = readCookie("fbo_csrf");
  let url = path;
  if (opts.query) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.query)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
    const s = q.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  let res: Response;
  try {
    res = await fetch(url, { method, headers, body, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network");
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = typeof data === "object" && data ? (data as { detail?: unknown }).detail : data;
    let code = "generic";
    if (typeof detail === "string") code = detail;
    else if (Array.isArray(detail)) code = String(detail[0] ?? "generic");
    else if (detail && typeof detail === "object" && "message" in detail) code = String((detail as { message: string }).message);
    if (res.status === 401 && onUnauthorized && !path.startsWith("/api/auth/login")) onUnauthorized();
    throw new ApiError(res.status, code, data);
  }
  return data as T;
}

// ---- types (mirror backend schemas) ----
export type Role = "admin" | "investigator" | "viewer";
export interface User { id: number; username: string; full_name: string; role: Role; is_active: boolean; language: "ar" | "en"; last_login_at: string | null; created_at: string }
export interface Investigation {
  id: number; reference: string; title: string; target_input: string; target_type: string; normalized_url: string; identifier: string;
  object_type: string; graph_object_id: string; purpose: string; legal_basis: string; notes: string; options: Record<string, unknown>;
  extra_urls: string[]; status: string; status_message: string; limitations: { code: string; message: string }[];
  created_by_id: number | null; created_at: string; updated_at: string; started_at: string | null; completed_at: string | null;
  counts: Record<string, number>; created_by_username: string;
}
export interface DataPoint { id: number; category: string; field: string; value: string; source_url: string; source_type: string; extraction_method: string; collected_at: string; availability: string; verification_status: string; confidence: string; classification: string; manually_reviewed: boolean; notes: string }
export interface Post { id: number; external_id: string; kind: string; parent_external_id: string; message: string; created_time: string | null; permalink: string; shared_link: string; source_url: string; source_type: string; collected_at: string }
export interface Media { id: number; kind: string; source_url: string; source_type: string; external_id: string; caption: string; created_time: string | null; mime_type: string; size_bytes: number; width: number; height: number; sha256: string; phash: string; dhash: string; metadata_json: Record<string, unknown>; duplicate_group: number | null; status: string; error_message: string; collected_at: string }
export interface Source { id: number; url: string; final_url: string; domain: string; source_type: string; status: string; http_status: number | null; title: string; content_sha256: string; error_message: string; fetched_at: string; data_points: number }
export interface CollectionEvent { id: number; step: string; level: string; message: string; details: Record<string, unknown>; created_at: string }
export interface AuditEntry { id: number; created_at: string; user_id: number | null; username: string; action: string; target_type: string; target_id: string; ip_address: string; success: boolean; details: Record<string, unknown> }

export const isSafeHttpUrl = (u: string) => /^https?:\/\//i.test(u);
