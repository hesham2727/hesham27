import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api, type User } from "./api";
import { AuthContext } from "./auth";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Setup from "./pages/Setup";
import Dashboard from "./pages/Dashboard";
import NumberCheckPage from "./pages/NumberCheck";
import Investigations from "./pages/Investigations";
import InvestigationDetail from "./pages/InvestigationDetail";
import Customers from "./pages/Customers";
import CustomerDetail from "./pages/CustomerDetail";
import DataSources from "./pages/DataSources";
import AuditLog from "./pages/AuditLog";
import SettingsPage from "./pages/Settings";
import Users from "./pages/Users";
import Account from "./pages/Account";

interface Status {
  setup_required: boolean;
  version: string;
  mode: string;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const s = await api<Status>("/api/system/status");
        setStatus(s);
        if (!s.setup_required) {
          try {
            setUser(await api<User>("/api/auth/me"));
          } catch {
            setUser(null);
          }
        }
      } finally {
        setLoading(false);
      }
    })();
    const onUnauthorized = () => setUser(null);
    window.addEventListener("tahqiq:unauthorized", onUnauthorized);
    return () => window.removeEventListener("tahqiq:unauthorized", onUnauthorized);
  }, []);

  if (loading) return <div className="p-10 text-center text-slate-500">جارٍ التحميل…</div>;
  if (!status) return <div className="p-10 text-center text-red-700">تعذر الاتصال بالخادم المحلي.</div>;

  if (status.setup_required && !user) {
    return (
      <AuthContext.Provider value={{ user, setUser }}>
        <Setup onDone={(u) => { setStatus({ ...status, setup_required: false }); setUser(u); }} />
      </AuthContext.Provider>
    );
  }
  if (!user) {
    return (
      <AuthContext.Provider value={{ user, setUser }}>
        <Login />
      </AuthContext.Provider>
    );
  }

  const admin = user.role === "admin";
  return (
    <AuthContext.Provider value={{ user, setUser }}>
      <Layout version={status.version} mode={status.mode}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/check" element={<NumberCheckPage />} />
          <Route path="/investigations" element={<Investigations />} />
          <Route path="/investigations/:id" element={<InvestigationDetail />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/customers/:id" element={<CustomerDetail />} />
          <Route path="/sources" element={<DataSources />} />
          <Route path="/account" element={<Account />} />
          {admin && <Route path="/audit" element={<AuditLog />} />}
          {admin && <Route path="/settings" element={<SettingsPage />} />}
          {admin && <Route path="/users" element={<Users />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </AuthContext.Provider>
  );
}
