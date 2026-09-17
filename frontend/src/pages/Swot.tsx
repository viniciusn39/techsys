import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Modal, Nav } from "react-bootstrap";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_V, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { EmptyState, Panel, Skeleton } from "../components/ui";
import { useTheme } from "../hooks/useTheme";

interface Item {
  id: number;
  quadrant: "S" | "W" | "O" | "T";
  quadrant_label: string;
  text: string;
  detail: string;
  importance: number;
  intensity: number;
  trend: number;
  score: number;
  impact: number;
  org_unit: number | null;
  org_unit_name: string;
  objective: number | null;
  objective_name: string;
  projects_count: number;
}

interface Objetivo { id: number; name: string }
interface Unidade { id: number; name: string; is_active?: boolean }

const QUADRANTES: { key: Item["quadrant"]; label: string; singular: string; hint: string; icon: string; color: string; lado: string }[] = [
  { key: "S", label: "Forças", singular: "força", hint: "O que fazemos bem e é difícil de copiar", icon: "bi-shield-check", color: "#198754", lado: "Ambiente interno" },
  { key: "W", label: "Fraquezas", singular: "fraqueza", hint: "O que nos limita hoje", icon: "bi-exclamation-octagon", color: "#dc3545", lado: "Ambiente interno" },
  { key: "O", label: "Oportunidades", singular: "oportunidade", hint: "O que o mercado abre para nós", icon: "bi-lightbulb", color: "#0d6efd", lado: "Ambiente externo" },
  { key: "T", label: "Ameaças", singular: "ameaça", hint: "O que pode nos prejudicar de fora", icon: "bi-cloud-lightning", color: "#fd7e14", lado: "Ambiente externo" },
];

const IMPORTANCIA = ["Sem importância", "Pouco importante", "Importante", "Muito importante", "Totalmente importante"];
const INTENSIDADE = ["Muito fraca", "Fraca", "Média", "Forte", "Muito forte"];
const TENDENCIA = ["Piora muito", "Piora", "Mantém", "Melhora", "Melhora muito"];

