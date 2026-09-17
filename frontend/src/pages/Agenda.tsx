import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Collapse, Form, Modal } from "react-bootstrap";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { EmptyState, Panel, Skeleton } from "../components/ui";

interface Agenda {
  id: number; title: string; description: string; color: string; category: number | null; category_name: string;
  kind: string; kind_label: string; status: string; status_label: string;
  starts_at: string; ends_at: string | null; location: string; org_unit: number | null; org_unit_name: string;
  organizer: number | null; organizer_name: string; participants: number[]; participant_names: string[];
  stakeholders: number[]; stakeholder_names: string[]; indicators: number[]; indicator_codes: string[];
  map: number | null; map_name: string; project: number | null; project_title: string; labels: string[];
  agenda: string; minutes: string; decisions: string;
}
/** O formulário separa data e hora, como na agenda de trabalho: início e fim podem ser em dias diferentes. */
type Edicao = Partial<Agenda> & { dIni: string; hIni: string; dFim: string; hFim: string };
interface Opcao { id: number; name?: string; title?: string; first_name?: string; last_name?: string; email?: string; code?: string | number; map?: number | null }
interface Categoria { id: number; name: string; meetings_count: number }

const TIPOS = [
  ["outra", "Agenda comum"], ["resultados", "Reunião de resultados"], ["planejamento", "Planejamento estratégico"],
  ["acompanhamento", "Acompanhamento de planos"], ["diretoria", "Diretoria"],
];
const CORES: [string, string, string][] = [
  ["azul", "Azul", "#2a78d6"], ["verde", "Verde", "#1baf7a"], ["amarelo", "Amarelo", "#eda100"], ["vermelho", "Vermelho", "#d03b3b"], ["roxo", "Roxo", "#7c5cd6"],
  ["rosa", "Rosa", "#d6488f"], ["ciano", "Ciano", "#15aabf"], ["laranja", "Laranja", "#eb6834"], ["cinza", "Cinza", "#6b717b"],
];
const HEX = Object.fromEntries(CORES.map(([k, , h]) => [k, h]));
const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const HORAS = Array.from({ length: 16 }, (_, i) => i + 6); // 06h às 21h

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const hhmm = (d: Date) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
const hora = (s: string) => hhmm(new Date(s));
const nomeDe = (u: Opcao) => [u.first_name, u.last_name].filter(Boolean).join(" ") || u.email || u.name || "";
const fimDe = (a: Agenda) => a.ends_at ?? a.starts_at;
const variosDias = (a: Agenda) => iso(new Date(a.starts_at)) !== iso(new Date(fimDe(a)));

/** Faixa do evento: cor só como detalhe (borda e ponto), no padrão do sistema. */
function Faixa({ a, dia, onClick, compacta = false }: { a: Agenda; dia: string; onClick: () => void; compacta?: boolean }) {
  const comeca = iso(new Date(a.starts_at)) === dia;
  return (
    <div role="button" onClick={(e) => { e.stopPropagation(); onClick(); }} title={`${a.title}${a.category_name ? ` · ${a.category_name}` : ""}`}
      className="text-truncate px-1 rounded mb-1"
      style={{ fontSize: compacta ? "0.7rem" : "0.8rem", background: "var(--surface-sunken)", borderLeft: `3px solid ${HEX[a.color] ?? HEX.azul}`, textDecoration: a.status === "cancelada" ? "line-through" : undefined }}>
      {comeca && !variosDias(a) && <span className="text-muted-2 me-1">{hora(a.starts_at)}</span>}{a.title}
    </div>
  );
}

