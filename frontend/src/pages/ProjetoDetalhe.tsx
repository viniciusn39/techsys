import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Form, Modal, Nav } from "react-bootstrap";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { vizTokens } from "../charts/theme";
import {
  ANDAMENTO, AndamentoPill, Avanco, FASES, FCA_STATUS, LegendaAvanco, corAvanco, nomeUsuario,
  type Atividade, type Fca, type Projeto, type Usuario,
} from "../components/projetos";
import { EmptyState, Panel, Skeleton, StatCard } from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import { fmtDate } from "../utils/format";

interface Objetivo { id: number; name: string; perspective_name: string }
interface SwotItem { id: number; quadrant_label: string; text: string }

const erroDaApi = (e: unknown) => {
  const d = (e as ApiError).data;
  return d && typeof d === "object" ? Object.values(d).flat().join(" ") : (e as Error).message;
};

// --- Gantt -------------------------------------------------------------------

const DIA = 86_400_000;
const dia = (iso: string) => new Date(`${iso}T00:00:00`).getTime();

function Gantt({ projeto, linhas }: { projeto: Projeto; linhas: Atividade[] }) {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const datas = [projeto.start_date, projeto.end_date, ...linhas.flatMap((a) => [a.start_date, a.end_date])].filter(Boolean) as string[];
  const min = new Date(Math.min(...datas.map(dia)));
  const max = new Date(Math.max(...datas.map(dia)));
  const ini = new Date(min.getFullYear(), min.getMonth(), 1).getTime();
  const fim = new Date(max.getFullYear(), max.getMonth() + 1, 1).getTime();
  const total = fim - ini;
  const pos = (ms: number) => ((ms - ini) / total) * 100;

  const meses: { label: string; left: number; width: number }[] = [];
  for (let d = new Date(ini); d.getTime() < fim; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
    const prox = new Date(d.getFullYear(), d.getMonth() + 1, 1).getTime();
    meses.push({ label: d.toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }).replace(".", ""), left: pos(d.getTime()), width: pos(prox) - pos(d.getTime()) });
  }
  const hoje = Date.now();
  const largura = Math.max(560, meses.length * 110);

  return (
    <div className="d-flex" style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ width: 300, flexShrink: 0, borderRight: "1px solid var(--border)" }}>
        <div className="px-2 small text-muted-2 text-uppercase fw-semibold d-flex align-items-center" style={{ height: 32, background: "var(--surface-sunken)", fontSize: "0.7rem" }}>Atividade</div>
        {linhas.map((a) => (
          <div key={a.id} className="px-2 d-flex align-items-center gap-2 small" style={{ height: 32, borderTop: "1px solid var(--border)" }}>
            <span className={`text-truncate flex-grow-1 ${a.depth === 0 ? "fw-semibold" : ""}`} style={{ paddingLeft: a.depth * 12 }} title={a.title}>
              <span className="text-muted-2 me-1">{a.wbs}</span>{a.title}
            </span>
            <span className="num text-muted-2">{a.progress}%</span>
          </div>
        ))}
      </div>
      <div style={{ overflowX: "auto", flexGrow: 1 }}>
        <div style={{ minWidth: largura, width: "100%", position: "relative" }}>
          <div style={{ height: 32, position: "relative", background: "var(--surface-sunken)" }}>
            {meses.map((m) => (
              <div key={m.left} className="small text-muted-2 text-center" style={{ position: "absolute", left: `${m.left}%`, width: `${m.width}%`, lineHeight: "32px", borderLeft: "1px solid var(--border)", fontSize: "0.72rem" }}>{m.label}</div>
            ))}
          </div>
          {linhas.map((a) => {
            const temDatas = a.start_date && a.end_date;
            const left = temDatas ? pos(dia(a.start_date!)) : 0;
            const width = temDatas ? Math.max(0.8, pos(dia(a.end_date!) + DIA) - left) : 0;
            const cor = corAvanco(t, a.progress, a.late);
            return (
              <div key={a.id} style={{ height: 32, position: "relative", borderTop: "1px solid var(--border)" }}>
                {meses.map((m) => <div key={m.left} style={{ position: "absolute", left: `${m.left}%`, top: 0, bottom: 0, borderLeft: "1px solid var(--border)" }} />)}
                {temDatas ? (
                  <div title={`${a.title} · ${fmtDate(a.start_date)} a ${fmtDate(a.end_date)} · ${a.progress}%${a.late ? " · atrasada" : ""}`}
                    style={{ position: "absolute", left: `${left}%`, width: `${width}%`, top: a.has_children ? 11 : 8, height: a.has_children ? 10 : 16, borderRadius: 4, border: `1px solid ${cor}`, background: "var(--surface)", overflow: "hidden" }}>
                    <div style={{ width: `${a.progress}%`, height: "100%", background: cor, opacity: a.has_children ? 0.55 : 0.85 }} />
                  </div>
                ) : <span className="small text-muted-2" style={{ position: "absolute", left: 8, lineHeight: "32px", fontSize: "0.72rem" }}>sem datas</span>}
              </div>
            );
          })}
          {hoje >= ini && hoje <= fim && (
            <div style={{ position: "absolute", left: `${pos(hoje)}%`, top: 0, bottom: 0, borderLeft: `2px solid ${t.status.vermelho}` }}>
              <span className="small" style={{ position: "absolute", top: 34, left: 4, color: t.status.vermelho, background: "var(--surface)", padding: "0 2px", lineHeight: 1, fontSize: "0.68rem", fontWeight: 600 }}>hoje</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Página ------------------------------------------------------------------

export function ProjetoDetalhe() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { me } = useAuth();
  const podeEditar = me?.role !== "colaborador";

  const [projeto, setProjeto] = useState<Projeto | null>(null);
  const [naoAchou, setNaoAchou] = useState(false);
  const [linhas, setLinhas] = useState<Atividade[] | null>(null);
  const [fcas, setFcas] = useState<Fca[]>([]);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [objetivos, setObjetivos] = useState<Objetivo[]>([]);
  const [swot, setSwot] = useState<SwotItem[]>([]);
  const [aba, setAba] = useState<"atividades" | "gantt" | "fcas">("atividades");
  const [fechadas, setFechadas] = useState<Set<number>>(new Set());
  const [fResp, setFResp] = useState("");
  const [fFase, setFFase] = useState("");
  const [soAtrasadas, setSoAtrasadas] = useState(false);
  const [ativ, setAtiv] = useState<Partial<Atividade> | null>(null);
  const [fca, setFca] = useState<Partial<Fca> | null>(null);
  const [erro, setErro] = useState("");

  const load = useCallback(() => {
    api.get<Projeto>(`/api/projects/${id}/`).then(setProjeto).catch(() => setNaoAchou(true));
    api.get<Atividade[]>(`/api/projects/${id}/atividades/`).then(setLinhas).catch(() => setLinhas([]));
    api.get<Fca[]>(`/api/projects/${id}/fcas/`).then(setFcas).catch(() => setFcas([]));
  }, [id]);
  useEffect(() => {
    load();
    api.get<any>("/api/users/").then((d) => setUsuarios(d.results ?? d)).catch(() => {});
    api.get<any>("/api/objectives/").then((d) => setObjetivos(d.results ?? d)).catch(() => {});
    api.get<any>("/api/swot/").then((d) => setSwot(d.results ?? d)).catch(() => {});
  }, [load]);

  const filtrando = !!(fResp || fFase || soAtrasadas);
  const visiveis = useMemo(() => {
    const todas = linhas ?? [];
    if (filtrando) {
      return todas.filter((a) => (!fResp || String(a.responsible ?? "") === fResp) && (!fFase || a.phase === fFase) && (!soAtrasadas || a.late));
    }
    const pai = new Map(todas.map((a) => [a.id, a.parent]));
    return todas.filter((a) => {
      for (let p = a.parent; p != null; p = pai.get(p) ?? null) if (fechadas.has(p)) return false;
      return true;
    });
  }, [linhas, fechadas, filtrando, fResp, fFase, soAtrasadas]);

  const alternar = (aid: number) => setFechadas((s) => { const n = new Set(s); n.has(aid) ? n.delete(aid) : n.add(aid); return n; });

  const salvarAtiv = async () => {
    if (!ativ?.title?.trim()) { setErro("Dê um nome à atividade."); return; }
    const body = {
      project: Number(id), parent: ativ.parent ?? null, title: ativ.title, description: ativ.description ?? "",
      responsible: ativ.responsible || null, phase: ativ.phase, start_date: ativ.start_date || null, end_date: ativ.end_date || null,
      status: ativ.status, progress_pct: Number(ativ.progress_pct ?? 0), notes: ativ.notes ?? "",
    };
    try {
      if (ativ.id) await api.patch(`/api/project-activities/${ativ.id}/`, body);
      else await api.post("/api/project-activities/", body);
      setAtiv(null);
      load();
    } catch (e) { setErro(erroDaApi(e)); }
  };
  const excluirAtiv = async () => {
    if (!ativ?.id) return;
    await api.del(`/api/project-activities/${ativ.id}/`);
    setAtiv(null);
    load();
  };

  const salvarFca = async () => {
    if (!fca?.fact?.trim() || !fca.activity) { setErro("Escolha a atividade e descreva o fato."); return; }
    const body = { activity: fca.activity, fact: fca.fact, cause: fca.cause ?? "", action: fca.action ?? "", due_date: fca.due_date || null, responsible: fca.responsible || null, status: fca.status };
    try {
      if (fca.id) await api.patch(`/api/project-fcas/${fca.id}/`, body);
      else await api.post("/api/project-fcas/", body);
      setFca(null);
      load();
    } catch (e) { setErro(erroDaApi(e)); }
  };
  const excluirFca = async () => {
    if (!fca?.id) return;
    await api.del(`/api/project-fcas/${fca.id}/`);
    setFca(null);
    load();
  };

  const novaAtiv = (parent: Atividade | null) => {
    setErro("");
    setAtiv({ parent: parent?.id ?? null, phase: parent?.phase ?? "iniciacao", status: "nao_iniciado", progress_pct: 0, responsible: parent?.responsible ?? projeto?.owner ?? null, start_date: parent?.start_date ?? projeto?.start_date, end_date: parent?.end_date ?? projeto?.end_date });
  };
  const novoFca = (a: Atividade | null) => { setErro(""); setFca({ activity: a?.id, status: "em_andamento", responsible: a?.responsible ?? me?.id ?? null }); };

  const exportar = () => {
    const cel = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv = [["EAP", "Atividade", "Responsável", "Fase", "Início", "Fim", "Situação", "Avanço %", "Atrasada"],
      ...(linhas ?? []).map((a) => [a.wbs, a.title, a.responsible_name, a.phase_label, fmtDate(a.start_date), fmtDate(a.end_date), ANDAMENTO[a.status]?.label, a.progress, a.late ? "sim" : "não"])]
      .map((l) => l.map(cel).join(";")).join("\r\n");
    const url = URL.createObjectURL(new Blob([`﻿${csv}`], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `projeto-${projeto?.code}-atividades.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (naoAchou) return <Panel><EmptyState icon="bi-folder-x" title="Projeto não encontrado" action={<Button size="sm" onClick={() => navigate("/projetos")}>Voltar aos projetos</Button>} /></Panel>;
  if (!projeto || linhas === null) return <Panel><Skeleton height={320} /></Panel>;

  const meusObjetivos = objetivos.filter((o) => projeto.objectives.includes(o.id));
  const meuSwot = swot.filter((s) => projeto.swot_items.includes(s.id));
  const parceiros = usuarios.filter((u) => projeto.partners.includes(u.id));
  const fcasAbertos = fcas.filter((f) => f.status === "em_andamento");

  return (
    <div className="d-grid gap-3">
      <Panel
        title={`${projeto.code} · ${projeto.title}`}
        subtitle={<>{projeto.map_name && <>Planejamento: <strong>{projeto.map_name}</strong> · </>}{fmtDate(projeto.start_date)} a {fmtDate(projeto.end_date)} · {projeto.owner_name || "sem responsável"}{projeto.org_unit_name && ` · ${projeto.org_unit_name}`}</>}
        actions={<div className="d-flex align-items-center gap-2"><AndamentoPill status={projeto.status} /><Button size="sm" variant="outline-secondary" onClick={() => navigate("/projetos")}><i className="bi bi-arrow-left me-1" />Projetos</Button></div>}
      >
        {projeto.description && <p className="small mb-3">{projeto.description}</p>}
        <div className="row g-3 small">
          <div className="col-md-5">
            <div className="text-muted-2 fw-semibold mb-1"><i className="bi bi-bullseye me-1" />Objetivos do mapa que este projeto faz avançar</div>
            {meusObjetivos.length === 0 ? <span className="text-muted-2">Nenhum objetivo ligado.</span> : meusObjetivos.map((o) => (
              <div key={o.id}><Link to="/mapa-estrategico" className="text-decoration-none">{o.name}</Link> <span className="text-muted-2">· {o.perspective_name}</span></div>
            ))}
          </div>
          <div className="col-md-4">
            <div className="text-muted-2 fw-semibold mb-1"><i className="bi bi-grid-3x3-gap me-1" />Itens da SWOT tratados</div>
            {meuSwot.length === 0 ? <span className="text-muted-2">Nenhum item ligado.</span> : meuSwot.map((s) => (
              <div key={s.id}><span className="badge text-bg-light border fw-normal me-1">{s.quadrant_label}</span>{s.text}</div>
            ))}
          </div>
          <div className="col-md-3">
            <div className="text-muted-2 fw-semibold mb-1"><i className="bi bi-people me-1" />Parceiros</div>
            {parceiros.length === 0 ? <span className="text-muted-2">—</span> : parceiros.map((u) => <div key={u.id}>{nomeUsuario(u)}</div>)}
          </div>
        </div>
      </Panel>

      <div className="row g-3">
        <div className="col-6 col-xl-3"><StatCard icon="bi-graph-up" label="Avanço do projeto" value={`${projeto.progress}%`} foot="média das atividades de 1º nível" /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-clock-history" label="Atrasadas" value={projeto.late_count} foot={`de ${linhas.length} atividade(s)`} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-check2-circle" label="Concluídas" value={projeto.done_count} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-clipboard-check" label="FCAs em andamento" value={fcasAbertos.length} foot={fcasAbertos.some((f) => f.alert === "atrasado") ? `${fcasAbertos.filter((f) => f.alert === "atrasado").length} com prazo vencido` : undefined} /></div>
      </div>

      <Panel
        actions={
          <div className="d-flex flex-wrap align-items-center gap-2 w-100">
            <Nav variant="pills" activeKey={aba} onSelect={(k) => setAba(k as typeof aba)} className="me-auto">
              <Nav.Item><Nav.Link eventKey="atividades" className="py-1 px-3 small">Atividades</Nav.Link></Nav.Item>
              <Nav.Item><Nav.Link eventKey="gantt" className="py-1 px-3 small">Gantt</Nav.Link></Nav.Item>
              <Nav.Item><Nav.Link eventKey="fcas" className="py-1 px-3 small">FCAs{fcas.length > 0 && ` (${fcas.length})`}</Nav.Link></Nav.Item>
            </Nav>
            {aba !== "fcas" && (
              <>
                <Form.Select size="sm" value={fResp} onChange={(e) => setFResp(e.target.value)} style={{ width: 170 }}>
                  <option value="">Todos os responsáveis</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{nomeUsuario(u)}</option>)}
                </Form.Select>
                <Form.Select size="sm" value={fFase} onChange={(e) => setFFase(e.target.value)} style={{ width: 150 }}>
                  <option value="">Todas as fases</option>{FASES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </Form.Select>
                <Form.Check type="switch" id="so-atrasadas" className="small" label="Só atrasadas" checked={soAtrasadas} onChange={(e) => setSoAtrasadas(e.target.checked)} />
                <Button size="sm" variant="outline-secondary" onClick={exportar} disabled={linhas.length === 0} title="Exportar CSV"><i className="bi bi-download" /></Button>
                <Button size="sm" variant="outline-secondary" onClick={() => window.print()} title="Imprimir"><i className="bi bi-printer" /></Button>
              </>
            )}
            {podeEditar && (aba === "fcas"
              ? <Button size="sm" onClick={() => novoFca(null)} disabled={linhas.length === 0}><i className="bi bi-plus-lg me-1" />Novo FCA</Button>
              : <Button size="sm" onClick={() => novaAtiv(null)}><i className="bi bi-plus-lg me-1" />Nova atividade</Button>)}
          </div>
        }
      >
        {aba === "atividades" && (linhas.length === 0 ? (
          <EmptyState icon="bi-list-nested" title="Nenhuma atividade ainda" hint="Monte a estrutura do projeto: atividades, subatividades e quantos níveis precisar." />
        ) : (
          <>
            <div className="table-responsive">
              <table className="table table-sm table-hover align-middle">
                <thead><tr><th>Atividade</th><th>Responsável</th><th>Fase</th><th>Início</th><th>Fim</th><th>Situação</th><th>Avanço</th><th /></tr></thead>
                <tbody>
                  {visiveis.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <div className="d-flex align-items-center" style={{ paddingLeft: filtrando ? 0 : a.depth * 20 }}>
                          {a.has_children && !filtrando
                            ? <Button variant="link" size="sm" className="p-0 me-1 text-muted-2" onClick={() => alternar(a.id)} aria-label={fechadas.has(a.id) ? "Expandir" : "Recolher"}><i className={`bi ${fechadas.has(a.id) ? "bi-chevron-right" : "bi-chevron-down"}`} /></Button>
                            : <span style={{ width: 20 }} />}
                          <span className={a.depth === 0 ? "fw-semibold" : ""} role={podeEditar ? "button" : undefined} onClick={() => { if (podeEditar) { setErro(""); setAtiv(a); } }}>
                            <span className="text-muted-2 me-1">{a.wbs}</span>{a.title}
                          </span>
                        </div>
                      </td>
                      <td className="small">{a.responsible_name || "—"}</td>
                      <td className="small text-muted-2">{a.phase_label}</td>
                      <td className="small">{fmtDate(a.start_date)}</td>
                      <td className="small">{fmtDate(a.end_date)}</td>
                      <td><AndamentoPill status={a.status} /></td>
                      <td><Avanco progress={a.progress} late={a.late} width={90} /></td>
                      <td className="text-end text-nowrap">
                        {podeEditar && (
                          <>
                            <Button size="sm" variant="link" className="p-1" title="Nova subatividade" onClick={() => novaAtiv(a)}><i className="bi bi-node-plus" /></Button>
                            <Button size="sm" variant="link" className="p-1" title="Novo FCA (fato, causa, ação)" onClick={() => novoFca(a)}><i className="bi bi-clipboard-plus" />{a.fcas_count > 0 && <span className="ms-1 small">{a.fcas_count}</span>}</Button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                  {visiveis.length === 0 && <tr><td colSpan={8} className="text-center text-muted-2 py-4">Nenhuma atividade com esses filtros.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="mt-3"><LegendaAvanco /></div>
          </>
        ))}

        {aba === "gantt" && (visiveis.length === 0
          ? <EmptyState icon="bi-bar-chart-steps" title="Nada para mostrar no Gantt" hint="Cadastre atividades com data de início e fim." />
          : <><Gantt projeto={projeto} linhas={visiveis} /><div className="mt-3"><LegendaAvanco /></div></>)}

        {aba === "fcas" && (fcas.length === 0 ? (
          <EmptyState icon="bi-clipboard-check" title="Nenhum FCA registrado" hint="Quando uma atividade travar, registre o fato, a causa raiz e a ação corretiva." />
        ) : (
          <div className="table-responsive">
            <table className="table table-sm table-hover align-middle">
              <thead><tr><th>Atividade</th><th>Fato</th><th>Causa</th><th>Ação</th><th>Prazo</th><th>Responsável</th><th>Status</th></tr></thead>
              <tbody>
                {fcas.map((f) => (
                  <tr key={f.id} role={podeEditar ? "button" : undefined} onClick={() => { if (podeEditar) { setErro(""); setFca(f); } }}>
                    <td className="small fw-semibold">{f.activity_title}</td>
                    <td className="small">{f.fact}</td>
                    <td className="small text-muted-2">{f.cause || "—"}</td>
                    <td className="small">{f.action || "—"}</td>
                    <td className="small text-nowrap">
                      {fmtDate(f.due_date)}
                      {f.alert === "atrasado" && <span className="status-pill st-vermelho ms-2"><i className="bi bi-exclamation-triangle" />vencido</span>}
                      {f.alert === "vence_logo" && <span className="status-pill st-amarelo ms-2"><i className="bi bi-hourglass-split" />vence em breve</span>}
                    </td>
                    <td className="small">{f.responsible_name || "—"}</td>
                    <td><span className={`status-pill ${FCA_STATUS[f.status]?.cls}`}>{FCA_STATUS[f.status]?.label}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </Panel>

      <Modal show={!!ativ} onHide={() => setAtiv(null)} size="lg" scrollable>
        <Modal.Header closeButton><Modal.Title>{ativ?.id ? `Atividade ${ativ.wbs ?? ""}` : ativ?.parent ? "Nova subatividade" : "Nova atividade"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {ativ && (
            <div className="row g-3">
              {erro && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erro}</Alert></div>}
              <div className="col-12"><Form.Label>Nome da atividade *</Form.Label><Form.Control autoFocus value={ativ.title ?? ""} onChange={(e) => setAtiv({ ...ativ, title: e.target.value })} /></div>
              <div className="col-12"><Form.Label>Descrição</Form.Label><Form.Control as="textarea" rows={2} value={ativ.description ?? ""} onChange={(e) => setAtiv({ ...ativ, description: e.target.value })} /></div>
              <div className="col-md-6"><Form.Label>Fica abaixo de</Form.Label>
                <Form.Select value={ativ.parent ?? ""} onChange={(e) => setAtiv({ ...ativ, parent: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">— (atividade de 1º nível)</option>
                  {linhas.filter((l) => l.id !== ativ.id).map((l) => <option key={l.id} value={l.id}>{"  ".repeat(l.depth)}{l.wbs} {l.title}</option>)}
                </Form.Select></div>
              <div className="col-md-6"><Form.Label>Responsável</Form.Label>
                <Form.Select value={ativ.responsible ?? ""} onChange={(e) => setAtiv({ ...ativ, responsible: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{nomeUsuario(u)}</option>)}
                </Form.Select></div>
              <div className="col-md-4"><Form.Label>Fase</Form.Label>
                <Form.Select value={ativ.phase} onChange={(e) => setAtiv({ ...ativ, phase: e.target.value })}>{FASES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Form.Select></div>
              <div className="col-md-4"><Form.Label>Início</Form.Label><Form.Control type="date" value={ativ.start_date ?? ""} onChange={(e) => setAtiv({ ...ativ, start_date: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Fim</Form.Label><Form.Control type="date" value={ativ.end_date ?? ""} onChange={(e) => setAtiv({ ...ativ, end_date: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Situação</Form.Label>
                <Form.Select value={ativ.status} onChange={(e) => setAtiv({ ...ativ, status: e.target.value })}>{Object.entries(ANDAMENTO).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Form.Select></div>
              <div className="col-md-8">
                <Form.Label>% de andamento{ativ.has_children ? " (calculado pelas subatividades)" : `: ${ativ.progress_pct ?? 0}%`}</Form.Label>
                {ativ.has_children
                  ? <div className="pt-1"><Avanco progress={ativ.progress ?? 0} late={ativ.late} width={220} /></div>
                  : <Form.Range min={0} max={100} step={5} value={ativ.progress_pct ?? 0} onChange={(e) => setAtiv({ ...ativ, progress_pct: Number(e.target.value) })} />}
              </div>
              <div className="col-12"><Form.Label>Registros (o que foi feito, decisões, pendências)</Form.Label><Form.Control as="textarea" rows={4} value={ativ.notes ?? ""} onChange={(e) => setAtiv({ ...ativ, notes: e.target.value })} /></div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          {ativ?.id && <Button variant="outline-danger" className="me-auto" onClick={excluirAtiv} title={ativ.has_children ? "Exclui também as subatividades" : undefined}>Excluir{ativ.has_children ? " com subatividades" : ""}</Button>}
          <Button variant="outline-secondary" onClick={() => setAtiv(null)}>Cancelar</Button>
          <Button onClick={salvarAtiv}>Salvar</Button>
        </Modal.Footer>
      </Modal>

      <Modal show={!!fca} onHide={() => setFca(null)} size="lg">
        <Modal.Header closeButton><Modal.Title>{fca?.id ? "FCA" : "Novo FCA"} <span className="text-muted-2 fs-6 fw-normal">fato · causa · ação</span></Modal.Title></Modal.Header>
        <Modal.Body>
          {fca && (
            <div className="row g-3">
              {erro && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erro}</Alert></div>}
              <div className="col-12"><Form.Label>Atividade *</Form.Label>
                <Form.Select value={fca.activity ?? ""} onChange={(e) => setFca({ ...fca, activity: e.target.value ? Number(e.target.value) : undefined })}>
                  <option value="">Selecione…</option>{linhas.map((l) => <option key={l.id} value={l.id}>{l.wbs} {l.title}</option>)}
                </Form.Select></div>
              <div className="col-12"><Form.Label>Fato *</Form.Label><Form.Control as="textarea" rows={2} placeholder="O que foi observado" value={fca.fact ?? ""} onChange={(e) => setFca({ ...fca, fact: e.target.value })} /></div>
              <div className="col-12"><Form.Label>Causa</Form.Label><Form.Control as="textarea" rows={2} placeholder="A causa raiz" value={fca.cause ?? ""} onChange={(e) => setFca({ ...fca, cause: e.target.value })} /></div>
              <div className="col-12"><Form.Label>Ação</Form.Label><Form.Control as="textarea" rows={2} placeholder="A ação corretiva" value={fca.action ?? ""} onChange={(e) => setFca({ ...fca, action: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Prazo</Form.Label><Form.Control type="date" value={fca.due_date ?? ""} onChange={(e) => setFca({ ...fca, due_date: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Responsável</Form.Label>
                <Form.Select value={fca.responsible ?? ""} onChange={(e) => setFca({ ...fca, responsible: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{nomeUsuario(u)}</option>)}
                </Form.Select></div>
              <div className="col-md-4"><Form.Label>Status</Form.Label>
                <Form.Select value={fca.status} onChange={(e) => setFca({ ...fca, status: e.target.value })}>{Object.entries(FCA_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Form.Select></div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          {fca?.id && <Button variant="outline-danger" className="me-auto" onClick={excluirFca}>Excluir</Button>}
          <Button variant="outline-secondary" onClick={() => setFca(null)}>Cancelar</Button>
          <Button onClick={salvarFca}>Salvar</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
