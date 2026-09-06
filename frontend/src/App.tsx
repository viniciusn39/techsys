import React from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { AppLayout } from "./layout/AppLayout";
import { ChatIA } from "./pages/ChatIA";
import { Conector } from "./pages/Conector";
import { PainelErp } from "./pages/PainelErp";
import { CatalogoTecnico } from "./pages/CatalogoTecnico";
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
import { PerfisAcesso } from "./pages/PerfisAcesso";
import { Agenda } from "./pages/Agenda";
import { Ajuda } from "./pages/Ajuda";
import { Chamados } from "./pages/Chamados";
import { Servidor } from "./pages/Servidor";
import { SuporteChamados } from "./pages/SuporteChamados";
import { Canvas } from "./pages/Canvas";
import { Cultura } from "./pages/Cultura";
import { PlanosAcao } from "./pages/PlanosAcao";
import { Relatorio } from "./pages/Relatorio";
import { Stakeholders } from "./pages/Stakeholders";
import { Swot } from "./pages/Swot";
import { Tenants } from "./pages/Tenants";
import { Usuarios } from "./pages/Usuarios";

/**
 * Rotas de empresa. O root global só entra nelas depois de abrir uma empresa
 * (header X-Tenant-Id) — sem isso a API não devolve dado nenhum, então mandamos
 * ele para a gestão de empresas em vez de mostrar telas vazias.
 */
/** Uma tela com erro de JavaScript não pode apagar o app inteiro: mostra o erro no lugar dela. */
class PaginaComErro extends React.Component<{ children: React.ReactNode }, { erro: string }> {
  state = { erro: "" };
  static getDerivedStateFromError(e: any) { return { erro: String(e?.message || e) }; }
  render() {
    if (this.state.erro) {
      return (
        <div className="panel p-4">
          <div className="fw-semibold mb-1"><i className="bi bi-bug me-1" />Esta tela encontrou um erro</div>
          <div className="small text-muted-2 mb-3">{this.state.erro}</div>
          <button className="btn btn-sm btn-outline-secondary" onClick={() => this.setState({ erro: "" })}>Tentar de novo</button>
        </div>
      );
    }
    return this.props.children;
  }
}

function TenantRoute({ children }: { children: React.ReactNode }) {
  const { me } = useAuth();
  const location = useLocation();
  if (me?.role === "root" && !me.acting_tenant) {
    return <Navigate to="/root/tenants" replace state={{ from: location.pathname }} />;
  }
  return <PaginaComErro>{children}</PaginaComErro>;
}

/** Rotas exclusivas do root global. */
function RootRoute({ children }: { children: React.ReactNode }) {
  const { me } = useAuth();
  if (me?.role !== "root") return <Navigate to="/" replace />;
  return <PaginaComErro>{children}</PaginaComErro>;
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
        <Route path="/erp/painel" element={<TenantRoute><PainelErp /></TenantRoute>} />
        <Route path="/planos-acao" element={<TenantRoute><PlanosAcao /></TenantRoute>} />
        <Route path="/agenda" element={<TenantRoute><Agenda /></TenantRoute>} />
        <Route path="/chamados" element={<TenantRoute><Chamados /></TenantRoute>} />
        <Route path="/ajuda" element={<TenantRoute><Ajuda /></TenantRoute>} />
        <Route path="/cultura" element={<TenantRoute><Cultura /></TenantRoute>} />
        <Route path="/swot" element={<TenantRoute><Swot /></TenantRoute>} />
        <Route path="/canvas" element={<TenantRoute><Canvas /></TenantRoute>} />
        <Route path="/stakeholders" element={<TenantRoute><Stakeholders /></TenantRoute>} />
        <Route path="/relatorio" element={<TenantRoute><Relatorio /></TenantRoute>} />
        <Route path="/desvios" element={<TenantRoute><Desvios /></TenantRoute>} />
        <Route path="/ia/chat" element={<TenantRoute><ChatIA /></TenantRoute>} />
        <Route path="/admin/usuarios" element={<TenantRoute><Usuarios /></TenantRoute>} />
        <Route path="/admin/organograma" element={<TenantRoute><Organograma /></TenantRoute>} />
        <Route path="/admin/perfis" element={<TenantRoute><PerfisAcesso /></TenantRoute>} />
        <Route path="/admin/conector" element={<TenantRoute><Conector /></TenantRoute>} />
        <Route path="/root/tenants" element={<RootRoute><Tenants /></RootRoute>} />
        <Route path="/root/integracoes" element={<RootRoute><Integracoes /></RootRoute>} />
        <Route path="/root/instalador" element={<RootRoute><Instalador /></RootRoute>} />
        <Route path="/root/catalogo" element={<RootRoute><CatalogoTecnico /></RootRoute>} />
        <Route path="/root/chamados" element={<RootRoute><SuporteChamados /></RootRoute>} />
        <Route path="/root/servidor" element={<RootRoute><Servidor /></RootRoute>} />
        <Route path="*" element={<Navigate to={homeForRole} />} />
      </Route>
    </Routes>
  );
}