/** Agenda de trabalho e folgas das pessoas, e das reuniões de gestão (pauta, ata, decisões). */
export function Agenda() {
  const navigate = useNavigate();
  const { me } = useAuth();
  const podeEditar = me?.role !== "colaborador";
  const hoje = new Date();
  const [ano, setAno] = useState(hoje.getFullYear());
  const [mes, setMes] = useState(hoje.getMonth());
  const [dia, setDia] = useState<string>(iso(hoje));
  const [visao, setVisao] = useState<"mensal" | "diario">("mensal");
  const [fPessoa, setFPessoa] = useState("");
  const [fEtiqueta, setFEtiqueta] = useState("");
  const [agendas, setAgendas] = useState<Agenda[] | null>(null);
  const [editing, setEditing] = useState<Edicao | null>(null);
  const [erro, setErro] = useState("");
  const [gestao, setGestao] = useState(false);
  const [usuarios, setUsuarios] = useState<Opcao[]>([]);
  const [stakeholders, setStakeholders] = useState<Opcao[]>([]);
  const [indicadores, setIndicadores] = useState<Opcao[]>([]);
  const [unidades, setUnidades] = useState<Opcao[]>([]);
  const [mapas, setMapas] = useState<Opcao[]>([]);
  const [projetos, setProjetos] = useState<Opcao[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [etiquetas, setEtiquetas] = useState<string[]>([]);
  const [editCats, setEditCats] = useState(false);
  const [novaCat, setNovaCat] = useState("");

  const load = useCallback(() => {
    const q = new URLSearchParams({ de: iso(new Date(ano, mes, 1 - 7)), ate: iso(new Date(ano, mes + 1, 7)) });
    if (fPessoa) q.set("pessoa", fPessoa);
    if (fEtiqueta) q.set("etiqueta", fEtiqueta);
    api.get<Agenda[]>(`/api/meetings/?${q}`).then(setAgendas).catch(() => setAgendas([]));
    api.get<string[]>("/api/meetings/etiquetas/").then(setEtiquetas).catch(() => {});
  }, [ano, mes, fPessoa, fEtiqueta]);
  const loadCats = useCallback(() => { api.get<Categoria[]>("/api/agenda-categorias/").then(setCategorias).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    loadCats();
    api.get<any>("/api/users/").then((d) => setUsuarios(d.results ?? d)).catch(() => {});
    api.get<Opcao[]>("/api/stakeholders/").then(setStakeholders).catch(() => {});
    api.get<any>("/api/indicators/").then((d) => setIndicadores(d.results ?? d)).catch(() => {});
    api.get<any>("/api/org-units/").then((d) => setUnidades(d.results ?? d)).catch(() => {});
    api.get<any>("/api/strategic-maps/").then((d) => setMapas(d.results ?? d)).catch(() => {});
    api.get<Opcao[]>("/api/projects/").then(setProjetos).catch(() => {});
  }, [loadCats]);

  // Agenda de vários dias aparece em todos os dias que cobre.
  const porDia = useMemo(() => {
    const m: Record<string, Agenda[]> = {};
    (agendas ?? []).forEach((a) => {
      const fim = new Date(fimDe(a));
      for (let d = new Date(new Date(a.starts_at).toDateString()); d <= fim; d.setDate(d.getDate() + 1)) (m[iso(d)] = m[iso(d)] ?? []).push(a);
    });
    Object.values(m).forEach((l) => l.sort((a, b) => a.starts_at.localeCompare(b.starts_at)));
    return m;
  }, [agendas]);

  const celulas = useMemo(() => {
    const out: { d: Date; fora: boolean }[] = [];
    const ini = new Date(ano, mes, 1 - new Date(ano, mes, 1).getDay());
    for (let i = 0; i < 42; i++) { const d = new Date(ini); d.setDate(ini.getDate() + i); out.push({ d, fora: d.getMonth() !== mes }); }
    return out.slice(0, out[35].d.getMonth() === mes ? 42 : 35);
  }, [ano, mes]);

  const irPara = (d: Date) => { setAno(d.getFullYear()); setMes(d.getMonth()); setDia(iso(d)); };
  const mover = (delta: number) => {
    if (visao === "mensal") { const d = new Date(ano, mes + delta, 1); setAno(d.getFullYear()); setMes(d.getMonth()); }
    else { const d = new Date(`${dia}T00:00`); d.setDate(d.getDate() + delta); irPara(d); }
  };

  const nova = (d: string) => {
    setErro(""); setGestao(false);
    setEditing({ title: "", description: "", color: "azul", kind: "outra", status: "agendada", organizer: me?.id ?? null,
      category: categorias.find((c) => c.name === "Trabalho")?.id ?? categorias[0]?.id ?? null,
      participants: [], stakeholders: [], indicators: [], map: null, project: null, location: "", agenda: "", minutes: "", decisions: "",
      dIni: d, hIni: "08:00", dFim: d, hFim: "18:00" });
  };
  const abrir = (a: Agenda) => {
    const i = new Date(a.starts_at), f = new Date(fimDe(a));
    setErro(""); setGestao(a.kind !== "outra" || !!(a.agenda || a.minutes || a.decisions));
    setEditing({ ...a, dIni: iso(i), hIni: hhmm(i), dFim: iso(f), hFim: a.ends_at ? hhmm(f) : hhmm(i) });
  };

  const save = async () => {
    if (!editing) return;
    if (!editing.title?.trim() || !editing.organizer || !editing.dIni || !editing.dFim) { setErro("Preencha título, responsável e as datas de início e fim."); return; }
    const body = {
      title: editing.title, description: editing.description ?? "", color: editing.color, category: editing.category || null,
      organizer: editing.organizer, participants: editing.participants ?? [], map: editing.map || null, project: editing.project || null,
      starts_at: new Date(`${editing.dIni}T${editing.hIni || "08:00"}`).toISOString(), ends_at: new Date(`${editing.dFim}T${editing.hFim || "18:00"}`).toISOString(),
      kind: editing.kind, status: editing.status, location: editing.location ?? "", org_unit: editing.org_unit || null,
      stakeholders: editing.stakeholders ?? [], indicators: editing.indicators ?? [],
      agenda: editing.agenda ?? "", minutes: editing.minutes ?? "", decisions: editing.decisions ?? "",
    };
    try {
      if (editing.id) await api.patch(`/api/meetings/${editing.id}/`, body);
      else await api.post("/api/meetings/", body);
      setEditing(null);
      load();
    } catch (e) {
      const d = (e as ApiError).data;
      setErro(d && typeof d === "object" ? Object.values(d).flat().join(" ") : (e as Error).message);
    }
  };
  const remove = async () => { if (editing?.id) { await api.del(`/api/meetings/${editing.id}/`); setEditing(null); load(); } };

  const criarCat = async () => {
    if (!novaCat.trim()) return;
    try { await api.post("/api/agenda-categorias/", { name: novaCat.trim(), order: categorias.length }); setNovaCat(""); loadCats(); }
    catch (e) { setErro((e as ApiError).data?.name?.[0] ?? (e as Error).message); }
  };
  const excluirCat = async (c: Categoria) => { await api.del(`/api/agenda-categorias/${c.id}/`); loadCats(); load(); };

  const alternar = (vals: number[] | undefined, id: number) => { const s = new Set(vals ?? []); s.has(id) ? s.delete(id) : s.add(id); return Array.from(s); };

  if (agendas === null) return <Panel><Skeleton height={400} /></Panel>;

  const doDia = porDia[dia] ?? [];
  const diaLongo = new Date(`${dia}T00:00`).toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const projetosDoMapa = projetos.filter((p) => !editing?.map || p.map === editing.map);

  return (
    <div className="d-grid gap-3">
      <div className="d-flex flex-wrap align-items-center gap-2">
        <div className="btn-group btn-group-sm">
          <button className="btn btn-outline-secondary" onClick={() => mover(-1)} aria-label="Anterior"><i className="bi bi-chevron-left" /></button>
          <button className="btn btn-outline-secondary" onClick={() => irPara(new Date())}>Hoje</button>
          <button className="btn btn-outline-secondary" onClick={() => mover(1)} aria-label="Próximo"><i className="bi bi-chevron-right" /></button>
        </div>
        <span className="fw-semibold text-capitalize me-auto">{visao === "mensal" ? `${MESES[mes]} ${ano}` : diaLongo}</span>
        <Form.Select size="sm" value={fPessoa} onChange={(e) => setFPessoa(e.target.value)} style={{ width: 190 }} aria-label="Pessoa">
          <option value="">Pessoa: todas</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{nomeDe(u)}</option>)}
        </Form.Select>
        <Form.Select size="sm" value={fEtiqueta} onChange={(e) => setFEtiqueta(e.target.value)} style={{ width: 170 }} aria-label="Etiqueta">
          <option value="">Etiqueta: todas</option>{etiquetas.map((e) => <option key={e}>{e}</option>)}
        </Form.Select>
        <div className="btn-group btn-group-sm" role="group" aria-label="Visão">
          <button className={`btn ${visao === "mensal" ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setVisao("mensal")}>Mensal</button>
          <button className={`btn ${visao === "diario" ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setVisao("diario")}>Diário</button>
        </div>
        <Button size="sm" variant="outline-secondary" onClick={() => navigate("/painel-agenda")}><i className="bi bi-calendar2-week me-1" />Painel</Button>
        <Button size="sm" variant="outline-secondary" onClick={() => window.print()}><i className="bi bi-printer me-1" />Imprimir</Button>
        {podeEditar && <Button size="sm" onClick={() => nova(dia)}><i className="bi bi-plus-lg me-1" />Nova agenda</Button>}
      </div>

      <div className="row g-3">
        <div className="col-xl-8">
          <Panel title="Agendas" subtitle="Agendas de trabalho e folgas das pessoas, e as reuniões de gestão com pauta, ata e decisões.">
            {visao === "mensal" ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
                {["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"].map((d) => <div key={d} className="small text-muted-2 text-center fw-semibold py-1">{d}</div>)}
                {celulas.map(({ d, fora }) => {
                  const k = iso(d);
                  const lista = porDia[k] ?? [];
                  const ehHoje = k === iso(hoje);
                  return (
                    <div key={k} onClick={() => setDia(k)} onDoubleClick={() => podeEditar && nova(k)} role="button"
                      style={{ minHeight: 88, border: `1px solid ${k === dia ? "var(--brand)" : "var(--border)"}`, borderRadius: 8, padding: 4, background: fora ? "var(--surface-sunken)" : k === dia ? "var(--brand-soft)" : "transparent", opacity: fora ? 0.6 : 1, minWidth: 0 }}>
                      <div className={`small ${ehHoje ? "fw-bold" : ""}`} style={ehHoje ? { color: "var(--brand)" } : undefined}>{d.getDate()}</div>
                      {lista.slice(0, 3).map((a) => <Faixa key={a.id} a={a} dia={k} onClick={() => { setDia(k); if (podeEditar) abrir(a); }} compacta />)}
                      {lista.length > 3 && <div className="small text-muted-2">+{lista.length - 3}</div>}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div>
                {doDia.filter(variosDias).length > 0 && (
                  <div className="mb-2 pb-2" style={{ borderBottom: "1px solid var(--border)" }}>
                    <div className="small text-muted-2 mb-1">Vários dias</div>
                    {doDia.filter(variosDias).map((a) => <Faixa key={a.id} a={a} dia={dia} onClick={() => podeEditar && abrir(a)} />)}
                  </div>
                )}
                {HORAS.map((h) => {
                  const naHora = doDia.filter((a) => !variosDias(a) && Math.min(21, Math.max(6, new Date(a.starts_at).getHours())) === h);
                  return (
                    <div key={h} className="d-flex gap-2" style={{ borderTop: "1px solid var(--border)", minHeight: 34 }} onDoubleClick={() => podeEditar && nova(dia)}>
                      <div className="small text-muted-2 pt-1" style={{ width: 44 }}>{String(h).padStart(2, "0")}:00</div>
                      <div className="flex-grow-1 pt-1" style={{ minWidth: 0 }}>
                        {naHora.map((a) => (
                          <div key={a.id} role="button" onClick={() => podeEditar && abrir(a)} className="px-2 py-1 rounded mb-1 small" style={{ background: "var(--surface-sunken)", borderLeft: `3px solid ${HEX[a.color] ?? HEX.azul}` }}>
                            <span className="fw-semibold">{hora(a.starts_at)}{a.ends_at ? `–${hora(a.ends_at)}` : ""} · {a.title}</span>
                            <span className="text-muted-2"> · {[a.category_name, a.organizer_name, a.project_title].filter(Boolean).join(" · ")}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="d-flex flex-wrap gap-3 mt-3 small text-muted-2">
              <span>Dê dois cliques num dia para criar uma agenda nele.</span>
              <span>Etiquetas: escreva (cliente), [urgente] ou "fechamento" no título.</span>
            </div>
          </Panel>
        </div>

        <div className="col-xl-4">
          <Panel title={diaLongo.replace(/^./, (c) => c.toUpperCase())} subtitle={doDia.length === 0 ? "Nenhuma agenda para este dia" : `${doDia.length} agenda(s)`}
            actions={podeEditar ? <Button size="sm" variant="outline-secondary" onClick={() => nova(dia)} aria-label="Nova agenda neste dia"><i className="bi bi-plus-lg" /></Button> : undefined}>
            {doDia.length === 0 ? (
              <EmptyState icon="bi-calendar3" title="Nenhuma agenda neste dia" action={podeEditar ? <Button size="sm" variant="link" onClick={() => nova(dia)}>Criar nova agenda</Button> : undefined} />
            ) : doDia.map((a) => (
              <div key={a.id} className="p-2 rounded mb-2" style={{ background: "var(--surface-sunken)", borderLeft: `3px solid ${HEX[a.color] ?? HEX.azul}` }} role={podeEditar ? "button" : undefined} onClick={() => podeEditar && abrir(a)}>
                <div className="fw-semibold small">{a.title}</div>
                <div className="small text-muted-2">
                  {variosDias(a)
                    ? `${new Date(a.starts_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} ${hora(a.starts_at)} até ${new Date(fimDe(a)).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} ${hora(fimDe(a))}`
                    : `${hora(a.starts_at)}${a.ends_at ? `–${hora(a.ends_at)}` : ""}`}
                  {a.category_name && ` · ${a.category_name}`}{a.kind !== "outra" && ` · ${a.kind_label}`} · {a.status_label}
                </div>
                <div className="small text-muted-2"><i className="bi bi-person me-1" />{[a.organizer_name, ...a.participant_names.filter((n) => n !== a.organizer_name)].filter(Boolean).join(", ") || "—"}</div>
                {(a.map_name || a.project_title) && <div className="small text-muted-2"><i className="bi bi-folder2-open me-1" />{[a.map_name, a.project_title].filter(Boolean).join(" · ")}</div>}
                {a.labels.length > 0 && <div className="mt-1">{a.labels.map((l) => <span key={l} className="badge text-bg-light border fw-normal me-1">{l}</span>)}</div>}
              </div>
            ))}
          </Panel>
        </div>
      </div>

      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg" scrollable>
        <Modal.Header closeButton><Modal.Title>{editing?.id ? "Agenda" : "Nova agenda"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="row g-3">
              {erro && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erro}</Alert></div>}
              <div className="col-12"><Form.Label>Título da agenda *</Form.Label>
                <Form.Control autoFocus value={editing.title ?? ""} onChange={(e) => setEditing({ ...editing, title: e.target.value })} placeholder="Ex.: (CLIENTE) Reunião de alinhamento" />
                <Form.Text>Use (rótulo), [rótulo] ou "rótulo" dentro do título para etiquetar.</Form.Text></div>
              <div className="col-12"><Form.Label>Descrição</Form.Label><Form.Control as="textarea" rows={2} value={editing.description ?? ""} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></div>
              <div className="col-12"><Form.Label>Cor da agenda</Form.Label>
                <div className="d-flex gap-2">
                  {CORES.map(([k, rotulo, hex]) => (
                    <button key={k} type="button" title={rotulo} aria-label={rotulo} aria-pressed={editing.color === k} onClick={() => setEditing({ ...editing, color: k })}
                      style={{ width: 26, height: 26, borderRadius: "50%", background: hex, border: "2px solid var(--surface)", outline: editing.color === k ? `2px solid ${hex}` : "none", color: "#fff", fontSize: "0.7rem", lineHeight: 1 }}>
                      {editing.color === k && <i className="bi bi-check-lg" />}
                    </button>
                  ))}
                </div></div>
              <div className="col-md-6"><Form.Label>Responsável *</Form.Label>
                <Form.Select value={editing.organizer ?? ""} onChange={(e) => setEditing({ ...editing, organizer: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Selecione…</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{nomeDe(u)}</option>)}
                </Form.Select></div>
              <div className="col-md-6"><Form.Label>Categoria</Form.Label>
                <div className="d-flex gap-2">
                  <Form.Select value={editing.category ?? ""} onChange={(e) => setEditing({ ...editing, category: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">—</option>{categorias.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </Form.Select>
                  <Button variant="outline-secondary" title="Editar categorias" onClick={() => setEditCats(true)}><i className="bi bi-pencil" /></Button>
                </div></div>
              <div className="col-12">
                <div className="d-flex justify-content-between"><Form.Label>Pessoas vinculadas</Form.Label>
                  <Button variant="link" size="sm" className="p-0" onClick={() => setEditing({ ...editing, participants: usuarios.map((u) => u.id) })}>Vincular todos</Button></div>
                <div className="d-flex flex-wrap gap-1">{usuarios.map((u) => <button type="button" key={u.id} className={`btn btn-sm ${editing.participants?.includes(u.id) ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setEditing({ ...editing, participants: alternar(editing.participants, u.id) })}>{nomeDe(u)}</button>)}</div>
              </div>
              <div className="col-md-6"><Form.Label>Planejamento</Form.Label>
                <Form.Select value={editing.map ?? ""} onChange={(e) => setEditing({ ...editing, map: e.target.value ? Number(e.target.value) : null, project: null })}>
                  <option value="">—</option>{mapas.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </Form.Select></div>
              <div className="col-md-6"><Form.Label>Projeto</Form.Label>
                <Form.Select value={editing.project ?? ""} onChange={(e) => setEditing({ ...editing, project: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>{projetosDoMapa.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.title}</option>)}
                </Form.Select></div>
              <div className="col-md-3 col-6"><Form.Label>Data de início *</Form.Label><Form.Control type="date" value={editing.dIni} onChange={(e) => setEditing({ ...editing, dIni: e.target.value, dFim: editing.dFim < e.target.value ? e.target.value : editing.dFim })} /></div>
              <div className="col-md-3 col-6"><Form.Label>Horário de início *</Form.Label><Form.Control type="time" value={editing.hIni} onChange={(e) => setEditing({ ...editing, hIni: e.target.value })} /></div>
              <div className="col-md-3 col-6"><Form.Label>Data de fim *</Form.Label><Form.Control type="date" value={editing.dFim} min={editing.dIni} onChange={(e) => setEditing({ ...editing, dFim: e.target.value })} /></div>
              <div className="col-md-3 col-6"><Form.Label>Horário de fim *</Form.Label><Form.Control type="time" value={editing.hFim} onChange={(e) => setEditing({ ...editing, hFim: e.target.value })} /></div>

              <div className="col-12">
                <Button variant="link" size="sm" className="p-0" onClick={() => setGestao(!gestao)} aria-expanded={gestao}>
                  <i className={`bi ${gestao ? "bi-chevron-down" : "bi-chevron-right"} me-1`} />Reunião de gestão: tipo, situação, local, pauta, ata, decisões e indicadores
                </Button>
              </div>
              <Collapse in={gestao}>
                <div className="col-12">
                  <div className="row g-3">
                    <div className="col-md-4"><Form.Label>Tipo</Form.Label><Form.Select value={editing.kind} onChange={(e) => setEditing({ ...editing, kind: e.target.value })}>{TIPOS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Form.Select></div>
                    <div className="col-md-4"><Form.Label>Situação</Form.Label><Form.Select value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })}><option value="agendada">Agendada</option><option value="realizada">Realizada</option><option value="cancelada">Cancelada</option></Form.Select></div>
                    <div className="col-md-4"><Form.Label>Área</Form.Label><Form.Select value={editing.org_unit ?? ""} onChange={(e) => setEditing({ ...editing, org_unit: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Form.Select></div>
                    <div className="col-12"><Form.Label>Local / link</Form.Label><Form.Control value={editing.location ?? ""} onChange={(e) => setEditing({ ...editing, location: e.target.value })} /></div>
                    <div className="col-md-6"><Form.Label>Stakeholders convidados</Form.Label>
                      <div className="d-flex flex-wrap gap-1">{stakeholders.length === 0 ? <span className="small text-muted-2">Cadastre em Stakeholders.</span> : stakeholders.map((s) => <button type="button" key={s.id} className={`btn btn-sm ${editing.stakeholders?.includes(s.id) ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setEditing({ ...editing, stakeholders: alternar(editing.stakeholders, s.id) })}>{s.name}</button>)}</div></div>
                    <div className="col-md-6"><Form.Label>Indicadores revisados</Form.Label>
                      <div className="d-flex flex-wrap gap-1" style={{ maxHeight: 96, overflow: "auto" }}>{indicadores.map((i) => <button type="button" key={i.id} className={`btn btn-sm ${editing.indicators?.includes(i.id) ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setEditing({ ...editing, indicators: alternar(editing.indicators, i.id) })}>{i.code}</button>)}</div></div>
                    <div className="col-md-4"><Form.Label>Pauta</Form.Label><Form.Control as="textarea" rows={5} value={editing.agenda ?? ""} onChange={(e) => setEditing({ ...editing, agenda: e.target.value })} /></div>
                    <div className="col-md-4"><Form.Label>Ata</Form.Label><Form.Control as="textarea" rows={5} value={editing.minutes ?? ""} onChange={(e) => setEditing({ ...editing, minutes: e.target.value })} /></div>
                    <div className="col-md-4"><Form.Label>Decisões</Form.Label><Form.Control as="textarea" rows={5} value={editing.decisions ?? ""} onChange={(e) => setEditing({ ...editing, decisions: e.target.value })} /></div>
                    {editing.id && <div className="col-12 small text-muted-2">Decisões que virarem ação: registre em <Link to="/planos-acao">Planos de Ação</Link>.</div>}
                  </div>
                </div>
              </Collapse>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          {editing?.id && <Button variant="outline-danger" className="me-auto" onClick={remove}>Excluir</Button>}
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save}>{editing?.id ? "Salvar" : "Criar"}</Button>
        </Modal.Footer>
      </Modal>

      <Modal show={editCats} onHide={() => setEditCats(false)} centered>
        <Modal.Header closeButton><Modal.Title>Categorias da agenda</Modal.Title></Modal.Header>
        <Modal.Body>
          {categorias.map((c) => (
            <div key={c.id} className="d-flex align-items-center gap-2 py-1" style={{ borderBottom: "1px solid var(--border)" }}>
              <span className="flex-grow-1">{c.name}</span>
              <span className="small text-muted-2">{c.meetings_count} agenda(s)</span>
              <Button size="sm" variant="link" className="p-1 text-danger" title="Excluir categoria" onClick={() => excluirCat(c)}><i className="bi bi-trash" /></Button>
            </div>
          ))}
          <div className="d-flex gap-2 mt-3">
            <Form.Control size="sm" placeholder="Nova categoria (ex.: Viagem, Treinamento)" value={novaCat} onChange={(e) => setNovaCat(e.target.value)} onKeyDown={(e) => e.key === "Enter" && criarCat()} />
            <Button size="sm" onClick={criarCat} disabled={!novaCat.trim()}>Adicionar</Button>
          </div>
          <div className="small text-muted-2 mt-2">Excluir uma categoria não apaga as agendas dela; elas só ficam sem categoria.</div>
        </Modal.Body>
      </Modal>
    </div>
  );
}
