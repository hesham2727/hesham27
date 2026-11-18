import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Investigation } from "../api";
import { useAuth } from "../auth";
import { setCurrent } from "../components/Layout";
import { Badge, Card, ErrorBox, Spinner, useAsync } from "../components/ui";
import { useI18n } from "../i18n";

export default function History() {
  const { t, fmtDate } = useI18n();
  const { user } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const pick = params.get("pick") || "profile";
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [mine, setMine] = useState(false);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState({ q: "", status: "", mine: false, page: 1 });
  const { data, error, loading, reload } = useAsync(() => api<{ total: number; items: Investigation[] }>("/api/investigations", { query: { ...query, page_size: 25 } }), [query]);
  const pages = data ? Math.max(1, Math.ceil(data.total / 25)) : 1;
  const go = (p: number) => { setPage(p); setQuery({ q, status, mine, page: p }); };

  const del = async (inv: Investigation) => {
    if (!window.confirm(`${t("common.confirm_delete")}\n${inv.reference}`)) return;
    await api(`/api/investigations/${inv.id}`, { method: "DELETE" });
    void reload();
  };

  return (
    <div className="stack">
      <h1>{t("history.title")}</h1>
      {params.get("pick") && <div className="alert alert-info">{t("common.select_investigation")}</div>}
      <Card>
        <form className="toolbar" onSubmit={(e) => { e.preventDefault(); go(1); }}>
          <input placeholder={t("history.search")} value={q} onChange={(e) => setQ(e.target.value)} maxLength={200} data-testid="history-search" />
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("common.all")}</option>
            {["completed", "partial", "running", "pending", "failed"].map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
          </select>
          <label className="check"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> {t("history.mine")}</label>
          <button className="btn" type="submit">{t("common.search")}</button>
        </form>
        <ErrorBox error={error} />
        {loading && !data ? <Spinner /> : data && data.items.length === 0 ? <p className="muted">{t("history.empty")}</p> : data && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t("inv.reference")}</th><th>{t("inv.target")}</th><th>{t("inv.object_type")}</th><th>{t("inv.status")}</th><th>{t("inv.created_by")}</th><th>{t("inv.created")}</th><th>{t("common.actions")}</th></tr></thead>
              <tbody>
                {data.items.map((i) => (
                  <tr key={i.id}>
                    <td><Link className="mono" to={`/investigations/${i.id}/${pick}`} onClick={() => setCurrent(i.id)}>{i.reference}</Link></td>
                    <td className="ltr-text">{i.title && i.title !== i.identifier ? <><strong>{i.title}</strong><br /></> : null}{i.target_input}</td>
                    <td>{t(`obj.${i.object_type}`)}</td>
                    <td><Badge prefix="status" value={i.status} /></td>
                    <td>{i.created_by_username}</td>
                    <td>{fmtDate(i.created_at)}</td>
                    <td className="nowrap">
                      <button className="btn btn-small" onClick={() => { setCurrent(i.id); nav(`/investigations/${i.id}/${pick}`); }}>{t("common.open")}</button>{" "}
                      {(user?.role === "admin" || (user?.role === "investigator" && i.created_by_id === user.id)) && (
                        <button className="btn btn-small btn-danger" onClick={() => del(i)}>{t("common.delete")}</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && pages > 1 && (
          <div className="pager">
            <button className="btn btn-small" disabled={page <= 1} onClick={() => go(page - 1)}>{t("common.prev")}</button>
            <span>{t("common.page")} {page} {t("common.of")} {pages}</span>
            <button className="btn btn-small" disabled={page >= pages} onClick={() => go(page + 1)}>{t("common.next")}</button>
          </div>
        )}
      </Card>
    </div>
  );
}
