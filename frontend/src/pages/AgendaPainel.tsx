import { useEffect, useMemo, useState } from "react";
import { Button, Form } from "react-bootstrap";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, BAR_RADIUS_V, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { EmptyState, Panel, Skeleton, StatCard } from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import { MONTHS_SHORT } from "../utils/format";

interface Reuniao { id: number; title: string; kind: string; kind_label: string; status: string; starts_at: string; ends_at: string | null; location: string; pessoas: string[] }
interface Painel {
  de: string; ate: string; total: number; anterior: number; variacao_pct: number | null; horas: number; realizadas: number;
  pessoas_envolvidas: number; total_usuarios: number;
  conflitos: { pessoa: string; a: string; b: string; quando: string }[];
  carga: { id: number; nome: string; reunioes: number; horas: number }[];
  por_tipo: { kind: string; label: string; total: number }[];
  por_dia_semana: { dia: string; total: number }[];
  proximas: Reuniao[]; reunioes: Reuniao[];
  evolucao: { mes: string; reunioes: number }[];
}
interface Usuario { id: number; first_name: string; last_name?: string; email: string }

const TIPOS: [string, string][] = [
  ["resultados", "Reunião de resultados"], ["planejamento", "Planejamento estratégico"], ["acompanhamento", "Acompanhamento de planos"],
  ["diretoria", "Diretoria"], ["outra", "Outra"],
];
const SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const mesAtual = () => { const h = new Date(); return [iso(new Date(h.getFullYear(), h.getMonth(), 1)), iso(new Date(h.getFullYear(), h.getMonth() + 1, 0))]; };
const hora = (s: string) => new Date(s).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const diaMes = (s: string) => new Date(s).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

function LinhaReuniao({ r }: { r: Reuniao }) {
  return (
    <div className="d-flex align-items-start gap-3">
      <div className="text-nowrap small fw-semibold" style={{ color: "var(--brand)", minWidth: 86 }}>{diaMes(r.starts_at)} · {hora(r.starts_at)}{r.ends_at && `–${hora(r.ends_at)}`}</div>
      <div className="flex-grow-1 min-w-0">
        <div className="fw-semibold small text-truncate">{r.title}{r.status === "realizada" && <span className="status-pill st-verde ms-2"><i className="bi bi-check-lg" />realizada</span>}</div>
        <div className="small text-muted-2 text-truncate">{[r.kind_label, r.location, r.pessoas.join(", ")].filter(Boolean).join(" · ")}</div>
      </div>
    </div>
  );
}

