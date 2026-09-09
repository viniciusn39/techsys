import { useState } from "react";
import { Link } from "react-router-dom";
import { Panel } from "../components/ui";

interface Topico { key: string; icon: string; title: string; to?: string; resumo: string; passos: string[]; dicas?: string[] }

const TOPICOS: Topico[] = [
  { key: "inicio", icon: "bi-rocket-takeoff", title: "Por onde começar", resumo: "A ordem que funciona: identidade → diagnóstico → mapa → indicadores → metas → rituais.", passos: [
    "Cultura e identidade: escreva propósito, missão, visão e valores.",
    "Análise SWOT e Canvas: o diagnóstico de onde a empresa está.",
    "Mapa estratégico: objetivos por perspectiva, ligados por causa e efeito.",
    "Indicadores: plugue os KPIs do catálogo do ERP e crie os manuais.",
    "Metas: desdobre a meta da empresa por área, time e pessoa.",
    "Agenda de gestão: marque a reunião mensal de resultados e o acompanhamento semanal dos planos.",
  ] },
  { key: "dashboard", icon: "bi-grid-1x2", title: "Dashboard", to: "/", resumo: "Visão executiva do mês: quantos indicadores atingiram a meta, ranking por atingimento, evolução e mapa de calor.", passos: [
    "Escolha o mês e a área nos filtros do topo.",
    "O ranking mostra o % da meta de cada indicador; a linha marca 100 %.",
    "Clique em 'Tratar desvios' para ver os faróis vermelhos sem plano.",
  ], dicas: ["No mês em curso a meta dos indicadores de soma é proporcional aos dias já medidos no ERP."] },
  { key: "mapa", icon: "bi-diagram-3", title: "Mapa estratégico (BSC)", to: "/mapa-estrategico", resumo: "Objetivos nas perspectivas Financeira, Clientes, Processos e Aprendizado, com setas de causa e efeito.", passos: [
    "Crie objetivos em cada faixa e arraste para posicionar.",
    "Use 'Ligar objetivos' para desenhar a relação de causa e efeito.",
    "Cada objetivo mostra os faróis dos indicadores ligados a ele.",
  ] },
  { key: "indicadores", icon: "bi-graph-up-arrow", title: "Indicadores e catálogo do ERP", to: "/indicadores", resumo: "KPIs com meta e farol. Os do ERP são calculados pelo agente a cada 30 minutos; os manuais você lança mês a mês.", passos: [
    "Clique em 'Catálogo do ERP' e plugue os KPIs com um clique. Cada um traz como é calculado e por que importa.",
    "Na página do indicador veja a ficha, o gráfico meta × realizado, a quebra por período (dia, semana, mês) e por filial.",
    "Metas: cadastre por mês ou deixe que venham do ERP quando o KPI tiver meta no WinThor.",
  ], dicas: ["Farol: verde ≥ 100 % da meta, amarelo ≥ 90 %, vermelho abaixo. 'Menor é melhor' inverte a conta.", "Indicadores do ERP não aceitam lançamento manual: o valor vem do espelho do ERP."] },
  { key: "metas", icon: "bi-bullseye", title: "Desdobramento de metas", to: "/metas", resumo: "Da meta da empresa para área, time e pessoa, cada uma ligada a um indicador.", passos: ["Crie a meta da empresa e desdobre em metas filhas.", "Vincule cada meta a um indicador para herdar o farol."] },
  { key: "planos", icon: "bi-kanban", title: "Projetos (5W2H) e Kanban", to: "/planos-acao", resumo: "Projeto 5W2H com etapas PDCA e atividades no Kanban (a fazer, fazendo, bloqueado, feito).", passos: [
    "Crie o plano (o quê, por quê, onde, quem, quando, como, quanto) ou gere um a partir de um desvio.",
    "Adicione atividades com responsável, prazo e prioridade; arraste entre as colunas.",
    "Use a aba Análise para ver atrasadas, lead time e vazão semanal.",
  ] },
  { key: "desvios", icon: "bi-exclamation-triangle", title: "Desvios", to: "/desvios", resumo: "Todo farol vermelho vira um desvio. Registre a causa raiz e crie o plano de ação já preenchido.", passos: ["Abra o desvio, escreva a causa raiz e clique em 'Criar plano'.", "Concluir o plano fecha o desvio."] },
  { key: "erp", icon: "bi-bar-chart-line", title: "Painel do ERP e conector", to: "/erp/painel", resumo: "Mini BI com o que já veio do ERP: faturamento por dia, por filial, rankings e conferência dos indicadores.", passos: [
    "O painel é atualizado a cada 30 minutos; use 'Recalcular' para forçar.",
    "Em Conector ERP (admin) acompanhe a carga de cada tabela, o ritmo e os comandos do agente.",
  ] },
  { key: "agenda", icon: "bi-calendar3", title: "Agenda de gestão", to: "/agenda", resumo: "Reuniões de resultados, planejamento e acompanhamento, com pauta, ata, decisões, participantes e indicadores revisados.", passos: ["Clique num dia e em 'Nova reunião'.", "Depois da reunião, registre ata e decisões; decisões que viram ação vão para Planos de Ação."] },
  { key: "identidade", icon: "bi-gem", title: "Cultura, SWOT, Canvas e stakeholders", to: "/swot", resumo: "As ferramentas de planejamento: identidade, diagnóstico interno e externo, modelo de negócio e partes interessadas.", passos: [
    "SWOT: liste forças, fraquezas, oportunidades e ameaças com impacto de 1 a 5 e ligue ao objetivo; a matriz cruzada guarda as estratégias.",
    "Canvas: um post-it por item em cada um dos nove blocos.",
    "Stakeholders: influência e interesse definem a estratégia de relacionamento.",
    "Relatório: tudo isso num documento para imprimir ou salvar em PDF.",
  ] },
  { key: "acesso", icon: "bi-shield-lock", title: "Usuários e perfis de acesso", to: "/admin/usuarios", resumo: "Papéis (admin, gestor, colaborador) e perfis por setor que limitam os indicadores e módulos que cada um vê.", passos: [
    "Crie o usuário com papel e unidade.",
    "Escolha o perfil de acesso (Comercial, Financeiro, Logística, Suprimentos, Pessoas ou Diretoria). Admin vê tudo.",
    "Ajuste ou crie perfis em Perfis de acesso.",
  ] },
  { key: "ia", icon: "bi-stars", title: "Assistente de IA", to: "/ia/chat", resumo: "Converse sobre os seus números e gere análises de indicador e de desvio com causa raiz e contramedidas.", passos: ["Na página do indicador, clique em 'Analisar com IA'.", "No chat, pergunte em linguagem natural sobre os resultados da empresa."] },
];

