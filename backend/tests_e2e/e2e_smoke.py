"""End-to-end smoke test through a real browser (optional, not part of pytest).

Prerequisites: frontend built (frontend/dist), Playwright + Chromium installed.
    python tests_e2e/e2e_smoke.py [screenshot_dir]

Starts the full server on a free port with a throw-away data directory and
walks through: first-run setup -> number check -> investigation -> public
source record -> invitation (Internet Mode) -> customer consent with browser
geolocation -> historical location on the map -> PDF/Excel downloads.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BACKEND = Path(__file__).resolve().parents[1]


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> int:
    shots = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp())
    shots.mkdir(parents=True, exist_ok=True)
    port = free_port()
    data = tempfile.mkdtemp()
    env = dict(os.environ, TAHQIQ_DATA_DIR=data, TAHQIQ_MODE="server")
    proc = subprocess.Popen([sys.executable, "-m", "app.serve", "--port", str(port)], cwd=BACKEND, env=env)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{base}/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        with sync_playwright() as pw:
            exe = os.environ.get("E2E_CHROMIUM")  # optional path to an existing Chromium
            browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
            ctx = browser.new_context(locale="ar-EG", viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            page.goto(base)
            expect(page.get_by_text("الإعداد الأول")).to_be_visible()
            page.get_by_label("الاسم الكامل").fill("هشام")
            page.get_by_label("كلمة المرور (10").fill("Admin-Passw0rd")
            page.get_by_label("تأكيد كلمة المرور").fill("Admin-Passw0rd")
            page.get_by_role("button", name="إنشاء حساب المدير").click()
            expect(page.get_by_role("heading", name="لوحة المتابعة")).to_be_visible()
            page.screenshot(path=shots / "01-dashboard.png")

            page.get_by_role("link", name="التحقق من رقم").click()
            page.get_by_label("رقم الهاتف").fill("01001234567")
            page.get_by_role("button", name="تحقق").click()
            expect(page.get_by_text("رقم صالح")).to_be_visible()
            expect(page.get_by_text("CURRENT LOCATION UNAVAILABLE – NO AUTHORIZED LOCATION SOURCE.")).to_be_visible()
            page.screenshot(path=shots / "02-number-check.png", full_page=True)

            page.get_by_role("button", name="فتح تحقيق لهذا الرقم").click()
            page.get_by_label("عنوان التحقيق").fill("التحقق من رقم مورد ألومنيوم")
            page.get_by_label("الغرض المشروع").fill("التحقق من بيانات مورد قبل توقيع أمر الشراء")
            page.get_by_role("button", name="إنشاء والتحقق من الرقم").click()
            expect(page.get_by_text("نتيجة التحقق من الرقم")).to_be_visible()

            page.get_by_role("button", name="المصادر العامة").click()
            page.get_by_label("اسم المصدر").fill("الموقع الرسمي للمورد")
            page.get_by_label("الرابط").fill("https://example.com/contact")
            page.get_by_label("ملخص ما تم العثور عليه").fill("الرقم منشور كرقم المبيعات في صفحة التواصل")
            page.get_by_role("button", name="حفظ السجل").click()
            expect(page.get_by_role("link", name="الموقع الرسمي للمورد")).to_be_visible()

            page.get_by_role("button", name="الموقع (0)").click()
            expect(page.get_by_text("دعوات العملاء الخارجية معطّلة")).to_be_visible()
            page.screenshot(path=shots / "03-invitations-disabled.png", full_page=True)
            inv_url = page.url

            page.get_by_role("link", name="الإعدادات").click()
            page.get_by_label("اسم الجهة").fill("مصنع قصور السلطان")
            page.get_by_label("عنوان الوصول العام HTTPS").fill("https://demo-tunnel.trycloudflare.com")
            page.locator("section").first.get_by_role("button", name="حفظ").click()
            expect(page.get_by_text("تم الحفظ ✓")).to_be_visible()
            page.screenshot(path=shots / "04-settings.png", full_page=True)

            page.goto(inv_url)
            page.get_by_role("button", name="الموقع (0)").click()
            page.get_by_label("الغرض الذي سيظهر للعميل").fill("تأكيد موقع التسليم للطلبية")
            page.get_by_role("button", name="إنشاء رابط الدعوة").click()
            link = page.get_by_test_id("invite-link").inner_text()
            assert link.startswith("https://demo-tunnel.trycloudflare.com/p/"), link
            page.screenshot(path=shots / "05-invitation-created.png", full_page=True)

            # The customer's phone: open the consent page locally (localhost counts as a secure context).
            cust = browser.new_context(locale="ar-EG", viewport={"width": 390, "height": 844},
                                       geolocation={"latitude": 30.0444, "longitude": 31.2357, "accuracy": 25},
                                       permissions=["geolocation"])
            cp = cust.new_page()
            cp.goto(base + "/p/" + link.rsplit("/p/", 1)[1])
            expect(cp.get_by_text("مصنع قصور السلطان")).to_be_visible()
            cp.screenshot(path=shots / "06-consent-page.png", full_page=True)
            cp.get_by_role("button", name="أوافق وأشارك موقعي").click()
            expect(cp.get_by_text("تم إرسال موقعك مرة واحدة")).to_be_visible()
            cp.screenshot(path=shots / "07-consent-done.png", full_page=True)
            cust.close()

            page.reload()
            page.get_by_role("button", name="الموقع (1)").click()
            expect(page.get_by_text("مواقع تمت مشاركتها سابقاً")).to_be_visible()
            expect(page.get_by_text("30.044400, 31.235700")).to_be_visible()
            expect(page.locator(".leaflet-container")).to_be_visible()
            page.screenshot(path=shots / "08-historical-location.png", full_page=True)

            with page.expect_download() as d:
                page.get_by_role("link", name="تقرير PDF").click()
            pdf = shots / d.value.suggested_filename
            d.value.save_as(pdf)
            assert pdf.read_bytes().startswith(b"%PDF")
            with page.expect_download() as d:
                page.get_by_role("link", name="Excel").click()
            d.value.save_as(shots / d.value.suggested_filename)

            page.get_by_role("link", name="سجل التدقيق").click()
            expect(page.get_by_text("مشاركة الموقع بموافقة")).to_be_visible()
            page.screenshot(path=shots / "09-audit.png", full_page=True)

            assert not errors, errors
            browser.close()
        print(f"E2E OK – screenshots in {shots}")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
