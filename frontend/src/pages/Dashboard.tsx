import { Link } from "react-router-dom";
import { api, type Investigation } from "../api";
import { Badge, BarChart, Card, ErrorBox, Spinner, Stat, useAsync } from "../components/ui";
import { useI18n } from "../i18n";

interface Dash { totals: Record<string, number>; by_status: Record<string, number>; last_30_days: { date: string; count: number }[]; recent: Investigation[] }

export default function Dashboard() {
  const { t, fmtDate } = useI18n();
  const { data, error, loading } = useAsync(() => api<Dash>("/api/dashboard"), []);
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const tot = data.totals;
  return (
    <div className="stack">
      <h1>{t("dash.title")}</h1>
      <div className="stats-grid">
        <Stat label={t("dash.investigations")} value={tot.investigations} />
        <Stat label={t("dash.data_points")} value={tot.data_points} />
        <Stat label={t("dash.contacts")} value={tot.contacts} />
        <Stat label={t("dash.posts")} value={tot.posts} />
        <Stat label={t("dash.media")} value={tot.media} />
        <Stat label={t("dash.sources")} value={tot.sources} />
      </div>
      <div className="grid-2">
        <Card title={t("dash.last30")}>
          <BarChart data={data.last_30_days} labelKey="date" valueKey="count" />
        </Card>
        <Card title={t("dash.by_status")}>
          <ul className="status-list">
            {["completed", "partial", "running", "pending", "failed"].map((s) => (
              <li key={s}><Badge prefix="status" value={s} /> <strong>{data.by_status[s] ?? 0}</strong></li>
            ))}
          </ul>
        </Card>
      </div>
      <Card title={t("dash.recent")} actions={<Link className="btn btn-primary" to="/new">{t("nav.new")}</Link>}>
        {data.recent.length === 0 ? <p className="muted">{t("dash.empty")}</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t("inv.reference")}</th><th>{t("inv.target")}</th><th>{t("inv.status")}</th><th>{t("inv.created")}</th></tr></thead>
              <tbody>
                {data.recent.map((i) => (
                  <tr key={i.id}>
                    <td><Link to={`/investigations/${i.id}/profile`} className="mono">{i.reference}</Link></td>
                    <td className="ltr-text">{i.title || i.target_input}</td>
                    <td><Badge prefix="status" value={i.status} /></td>
                    <td>{fmtDate(i.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
