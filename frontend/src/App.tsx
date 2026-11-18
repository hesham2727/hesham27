import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import Investigation from "./pages/Investigation";
import Login from "./pages/Login";
import NewInvestigation from "./pages/NewInvestigation";
import Settings from "./pages/Settings";

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="center-page"><Spinner /></div>;
  if (!user) return <Login />;
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/new" element={<NewInvestigation />} />
        <Route path="/history" element={<History />} />
        <Route path="/investigations/:id" element={<Navigate to="profile" replace />} />
        <Route path="/investigations/:id/:section" element={<Investigation />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
