import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, BAR_RADIUS_V, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { ANDAMENTO, AndamentoPill, Avanco } from "../components/projetos";
import { EmptyState, Meter, Panel, Skeleton, StatCard } from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import { MONTHS_SHORT, fmtNumber, fmtPeriod } from "../utils/format";

interface Overview {
  mapa: { id: number; name: string } | null;
  referencia: string | null;
  contagens: {
    planejamentos: number; objetivos: number; objetivos_alcancados: number; objetivos_medidos: number; indicadores: number;
    projetos: number; projetos_abertos: number; planos_abertos: number; desvios_abertos: number;
  };
  performance: { period: string; realizado: number | null }[];
  performance_media: number | null;
  perspectivas: { id: number; name: string; color: string; objetivos: number; indicadores: number; atingimento: number | null }[];
  projetos_por_status: Record<string, number>;
  projetos_atrasados: { id: number; code: number; title: string; status: string; progress: number; dias: number }[];
  projetos_progresso_medio: number;
  atividades_por_mes: { mes: string; criadas: number }[];
  atividades_recentes: { id: number; project: number; project_title: string; title: string; status: string; created_at: string }[];
  swot: Record<"S" | "W" | "O" | "T", number>;
  agenda: { id: number; title: string; kind_label: string; starts_at: string; location: string }[];
}

const SWOT_ROTULO: [keyof Overview["swot"], string, string][] = [
  ["S", "Forças", "bi-shield-check"], ["W", "Fraquezas", "bi-bandaid"], ["O", "Oportunidades", "bi-lightbulb"], ["T", "Ameaças", "bi-cloud-lightning"],
];