const FAQ: [string, string][] = [
  ["Por que um indicador do ERP não tem valor?", "Ou a tabela ainda não foi carregada pelo agente (veja Conector ERP), ou o mês ainda não está coberto por completo. A ficha do indicador mostra a última carga e a cobertura."],
  ["O farol ficou vermelho no começo do mês.", "Indicadores de soma comparam com a meta proporcional aos dias já medidos; indicadores de média e saldo comparam com a meta cheia. Confira a regra na ficha do indicador."],
  ["Como mudo a meta de um indicador do ERP?", "Se a meta vem do WinThor, ela é bloqueada aqui e muda lá. Se é manual, edite na aba Metas do ano."],
  ["Quem vê o quê?", "Admin vê tudo. Gestor e colaborador veem os indicadores dos setores do seu perfil de acesso e os módulos liberados; colaborador só lança valores e vê seus planos."],
  ["Preciso de ajuda de uma pessoa.", "Abra um chamado em Chamados: suporte técnico, dúvida, erro, dados do ERP ou consultoria de gestão. A equipe responde por lá."],
];

/** Central de ajuda: como usar cada módulo, perguntas frequentes e atalho para abrir chamado. */
export function Ajuda() {
  const [aberto, setAberto] = useState<string>("inicio");
  const [busca, setBusca] = useState("");
  const q = busca.trim().toLowerCase();
  const topicos = TOPICOS.filter((t) => !q || `${t.title} ${t.resumo} ${t.passos.join(" ")} ${(t.dicas ?? []).join(" ")}`.toLowerCase().includes(q));
  const faq = FAQ.filter(([p, r]) => !q || `${p} ${r}`.toLowerCase().includes(q));

  return (
    <div className="row g-3">
      <div className="col-xl-8 d-grid gap-3 align-content-start">
        <Panel
          title="Central de ajuda"
          subtitle="Como usar cada parte do sistema. Se não achar a resposta, abra um chamado."
          actions={<input className="form-control form-control-sm" style={{ width: 240 }} placeholder="Buscar na ajuda…" value={busca} onChange={(e) => setBusca(e.target.value)} />}
        >
          <div className="d-grid gap-2">
            {topicos.map((t) => (
              <div key={t.key} className="rounded" style={{ border: "1px solid var(--border)" }}>
                <div className="d-flex align-items-center gap-2 p-3" role="button" onClick={() => setAberto(aberto === t.key ? "" : t.key)}>
                  <span style={{ width: 32, height: 32, borderRadius: 8, display: "grid", placeItems: "center", background: "var(--brand-soft)", color: "var(--brand)" }}><i className={`bi ${t.icon}`} /></span>
                  <div className="flex-grow-1">
                    <div className="fw-semibold">{t.title}</div>
                    <div className="small text-muted-2">{t.resumo}</div>
                  </div>
                  <i className={`bi ${aberto === t.key ? "bi-chevron-up" : "bi-chevron-down"} text-muted-2`} />
                </div>
                {(aberto === t.key || q) && (
                  <div className="px-3 pb-3">
                    <ol className="small mb-2 ps-3">{t.passos.map((p, i) => <li key={i} className="mb-1">{p}</li>)}</ol>
                    {t.dicas?.map((d, i) => <div key={i} className="small text-muted-2"><i className="bi bi-lightbulb me-1" />{d}</div>)}
                    {t.to && <Link to={t.to} className="btn btn-sm btn-outline-secondary mt-2"><i className="bi bi-box-arrow-up-right me-1" />Abrir {t.title}</Link>}
                  </div>
                )}
              </div>
            ))}
            {topicos.length === 0 && <div className="small text-muted-2">Nada encontrado para "{busca}".</div>}
          </div>
        </Panel>
      </div>
      <div className="col-xl-4 d-grid gap-3 align-content-start">
        <Panel title="Precisa de uma pessoa?">
          <div className="small mb-2">Suporte técnico, dúvida de uso, erro, dados do ERP ou consultoria de gestão: a equipe responde no chamado e você acompanha por aqui.</div>
          <Link to="/chamados?novo=1" className="btn btn-primary btn-sm w-100 mb-2"><i className="bi bi-life-preserver me-1" />Abrir chamado</Link>
          <Link to="/chamados?novo=1&categoria=consultoria" className="btn btn-outline-secondary btn-sm w-100"><i className="bi bi-mortarboard me-1" />Pedir consultoria de gestão</Link>
        </Panel>
        <Panel title="Perguntas frequentes">
          <div className="d-grid gap-2">
            {faq.map(([p, r]) => (
              <details key={p}><summary className="small fw-semibold" style={{ cursor: "pointer" }}>{p}</summary><div className="small text-muted-2 mt-1">{r}</div></details>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
