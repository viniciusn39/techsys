import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Form, Modal } from "react-bootstrap";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { EmptyState, Panel, Skeleton } from "../components/ui";

interface Planejamento {
  id: number; name: string; scope: string; year_start: number; year_end: number; is_active: boolean;
  partners: number[]; partner_names: string[]; org_units: number[]; org_unit_names: string[];
  objectives_count: number; projects_count: number;
}
interface Usuario { id: number; first_name: string; last_name?: string; email: string }
interface Unidade { id: number; name: string; is_active?: boolean }

const nome = (u: Usuario) => [u.first_name, u.last_name].filter(Boolean).join(" ") || u.email;

function Marcar<T extends { id: number }>({ itens, marcados, onChange, rotulo, vazio }: {
  itens: T[]; marcados: number[]; onChange: (ids: number[]) => void; rotulo: (i: T) => string; vazio: string;
}) {
  if (itens.length === 0) return <div className="small text-muted-2">{vazio}</div>;
  const alternar = (id: number) => onChange(marcados.includes(id) ? marcados.filter((x) => x !== id) : [...marcados, id]);
  return (
    <div className="rounded" style={{ border: "1px solid var(--border)", background: "var(--surface-sunken)" }}>
      <div className="p-2" style={{ maxHeight: 170, overflowY: "auto" }}>
        {itens.map((i) => <Form.Check key={i.id} id={`pl-${rotulo(i)}-${i.id}`} className="small" label={rotulo(i)} checked={marcados.includes(i.id)} onChange={() => alternar(i.id)} />)}
      </div>
      <div className="px-2 py-1 small text-muted-2 d-flex justify-content-between" style={{ borderTop: "1px solid var(--border)" }}>
        <span>{marcados.length} selecionado(s)</span>
        <span>
          <Button variant="link" size="sm" className="p-0 me-2" onClick={() => onChange(itens.map((i) => i.id))}>todos</Button>
          <Button variant="link" size="sm" className="p-0" onClick={() => onChange([])}>nenhum</Button>
        </span>
      </div>
    </div>
  );
}

