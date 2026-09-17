import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Form, Modal } from "react-bootstrap";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ANDAMENTO, AndamentoPill, Avanco, LegendaAvanco, nomeUsuario, type Projeto, type Usuario } from "../components/projetos";
import { EmptyState, Panel, Skeleton, StatCard } from "../components/ui";
import { fmtDate } from "../utils/format";

interface Mapa { id: number; name: string; is_active: boolean }
interface Unidade { id: number; name: string }
interface Objetivo { id: number; name: string; perspective_name: string; map: number }
interface SwotItem { id: number; quadrant: string; quadrant_label: string; text: string }

/** Lista de marcar com busca: serve para parceiros, itens da SWOT e objetivos do mapa. */
function Marcar<T extends { id: number }>({ itens, marcados, onChange, rotulo, grupo, vazio }: {
  itens: T[]; marcados: number[]; onChange: (ids: number[]) => void;
  rotulo: (i: T) => string; grupo?: (i: T) => string; vazio: string;
}) {
  const [q, setQ] = useState("");
  const visiveis = itens.filter((i) => !q.trim() || rotulo(i).toLowerCase().includes(q.trim().toLowerCase()));
  const grupos = useMemo(() => {
    const m = new Map<string, T[]>();
    visiveis.forEach((i) => { const g = grupo ? grupo(i) : ""; m.set(g, [...(m.get(g) ?? []), i]); });
    return [...m.entries()];
  }, [visiveis, grupo]);
  if (itens.length === 0) return <div className="small text-muted-2">{vazio}</div>;
  const alternar = (id: number) => onChange(marcados.includes(id) ? marcados.filter((x) => x !== id) : [...marcados, id]);
  return (
    <div className="rounded" style={{ border: "1px solid var(--border)", background: "var(--surface-sunken)" }}>
      {itens.length > 6 && <Form.Control size="sm" className="border-0 border-bottom rounded-0" placeholder="Filtrar…" value={q} onChange={(e) => setQ(e.target.value)} />}
      <div className="p-2" style={{ maxHeight: 180, overflowY: "auto" }}>
        {grupos.map(([g, lista]) => (
          <div key={g} className="mb-1">
            {g && <div className="text-muted-2 text-uppercase fw-semibold" style={{ fontSize: "0.68rem", letterSpacing: "0.04em" }}>{g}</div>}
            {lista.map((i) => <Form.Check key={i.id} id={`mk-${g}-${i.id}`} className="small" label={rotulo(i)} checked={marcados.includes(i.id)} onChange={() => alternar(i.id)} />)}
          </div>
        ))}
      </div>
      <div className="px-2 py-1 small text-muted-2" style={{ borderTop: "1px solid var(--border)" }}>{marcados.length} selecionado(s)</div>
    </div>
  );
}