/** Análise SWOT do planejamento em uso: itens pontuados (importância × intensidade × tendência), por departamento. */
export function Swot() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [itens, setItens] = useState<Item[] | null>(null);
  const [objetivos, setObjetivos] = useState<Objetivo[]>([]);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [editing, setEditing] = useState<Partial<Item> | null>(null);
  const [erro, setErro] = useState("");
  const [aba, setAba] = useState<"tradicional" | "cruzada">("tradicional");
  const [fDepto, setFDepto] = useState("");
  const [ordem, setOrdem] = useState<"desc" | "asc">("desc");

  const load = useCallback(() => {
    api.get<Item[]>("/api/swot/").then(setItens).catch((e) => { setErro(e.message); setItens([]); });
    api.get<any>("/api/strategic-maps/active/").then((m) => {
      const objs: Objetivo[] = [];
      (m?.perspectives ?? []).forEach((p: any) => (p.objectives ?? []).forEach((o: any) => objs.push({ id: o.id, name: o.name })));
      setObjetivos(objs);
    }).catch(() => {});
  }, []);

  useEffect(() => { load(); api.get<any>("/api/org-units/").then((d) => setUnidades((d.results ?? d).filter((u: Unidade) => u.is_active !== false))).catch(() => {}); }, [load]);

  const filtrados = useMemo(() => (itens ?? []).filter((i) => !fDepto || String(i.org_unit ?? "") === fDepto), [itens, fDepto]);
  const porQuadrante = useMemo(() => {
    const m: Record<string, Item[]> = { S: [], W: [], O: [], T: [] };
    filtrados.forEach((i) => m[i.quadrant].push(i));
    Object.values(m).forEach((l) => l.sort((a, b) => (ordem === "desc" ? b.score - a.score : a.score - b.score)));
    return m;
  }, [filtrados, ordem]);
  const total = (q: string) => porQuadrante[q].reduce((a, i) => a + i.score, 0);
  const totalGeral = QUADRANTES.reduce((a, q) => a + total(q.key), 0);

  const porDepto = useMemo(() => {
    const m = new Map<string, Record<string, number>>();
    filtrados.forEach((i) => {
      const nome = i.org_unit_name || "Sem departamento";
      const linha = m.get(nome) ?? { S: 0, W: 0, O: 0, T: 0 };
      linha[i.quadrant] += i.score;
      m.set(nome, linha);
    });
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtrados]);

  const novo = (q: Item["quadrant"]) => setEditing({ quadrant: q, importance: 3, intensity: 3, trend: 3, text: "", org_unit: fDepto ? Number(fDepto) : null });

  const save = async () => {
    if (!editing?.text?.trim()) return;
    const body = {
      quadrant: editing.quadrant, text: editing.text, detail: editing.detail ?? "", org_unit: editing.org_unit || null,
      importance: editing.importance ?? 3, intensity: editing.intensity ?? 3, trend: editing.trend ?? 3, objective: editing.objective ?? null,
    };
    if (editing.id) await api.patch(`/api/swot/${editing.id}/`, body);
    else await api.post("/api/swot/", body);
    setEditing(null);
    load();
  };

  const remove = async (id: number) => {
    await api.del(`/api/swot/${id}/`);
    load();
  };

  if (itens === null) return <Panel><Skeleton height={300} /></Panel>;

  const pontuacao = (editing?.importance ?? 3) * (editing?.intensity ?? 3) * (editing?.trend ?? 3);
  const quad = QUADRANTES.find((q) => q.key === editing?.quadrant);

  return (
    <div className="d-grid gap-3">
      <div className="d-flex flex-wrap align-items-center gap-2 no-print">
        <Nav variant="pills" activeKey={aba} onSelect={(k) => setAba(k as typeof aba)} className="me-auto">
          <Nav.Item><Nav.Link eventKey="tradicional" className="py-1 px-3 small">SWOT tradicional</Nav.Link></Nav.Item>
          <Nav.Item><Nav.Link eventKey="cruzada" className="py-1 px-3 small">SWOT cruzada</Nav.Link></Nav.Item>
        </Nav>
        <Form.Select size="sm" value={fDepto} onChange={(e) => setFDepto(e.target.value)} style={{ width: 230 }} aria-label="Departamento">
          <option value="">Todos os departamentos</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </Form.Select>
        <button className="btn btn-sm btn-outline-secondary" onClick={() => window.print()}><i className="bi bi-printer me-1" />Imprimir</button>
      </div>

      {aba === "tradicional" && (
        <>
          <Panel title="Análise SWOT" subtitle="Forças e fraquezas (dentro da empresa), oportunidades e ameaças (fora). Pontuação = importância × intensidade × tendência (de 1 a 125).">
            {erro && <div className="alert alert-warning py-2 small">{erro}</div>}
            <div className="row g-3">
              {QUADRANTES.map((q) => (
                <div className="col-xl-6" key={q.key}>
                  <div className="h-100 rounded" style={{ border: "1px solid var(--border)", borderTop: `4px solid ${q.color}` }}>
                    <div className="d-flex align-items-center gap-2 p-3 pb-2">
                      <i className={`bi ${q.icon}`} style={{ color: q.color, fontSize: "1.2rem" }} />
                      <div>
                        <div className="fw-semibold">{q.label} <span className="text-muted-2 fw-normal small">· {q.lado}</span></div>
                        <div className="small text-muted-2">{q.hint}</div>
                      </div>
                      <Button size="sm" variant="outline-secondary" className="ms-auto no-print" onClick={() => novo(q.key)}><i className="bi bi-plus-lg me-1" />Adicionar</Button>
                    </div>
                    <div className="px-3 pb-3">
                      {porQuadrante[q.key].length === 0 ? <div className="small text-muted-2">Nenhum item ainda.</div> : (
                        <table className="table table-sm table-hover align-middle mb-0">
                          <thead><tr>
                            <th>Descrição</th>
                            <th className="num" role="button" onClick={() => setOrdem(ordem === "desc" ? "asc" : "desc")} title="Ordenar pela pontuação">Pontuação <i className={`bi ${ordem === "desc" ? "bi-sort-down" : "bi-sort-up"}`} /></th>
                            <th className="num">Projetos</th>
                            <th className="no-print" />
                          </tr></thead>
                          <tbody>
                            {porQuadrante[q.key].map((i) => (
                              <tr key={i.id}>
                                <td role="button" onClick={() => setEditing(i)}>
                                  <div className="fw-semibold small">{i.text}</div>
                                  {i.detail && <div className="small text-muted-2 text-truncate" style={{ maxWidth: 360 }}>{i.detail}</div>}
                                  {(i.org_unit_name || i.objective_name) && (
                                    <div className="small text-muted-2">
                                      {i.org_unit_name && <span className="me-2"><i className="bi bi-diagram-2 me-1" />{i.org_unit_name}</span>}
                                      {i.objective_name && <span><i className="bi bi-bullseye me-1" />{i.objective_name}</span>}
                                    </div>
                                  )}
                                </td>
                                <td className="num fw-semibold" title={`${i.importance} × ${i.intensity} × ${i.trend}`} style={{ color: q.color }}>{i.score}</td>
                                <td className="num">{i.projects_count > 0 ? <Link to="/projetos" title="Projetos que tratam este item">{i.projects_count}</Link> : <span className="text-muted-2">0</span>}</td>
                                <td className="text-end text-nowrap no-print">
                                  <Button size="sm" variant="link" className="p-1" title="Editar" onClick={() => setEditing(i)}><i className="bi bi-pencil" /></Button>
                                  <Button size="sm" variant="link" className="p-1 text-danger" title="Excluir" onClick={() => remove(i.id)}><i className="bi bi-trash" /></Button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot><tr><td className="small text-muted-2">Total</td><td className="num fw-semibold" style={{ color: q.color }}>{total(q.key)} pontos</td><td /><td className="no-print" /></tr></tfoot>
                        </table>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {itens.length === 0 && <div className="mt-3"><EmptyState icon="bi-grid-3x3-gap" title="Comece pelas forças" hint="Liste o que a empresa faz bem hoje; depois fraquezas, oportunidades e ameaças." /></div>}
          </Panel>

          {filtrados.length > 0 && (
            <>
              <div className="row g-3">
                <div className="col-xl-4">
                  <Panel title="Resumo SWOT" subtitle="Soma da pontuação por quadrante" className="h-100">
                    {QUADRANTES.map((q) => (
                      <div key={q.key} className="d-flex justify-content-between align-items-center py-2" style={{ borderBottom: "1px solid var(--border)" }}>
                        <span><i className={`bi ${q.icon} me-2`} style={{ color: q.color }} />{q.label}</span><span className="fw-semibold num">{total(q.key)}</span>
                      </div>
                    ))}
                    <div className="d-flex justify-content-between pt-2 fw-semibold"><span>Total geral</span><span className="num">{totalGeral}</span></div>
                  </Panel>
                </div>
                <div className="col-xl-4">
                  <Panel title="Radar" subtitle="O peso de cada quadrante" className="h-100">
                    <EChart height={240} option={{
                      tooltip: {},
                      radar: { indicator: QUADRANTES.map((q) => ({ name: q.label, max: Math.max(1, ...QUADRANTES.map((x) => total(x.key))) })), radius: "62%", axisName: { color: t.inkSecondary }, splitLine: { lineStyle: { color: t.grid } }, splitArea: { show: false }, axisLine: { lineStyle: { color: t.grid } } },
                      series: [{ type: "radar", data: [{ value: QUADRANTES.map((q) => total(q.key)), name: "Pontuação" }], lineStyle: { color: t.series[0], width: 2 }, itemStyle: { color: t.series[0] }, areaStyle: { color: t.series[0], opacity: 0.12 } }],
                    }} />
                  </Panel>
                </div>
                <div className="col-xl-4">
                  <Panel title="Comparativo" subtitle="Pontuação por quadrante" className="h-100">
                    <EChart height={240} option={{
                      grid: { left: 4, right: 8, top: 24, bottom: 4, containLabel: true },
                      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
                      xAxis: { type: "category", data: QUADRANTES.map((q) => q.label), axisLabel: { interval: 0, fontSize: 10 } },
                      yAxis: { type: "value" },
                      series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, label: { show: true, position: "top" }, data: QUADRANTES.map((q) => ({ value: total(q.key), itemStyle: { color: q.color, borderRadius: BAR_RADIUS_V } })) }],
                    }} />
                  </Panel>
                </div>
              </div>

              <Panel title="Resumo por departamento" subtitle="Onde estão os pontos de cada quadrante">
                <div className="table-responsive">
                  <table className="table table-sm align-middle mb-0">
                    <thead><tr><th>Departamento</th>{QUADRANTES.map((q) => <th key={q.key} className="num">{q.label}</th>)}<th className="num">Total</th></tr></thead>
                    <tbody>
                      {porDepto.map(([nome, l]) => (
                        <tr key={nome}><td>{nome}</td>{QUADRANTES.map((q) => <td key={q.key} className="num">{l[q.key] || <span className="text-muted-2">0</span>}</td>)}<td className="num fw-semibold">{l.S + l.W + l.O + l.T}</td></tr>
                      ))}
                    </tbody>
                    <tfoot><tr className="fw-semibold"><td>Total</td>{QUADRANTES.map((q) => <td key={q.key} className="num">{total(q.key)}</td>)}<td className="num">{totalGeral}</td></tr></tfoot>
                  </table>
                </div>
              </Panel>
            </>
          )}
        </>
      )}

      {aba === "cruzada" && <MatrizSwot itens={filtrados} objetivos={objetivos} />}

      <Modal show={!!editing} onHide={() => setEditing(null)}>
        <Modal.Header closeButton><Modal.Title><i className={`bi ${quad?.icon} me-2`} style={{ color: quad?.color }} />{editing?.id ? "Editar" : "Nova"} {quad?.singular}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="row g-3">
              <div className="col-12"><Form.Label>Título *</Form.Label>
                <Form.Control autoFocus value={editing.text ?? ""} onChange={(e) => setEditing({ ...editing, text: e.target.value })} placeholder="Ex.: Frota própria com entrega em 24 h" /></div>
              <div className="col-md-6"><Form.Label>Departamento</Form.Label>
                <Form.Select value={editing.org_unit ?? ""} onChange={(e) => setEditing({ ...editing, org_unit: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Nenhum</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </Form.Select></div>
              <div className="col-md-6"><Form.Label>Quadrante</Form.Label>
                <Form.Select value={editing.quadrant} onChange={(e) => setEditing({ ...editing, quadrant: e.target.value as Item["quadrant"] })}>
                  {QUADRANTES.map((q) => <option key={q.key} value={q.key}>{q.label}</option>)}
                </Form.Select></div>
              <div className="col-12"><Form.Label>Descrição</Form.Label>
                <Form.Control as="textarea" rows={2} value={editing.detail ?? ""} onChange={(e) => setEditing({ ...editing, detail: e.target.value })} placeholder="Detalhes adicionais (opcional)" /></div>
              {([["importance", "Importância", IMPORTANCIA], ["intensity", "Intensidade", INTENSIDADE], ["trend", "Tendência", TENDENCIA]] as ["importance" | "intensity" | "trend", string, string[]][]).map(([campo, rotulo, opcoes]) => (
                <div className="col-md-4" key={campo}><Form.Label>{rotulo}</Form.Label>
                  <Form.Select value={editing[campo] ?? 3} onChange={(e) => setEditing({ ...editing, [campo]: Number(e.target.value) })}>
                    {opcoes.map((o, n) => <option key={o} value={n + 1}>{n + 1} - {o}</option>)}
                  </Form.Select></div>
              ))}
              <div className="col-12">
                <div className="d-flex justify-content-between align-items-center p-2 rounded" style={{ background: "var(--surface-sunken)" }}>
                  <span className="small text-muted-2">Pontuação calculada ({editing.importance ?? 3} × {editing.intensity ?? 3} × {editing.trend ?? 3})</span>
                  <span className="fs-5 fw-semibold" style={{ color: quad?.color }}>{pontuacao}</span>
                </div>
              </div>
              <div className="col-12"><Form.Label>Objetivo do mapa que responde a este item</Form.Label>
                <Form.Select value={editing.objective ?? ""} onChange={(e) => setEditing({ ...editing, objective: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>
                  {objetivos.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </Form.Select></div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save}>{editing?.id ? "Salvar" : "Criar item"}</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}


interface Estrategia { id: number; kind: "SO" | "WO" | "ST" | "WT"; text: string; objective: number | null; objective_name: string }

const CRUZAMENTOS: Record<Estrategia["kind"], { titulo: string; hint: string }> = {
  SO: { titulo: "Ofensiva", hint: "Usar as forças para aproveitar as oportunidades" },
  WO: { titulo: "Reforço", hint: "Corrigir fraquezas para não perder oportunidades" },
  ST: { titulo: "Defesa", hint: "Usar as forças para neutralizar ameaças" },
  WT: { titulo: "Sobrevivência", hint: "Reduzir fraquezas expostas às ameaças" },
};

/** Matriz SWOT cruzada: forças/fraquezas × oportunidades/ameaças, com as estratégias de cada célula. */
function MatrizSwot({ itens, objetivos }: { itens: Item[]; objetivos: Objetivo[] }) {
  const [lista, setLista] = useState<Estrategia[]>([]);
  const [novo, setNovo] = useState<{ kind: Estrategia["kind"]; text: string } | null>(null);
  const [editando, setEditando] = useState<Estrategia | null>(null);

  const load = useCallback(() => { api.get<Estrategia[]>("/api/swot-estrategias/").then(setLista).catch(() => setLista([])); }, []);
  useEffect(() => { load(); }, [load]);

  const top = (q: Item["quadrant"]) => itens.filter((i) => i.quadrant === q).sort((a, b) => b.score - a.score).slice(0, 4);
  const salvarNovo = async () => {
    if (novo?.text.trim()) await api.post("/api/swot-estrategias/", { kind: novo.kind, text: novo.text.trim() });
    setNovo(null); load();
  };
  const salvarEdicao = async () => {
    if (!editando) return;
    await api.patch(`/api/swot-estrategias/${editando.id}/`, { text: editando.text, objective: editando.objective });
    setEditando(null); load();
  };
  const remover = async (id: number) => { await api.del(`/api/swot-estrategias/${id}/`); load(); };

  const Celula = ({ kind }: { kind: Estrategia["kind"] }) => {
    const c = CRUZAMENTOS[kind];
    const es = lista.filter((e) => e.kind === kind);
    return (
      <div className="p-3 h-100" style={{ background: "var(--surface-sunken)", borderRadius: 10, border: "1px solid var(--border)" }}>
        <div className="d-flex align-items-center gap-2 mb-1">
          <span className="badge rounded-pill" style={{ background: "var(--brand-soft)", color: "var(--brand)" }}>{kind}</span>
          <span className="fw-semibold small">{c.titulo}</span>
          <button className="btn btn-sm btn-link p-0 ms-auto no-print" title="Adicionar estratégia" onClick={() => setNovo({ kind, text: "" })}><i className="bi bi-plus-lg" /></button>
        </div>
        <div className="small text-muted-2 mb-2">{c.hint}</div>
        <ul className="ps-3 mb-0 small">
          {es.map((e) => (
            <li key={e.id} className="mb-1" role="button" onClick={() => setEditando(e)}>
              {e.text}{e.objective_name && <span className="text-muted-2"> · {e.objective_name}</span>}
              <button className="btn btn-sm btn-link text-danger p-0 ms-1 no-print" onClick={(ev) => { ev.stopPropagation(); remover(e.id); }}><i className="bi bi-x" /></button>
            </li>
          ))}
        </ul>
        {novo?.kind === kind && (
          <input autoFocus className="form-control form-control-sm mt-2" placeholder="Estratégia e Enter" value={novo.text}
            onChange={(e) => setNovo({ kind, text: e.target.value })} onBlur={salvarNovo}
            onKeyDown={(e) => { if (e.key === "Enter") salvarNovo(); if (e.key === "Escape") setNovo(null); }} />
        )}
        {es.length === 0 && novo?.kind !== kind && <div className="small text-muted-2 fst-italic">Nenhuma estratégia ainda.</div>}
      </div>
    );
  };

  const Fatores = ({ q, titulo }: { q: Item["quadrant"]; titulo: string }) => (
    <div className="p-2 h-100">
      <div className="fw-semibold small mb-1">{titulo}</div>
      <ul className="ps-3 mb-0 small text-muted-2">{top(q).map((i) => <li key={i.id}>{i.text}</li>)}{top(q).length === 0 && <li>—</li>}</ul>
    </div>
  );

  return (
    <Panel title="Matriz SWOT cruzada" subtitle="Cada célula responde: o que fazemos com esta combinação? Os fatores de maior pontuação aparecem nas bordas; as estratégias viram objetivos e planos de ação.">
      <div style={{ display: "grid", gridTemplateColumns: "minmax(160px, 1fr) 2fr 2fr", gap: 8 }}>
        <div />
        <Fatores q="O" titulo="Oportunidades (externo)" />
        <Fatores q="T" titulo="Ameaças (externo)" />
        <Fatores q="S" titulo="Forças (interno)" />
        <Celula kind="SO" />
        <Celula kind="ST" />
        <Fatores q="W" titulo="Fraquezas (interno)" />
        <Celula kind="WO" />
        <Celula kind="WT" />
      </div>

      <Modal show={!!editando} onHide={() => setEditando(null)}>
        <Modal.Header closeButton><Modal.Title>Estratégia · {editando && CRUZAMENTOS[editando.kind].titulo}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editando && (
            <div className="d-grid gap-3">
              <Form.Control as="textarea" rows={2} autoFocus value={editando.text} onChange={(e) => setEditando({ ...editando, text: e.target.value })} />
              <Form.Group>
                <Form.Label>Objetivo do mapa que realiza esta estratégia</Form.Label>
                <Form.Select value={editando.objective ?? ""} onChange={(e) => setEditando({ ...editando, objective: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>
                  {objetivos.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </Form.Select>
              </Form.Group>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditando(null)}>Cancelar</Button>
          <Button onClick={salvarEdicao}>Salvar</Button>
        </Modal.Footer>
      </Modal>
    </Panel>
  );
}
