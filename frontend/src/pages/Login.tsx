import { useState, type FormEvent } from "react";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Field } from "../components/ui";
import { useI18n } from "../i18n";

export default function Login() {
  const { t, lang, setLang } = useI18n();
  const { login, needsSetup, setup } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (needsSetup) await setup(username, password, fullName);
      else await login(username, password);
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, "generic"));
    } finally {
      setBusy(false);
    }
  };

  const detail = error?.details as { detail?: unknown } | undefined;
  const problems = Array.isArray(detail?.detail) ? (detail!.detail as string[]) : [];

  return (
    <div className="login-wrap">
      <form className="login-card card" onSubmit={submit}>
        <div className="login-head">
          <img src="/favicon.svg" alt="" width={48} height={48} />
          <div>
            <h1>{t("app.name")}</h1>
            <div className="muted small">{t("app.tagline")}</div>
          </div>
          <button type="button" className="btn btn-ghost" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{t("lang.toggle")}</button>
        </div>
        <h2>{needsSetup ? t("auth.setup_title") : t("auth.title")}</h2>
        {needsSetup && (
          <Field label={t("auth.full_name")}>
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={128} />
          </Field>
        )}
        <Field label={t("auth.username")}>
          <input name="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required maxLength={64} />
        </Field>
        <Field label={t("auth.password")} hint={needsSetup ? t("auth.password_hint") : undefined}>
          <input name="password" type="password" autoComplete={needsSetup ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} required maxLength={256} />
        </Field>
        <ErrorBox error={error} />
        {problems.length > 0 && <div className="alert alert-error">{problems.join(", ")}</div>}
        <button className="btn btn-primary btn-block" disabled={busy} type="submit">{needsSetup ? t("auth.create_admin") : t("auth.login")}</button>
        <p className="muted small">{t("auth.legal")}</p>
      </form>
    </div>
  );
}
