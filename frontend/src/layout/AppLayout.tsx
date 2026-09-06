import { useEffect, useState } from "react";
import { Dropdown } from "react-bootstrap";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { Tenant } from "../types";

interface MenuItem {
  to: string;
  icon: string;
  label: string;
  title: string;
  sub?: string;
  roles: string[];
  /** Chave do módulo no perfil de acesso (RBAC por setor). Sem chave = sempre visível ao papel. */
  module?: string;
}

/** Itens que só fazem sentido dentro de uma empresa. */
const TENANT_SECTIONS: { label: string; items: MenuItem[] }[] = [
  {
    label: "Desempenho",
    items: [
      { to: "/", module: "dashboard", icon: "bi-grid-1x2", label: "Dashboard", title: "Dashboard", sub: "Visão executiva dos resultados", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/mapa-estrategico", module: "mapa", icon: "bi-diagram-3", label: "Mapa Estratégico", title: "Mapa Estratégico", sub: "Objetivos por perspectiva BSC", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/metas", module: "metas", icon: "bi-bullseye", label: "Metas", title: "Desdobramento de Metas", sub: "Empresa → Área → Time → Pessoa", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/indicadores", module: "indicadores", icon: "bi-graph-up-arrow", label: "Indicadores", title: "Indicadores", sub: "KPIs, metas e farol", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/erp/painel", module: "painel_erp", icon: "bi-bar-chart-line", label: "Painel do ERP", title: "Painel do ERP", sub: "Dados do ERP e conferência dos indicadores", roles: ["root", "admin", "gestor"] },
    ],
  },
  {
    label: "Planejamento",
    items: [
      { to: "/cultura", module: "cultura", icon: "bi-gem", label: "Cultura e identidade", title: "Cultura e identidade", sub: "Propósito, missão, visão e valores", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/swot", module: "swot", icon: "bi-grid-3x3-gap", label: "Análise SWOT", title: "Análise SWOT", sub: "Forças, fraquezas, oportunidades e ameaças", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/canvas", module: "canvas", icon: "bi-columns-gap", label: "Canvas", title: "Business Model Canvas", sub: "Como a empresa cria, entrega e captura valor", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/stakeholders", module: "stakeholders", icon: "bi-people-fill", label: "Stakeholders", title: "Stakeholders", sub: "Partes interessadas e matriz influência × interesse", roles: ["root", "admin", "gestor"] },
      { to: "/relatorio", module: "relatorio", icon: "bi-file-earmark-text", label: "Relatório", title: "Relatório do planejamento", sub: "Identidade, SWOT, canvas, mapa, indicadores e metas para imprimir", roles: ["root", "admin", "gestor", "colaborador"] },
    ],
  },
  {
    label: "Execução",
    items: [
      { to: "/planos-acao", module: "planos", icon: "bi-kanban", label: "Planos de Ação", title: "Planos de Ação", sub: "5W2H, PDCA e Kanban", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/agenda", module: "agenda", icon: "bi-calendar3", label: "Agenda de gestão", title: "Agenda de gestão", sub: "Reuniões de resultados, pauta, ata e decisões", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/desvios", module: "desvios", icon: "bi-exclamation-triangle", label: "Desvios", title: "Tratamento de Desvios", sub: "Faróis vermelhos e causa raiz", roles: ["root", "admin", "gestor", "colaborador"] },
      { to: "/ia/chat", module: "ia", icon: "bi-stars", label: "Assistente IA", title: "Assistente de Resultados", sub: "Converse sobre os seus indicadores", roles: ["root", "admin", "gestor", "colaborador"] },
    ],
  },
  {
    label: "Administração da empresa",
    items: [
      { to: "/admin/usuarios", module: "usuarios", icon: "bi-people", label: "Usuários", title: "Usuários", sub: "Acessos e papéis", roles: ["root", "admin"] },
      { to: "/admin/organograma", module: "organograma", icon: "bi-diagram-2", label: "Organograma", title: "Organograma", sub: "Estrutura da empresa", roles: ["root", "admin"] },
      { to: "/admin/conector", module: "conector", icon: "bi-robot", label: "Conector ERP", title: "Conector ERP", sub: "Agente de coleta e sincronização dos dados", roles: ["root", "admin"] },
      { to: "/admin/perfis", module: "usuarios", icon: "bi-shield-lock", label: "Perfis de acesso", title: "Perfis de acesso", sub: "O que cada setor enxerga: indicadores e módulos", roles: ["root", "admin"] },
    ],
  },
];

/** Itens do root global — administram o SaaS, não uma empresa. */
const ROOT_SECTION: { label: string; items: MenuItem[] } = {
  label: "Administração do sistema",
  items: [
    { to: "/root/tenants", icon: "bi-buildings", label: "Empresas", title: "Empresas", sub: "Gestão de tenants", roles: ["root"] },
    { to: "/root/instalador", icon: "bi-robot", label: "Instalador do agente", title: "Instalador do agente", sub: "Escolha o cliente, pegue a chave e o script pronto", roles: ["root"] },
    { to: "/root/integracoes", icon: "bi-plug", label: "Integrações", title: "Integrações", sub: "Provedor de IA e fontes de dados", roles: ["root"] },
    { to: "/root/catalogo", icon: "bi-braces-asterisk", label: "Catálogo técnico", title: "Catálogo técnico de KPIs", sub: "Regra, SQL executado no ERP e fórmula de cada indicador", roles: ["root"] },
  ],
};

const ALL_ITEMS = [...TENANT_SECTIONS.flatMap((s) => s.items), ...ROOT_SECTION.items];

export function AppLayout() {
  const { me, logout, actAsTenant } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [tenants, setTenants] = useState<Tenant[]>([]);

  const isRoot = me?.role === "root";
  const activeTenant = me?.acting_tenant ?? (isRoot ? null : me?.tenant ?? null);

  useEffect(() => {
    if (isRoot) {
      api.get("/api/tenants/").then((d) => setTenants(d.results ?? d)).catch(() => {});
    }
  }, [isRoot]);

  if (!me) return null;

  // Dois contextos que não se misturam: root SEM empresa aberta administra o
  // sistema (Empresas, Instalador, Integrações); com uma empresa aberta, vê só
  // o que a empresa vê — o bloco do sistema some até ele "sair da empresa".
  const sections = activeTenant ? TENANT_SECTIONS : isRoot ? [ROOT_SECTION] : TENANT_SECTIONS;

  const current =
    ALL_ITEMS.find((i) => i.to !== "/" && location.pathname.startsWith(i.to)) ||
    ALL_ITEMS.find((i) => i.to === location.pathname);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark"><i className="bi bi-compass" /></span>
          <span>TechSys Gestão</span>
        </div>

        {isRoot ? (
          <div className="px-3 pb-2">
            <div className="sidebar-tenant mx-0 mb-2">
              <div className="label">
                <i className="bi bi-key-fill me-1" />Acesso root
              </div>
              <div className="value">
                {activeTenant ? `Atuando em ${activeTenant.name}` : "Nenhuma empresa aberta"}
              </div>
            </div>
            <select
              className="form-select form-select-sm"
              value={activeTenant?.id ?? ""}
              onChange={async (e) => {
                await actAsTenant(e.target.value ? Number(e.target.value) : null);
                navigate(e.target.value ? "/" : "/root/tenants");
              }}
            >
              <option value="">— administrar o sistema —</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>Abrir {t.name}</option>
              ))}
            </select>
          </div>
        ) : (
          activeTenant && (
            <div className="sidebar-tenant">
              <div className="label">Empresa</div>
              <div className="value">{activeTenant.name}</div>
            </div>
          )
        )}

        <nav className="sidebar-nav">
          {sections.map((section) => {
            const items = section.items.filter((i) => i.roles.includes(me.role) && (!i.module || !me.modules || me.modules.includes(i.module)));
            if (items.length === 0) return null;
            return (
              <div key={section.label}>
                <div className="sidebar-section">{section.label}</div>
                {items.map((m) => (
                  <NavLink key={m.to} to={m.to} end={m.to === "/"} className="sidebar-link">
                    <i className={`bi ${m.icon}`} aria-hidden="true" />
                    <span>{m.label}</span>
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="fw-semibold text-truncate" style={{ color: "#fff" }}>{me.first_name}</div>
          <div className="text-truncate" style={{ opacity: 0.6, fontSize: "0.72rem" }}>{me.email}</div>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div className="flex-grow-1 min-w-0">
            <h1 className="topbar-title">{current?.title ?? "TechSys Gestão"}</h1>
            {current?.sub && <div className="topbar-sub">{current.sub}</div>}
          </div>

          <Dropdown align="end">
            <Dropdown.Toggle
              variant="link"
              className="p-0 text-decoration-none border-0"
              style={{ color: "var(--ink)" }}
            >
              <span className="d-inline-flex align-items-center gap-2">
                <span
                  className="rounded-circle"
                  style={{
                    width: 32, height: 32, background: "var(--brand-soft)",
                    color: "var(--brand)", display: "grid", placeItems: "center", fontWeight: 600,
                  }}
                >
                  {me.first_name?.[0]?.toUpperCase() ?? "?"}
                </span>
                <span className="d-none d-md-inline small fw-semibold">{me.first_name}</span>
              </span>
            </Dropdown.Toggle>
            <Dropdown.Menu>
              <Dropdown.Header className="small">
                {me.email}
                <div className="text-muted-2 text-capitalize">
                  {isRoot ? "Administrador do sistema" : me.role}
                </div>
              </Dropdown.Header>
              <Dropdown.Divider />
              <Dropdown.Item
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
              >
                <i className="bi bi-box-arrow-right me-2" />Sair
              </Dropdown.Item>
            </Dropdown.Menu>
          </Dropdown>
        </header>

        {/* Root atuando dentro de uma empresa: deixa o contexto explícito. */}
        {isRoot && activeTenant && (
          <div className="impersonation-bar">
            <i className="bi bi-eye" />
            Você está vendo os dados de <strong>{activeTenant.name}</strong> como administrador do sistema.
            <button
              className="btn btn-sm btn-link p-0 ms-auto"
              onClick={async () => {
                await actAsTenant(null);
                navigate("/root/tenants");
              }}
            >
              Sair da empresa
            </button>
          </div>
        )}

        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
