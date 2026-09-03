import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { AppLayout } from "./layout/AppLayout";
import { ChatIA } from "./pages/ChatIA";
import { Conector } from "./pages/Conector";
import { Dashboard } from "./pages/Dashboard";
import { Desvios } from "./pages/Desvios";
import { IndicadorDetalhe } from "./pages/IndicadorDetalhe";
import { Indicadores } from "./pages/Indicadores";
import { Instalador } from "./pages/Instalador";
import { Integracoes } from "./pages/Integracoes";
import { Login } from "./pages/Login";
import { MapaEstrategico } from "./pages/MapaEstrategico";
import { Metas } from "./pages/Metas";
import { Organograma } from "./pages/Organograma";
import { PlanosAcao } from "./pages/PlanosAcao";
import { Tenants } from "./pages/Tenants";
import { Usuarios } from "./pages/Usuarios";

/**
 * Rotas de empresa. O root global só entra nelas depois de abrir uma empresa
 * (header X-Tenant-Id) — sem isso a API não devolve dado nenhum, então mandamos
 * ele para a gestão de empresas em vez de mostrar telas vazias.
 */
function TenantRoute({ children }: { children: React.ReactNode }) {
  const { me } = useAuth();
  const location = useLocation();
  if (me?.role === "root" && !me.acting_tenant) {
    return <Navigate to="/root/tenants" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

/** Rotas exclusivas do root global. */
function RootRoute({ children }: { children: React.ReactNode }) {
  const { me } = useAuth();
  if (me?.role !== "root") return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  const { me, loading } = useAuth();

  if (loading) {
    return (
      <div className="d-flex justify-content-center align-items-center vh-100">
        <div className="spinner-border text-primary" />
      </div>
    );
  }

  const homeForRole = me?.role === "root" && !me.acting_tenant ? "/root/tenants" : "/";

  return (
    <Routes>
      <Route path="/login" element={me ? <Navigate to={homeForRole} /> : <Login />} />
      <Route element={me ? <AppLayout /> : <Navigate to="/login" />}>
        <Route path="/" element={<TenantRoute><Dashboard /></TenantRoute>} />
        <Route path="/mapa-estrategico" element={<TenantRoute><MapaEstrategico /></TenantRoute>} />
        <Route path="/metas" element={<TenantRoute><Metas /></TenantRoute>} />
        <Route path="/indicadores" element={<TenantRoute><Indicadores /></TenantRoute>} />
        <Route path="/indicadores/:id" element={<TenantRoute><IndicadorDetalhe /></TenantRoute>} />
        <Route path="/planos-acao" element={<TenantRoute><PlanosAcao /></TenantRoute>} />
        <Route path="/desvios" element={<TenantRoute><Desvios /></TenantRoute>} />
        <Route path="/ia/chat" element={<TenantRoute><ChatIA /></TenantRoute>} />
        <Route path="/admin/usuarios" element={<TenantRoute><Usuarios /></TenantRoute>} />
        <Route path="/admin/organograma" element={<TenantRoute><Organograma /></TenantRoute>} />
        <Route path="/admin/conector" element={<TenantRoute><Conector /></TenantRoute>} />
        <Route path="/root/tenants" element={<RootRoute><Tenants /></RootRoute>} />
        <Route path="/root/integracoes" element={<RootRoute><Integracoes /></RootRoute>} />
        <Route path="/root/instalador" element={<RootRoute><Instalador /></RootRoute>} />
        <Route path="*" element={<Navigate to={homeForRole} />} />
      </Route>
    </Routes>
  );
}