export function Projetos() {
  const navigate = useNavigate();
  const { me, mapId } = useAuth();
  const podeEditar = me?.role !== "colaborador";

  const [lista, setLista] = useState<Projeto[] | null>(null);
  const [mapas, setMapas] = useState<Mapa[]>([]);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [objetivos, setObjetivos] = useState<Objetivo[]>([]);
  const [swot, setSwot] = useState<SwotItem[]>([]);
  const [busca, setBusca] = useState("");
  const [fMapa, setFMapa] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [editing, setEditing] = useState<Partial<Projeto> | null>(null);
  const [erro, setErro] = useState("");
  const [excluir, setExcluir] = useState<Projeto | null>(null);

  const load = useCallback(() => {
    api.get<Projeto[]>("/api/projects/").then(setLista).catch(() => setLista([]));
  }, []);
  useEffect(() => {
    load();
    api.get<any>("/api/strategic-maps/").then((d) => setMapas(d.results ?? d)).catch(() => {});
    api.get<any>("/api/users/").then((d) => setUsuarios(d.results ?? d)).catch(() => {});
    api.get<any>("/api/org-units/").then((d) => setUnidades(d.results ?? d)).catch(() => {});
    // Objetivos de todos os planejamentos: o formulário mostra os do planejamento escolhido para o projeto.
    api.get<any>("/api/objectives/?todos=1").then((d) => setObjetivos(d.results ?? d)).catch(() => {});
  }, [load]);

  // A SWOT é por planejamento: recarrega quando o planejamento do projeto em edição muda.
  const mapaEmEdicao = editing?.map ?? null;
  useEffect(() => {
    if (!editing) return;
    api.get<any>(`/api/swot/${mapaEmEdicao ? `?map=${mapaEmEdicao}` : ""}`).then((d) => setSwot(d.results ?? d)).catch(() => setSwot([]));
  }, [mapaEmEdicao, !!editing]);

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (lista ?? []).filter((p) =>
      (!q || `${p.code} ${p.title} ${p.owner_name}`.toLowerCase().includes(q)) &&
      (!fMapa || String(p.map ?? "") === fMapa) && (!fStatus || p.status === fStatus));
  }, [lista, busca, fMapa, fStatus]);

  const novo = () => {
    setErro("");
    setEditing({ status: "nao_iniciado", owner: me?.id ?? null, map: mapas.find((m) => m.id === mapId)?.id ?? mapas.find((m) => m.is_active)?.id ?? mapas[0]?.id ?? null, partners: [], swot_items: [], objectives: [] });
  };

  const save = async () => {
    if (!editing) return;
    if (!editing.title?.trim() || !editing.owner || !editing.start_date || !editing.end_date) {
      setErro("Preencha título, responsável, data de início e data final.");
      return;
    }
    const body = {
      title: editing.title, description: editing.description ?? "", owner: editing.owner, org_unit: editing.org_unit || null,
      map: editing.map || null, start_date: editing.start_date, end_date: editing.end_date, status: editing.status,
      partners: editing.partners ?? [], swot_items: editing.swot_items ?? [], objectives: editing.objectives ?? [],
    };
    try {
      if (editing.id) await api.patch(`/api/projects/${editing.id}/`, body);
      else {
        const criado = await api.post<Projeto>("/api/projects/", body);
        setEditing(null);
        navigate(`/projetos/${criado.id}`);
        return;
      }
      setEditing(null);
      load();
    } catch (e) {
      const d = (e as ApiError).data;
      setErro(d && typeof d === "object" ? Object.values(d).flat().join(" ") : (e as Error).message);
    }
  };

  const remover = async () => {
    if (!excluir) return;
    try {
      await api.del(`/api/projects/${excluir.id}/`);
      setExcluir(null);
      load();
    } catch (e) { setErro((e as Error).message); }
  };

  if (lista === null) return <Panel><Skeleton height={300} /></Panel>;

  const conta = (s: string) => visiveis.filter((p) => p.status === s).length;
  const media = visiveis.length ? Math.round(visiveis.reduce((a, p) => a + p.progress, 0) / visiveis.length) : 0;

  return (
    <div className="d-grid gap-3">
      {lista.length > 0 && (
        <div className="row g-3">
          <div className="col-6 col-xl-3"><StatCard icon="bi-folder2-open" label="Projetos" value={visiveis.length} foot={`${conta("em_andamento")} em andamento · ${conta("finalizado")} finalizado(s)`} /></div>
          <div className="col-6 col-xl-3"><StatCard icon="bi-graph-up" label="Avanço médio" value={`${media}%`} /></div>
          <div className="col-6 col-xl-3"><StatCard icon="bi-list-check" label="Atividades" value={visiveis.reduce((a, p) => a + p.activities_count + p.subactivities_count, 0)} foot={`${visiveis.reduce((a, p) => a + p.done_count, 0)} concluída(s)`} /></div>
          <div className="col-6 col-xl-3"><StatCard icon="bi-clock-history" label="Atividades atrasadas" value={visiveis.reduce((a, p) => a + p.late_count, 0)} /></div>
        </div>
      )}

      <Panel
        title="Projetos"
        subtitle="Projetos que tiram o planejamento do papel: cada um ligado aos itens da SWOT e aos objetivos do mapa que ele faz avançar."
        actions={
          <div className="d-flex flex-wrap gap-2">
            <Form.Control size="sm" placeholder="Buscar…" value={busca} onChange={(e) => setBusca(e.target.value)} style={{ width: 180 }} />
            {mapas.length > 1 && (
              <Form.Select size="sm" value={fMapa} onChange={(e) => setFMapa(e.target.value)} style={{ width: 200 }}>
                <option value="">Todos os planejamentos</option>
                {mapas.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </Form.Select>
            )}
            <Form.Select size="sm" value={fStatus} onChange={(e) => setFStatus(e.target.value)} style={{ width: 160 }}>
              <option value="">Todas as situações</option>
              {Object.entries(ANDAMENTO).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Form.Select>
            {podeEditar && <Button size="sm" onClick={novo}><i className="bi bi-plus-lg me-1" />Novo projeto</Button>}
          </div>
        }
      >
        {lista.length === 0 ? (
          <EmptyState icon="bi-folder2-open" title="Nenhum projeto cadastrado" hint="Crie o primeiro projeto e ligue-o aos objetivos do mapa estratégico."
            action={podeEditar ? <Button size="sm" onClick={novo}>Novo projeto</Button> : undefined} />
        ) : (
          <>
            <div className="table-responsive">
              <table className="table table-sm table-hover align-middle">
                <thead><tr><th>Cód.</th><th>Projeto</th><th>Responsável</th><th>Início</th><th>Fim</th><th>Situação</th><th className="num">Ativ.</th><th className="num">Subativ.</th><th>Avanço</th><th /></tr></thead>
                <tbody>
                  {visiveis.map((p) => (
                    <tr key={p.id} role="button" onClick={() => navigate(`/projetos/${p.id}`)}>
                      <td className="text-muted-2 num" style={{ textAlign: "left" }}>{p.code}</td>
                      <td>
                        <div className="fw-semibold">{p.title}</div>
                        <div className="small text-muted-2">
                          {[p.map_name, p.org_unit_name].filter(Boolean).join(" · ")}
                          {p.objectives.length > 0 && <span className="ms-2"><i className="bi bi-bullseye me-1" />{p.objectives.length} objetivo(s)</span>}
                          {p.swot_items.length > 0 && <span className="ms-2"><i className="bi bi-grid-3x3-gap me-1" />{p.swot_items.length} SWOT</span>}
                        </div>
                      </td>
                      <td className="small">{p.owner_name || "—"}</td>
                      <td className="small">{fmtDate(p.start_date)}</td>
                      <td className="small">{fmtDate(p.end_date)}</td>
                      <td><AndamentoPill status={p.status} /></td>
                      <td className="num">{p.activities_count}</td>
                      <td className="num">{p.subactivities_count}</td>
                      <td><Avanco progress={p.progress} late={p.late_count > 0} /></td>
                      <td className="text-end text-nowrap" onClick={(e) => e.stopPropagation()}>
                        {podeEditar && (
                          <>
                            <Button size="sm" variant="link" className="p-1" title="Editar" onClick={() => { setErro(""); setEditing(p); }}><i className="bi bi-pencil" /></Button>
                            <Button size="sm" variant="link" className="p-1 text-danger" title="Excluir" onClick={() => setExcluir(p)}><i className="bi bi-trash" /></Button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                  {visiveis.length === 0 && <tr><td colSpan={10} className="text-center text-muted-2 py-4">Nenhum projeto com esses filtros.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="mt-3"><LegendaAvanco /></div>
          </>
        )}
      </Panel>

      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg" scrollable>
        <Modal.Header closeButton><Modal.Title>{editing?.id ? `Editar projeto ${editing.code}` : "Novo projeto"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="row g-3">
              {erro && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erro}</Alert></div>}
              <div className="col-12"><Form.Label>Título do projeto *</Form.Label><Form.Control autoFocus value={editing.title ?? ""} onChange={(e) => setEditing({ ...editing, title: e.target.value })} /></div>
              <div className="col-12"><Form.Label>Descrição</Form.Label><Form.Control as="textarea" rows={2} value={editing.description ?? ""} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></div>
              <div className="col-md-6"><Form.Label>Responsável *</Form.Label>
                <Form.Select value={editing.owner ?? ""} onChange={(e) => setEditing({ ...editing, owner: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Selecione…</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{nomeUsuario(u)}</option>)}
                </Form.Select></div>
              <div className="col-md-6"><Form.Label>Departamento</Form.Label>
                <Form.Select value={editing.org_unit ?? ""} onChange={(e) => setEditing({ ...editing, org_unit: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </Form.Select></div>
              <div className="col-md-3"><Form.Label>Início *</Form.Label><Form.Control type="date" value={editing.start_date ?? ""} onChange={(e) => setEditing({ ...editing, start_date: e.target.value })} /></div>
              <div className="col-md-3"><Form.Label>Fim *</Form.Label><Form.Control type="date" value={editing.end_date ?? ""} onChange={(e) => setEditing({ ...editing, end_date: e.target.value })} /></div>
              <div className="col-md-3"><Form.Label>Situação</Form.Label>
                <Form.Select value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })}>
                  {Object.entries(ANDAMENTO).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </Form.Select></div>
              <div className="col-md-3"><Form.Label>Planejamento</Form.Label>
                <Form.Select value={editing.map ?? ""} onChange={(e) => setEditing({ ...editing, map: e.target.value ? Number(e.target.value) : null, objectives: [], swot_items: [] })}>
                  <option value="">—</option>{mapas.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </Form.Select></div>
              <div className="col-md-6"><Form.Label>Objetivos do mapa estratégico</Form.Label>
                <Marcar itens={objetivos.filter((o) => !editing.map || o.map === editing.map)} marcados={editing.objectives ?? []} onChange={(ids) => setEditing({ ...editing, objectives: ids })}
                  rotulo={(o) => o.name} grupo={(o) => o.perspective_name} vazio="Nenhum objetivo no mapa estratégico ainda." /></div>
              <div className="col-md-6"><Form.Label>Itens da SWOT que o projeto trata</Form.Label>
                <Marcar itens={swot} marcados={editing.swot_items ?? []} onChange={(ids) => setEditing({ ...editing, swot_items: ids })}
                  rotulo={(s) => s.text} grupo={(s) => s.quadrant_label} vazio="Nenhum item na análise SWOT ainda." /></div>
              <div className="col-12"><Form.Label>Parceiros (quem participa além do responsável)</Form.Label>
                <Marcar itens={usuarios.filter((u) => u.id !== editing.owner)} marcados={editing.partners ?? []} onChange={(ids) => setEditing({ ...editing, partners: ids })}
                  rotulo={nomeUsuario} vazio="Nenhum outro usuário na empresa." /></div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save}>Salvar</Button>
        </Modal.Footer>
      </Modal>

      <Modal show={!!excluir} onHide={() => setExcluir(null)}>
        <Modal.Header closeButton><Modal.Title>Excluir projeto</Modal.Title></Modal.Header>
        <Modal.Body>
          {erro && <Alert variant="danger" className="py-2 small">{erro}</Alert>}
          Excluir <strong>{excluir?.title}</strong>? Vão junto {(excluir?.activities_count ?? 0) + (excluir?.subactivities_count ?? 0)} atividade(s) e os FCAs delas. Não dá para desfazer.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setExcluir(null)}>Cancelar</Button>
          <Button variant="danger" onClick={remover}>Excluir</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
