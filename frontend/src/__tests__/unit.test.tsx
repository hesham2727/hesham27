import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ar from "../../../shared/i18n/ar.json";
import en from "../../../shared/i18n/en.json";
import { api, ApiError, readCookie } from "../api";
import { SafeLink } from "../components/ui";
import { I18nProvider, useI18n } from "../i18n";

describe("i18n dictionaries", () => {
  it("have identical keys and no empty values", () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort());
    for (const [k, v] of Object.entries(ar)) expect(v, k).not.toBe("");
    for (const [k, v] of Object.entries(en)) expect(v, k).not.toBe("");
  });
  it("Arabic strings contain Arabic script (not untranslated copies)", () => {
    const untranslated = Object.entries(ar).filter(([k, v]) => v === (en as Record<string, string>)[k] && /[a-z]{4,}/i.test(v) && !/(HTTP|IP|SHA-256|Meta Graph API|^https?:)/.test(v));
    expect(untranslated).toEqual([]);
  });
  it("defaults to Arabic RTL", () => {
    localStorage.clear();
    function Probe() {
      const { lang, dir, t } = useI18n();
      return <div>{lang}|{dir}|{t("nav.dashboard")}</div>;
    }
    render(<I18nProvider><Probe /></I18nProvider>);
    expect(screen.getByText("ar|rtl|لوحة التحقيقات")).toBeTruthy();
    expect(document.documentElement.dir).toBe("rtl");
  });
});

describe("api client", () => {
  afterEach(() => vi.restoreAllMocks());
  it("sends CSRF header on unsafe methods only", async () => {
    document.cookie = "fbo_csrf=tok123";
    expect(readCookie("fbo_csrf")).toBe("tok123");
    const f = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ ok: 1 }), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", f);
    await api("/api/x", { method: "POST", body: { a: 1 } });
    await api("/api/y", { query: { q: "a b", empty: "" } });
    expect(f.mock.calls[0][1].headers["X-CSRF-Token"]).toBe("tok123");
    expect(f.mock.calls[1][1].headers["X-CSRF-Token"]).toBeUndefined();
    expect(f.mock.calls[1][0]).toBe("/api/y?q=a+b");
  });
  it("maps error responses to ApiError codes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "invalid_credentials" }), { status: 401, headers: { "content-type": "application/json" } })));
    await expect(api("/api/auth/login", { method: "POST", body: {} })).rejects.toMatchObject({ status: 401, code: "invalid_credentials" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    await expect(api("/api/x")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("SafeLink", () => {
  it("never renders javascript: URLs as links", () => {
    const { container } = render(<SafeLink href="javascript:alert(1)" />);
    expect(container.querySelector("a")).toBeNull();
    const ok = render(<SafeLink href="https://example.com/a" />);
    const a = ok.container.querySelector("a")!;
    expect(a.getAttribute("rel")).toContain("noopener");
  });
});