/** Os planejamentos estratégicos da empresa. Cada um tem o seu mapa, SWOT, canvas, cultura e projetos. */
export function Planejamentos() {
  const navigate = useNavigate();
  const { me, mapId, selectMap } = useAuth();
  const admin = me?.role === "admin" || me?.role === "root";
  const empresa = me?.acting_tenant?.name ?? "";

  const [lista, setLista] = useState<Planejamento[] | null>(null);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [busca, setBusca] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [editing, setEditing] = useState<Partial<Planejamento> | null>(null);
  const [excluir, setExcluir] = useState<Planejamento | null>(null);
  const [erro, setErro] = useState("");

  const load = useCallback(() => {
    api.get<any>("/api/strategic-maps/").then((d) => setLista(d.results ?? d)).catch(() => setLista([]));
  }, []);
  useEffect(() => {
    load();
    api.get<any>("/api/users/").then((d) => setUsuarios(d.results ?? d)).catch(() => {});
    api.get<any>("/api/org-units/").then((d) => setUnidades((d.results ?? d).filter((u: Unidade) => u.is_active !== false))).catch(() => {});
  }, [load]);

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (lista ?? []).filter((p) => (!q || `${p.name} ${p.scope}`.toLowerCase().includes(q)) && (!fStatus || String(p.is_active) === fStatus));
  }, [lista, busca, fStatus]);

  // O que está em uso: o escolhido no seletor ou, sem escolha, o padrão (ativo mais recente).
  const emUso = useMemo(() => {
    if (!lista?.length) return null;
    return lista.find((p) => p.id === mapId) ?? lista.find((p) => p.is_active) ?? lista[0];
  }, [lista, mapId]);

  const erroDaApi = (e: unknown) => {
    const d = (e as ApiError).data;
    return Array.isArray(d) ? d.join(" ") : d && typeof d === "object" ? Object.values(d).flat().join(" ") : (e as Error).message;
  };

  const novo = () => {
    const ano = new Date().getFullYear();
    setErro("");
    setEditing({ is_active: true, year_start: ano, year_end: ano, partners: me ? [me.id] : [], org_units: [] });
  };

  const save = async () => {
    if (!editing?.name?.trim()) { setErro("Dê um nome ao planejamento."); return; }
    const body = {
      name: editing.name, scope: editing.scope ?? "", year_start: Number(editing.year_start), year_end: Number(editing.year_end),
      is_active: editing.is_active ?? true, partners: editing.partners ?? [], org_units: editing.org_units ?? [],
    };
    try {
      if (editing.id) await api.patch(`/api/strategic-maps/${editing.id}/`, body);
      else await api.post("/api/strategic-maps/", body);
      setEditing(null);
      load();
    } catch (e) { setErro(erroDaApi(e)); }
  };

  const remover = async () => {
    if (!excluir) return;
    try {
      await api.del(`/api/strategic-maps/${excluir.id}/`);
      if (mapId === excluir.id) selectMap(null);
      setExcluir(null);
      load();
    } catch (e) { setErro(erroDaApi(e)); }
  };

  if (lista === null) return <Panel><Skeleton height={300} /></Panel>;

  return (
    <div className="d-grid gap-3">
      <Panel
        title="Lista de planejamentos"
        subtitle="Cada planejamento tem o seu mapa estratégico, SWOT, canvas, cultura e projetos. Quando há mais de um, essas telas mostram no topo os botões para escolher qual ver."
        actions={
          <div className="d-flex flex-wrap gap-2">
            <Form.Control size="sm" placeholder="Buscar planejamentos…" value={busca} onChange={(e) => setBusca(e.target.value)} style={{ width: 210 }} />
            <Form.Select size="sm" value={fStatus} onChange={(e) => setFStatus(e.target.value)} style={{ width: 140 }}>
              <option value="">Todos</option><option value="true">Ativos</option><option value="false">Inativos</option>
            </Form.Select>
            <Button size="sm" variant="outline-secondary" onClick={() => navigate("/relatorio")}><i className="bi bi-file-earmark-text me-1" />Relatório</Button>
            {admin && <Button size="sm" onClick={novo}><i className="bi bi-plus-lg me-1" />Novo planejamento</Button>}
          </div>
        }
      >
        {lista.length === 0 ? (
          <EmptyState icon="bi-journal-richtext" title="Nenhum planejamento" hint="Crie o primeiro planejamento estratégico da empresa." />
        ) : (
          <div className="table-responsive">
            <table className="table table-sm table-hover align-middle mb-0">
              <thead><tr><th>Nome</th><th>Empresa</th><th>Período</th><th>Parceiros</th><th>Departamentos</th><th className="num">Objetivos</th><th className="num">Projetos</th><th>Status</th><th /></tr></thead>
              <tbody>
                {visiveis.map((p) => (
                  <tr key={p.id} className={p.is_active ? "" : "text-muted-2"}>
                    <td>
                      <div className="fw-semibold">{p.name}{emUso?.id === p.id && <span className="status-pill st-verde ms-2"><i className="bi bi-check2" />em uso</span>}</div>
                      {p.scope && <div className="small text-muted-2 text-truncate" style={{ maxWidth: 340 }}>{p.scope}</div>}
                    </td>
                    <td className="small"><i className="bi bi-building me-1 text-muted-2" />{empresa}</td>
                    <td className="small text-nowrap">{p.year_start === p.year_end ? p.year_start : `${p.year_start}–${p.year_end}`}</td>
                    <td className="small">{p.partner_names.join(", ") || "—"}</td>
                    <td className="small">{p.org_unit_names.join(", ") || "—"}</td>
                    <td className="num">{p.objectives_count}</td>
                    <td className="num">{p.projects_count}</td>
                    <td>{p.is_active
                      ? <span className="status-pill st-verde"><i className="bi bi-check-lg" />Ativo</span>
                      : <span className="status-pill st-neutro"><i className="bi bi-x-lg" />Inativo</span>}</td>
                    <td className="text-end text-nowrap">
                      {emUso?.id !== p.id && <Button size="sm" variant="outline-secondary" className="me-1" onClick={() => selectMap(p.id)}>Usar</Button>}
                      {admin && (
                        <>
                          <Button size="sm" variant="link" className="p-1" title="Editar" onClick={() => { setErro(""); setEditing(p); }}><i className="bi bi-pencil" /></Button>
                          <Button size="sm" variant="link" className="p-1 text-danger" title="Excluir" onClick={() => { setErro(""); setExcluir(p); }}><i className="bi bi-trash" /></Button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
                {visiveis.length === 0 && <tr><td colSpan={9} className="text-center text-muted-2 py-4">Nenhum planejamento com esses filtros.</td></tr>}
              </tbody>
            </table>
            <div className="small text-muted-2 mt-2">Mostrando {visiveis.length} de {lista.length} planejamento(s)</div>
          </div>
        )}
      </Panel>

      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg" scrollable>
        <Modal.Header closeButton><Modal.Title>{editing?.id ? "Editar planejamento" : "Novo planejamento"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="row g-3">
              {erro && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erro}</Alert></div>}
              <div className="col-md-7"><Form.Label>Nome do planejamento *</Form.Label><Form.Control autoFocus value={editing.name ?? ""} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></div>
              <div className="col-md-5"><Form.Label>Empresa</Form.Label><Form.Control disabled value={empresa} /></div>
              <div className="col-12"><Form.Label>Escopo do planejamento</Form.Label><Form.Control as="textarea" rows={3} value={editing.scope ?? ""} onChange={(e) => setEditing({ ...editing, scope: e.target.value })} placeholder="O que este planejamento cobre" /></div>
              <div className="col-md-4"><Form.Label>Ano inicial</Form.Label><Form.Control type="number" value={editing.year_start ?? ""} onChange={(e) => setEditing({ ...editing, year_start: Number(e.target.value) })} /></div>
              <div className="col-md-4"><Form.Label>Ano final</Form.Label><Form.Control type="number" value={editing.year_end ?? ""} onChange={(e) => setEditing({ ...editing, year_end: Number(e.target.value) })} /></div>
              <div className="col-md-4"><Form.Label>Situação</Form.Label>
                <Form.Select value={String(editing.is_active ?? true)} onChange={(e) => setEditing({ ...editing, is_active: e.target.value === "true" })}><option value="true">Ativo</option><option value="false">Inativo</option></Form.Select></div>
              <div className="col-md-6"><Form.Label>Parceiros</Form.Label>
                <Marcar itens={usuarios} marcados={editing.partners ?? []} onChange={(ids) => setEditing({ ...editing, partners: ids })} rotulo={nome} vazio="Nenhum usuário na empresa." /></div>
              <div className="col-md-6"><Form.Label>Departamentos</Form.Label>
                <Marcar itens={unidades} marcados={editing.org_units ?? []} onChange={(ids) => setEditing({ ...editing, org_units: ids })} rotulo={(u) => u.name} vazio="Nenhum departamento cadastrado." /></div>
              {!editing.id && <div className="col-12 small text-muted-2">O planejamento já nasce com as perspectivas padrão do mapa (Financeira, Clientes, Processos e Aprendizado), que você pode editar.</div>}
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save}>Salvar</Button>
        </Modal.Footer>
      </Modal>

      <Modal show={!!excluir} onHide={() => setExcluir(null)}>
        <Modal.Header closeButton><Modal.Title>Excluir planejamento</Modal.Title></Modal.Header>
        <Modal.Body>
          {erro && <Alert variant="danger" className="py-2 small">{erro}</Alert>}
          Excluir <strong>{excluir?.name}</strong>? Vão junto o mapa ({excluir?.objectives_count} objetivo(s)), a SWOT, o canvas e a cultura dele. Os {excluir?.projects_count} projeto(s) ficam, mas sem planejamento. Não dá para desfazer — se a ideia é só tirar de cena, marque como inativo.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setExcluir(null)}>Cancelar</Button>
          <Button variant="danger" onClick={remover}>Excluir</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
