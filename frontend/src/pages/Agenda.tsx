import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton } from "../components/ui";

interface Reuniao {
  id: number; title: string; kind: string; kind_label: string; status: string; status_label: string;
  starts_at: string; ends_at: string | null; location: string; org_unit: number | null; org_unit_name: string;
  organizer: number | null; organizer_name: string; participants: number[]; participant_names: string[];
  stakeholders: number[]; stakeholder_names: string[]; indicators: number[]; indicator_codes: string[];
  agenda: string; minutes: string; decisions: string;
}
interface Opcao { id: number; name?: string; first_name?: string; email?: string; code?: string }

const TIPOS = [
  ["resultados", "Reunião de resultados"], ["planejamento", "Planejamento estratégico"], ["acompanhamento", "Acompanhamento de planos"], ["diretoria", "Diretoria"], ["outra", "Outra"],
];
const COR_TIPO: Record<string, string> = { resultados: "#0d6efd", planejamento: "#6f42c1", acompanhamento: "#198754", diretoria: "#fd7e14", outra: "#6c757d" };
const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const local = (isoStr: string) => { const d = new Date(isoStr); return `${String(d.getFullYear())}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const hora = (isoStr: string) => new Date(isoStr).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

/** Agenda dos rituais de gestão: calendário mensal, pauta, ata e decisões. */
export function Agenda() {
  const hoje = new Date();
  const [ano, setAno] = useState(hoje.getFullYear());
  const [mes, setMes] = useState(hoje.getMonth());
  const [reunioes, setReunioes] = useState<Reuniao[] | null>(null);
  const [dia, setDia] = useState<string>(iso(hoje));
  const [editing, setEditing] = useState<Partial<Reuniao> | null>(null);
  const [usuarios, setUsuarios] = useState<Opcao[]>([]);
  const [stakeholders, setStakeholders] = useState<Opcao[]>([]);
  const [indicadores, setIndicadores] = useState<Opcao[]>([]);
  const [unidades, setUnidades] = useState<Opcao[]>([]);

  const primeiro = new Date(ano, mes, 1);
  const ultimo = new Date(ano, mes + 1, 0);

  const load = useCallback(() => {
    const de = iso(new Date(ano, mes, 1 - 7));
    const ate = iso(new Date(ano, mes + 1, 7));
    api.get<Reuniao[]>(`/api/meetings/?de=${de}&ate=${ate}`).then(setReunioes).catch(() => setReunioes([]));
  }, [ano, mes]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get<any>("/api/users/").then((d) => setUsuarios(d.results ?? d)).catch(() => {});
    api.get<Opcao[]>("/api/stakeholders/").then(setStakeholders).catch(() => {});
    api.get<any>("/api/indicators/").then((d) => setIndicadores(d.results ?? d)).catch(() => {});
    api.get<any>("/api/org-units/").then((d) => setUnidades(d.results ?? d)).catch(() => {});
  }, []);

  const porDia = useMemo(() => {
    const m: Record<string, Reuniao[]> = {};
    (reunioes ?? []).forEach((r) => { const k = iso(new Date(r.starts_at)); (m[k] = m[k] ?? []).push(r); });
    Object.values(m).forEach((l) => l.sort((a, b) => a.starts_at.localeCompare(b.starts_at)));
    return m;
  }, [reunioes]);

  const celulas = useMemo(() => {
    const out: { d: Date; fora: boolean }[] = [];
    const ini = new Date(ano, mes, 1 - primeiro.getDay());
    for (let i = 0; i < 42; i++) { const d = new Date(ini); d.setDate(ini.getDate() + i); out.push({ d, fora: d.getMonth() !== mes }); }
    return out.slice(0, out[35].d.getMonth() === mes ? 42 : 35);
  }, [ano, mes, primeiro]);

  const novo = (d: string) => setEditing({ title: "", kind: "resultados", status: "agendada", starts_at: `${d}T09:00`, ends_at: `${d}T10:00`, participants: [], stakeholders: [], indicators: [], agenda: "", minutes: "", decisions: "", location: "" });

  const save = async () => {
    if (!editing?.title?.trim() || !editing.starts_at) return;
    const body = {
      title: editing.title, kind: editing.kind, status: editing.status, location: editing.location ?? "",
      starts_at: new Date(editing.starts_at).toISOString(), ends_at: editing.ends_at ? new Date(editing.ends_at).toISOString() : null,
      org_unit: editing.org_unit || null, participants: editing.participants ?? [], stakeholders: editing.stakeholders ?? [], indicators: editing.indicators ?? [],
      agenda: editing.agenda ?? "", minutes: editing.minutes ?? "", decisions: editing.decisions ?? "",
    };
    if (editing.id) await api.patch(`/api/meetings/${editing.id}/`, body);
    else await api.post("/api/meetings/", body);
    setEditing(null);
    load();
  };
  const remove = async () => { if (editing?.id) { await api.del(`/api/meetings/${editing.id}/`); setEditing(null); load(); } };
  const abrir = (r: Reuniao) => setEditing({ ...r, starts_at: local(r.starts_at), ends_at: r.ends_at ? local(r.ends_at) : null });

  const proximas = (reunioes ?? []).filter((r) => r.status === "agendada" && new Date(r.starts_at) >= new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate())).sort((a, b) => a.starts_at.localeCompare(b.starts_at)).slice(0, 6);
  const doDia = porDia[dia] ?? [];
  const multi = (vals: number[] | undefined, id: number) => { const s = new Set(vals ?? []); s.has(id) ? s.delete(id) : s.add(id); return Array.from(s); };

  if (reunioes === null) return <Panel><Skeleton height={400} /></Panel>;

  return (
    <div className="row g-3">
      <div className="col-xl-8">
        <Panel
          title="Agenda de gestão"
          subtitle="Reuniões de resultados, planejamento e acompanhamento de planos, com pauta, ata e decisões."
          actions={
            <div className="d-flex align-items-center gap-2">
              <div className="btn-group btn-group-sm">
                <button className="btn btn-outline-secondary" onClick={() => { const d = new Date(ano, mes - 1, 1); setAno(d.getFullYear()); setMes(d.getMonth()); }}><i className="bi bi-chevron-left" /></button>
                <button className="btn btn-outline-secondary" onClick={() => { setAno(hoje.getFullYear()); setMes(hoje.getMonth()); setDia(iso(hoje)); }}>Hoje</button>
                <button className="btn btn-outline-secondary" onClick={() => { const d = new Date(ano, mes + 1, 1); setAno(d.getFullYear()); setMes(d.getMonth()); }}><i className="bi bi-chevron-right" /></button>
              </div>
              <span className="fw-semibold text-capitalize" style={{ minWidth: 150 }}>{MESES[mes]} {ano}</span>
              <Button size="sm" onClick={() => novo(dia)}><i className="bi bi-plus-lg me-1" />Nova reunião</Button>
            </div>
          }
        >
          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
            {["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"].map((d) => <div key={d} className="small text-muted-2 text-center fw-semibold py-1">{d}</div>)}
            {celulas.map(({ d, fora }) => {
              const k = iso(d);
              const lista = porDia[k] ?? [];
              const ehHoje = k === iso(hoje);
              return (
                <div key={k} onClick={() => setDia(k)} role="button"
                  style={{ minHeight: 84, border: `1px solid ${k === dia ? "var(--brand)" : "var(--border)"}`, borderRadius: 8, padding: 4, background: fora ? "var(--surface-sunken)" : "transparent", opacity: fora ? 0.6 : 1 }}>
                  <div className={`small ${ehHoje ? "fw-bold" : ""}`} style={ehHoje ? { color: "var(--brand)" } : undefined}>{d.getDate()}</div>
                  {lista.slice(0, 3).map((r) => (
                    <div key={r.id} className="small text-truncate px-1 rounded mb-1 text-white" style={{ background: COR_TIPO[r.kind] ?? "#6c757d", fontSize: "0.7rem", textDecoration: r.status === "cancelada" ? "line-through" : undefined }} title={r.title} onClick={(e) => { e.stopPropagation(); abrir(r); }}>
                      {hora(r.starts_at)} {r.title}
                    </div>
                  ))}
                  {lista.length > 3 && <div className="small text-muted-2">+{lista.length - 3}</div>}
                </div>
              );
            })}
          </div>
          <div className="d-flex flex-wrap gap-2 mt-2 small text-muted-2">
            {TIPOS.map(([k, l]) => <span key={k}><span className="d-inline-block rounded-circle me-1" style={{ width: 10, height: 10, background: COR_TIPO[k] }} />{l}</span>)}
          </div>
        </Panel>
      </div>

      <div className="col-xl-4 d-grid gap-3 align-content-start">
        <Panel title={new Date(dia + "T00:00").toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })} actions={<Button size="sm" variant="outline-secondary" onClick={() => novo(dia)}><i className="bi bi-plus-lg" /></Button>}>
          {doDia.length === 0 ? <div className="small text-muted-2">Nenhuma reunião neste dia.</div> : doDia.map((r) => (
            <div key={r.id} className="p-2 rounded mb-2" style={{ background: "var(--surface-sunken)", borderLeft: `3px solid ${COR_TIPO[r.kind]}` }} role="button" onClick={() => abrir(r)}>
              <div className="fw-semibold small">{hora(r.starts_at)}{r.ends_at ? `–${hora(r.ends_at)}` : ""} · {r.title}</div>
              <div className="small text-muted-2">{r.kind_label} · {r.status_label}{r.location ? ` · ${r.location}` : ""}</div>
              {r.participant_names.length > 0 && <div className="small text-muted-2"><i className="bi bi-people me-1" />{r.participant_names.join(", ")}</div>}
            </div>
          ))}
        </Panel>
        <Panel title="Próximas">
          {proximas.length === 0 ? <div className="small text-muted-2">Nada agendado à frente neste mês.</div> : proximas.map((r) => (
            <div key={r.id} className="d-flex gap-2 small mb-2" role="button" onClick={() => abrir(r)}>
              <span className="text-muted-2" style={{ minWidth: 88 }}>{new Date(r.starts_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} {hora(r.starts_at)}</span>
              <span className="fw-semibold text-truncate">{r.title}</span>
            </div>
          ))}
        </Panel>
      </div>

      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg">
        <Modal.Header closeButton><Modal.Title>{editing?.id ? "Reunião" : "Nova reunião"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="row g-3">
              <div className="col-md-8"><Form.Label>Título</Form.Label><Form.Control autoFocus value={editing.title ?? ""} onChange={(e) => setEditing({ ...editing, title: e.target.value })} placeholder="Ex.: Reunião de resultados de setembro" /></div>
              <div className="col-md-4"><Form.Label>Tipo</Form.Label><Form.Select value={editing.kind} onChange={(e) => setEditing({ ...editing, kind: e.target.value })}>{TIPOS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Form.Select></div>
              <div className="col-md-4"><Form.Label>Início</Form.Label><Form.Control type="datetime-local" value={editing.starts_at ?? ""} onChange={(e) => setEditing({ ...editing, starts_at: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Fim</Form.Label><Form.Control type="datetime-local" value={editing.ends_at ?? ""} onChange={(e) => setEditing({ ...editing, ends_at: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Situação</Form.Label><Form.Select value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })}><option value="agendada">Agendada</option><option value="realizada">Realizada</option><option value="cancelada">Cancelada</option></Form.Select></div>
              <div className="col-md-6"><Form.Label>Local / link</Form.Label><Form.Control value={editing.location ?? ""} onChange={(e) => setEditing({ ...editing, location: e.target.value })} /></div>
              <div className="col-md-6"><Form.Label>Área</Form.Label><Form.Select value={editing.org_unit ?? ""} onChange={(e) => setEditing({ ...editing, org_unit: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Form.Select></div>
              <div className="col-md-6">
                <Form.Label>Participantes (usuários)</Form.Label>
                <div className="d-flex flex-wrap gap-1">{usuarios.map((u) => <button type="button" key={u.id} className={`btn btn-sm ${editing.participants?.includes(u.id) ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setEditing({ ...editing, participants: multi(editing.participants, u.id) })}>{u.first_name || u.email}</button>)}</div>
              </div>
              <div className="col-md-6">
                <Form.Label>Stakeholders</Form.Label>
                <div className="d-flex flex-wrap gap-1">{stakeholders.length === 0 ? <span className="small text-muted-2">Cadastre em Stakeholders.</span> : stakeholders.map((s) => <button type="button" key={s.id} className={`btn btn-sm ${editing.stakeholders?.includes(s.id) ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setEditing({ ...editing, stakeholders: multi(editing.stakeholders, s.id) })}>{s.name}</button>)}</div>
              </div>
              <div className="col-12">
                <Form.Label>Indicadores revisados</Form.Label>
                <div className="d-flex flex-wrap gap-1" style={{ maxHeight: 96, overflow: "auto" }}>{indicadores.map((i) => <button type="button" key={i.id} className={`btn btn-sm ${editing.indicators?.includes(i.id) ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setEditing({ ...editing, indicators: multi(editing.indicators, i.id) })}>{i.code}</button>)}</div>
              </div>
              <div className="col-md-4"><Form.Label>Pauta</Form.Label><Form.Control as="textarea" rows={5} value={editing.agenda ?? ""} onChange={(e) => setEditing({ ...editing, agenda: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Ata</Form.Label><Form.Control as="textarea" rows={5} value={editing.minutes ?? ""} onChange={(e) => setEditing({ ...editing, minutes: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Decisões</Form.Label><Form.Control as="textarea" rows={5} value={editing.decisions ?? ""} onChange={(e) => setEditing({ ...editing, decisions: e.target.value })} /></div>
              {editing.id && <div className="col-12 small text-muted-2">Decisões que virarem ação: registre em <Link to="/planos-acao">Planos de Ação</Link>.</div>}
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          {editing?.id && <Button variant="outline-danger" className="me-auto" onClick={remove}>Excluir</Button>}
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save}>Salvar</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
