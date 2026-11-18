import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import ar from "../../shared/i18n/ar.json";
import en from "../../shared/i18n/en.json";

export type Lang = "ar" | "en";
export const DICTS: Record<Lang, Record<string, string>> = { ar, en };

interface I18n { lang: Lang; dir: "rtl" | "ltr"; t: (key: string) => string; setLang: (l: Lang) => void; fmtDate: (iso: string | null | undefined, withTime?: boolean) => string }
const Ctx = createContext<I18n | null>(null);

function initialLang(): Lang {
  try {
    const v = localStorage.getItem("fbo_lang");
    if (v === "ar" || v === "en") return v;
  } catch {
    /* storage unavailable */
  }
  return "ar"; // Arabic is the default language
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const dir = lang === "ar" ? "rtl" : "ltr";
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("fbo_lang", l);
    } catch {
      /* ignore */
    }
  }, []);
  const t = useCallback((key: string) => DICTS[lang][key] ?? DICTS.en[key] ?? key, [lang]);
  const fmtDate = useCallback(
    (iso: string | null | undefined, withTime = true) => {
      if (!iso) return "—";
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return "—";
      return new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" }).format(d);
    },
    [lang],
  );
  const value = useMemo(() => ({ lang, dir, t, setLang, fmtDate }), [lang, dir, t, setLang, fmtDate]) as I18n;
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const v = useContext(Ctx);
  if (!v) throw new Error("I18nProvider missing");
  return v;
}

/** Human label for an enum value with a translation prefix, falling back to the raw value. */
export function useEnumLabel() {
  const { t } = useI18n();
  return (prefix: string, value: string) => {
    const k = `${prefix}.${value}`;
    const r = t(k);
    return r === k ? value : r;
  };
}
