import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth.jsx";
import { EditionProvider, moduleAllowed, useEdition } from "./edition.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Documents from "./pages/Documents.jsx";
import Cases from "./pages/Cases.jsx";
import Nomenclature from "./pages/Nomenclature.jsx";
import Lifecycle from "./pages/Lifecycle.jsx";
import Issues from "./pages/Issues.jsx";
import Upload from "./pages/Upload.jsx";
import Scanning from "./pages/Scanning.jsx";
import Search from "./pages/Search.jsx";
import Reports from "./pages/Reports.jsx";
import Enterprise from "./pages/Enterprise.jsx";
import Security from "./pages/Security.jsx";
import Account from "./pages/Account.jsx";
import Support from "./pages/Support.jsx";
import Help from "./pages/Help.jsx";
import ArchiveRequests from "./pages/ArchiveRequests.jsx";
import Inventories from "./pages/Inventories.jsx";
import Nto from "./pages/Nto.jsx";
import Imports from "./pages/Imports.jsx";
import Quality from "./pages/Quality.jsx";
import Admin from "./pages/Admin.jsx";

// Раздел недоступен по прямой ссылке, если он не входит в редакцию или закрыт
// для роли: иначе скрытый из меню модуль открывался бы из закладки. Права это
// не заменяет — их проверяет сервер.
function ModuleRoute({ module, children }) {
  const edition = useEdition();
  const { user } = useAuth();
  return edition.has(module) && moduleAllowed(module, user?.role)
    ? children
    : <Navigate to="/" replace />;
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center muted">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

const PAGES = [
  ["documents", "documents", <Documents />],
  ["cases", "cases", <Cases />],
  ["nomenclature", "nomenclature", <Nomenclature />],
  ["lifecycle", "lifecycle", <Lifecycle />],
  ["issues", "issues", <Issues />],
  ["search", "search", <Search />],
  ["scanning", "scanning", <Scanning />],
  ["upload", "upload", <Upload />],
  ["reports", "reports", <Reports />],
  ["enterprise", "enterprise", <Enterprise />],
  ["account", "account", <Account />],
  ["support", "support", <Support />],
  ["help", "help", <Help />],
  ["archive-requests", "archive_requests", <ArchiveRequests />],
  ["inventories", "inventories", <Inventories />],
  ["nto", "nto", <Nto />],
  ["quality", "quality", <Quality />],
  ["imports", "imports", <Imports />],
  ["admin", "admin", <Admin />],
  ["security", "security", <Security />],
];

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
        {PAGES.map(([path, module, element]) => (
          <Route
            key={path}
            path={path}
            element={<ModuleRoute module={module}>{element}</ModuleRoute>}
          />
        ))}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <EditionProvider>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </EditionProvider>
  );
}
