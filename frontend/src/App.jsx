import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Documents from "./pages/Documents.jsx";
import Cases from "./pages/Cases.jsx";
import Nomenclature from "./pages/Nomenclature.jsx";
import Lifecycle from "./pages/Lifecycle.jsx";
import Issues from "./pages/Issues.jsx";
import Upload from "./pages/Upload.jsx";
import Search from "./pages/Search.jsx";
import Reports from "./pages/Reports.jsx";
import Enterprise from "./pages/Enterprise.jsx";
import Security from "./pages/Security.jsx";
import Account from "./pages/Account.jsx";
import Help from "./pages/Help.jsx";

// Раздел «Безопасность» — только для администратора: там учётные записи,
// сессии и аудиторский след.
function AdminOnly({ children }) {
  const { user } = useAuth();
  return user?.role === "admin" ? children : <Navigate to="/" replace />;
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center muted">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function Shell() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="documents" element={<Documents />} />
        <Route path="cases" element={<Cases />} />
        <Route path="nomenclature" element={<Nomenclature />} />
        <Route path="lifecycle" element={<Lifecycle />} />
        <Route path="issues" element={<Issues />} />
        <Route path="search" element={<Search />} />
        <Route path="upload" element={<Upload />} />
        <Route path="reports" element={<Reports />} />
        <Route path="enterprise" element={<Enterprise />} />
        <Route path="account" element={<Account />} />
        <Route path="help" element={<Help />} />
        <Route path="security" element={<AdminOnly><Security /></AdminOnly>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
