# دليل التثبيت — محلل FBOSINT

## 1. المتطلبات

| البند | الحد الأدنى |
|---|---|
| نظام التشغيل | Windows 10 / 11 (64-bit) أو Windows Server 2019+ |
| الذاكرة | 4 GB (يفضل 8 GB) |
| المساحة | 1 GB للبرنامج + مساحة للبيانات والصور |
| الشبكة | اتصال إنترنت للوصول إلى Meta Graph API والروابط العامة |
| حساب Meta | تطبيق Meta Developer مع رمز وصول (انظر القسم 5) |

## 2. التثبيت على Windows (الطريقة الموصى بها)

1. شغّل الملف `FBOSINT-Setup-1.0.0.exe`.
2. اختر لغة المعالج (العربية/English) ثم مجلد التثبيت (الافتراضي `C:\Program Files\FBOSINT`).
3. اترك خيار **إنشاء اختصار على سطح المكتب** مفعلاً.
4. فعّل خيار **السماح عبر جدار الحماية** فقط إذا كان هذا الجهاز سيعمل كخادم في **وضع الشبكة**.
5. بعد التثبيت شغّل **FBOSINT Analyzer** من سطح المكتب.
6. عند أول تشغيل تظهر شاشة **الإعداد الأولي**: أنشئ حساب المدير (كلمة مرور 10 أحرف على الأقل تحتوي حروفاً وأرقاماً).

> البيانات تُحفظ في `%APPDATA%\FBOSINT` (قاعدة البيانات، الصور، النسخ الاحتياطية، مفتاح التشفير).
> إلغاء التثبيت لا يحذف هذه البيانات. التحديث يتم بتشغيل مثبت الإصدار الأحدث فوق الإصدار الحالي مع الحفاظ على البيانات.

### محتويات مجلد التثبيت

| الملف | الوظيفة |
|---|---|
| `FBOSINT.exe` | تطبيق سطح المكتب (يشغّل الخادم المحلي تلقائياً في الوضع المحلي) |
| `FBOSINT-Server.exe` | الخادم + لوحة الويب (للوضع الشبكي أو للتشغيل بدون واجهة) |
| `tools\backup.bat` | نسخ احتياطي فوري |
| `tools\restore.bat` | استعادة نسخة احتياطية |
| `tools\start-network-server.bat` | تشغيل الخادم في وضع الشبكة |
| `tools\create-admin.bat` | إنشاء مستخدم أو إعادة تعيين كلمة مروره |

## 3. الوضع المحلي (Local Mode) — جهاز واحد

* افتح `FBOSINT.exe` — يبدأ الخادم تلقائياً على `127.0.0.1:8765`.
* لوحة الويب متاحة على نفس الجهاز: `http://127.0.0.1:8765` (أو من الإعدادات ← Web dashboard).
* تطبيق سطح المكتب ولوحة الويب يستخدمان نفس قاعدة البيانات، لذلك تظهر التحقيقات فوراً في الاثنين.

## 4. وضع الشبكة (Network Mode) — خادم مركزي

### على الخادم
1. ثبّت البرنامج ونفّذ مرة واحدة (موجه الأوامر داخل مجلد التثبيت):
   ```bat
   FBOSINT-Server.exe gen-cert --ip 192.168.1.10
   ```
   (استبدل العنوان بعنوان IP الخادم). سيُنشأ الشهادة في `%APPDATA%\FBOSINT\tls`.
2. شغّل `tools\start-network-server.bat` (يستخدم الشهادة تلقائياً ويستمع على المنفذ 8765).
3. اسمح بالمنفذ 8765 في جدار الحماية (خيار المثبت أو يدوياً) **للشبكة الخاصة فقط**.
4. لتشغيله كخدمة دائمة استخدم Task Scheduler (عند بدء التشغيل) أو أداة مثل NSSM.

### على الأجهزة الأخرى
* **المتصفح:** افتح `https://192.168.1.10:8765` (أول مرة سيحذر المتصفح من الشهادة الذاتية — ثبّت `server.crt` في "Trusted Root" على الأجهزة المعتمدة).
* **تطبيق سطح المكتب:** الإعدادات ← Mode = Network، Server URL = `https://192.168.1.10:8765`، CA certificate = مسار نسخة من `server.crt`. احفظ وأعد التشغيل.

