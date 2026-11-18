import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type Investigation } from "../api";
import { useAuth } from "../auth";
import { setCurrent } from "../components/Layout";
import { Card, ErrorBox, Field } from "../components/ui";
import { useI18n } from "../i18n";

const TYPES = ["auto", "profile_url", "page_url", "username", "numeric_id", "authorized_account"];
const OPTS = ["collect_posts", "collect_photos", "collect_comments", "download_media", "follow_official_website"] as const;

export default function NewInvestigation() {
  const { t } = useI18n();
  const { user } = useAuth();
  const nav = useNavigate();
  const [target, setTarget] = useState("");
  const [targetType, setTargetType] = useState("auto");
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [legal, setLegal] = useState("");
  const [notes, setNotes] = useState("");
  const [urls, setUrls] = useState("");
  const [opts, setOpts] = useState<Record<string, boolean>>({ collect_posts: true, collect_photos: true, collect_comments: false, download_media: true, follow_official_website: true });
  const [maxPosts, setMaxPosts] = useState(100);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  if (user?.role === "viewer") return <div className="alert alert-error">{t("err.insufficient_role")}</div>;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const inv = await api<Investigation>("/api/investigations", {
        method: "POST",
        body: {
          target: targetType === "authorized_account" ? "me" : target, target_type: targetType, title, purpose, legal_basis: legal, notes,
          extra_urls: urls.split(/\s+/).map((u) => u.trim()).filter(Boolean), options: { ...opts, max_posts: maxPosts },
        },
      });
      setCurrent(inv.id);
      nav(`/investigations/${inv.id}/profile`);
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, "generic"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="stack" onSubmit={submit}>
      <h1>{t("new.title")}</h1>
      <div className="alert alert-info">{t("new.policy")}</div>
      <Card>
        <div className="grid-2">
          <Field label={t("new.target")}>
            <input name="target" dir="ltr" value={targetType === "authorized_account" ? "me" : target} disabled={targetType === "authorized_account"} onChange={(e) => setTarget(e.target.value)} placeholder={t("new.target_placeholder")} required maxLength={500} />
          </Field>
          <Field label={t("new.target_type")}>
            <select name="target_type" value={targetType} onChange={(e) => setTargetType(e.target.value)}>
              {TYPES.map((x) => <option key={x} value={x}>{t(`new.type.${x}`)}</option>)}
            </select>
          </Field>
          <Field label={t("new.title_field")}>
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
          </Field>
          <Field label={t("new.legal_basis")}>
            <input value={legal} onChange={(e) => setLegal(e.target.value)} maxLength={200} />
          </Field>
        </div>
        <Field label={t("new.purpose")} hint={t("new.purpose_hint")}>
          <textarea name="purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)} required minLength={5} maxLength={2000} rows={2} />
        </Field>
        <Field label={t("new.extra_urls")} hint={t("new.extra_urls_hint")}>
          <textarea name="extra_urls" dir="ltr" value={urls} onChange={(e) => setUrls(e.target.value)} rows={3} placeholder="https://example.com/contact" />
        </Field>
        <Field label={t("new.notes")}>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={5000} rows={2} />
        </Field>
      </Card>
      <Card title={t("new.options")}>
        <div className="checks">
          {OPTS.map((o) => (
            <label key={o} className="check">
              <input type="checkbox" checked={opts[o]} onChange={(e) => setOpts({ ...opts, [o]: e.target.checked })} /> {t(`new.opt.${o}`)}
            </label>
          ))}
          <label className="check">
            {t("new.opt.max_posts")} <input type="number" min={0} max={1000} value={maxPosts} onChange={(e) => setMaxPosts(Number(e.target.value))} style={{ width: 90 }} />
          </label>
        </div>
      </Card>
      <ErrorBox error={error} />
      <div><button className="btn btn-primary" type="submit" disabled={busy} data-testid="start">{t("new.start")}</button></div>
    </form>
  );
}