/** Painel da agenda: volume, horas, carga por pessoa, conflitos de horário e evolução. */
export function AgendaPainel() {
  const navigate = useNavigate();
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [de0, ate0] = mesAtual();
  const [de, setDe] = useState(de0);
  const [ate, setAte] = useState(ate0);
  const [participante, setParticipante] = useState("");
  const [tipo, setTipo] = useState("");
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [d, setD] = useState<Painel | null>(null);
  const [erro, setErro] = useState("");
  const [diaSel, setDiaSel] = useState(iso(new Date()));

  useEffect(() => { api.get<any>("/api/users/").then((r) => setUsuarios(r.results ?? r)).catch(() => {}); }, []);
  useEffect(() => {
    if (!de || !ate) return;
    const q = new URLSearchParams({ de, ate });
    if (participante) q.set("participante", participante);
    if (tipo) q.set("tipo", tipo);
    api.get<Painel>(`/api/meetings/dashboard/?${q}`).then((r) => { setD(r); setErro(""); }).catch((e) => setErro(e.data?.[0] ?? e.message));
  }, [de, ate, participante, tipo]);

  const limpar = () => { setDe(de0); setAte(ate0); setParticipante(""); setTipo(""); };

  // Calendário do mês em que o período começa.
  const calendario = useMemo(() => {
    const base = new Date(`${de}T00:00:00`);
    const primeiro = new Date(base.getFullYear(), base.getMonth(), 1);
    const dias = new Date(base.getFullYear(), base.getMonth() + 1, 0).getDate();
    const celulas: (string | null)[] = Array(primeiro.getDay()).fill(null);
    for (let i = 1; i <= dias; i++) celulas.push(iso(new Date(base.getFullYear(), base.getMonth(), i)));
    return { titulo: primeiro.toLocaleDateString("pt-BR", { month: "long", year: "numeric" }), celulas };
  }, [de]);
  const porDia = useMemo(() => {
    const m = new Map<string, Reuniao[]>();
    (d?.reunioes ?? []).forEach((r) => { const k = iso(new Date(r.starts_at)); m.set(k, [...(m.get(k) ?? []), r]); });
    return m;
  }, [d]);
  const mudarMes = (delta: number) => {
    const base = new Date(`${de}T00:00:00`);
    setDe(iso(new Date(base.getFullYear(), base.getMonth() + delta, 1)));
    setAte(iso(new Date(base.getFullYear(), base.getMonth() + delta + 1, 0)));
  };

  if (erro && !d) return <Panel><EmptyState icon="bi-exclamation-circle" title="Não foi possível carregar o painel" hint={erro} /></Panel>;
  if (!d) return <Panel><Skeleton height={340} /></Panel>;

  const variacao = d.variacao_pct === null ? (d.total > 0 && d.anterior === 0 ? "sem reuniões no período anterior" : "igual ao período anterior")
    : `${d.variacao_pct >= 0 ? "+" : ""}${d.variacao_pct}% vs período anterior (${d.anterior})`;
  const doDia = porDia.get(diaSel) ?? [];

  return (
    <div className="d-grid gap-3">
      <Panel
        title="Painel da agenda"
        subtitle="Monitoramento das reuniões por pessoa e período. Reunião sem hora de fim conta 1 hora; canceladas ficam de fora."
        actions={
          <div className="d-flex gap-2">
            <Button size="sm" variant="outline-secondary" onClick={() => window.print()}><i className="bi bi-printer me-1" />Imprimir</Button>
            <Button size="sm" onClick={() => navigate("/agenda")}><i className="bi bi-plus-lg me-1" />Nova agenda</Button>
          </div>
        }
      >
        <div className="d-flex flex-wrap align-items-center gap-2">
          <span className="small text-muted-2"><i className="bi bi-funnel me-1" />Filtros:</span>
          <Form.Select size="sm" value={participante} onChange={(e) => setParticipante(e.target.value)} style={{ width: 200 }}>
            <option value="">Todas as pessoas</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{[u.first_name, u.last_name].filter(Boolean).join(" ") || u.email}</option>)}
          </Form.Select>
          <Form.Select size="sm" value={tipo} onChange={(e) => setTipo(e.target.value)} style={{ width: 210 }}>
            <option value="">Todos os tipos</option>{TIPOS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </Form.Select>
          <Form.Control size="sm" type="date" value={de} onChange={(e) => setDe(e.target.value)} style={{ width: 150 }} aria-label="De" />
          <span className="small text-muted-2">até</span>
          <Form.Control size="sm" type="date" value={ate} onChange={(e) => setAte(e.target.value)} style={{ width: 150 }} aria-label="Até" />
          <Button size="sm" variant="link" onClick={limpar}>Limpar</Button>
          {erro && <span className="small" style={{ color: "var(--st-vermelho)" }}>{erro}</span>}
        </div>
      </Panel>

      <div className="row g-3">
        <div className="col-6 col-xl-3"><StatCard icon="bi-calendar3" label="Total de agendas" value={d.total} foot={variacao} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-clock" label="Horas em reunião" value={`${d.horas.toLocaleString("pt-BR")} h`} foot={`${d.realizadas} realizada(s) no período`} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-people" label="Pessoas envolvidas" value={d.pessoas_envolvidas} foot={`de ${d.total_usuarios} usuário(s) ativo(s)`} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-exclamation-triangle" label="Conflitos de horário" value={d.conflitos.length} foot={d.conflitos.length === 0 ? "tudo certo" : "mesma pessoa em duas reuniões ao mesmo tempo"} /></div>
      </div>

      {d.conflitos.length > 0 && (
        <Panel title="Conflitos detectados">
          <div className="d-grid gap-1">
            {d.conflitos.map((c, i) => (
              <div key={i} className="small"><span className="status-pill st-vermelho me-2"><i className="bi bi-exclamation-triangle" />{diaMes(c.quando)} {hora(c.quando)}</span><strong>{c.pessoa}</strong> está em “{c.a}” e “{c.b}”.</div>
            ))}
          </div>
        </Panel>
      )}

      <div className="row g-3">
        <div className="col-xl-7">
          <Panel title="Carga por pessoa" subtitle="Horas em reunião no período" className="h-100">
            {d.carga.length === 0 ? <EmptyState icon="bi-people" title="Sem dados no período" /> : (
              <EChart height={Math.max(160, Math.min(12, d.carga.length) * 32 + 30)} option={{
                grid: { left: 4, right: 70, top: 8, bottom: 4, containLabel: true },
                tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
                xAxis: { type: "value", axisLabel: { formatter: "{value} h" } },
                yAxis: { type: "category", inverse: true, data: d.carga.slice(0, 12).map((c) => c.nome) },
                series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[0], borderRadius: BAR_RADIUS_H },
                  label: { show: true, position: "right", formatter: (p: any) => `${p.value} h · ${d.carga[p.dataIndex].reunioes}` },
                  data: d.carga.slice(0, 12).map((c) => c.horas) }],
              }} />
            )}
          </Panel>
        </div>
        <div className="col-xl-5">
          <Panel title="Distribuição por tipo" className="h-100">
            {d.por_tipo.length === 0 ? <EmptyState icon="bi-pie-chart" title="Sem dados" /> : (
              <EChart height={Math.max(120, d.por_tipo.length * 32 + 20)} option={{
                grid: { left: 4, right: 36, top: 4, bottom: 4, containLabel: true },
                tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
                xAxis: { type: "value", minInterval: 1 },
                yAxis: { type: "category", inverse: true, data: d.por_tipo.map((p) => p.label) },
                series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[0], borderRadius: BAR_RADIUS_H }, label: { show: true, position: "right" }, data: d.por_tipo.map((p) => p.total) }],
              }} />
            )}
            <div className="small text-muted-2 fw-semibold mt-3 mb-1">Agendas por dia da semana</div>
            <EChart height={130} option={{
              grid: { left: 4, right: 8, top: 18, bottom: 4, containLabel: true },
              tooltip: { trigger: "axis" },
              xAxis: { type: "category", data: d.por_dia_semana.map((p) => p.dia) },
              yAxis: { type: "value", minInterval: 1, show: false },
              series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[2], borderRadius: BAR_RADIUS_V }, label: { show: true, position: "top" }, data: d.por_dia_semana.map((p) => p.total) }],
            }} />
          </Panel>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-xl-5">
          <Panel title="Próximas agendas" subtitle="Agendadas daqui para frente, dentro do período" className="h-100">
            {d.proximas.length === 0 ? <EmptyState icon="bi-calendar-check" title="Nenhuma agenda futura no período" /> : (
              <div className="d-grid gap-3">{d.proximas.map((r) => <LinhaReuniao key={r.id} r={r} />)}</div>
            )}
          </Panel>
        </div>
        <div className="col-xl-7">
          <Panel title={calendario.titulo.replace(/^./, (c) => c.toUpperCase())} className="h-100"
            actions={<div className="d-flex gap-1">
              <Button size="sm" variant="outline-secondary" onClick={() => mudarMes(-1)} aria-label="Mês anterior"><i className="bi bi-chevron-left" /></Button>
              <Button size="sm" variant="outline-secondary" onClick={() => mudarMes(1)} aria-label="Próximo mês"><i className="bi bi-chevron-right" /></Button>
            </div>}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
              {SEMANA.map((s) => <div key={s} className="text-center small text-muted-2">{s}</div>)}
              {calendario.celulas.map((dia, i) => {
                if (!dia) return <div key={`v${i}`} />;
                const n = porDia.get(dia)?.length ?? 0;
                const sel = dia === diaSel;
                const hoje = dia === iso(new Date());
                return (
                  <button key={dia} type="button" onClick={() => setDiaSel(dia)} className="btn btn-sm p-1"
                    style={{ border: `1px solid ${sel ? "var(--brand)" : "var(--border)"}`, background: sel ? "var(--brand-soft)" : "var(--surface)", color: "var(--ink)", fontWeight: hoje ? 700 : 400 }}>
                    <div>{Number(dia.slice(8))}</div>
                    <div style={{ fontSize: "0.65rem", height: 12, color: "var(--brand)" }}>{n > 0 ? `${n} agenda${n > 1 ? "s" : ""}` : ""}</div>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
              <div className="small fw-semibold mb-2">{new Date(`${diaSel}T00:00:00`).toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric" })}</div>
              {doDia.length === 0 ? <div className="small text-muted-2">Nenhuma agenda para este dia.</div> : <div className="d-grid gap-2">{doDia.map((r) => <LinhaReuniao key={r.id} r={r} />)}</div>}
            </div>
          </Panel>
        </div>
      </div>

      <Panel title="Evolução de agendas" subtitle="Últimos 6 meses (respeita os filtros de pessoa e tipo)">
        <EChart height={200} option={{
          grid: { left: 4, right: 12, top: 20, bottom: 4, containLabel: true },
          tooltip: { trigger: "axis" },
          xAxis: { type: "category", data: d.evolucao.map((m) => `${MONTHS_SHORT[Number(m.mes.slice(5, 7)) - 1]}/${m.mes.slice(2, 4)}`) },
          yAxis: { type: "value", minInterval: 1 },
          series: [{ name: "Agendas", type: "line", symbol: "circle", symbolSize: 7, lineStyle: { width: 2, color: t.series[0] }, itemStyle: { color: t.series[0] }, label: { show: true, position: "top" }, data: d.evolucao.map((m) => m.reunioes) }],
        }} />
      </Panel>
    </div>
  );
}