### قاعدة PostgreSQL (اختياري للفرق الكبيرة)
اضبط المتغير قبل تشغيل الخادم:
```bat
set FBO_DATABASE_URL=postgresql+psycopg://fbosint:PASSWORD@db-host:5432/fbosint
```
(يتطلب نسخة المصدر أو Docker لأن حزمة psycopg غير مضمنة في الملف التنفيذي.)

## 5. إعداد Meta Graph API

1. أنشئ تطبيقاً على https://developers.facebook.com (نوع Business).
2. للصفحات التي تديرها: أنشئ **Page access token** بالصلاحيات `pages_read_engagement` و `pages_show_list`.
3. للصفحات العامة التي لا تديرها: يلزم الحصول على ميزة **Page Public Metadata Access** أو **Page Public Content Access** عبر App Review و Business Verification.
4. لربط حسابك الشخصي (وضع "حسابي المصرح به"): أضف منتج Facebook Login، واضبط Valid OAuth Redirect URI على
   `http://127.0.0.1:8765/api/meta/oauth/callback` (أو عنوان الخادم في وضع الشبكة).
5. في البرنامج: الإعدادات ← بيانات اعتماد Meta ← أدخل App ID و App Secret و Access token ← حفظ ← اختبار الاتصال.

> **قيد مهم:** لا تسمح Meta بقراءة بيانات الملفات الشخصية للأفراد عبر الواجهة الرسمية إلا لمن يربط حسابه بنفسه. البرنامج يسجل ذلك كقيد واضح في التقرير ولا يحاول تجاوزه.

## 6. النسخ الاحتياطي والاستعادة

* **تلقائي:** نسخة كل 24 ساعة في `%APPDATA%\FBOSINT\backups` مع الاحتفاظ بآخر 14 نسخة (قابل للتعديل).
* **يدوي:** `tools\backup.bat` أو الإعدادات ← النسخ الاحتياطية ← نسخ احتياطي الآن.
* **استعادة:** أغلق البرنامج ثم: `tools\restore.bat "C:\...\fbosint-backup-....zip"` — يتم التحقق من سلامة الملف (SHA-256) وتُحفظ نسخة من القاعدة الحالية باسم `.pre-restore`.
* **مهم:** احتفظ بنسخة من الملف `%APPDATA%\FBOSINT\secret.key` في مكان آمن؛ بدونه لا يمكن فك تشفير بيانات اعتماد Meta المخزنة.

## 7. التثبيت من المصدر (للمطورين)

```powershell
git clone <repo> ; cd hesham27
python -m venv .venv ; .\.venv\Scripts\activate
pip install -r backend\requirements.txt -r desktop\requirements.txt pytest pytest-qt
cd frontend ; npm ci ; npm run build ; cd ..
python -m pytest backend\tests desktop\tests -q
python desktop\run_desktop.py            # تطبيق سطح المكتب
python -m fbosint.cli serve              # (من داخل مجلد backend) الخادم فقط
```
بناء الملف التنفيذي والمثبت: `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1` (يتطلب Inno Setup 6).

## 8. Docker (خادم Linux)

```bash
cp .env.example docker/.env      # اضبط FBO_ENCRYPTION_KEY و POSTGRES_PASSWORD
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml exec app python -m fbosint.cli create-admin admin
```

## 9. حل المشكلات

| المشكلة | الحل |
|---|---|
| "Local server could not start: port_in_use" | برنامج آخر يستخدم المنفذ 8765؛ غيّر Local port من الإعدادات |
| "تعذر الاتصال بالخادم" | تحقق من تشغيل الخادم، عنوان URL، وجدار الحماية؛ البرنامج يفتح في الوضع غير المتصل ويعرض التقارير المحفوظة |
| `graph_not_configured` في التحقيق | لم يتم إدخال رمز وصول Meta |
| `graph_not_found` | الهدف ملف شخصي أو صفحة غير متاحة للرمز الحالي — قيد من Meta وليس خطأ |
| `graph_rate_limited` | تم بلوغ حد الطلبات لدى Meta؛ أعد التشغيل لاحقاً |
| تم قفل الحساب | 5 محاولات فاشلة ← قفل 15 دقيقة، أو `tools\create-admin.bat <user>` لإعادة التعيين |
| فحص سلامة التثبيت | `FBOSINT.exe --self-test` (يعيد رمز 0 عند النجاح) |