const farolDoPct = (pct: number | null) => (pct === null ? null : pct >= 100 ? "verde" : pct >= 90 ? "amarelo" : "vermelho");
const mesDe = (iso: string) => MONTHS_SHORT[Number(iso.slice(5, 7)) - 1];
const dataHora = (iso: string) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/** Página inicial: o planejamento inteiro numa tela — estratégia, projetos, SWOT e agenda. */
export function Dashboard() {
  const navigate = useNavigate();
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [d, setD] = useState<Overview | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api.get<Overview>("/api/dashboard/overview/").then(setD).catch((e) => setErro(e.message));
  }, []);

  if (erro) return <Panel><EmptyState icon="bi-exclamation-circle" title="Não foi possível carregar a visão geral" hint={erro} /></Panel>;
  if (!d) return <Panel><Skeleton height={360} /></Panel>;

  const c = d.contagens;
  const statusProjetos = Object.entries(d.projetos_por_status).filter(([, v]) => v > 0);
  const corStatus: Record<string, string> = { nao_iniciado: t.status.sem_meta, em_andamento: t.series[0], finalizado: t.status.verde, pausado: t.series[3], cancelado: t.axis };
  const gap = d.performance_media === null ? null : d.performance_media - 100;

  return (
    <div className="d-grid gap-3">
      <div className="row g-3">
        <div className="col-6 col-xl-3"><StatCard icon="bi-diagram-3" label="Planejamento" value={<span className="d-block text-truncate" style={{ fontSize: "1.05rem", lineHeight: 1.9 }} title={d.mapa?.name}>{d.mapa?.name ?? "—"}</span>} foot={<Link to="/mapa-estrategico" className="text-decoration-none">{c.objetivos} objetivo(s) · {c.indicadores} indicador(es)</Link>} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-bullseye" label="Objetivos alcançados" value={`${c.objetivos_alcancados}/${c.objetivos}`} foot={d.referencia ? `${c.objetivos_medidos} medido(s) em ${fmtPeriod(d.referencia)}` : "sem indicadores medidos"} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-folder2-open" label="Projetos" value={c.projetos} foot={<Link to="/painel-projetos" className="text-decoration-none">{c.projetos_abertos} em aberto · avanço médio {d.projetos_progresso_medio}%</Link>} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-exclamation-triangle" label="Desvios em aberto" value={c.desvios_abertos} foot={<Link to="/planos-acao" className="text-decoration-none">{c.planos_abertos} plano(s) de ação em aberto</Link>} /></div>
      </div>

      <div className="row g-3">
        <div className="col-xl-8">
          <Panel title="Desempenho geral" subtitle="Atingimento médio das metas dos indicadores, mês a mês (a linha marca 100% da meta)"
            actions={<Link to="/painel-indicadores" className="btn btn-sm btn-outline-secondary">Painel de indicadores</Link>}>
            {d.performance.length === 0 ? (
              <EmptyState icon="bi-graph-up-arrow" title="Nenhum indicador com meta medido neste ano" hint="Plugue indicadores e cadastre metas para acompanhar o desempenho." />
            ) : (
              <>
                <EChart height={250} option={{
                  grid: { left: 4, right: 40, top: 16, bottom: 4, containLabel: true },
                  tooltip: { trigger: "axis", valueFormatter: (v: number) => `${fmtNumber(v, 1)}%` },
                  xAxis: { type: "category", data: d.performance.map((p) => mesDe(p.period)) },
                  yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
                  series: [{
                    name: "Realizado", type: "bar", barMaxWidth: BAR_MAX_WIDTH,
                    data: d.performance.map((p) => ({ value: p.realizado, itemStyle: { color: p.realizado !== null && p.realizado >= 100 ? t.status.verde : t.series[0], borderRadius: BAR_RADIUS_V } })),
                    markLine: { silent: true, symbol: "none", lineStyle: { color: t.inkMuted, type: "dashed" }, label: { formatter: "meta", color: t.inkMuted }, data: [{ yAxis: 100 }] },
                  }],
                }} />
                <div className="d-flex justify-content-around text-center pt-3 mt-2" style={{ borderTop: "1px solid var(--border)" }}>
                  <div><div className="fs-5 fw-semibold">{fmtNumber(d.performance_media, 1)}%</div><div className="small text-muted-2">Média realizada</div></div>
                  <div><div className="fs-5 fw-semibold">100%</div><div className="small text-muted-2">Meta</div></div>
                  <div>
                    <div className="fs-5 fw-semibold" style={{ color: gap !== null && gap >= 0 ? "var(--st-verde)" : "var(--st-vermelho)" }}>
                      <i className={`bi ${gap !== null && gap >= 0 ? "bi-arrow-up-right" : "bi-arrow-down-right"} me-1`} aria-hidden="true" />{gap !== null && gap >= 0 ? "+" : ""}{fmtNumber(gap, 1)} p.p.
                    </div>
                    <div className="small text-muted-2">Diferença para a meta</div>
                  </div>
                </div>
              </>
            )}
          </Panel>
        </div>
        <div className="col-xl-4">
          <Panel title="Situação dos projetos" subtitle="Distribuição atual" className="h-100">
            {statusProjetos.length === 0 ? (
              <EmptyState icon="bi-folder2-open" title="Nenhum projeto" action={<Link to="/projetos" className="btn btn-sm btn-primary">Criar projeto</Link>} />
            ) : (
              <EChart height={Math.max(150, statusProjetos.length * 40 + 30)} option={{
                grid: { left: 4, right: 36, top: 8, bottom: 4, containLabel: true },
                tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
                xAxis: { type: "value", minInterval: 1 },
                yAxis: { type: "category", inverse: true, data: statusProjetos.map(([k]) => ANDAMENTO[k]?.label ?? k) },
                series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, label: { show: true, position: "right" },
                  data: statusProjetos.map(([k, v]) => ({ value: v, itemStyle: { color: corStatus[k], borderRadius: BAR_RADIUS_H } })) }],
              }} />
            )}
          </Panel>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-xl-6">
          <Panel title="Projetos atrasados" subtitle="Prazo final vencido e ainda abaixo de 100%" className="h-100"
            actions={<Link to="/projetos" className="btn btn-sm btn-outline-secondary">Ver todos</Link>}>
            {d.projetos_atrasados.length === 0 ? <EmptyState icon="bi-check2-circle" title="Nenhum projeto atrasado" /> : (
              <div className="d-grid gap-2">
                {d.projetos_atrasados.map((p) => (
                  <div key={p.id} role="button" onClick={() => navigate(`/projetos/${p.id}`)} className="d-flex align-items-center gap-3 p-2 rounded" style={{ background: "var(--surface-sunken)" }}>
                    <div className="flex-grow-1 min-w-0"><div className="fw-semibold text-truncate">{p.title}</div><AndamentoPill status={p.status} /></div>
                    <Avanco progress={p.progress} late width={80} />
                    <span className="status-pill st-vermelho text-nowrap"><i className="bi bi-clock-history" />{p.dias} dia(s)</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
        <div className="col-xl-6">
          <Panel title="Atividades dos projetos" subtitle="Novas atividades por mês" className="h-100">
            {d.atividades_por_mes.length === 0 ? <EmptyState icon="bi-list-check" title="Nenhuma atividade criada neste ano" /> : (
              <EChart height={220} option={{
                grid: { left: 4, right: 8, top: 20, bottom: 4, containLabel: true },
                tooltip: { trigger: "axis" },
                xAxis: { type: "category", data: d.atividades_por_mes.map((m) => mesDe(`${m.mes}-01`)) },
                yAxis: { type: "value", minInterval: 1 },
                series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[0], borderRadius: BAR_RADIUS_V }, label: { show: true, position: "top" }, data: d.atividades_por_mes.map((m) => m.criadas) }],
              }} />
            )}
          </Panel>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-xl-6">
          <Panel title="Mapa estratégico (BSC)" subtitle={d.referencia ? `Atingimento médio por perspectiva em ${fmtPeriod(d.referencia)}` : "Perspectivas do planejamento"} className="h-100"
            actions={<Link to="/mapa-estrategico" className="btn btn-sm btn-outline-secondary">Ver mapa</Link>}>
            {d.perspectivas.length === 0 ? <EmptyState icon="bi-diagram-3" title="Nenhuma perspectiva no mapa" /> : (
              <div className="d-grid gap-3">
                {d.perspectivas.map((p) => (
                  <div key={p.id}>
                    <div className="d-flex justify-content-between align-items-baseline mb-1">
                      <span className="fw-semibold small"><span className="d-inline-block rounded-circle me-2" style={{ width: 8, height: 8, background: p.color }} />{p.name}
                        <span className="text-muted-2 fw-normal ms-2">{p.objetivos} objetivo(s) · {p.indicadores} indicador(es)</span></span>
                      <span className="small num">{p.atingimento === null ? "sem medição" : `${fmtNumber(p.atingimento, 1)}%`}</span>
                    </div>
                    <Meter pct={p.atingimento} status={farolDoPct(p.atingimento)} />
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
        <div className="col-xl-6">
          <Panel title="Análise SWOT" subtitle="Itens cadastrados por quadrante" className="h-100"
            actions={<Link to="/swot" className="btn btn-sm btn-outline-secondary">Ver análise</Link>}>
            <div className="row g-2">
              {SWOT_ROTULO.map(([k, rotulo, icon]) => (
                <div className="col-6" key={k}>
                  <div className="p-3 rounded h-100" style={{ border: "1px solid var(--border)", background: "var(--surface-sunken)" }}>
                    <div className="small text-muted-2"><i className={`bi ${icon} me-1`} aria-hidden="true" />{rotulo}</div>
                    <div className="fs-4 fw-semibold">{d.swot[k]}</div>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-xl-6">
          <Panel title="Atividades recentes" subtitle="Últimas atividades criadas nos projetos" className="h-100">
            {d.atividades_recentes.length === 0 ? <EmptyState icon="bi-activity" title="Nada por aqui ainda" /> : (
              <div className="d-grid gap-2">
                {d.atividades_recentes.map((a) => (
                  <div key={a.id} role="button" onClick={() => navigate(`/projetos/${a.project}`)} className="d-flex align-items-center gap-3">
                    <div className="flex-grow-1 min-w-0"><div className="fw-semibold small text-truncate">{a.title}</div><div className="small text-muted-2 text-truncate">{a.project_title}</div></div>
                    <AndamentoPill status={a.status} />
                    <span className="small text-muted-2 text-nowrap">{dataHora(a.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
        <div className="col-xl-6">
          <Panel title="Agenda" subtitle="Próximas reuniões de gestão" className="h-100"
            actions={<Link to="/agenda" className="btn btn-sm btn-outline-secondary">Ver agenda</Link>}>
            {d.agenda.length === 0 ? <EmptyState icon="bi-calendar3" title="Nenhuma reunião agendada" /> : (
              <div className="d-grid gap-2">
                {d.agenda.map((m) => (
                  <div key={m.id} className="d-flex align-items-center gap-3">
                    <span className="small fw-semibold text-nowrap" style={{ color: "var(--brand)" }}>{dataHora(m.starts_at)}</span>
                    <div className="flex-grow-1 min-w-0"><div className="fw-semibold small text-truncate">{m.title}</div><div className="small text-muted-2 text-truncate">{[m.kind_label, m.location].filter(Boolean).join(" · ")}</div></div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
