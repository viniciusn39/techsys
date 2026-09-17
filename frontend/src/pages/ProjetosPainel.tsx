import { useEffect, useMemo, useState } from "react";
import { Form } from "react-bootstrap";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, BAR_RADIUS_V, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { ANDAMENTO, AndamentoPill, Avanco, FASES, LegendaAvanco, corAvanco } from "../components/projetos";
import { EmptyState, Panel, Skeleton, StatCard } from "../components/ui";
import { useTheme } from "../hooks/useTheme";

interface Visao {
  id: number; code: number; title: string; owner_name: string; status: string;
  activities_count: number; subactivities_count: number; done_count: number; late_count: number; progress: number;
}
interface Painel {
  projetos: number; atividades: number; subatividades: number; progresso_medio: number; concluidas: number; atrasadas: number; em_andamento: number;
  por_status: Record<string, number>; por_fase: Record<string, number>;
  timeline: { mes: string; iniciadas: number; finalizadas: number }[];
  ranking: { nome: string; total: number; concluidas: number; atrasadas: number; eficiencia: number }[];
  visao_geral: Visao[];
}
interface Opcao { id: number; name?: string; title?: string; code?: number }

const mesCurto = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }).replace(".", "");
};

export function ProjetosPainel() {
  const navigate = useNavigate();
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [dados, setDados] = useState<Painel | null>(null);
  const [mapas, setMapas] = useState<Opcao[]>([]);
  const [projetos, setProjetos] = useState<Opcao[]>([]);
  const [fMapa, setFMapa] = useState("");
  const [fProjeto, setFProjeto] = useState("");

  useEffect(() => {
    api.get<any>("/api/strategic-maps/").then((d) => setMapas(d.results ?? d)).catch(() => {});
    api.get<Opcao[]>("/api/projects/").then(setProjetos).catch(() => {});
  }, []);
  useEffect(() => {
    const q = new URLSearchParams();
    if (fMapa) q.set("map", fMapa);
    if (fProjeto) q.set("project", fProjeto);
    api.get<Painel>(`/api/projects/dashboard/?${q}`).then(setDados).catch(() => setDados(null));
  }, [fMapa, fProjeto]);

  const porProjeto = useMemo(() => [...(dados?.visao_geral ?? [])].reverse(), [dados]);

  if (!dados) return <Panel><Skeleton height={320} /></Panel>;

  const statusComValor = Object.entries(dados.por_status).filter(([, v]) => v > 0);
  // Situação é categoria, não farol: cinzas e a série principal; verde só para o que terminou.
  const corStatus: Record<string, string> = { nao_iniciado: t.status.sem_meta, em_andamento: t.series[0], finalizado: t.status.verde, pausado: t.series[3], cancelado: t.axis };

  return (
    <div className="d-grid gap-3">
      <Panel
        title="Painel de projetos"
        subtitle="Visão consolidada dos projetos do planejamento: avanço, prazos e quem está com o quê."
        actions={
          <div className="d-flex flex-wrap gap-2">
            {mapas.length > 1 && (
              <Form.Select size="sm" value={fMapa} onChange={(e) => setFMapa(e.target.value)} style={{ width: 210 }}>
                <option value="">Todos os planejamentos</option>{mapas.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </Form.Select>
            )}
            <Form.Select size="sm" value={fProjeto} onChange={(e) => setFProjeto(e.target.value)} style={{ width: 230 }}>
              <option value="">Todos os projetos</option>{projetos.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.title}</option>)}
            </Form.Select>
          </div>
        }
      >
        {dados.projetos === 0 ? (
          <EmptyState icon="bi-folder2-open" title="Nenhum projeto para mostrar" hint="Cadastre projetos em Projetos para acompanhar o painel." />
        ) : (
          <div className="row g-3">
            <div className="col-6 col-md-4 col-xl-2"><StatCard icon="bi-folder2-open" label="Projetos" value={dados.projetos} /></div>
            <div className="col-6 col-md-4 col-xl-2"><StatCard icon="bi-list-check" label="Atividades" value={dados.atividades} foot={`${dados.subatividades} subatividade(s)`} /></div>
            <div className="col-6 col-md-4 col-xl-2"><StatCard icon="bi-graph-up" label="Avanço médio" value={`${dados.progresso_medio}%`} /></div>
            <div className="col-6 col-md-4 col-xl-2"><StatCard icon="bi-check2-circle" label="Concluídas" value={dados.concluidas} /></div>
            <div className="col-6 col-md-4 col-xl-2"><StatCard icon="bi-clock-history" label="Atrasadas" value={dados.atrasadas} /></div>
            <div className="col-6 col-md-4 col-xl-2"><StatCard icon="bi-play-circle" label="Em andamento" value={dados.em_andamento} /></div>
          </div>
        )}
      </Panel>

      {dados.projetos > 0 && (
        <>
          <div className="row g-3">
            <div className="col-xl-5">
              <Panel title="Atividades por situação" subtitle="Todas as atividades e subatividades">
                {statusComValor.length === 0 ? <EmptyState icon="bi-list-check" title="Sem atividades" /> : (
                  <EChart height={Math.max(140, statusComValor.length * 38 + 30)} option={{
                    grid: { left: 4, right: 36, top: 8, bottom: 4, containLabel: true },
                    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
                    xAxis: { type: "value", minInterval: 1 },
                    yAxis: { type: "category", inverse: true, data: statusComValor.map(([k]) => ANDAMENTO[k]?.label ?? k) },
                    series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, label: { show: true, position: "right" },
                      data: statusComValor.map(([k, v]) => ({ value: v, itemStyle: { color: corStatus[k], borderRadius: BAR_RADIUS_H } })) }],
                  }} />
                )}
              </Panel>
            </div>
            <div className="col-xl-7">
              <Panel title="Avanço por projeto" subtitle="Clique na barra para abrir o projeto">
                <EChart height={Math.max(140, porProjeto.length * 34 + 30)}
                  onEvents={{ click: (p: any) => { const alvo = porProjeto[p.dataIndex]; if (alvo) navigate(`/projetos/${alvo.id}`); } }}
                  option={{
                    grid: { left: 4, right: 44, top: 8, bottom: 4, containLabel: true },
                    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v: number) => `${v}%` },
                    xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
                    yAxis: { type: "category", data: porProjeto.map((p) => p.title.length > 28 ? `${p.title.slice(0, 27)}…` : p.title) },
                    series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, label: { show: true, position: "right", formatter: "{c}%" },
                      data: porProjeto.map((p) => ({ value: p.progress, itemStyle: { color: corAvanco(t, p.progress, p.late_count > 0), borderRadius: BAR_RADIUS_H } })) }],
                  }} />
                <div className="mt-2"><LegendaAvanco /></div>
              </Panel>
            </div>
          </div>

          <div className="row g-3">
            <div className="col-xl-7">
              <Panel title="Linha do tempo" subtitle="Atividades que começam e que terminam em cada mês">
                {dados.timeline.length === 0 ? <EmptyState icon="bi-calendar3" title="Atividades ainda sem datas" /> : (
                  <EChart height={240} option={{
                    grid: { left: 4, right: 8, top: 30, bottom: 4, containLabel: true },
                    legend: { top: 0, left: 0 },
                    tooltip: { trigger: "axis" },
                    xAxis: { type: "category", data: dados.timeline.map((m) => mesCurto(m.mes)) },
                    yAxis: { type: "value", minInterval: 1 },
                    series: [
                      { name: "Iniciadas", type: "bar", barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[0], borderRadius: BAR_RADIUS_V }, data: dados.timeline.map((m) => m.iniciadas) },
                      { name: "Finalizadas", type: "bar", barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[2], borderRadius: BAR_RADIUS_V }, data: dados.timeline.map((m) => m.finalizadas) },
                    ],
                  }} />
                )}
              </Panel>
            </div>
            <div className="col-xl-5">
              <Panel title="Atividades por fase" subtitle="Onde está o esforço do portfólio">
                <EChart height={240} option={{
                  grid: { left: 4, right: 8, top: 16, bottom: 4, containLabel: true },
                  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
                  xAxis: { type: "category", data: FASES.map(([, l]) => l), axisLabel: { interval: 0, fontSize: 10 } },
                  yAxis: { type: "value", minInterval: 1 },
                  series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[0], borderRadius: BAR_RADIUS_V }, label: { show: true, position: "top" }, data: FASES.map(([k]) => dados.por_fase[k] ?? 0) }],
                }} />
              </Panel>
            </div>
          </div>

          <div className="row g-3">
            <div className="col-xl-5">
              <Panel title="Por responsável" subtitle="Eficiência = concluídas ÷ total">
                {dados.ranking.length === 0 ? <EmptyState icon="bi-people" title="Sem atividades" /> : (
                  <div className="table-responsive">
                    <table className="table table-sm mb-0">
                      <thead><tr><th>Responsável</th><th className="num">Total</th><th className="num">Concluídas</th><th className="num">Atrasadas</th><th className="num">Eficiência</th></tr></thead>
                      <tbody>
                        {dados.ranking.map((r) => (
                          <tr key={r.nome}><td>{r.nome}</td><td className="num">{r.total}</td><td className="num">{r.concluidas}</td><td className="num">{r.atrasadas || "—"}</td><td className="num">{r.eficiencia}%</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Panel>
            </div>
            <div className="col-xl-7">
              <Panel title="Visão geral dos projetos">
                <div className="table-responsive">
                  <table className="table table-sm table-hover align-middle mb-0">
                    <thead><tr><th>Projeto</th><th>Situação</th><th className="num">Ativ.</th><th className="num">Atrasadas</th><th>Avanço</th></tr></thead>
                    <tbody>
                      {dados.visao_geral.map((p) => (
                        <tr key={p.id} role="button" onClick={() => navigate(`/projetos/${p.id}`)}>
                          <td><div className="fw-semibold">{p.title}</div><div className="small text-muted-2">{p.owner_name}</div></td>
                          <td><AndamentoPill status={p.status} /></td>
                          <td className="num">{p.activities_count + p.subactivities_count}</td>
                          <td className="num">{p.late_count || "—"}</td>
                          <td><Avanco progress={p.progress} late={p.late_count > 0} width={100} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
