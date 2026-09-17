import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Form, Modal, Nav } from "react-bootstrap";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { EmptyState, Panel, Skeleton } from "../components/ui";

interface Stakeholder {
  id: number; name: string; kind: "interno" | "externo"; organization: string; role: string; email: string; phone: string;
  influence: number; interest: number; expectations: string; org_unit: number | null; org_unit_name: string; user: number | null; is_active: boolean; strategy: string;
}
interface Unidade { id: number; name: string }
interface Departamento { id: number; parent: number | null; parent_name: string; name: string; kind: string; kind_label: string; manager: number | null; manager_name: string | null; is_active: boolean; users_count: number }
interface Empresa {
  id: number; name: string; legal_name: string; cnpj: string; address: string; address_number: string; address_complement: string;
  district: string; city: string; state: string; zip_code: string; contact_name: string; email: string; phone: string; is_active: boolean;
}
interface Usuario { id: number; first_name: string; last_name?: string; email: string }

const UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");

function Situacao({ ativo }: { ativo: boolean }) {
  return ativo
    ? <span className="status-pill st-verde"><i className="bi bi-check-lg" aria-hidden="true" />Ativo</span>
    : <span className="status-pill st-neutro"><i className="bi bi-x-lg" aria-hidden="true" />Inativo</span>;
}

const erroDaApi = (e: unknown) => {
  const d = (e as ApiError).data;
  return d && typeof d === "object" ? Object.values(d).flat().join(" ") : (e as Error).message;
};

const ESTRATEGIA_COR: Record<string, string> = {
  "gerenciar de perto": "text-bg-danger", "manter satisfeito": "text-bg-warning", "manter informado": "text-bg-info", "monitorar": "text-bg-light border",
};

/** Aba Stakeholders: partes interessadas do planejamento, com matriz influência × interesse. */
function AbaStakeholders({ podeEditar, novo }: { podeEditar: boolean; novo: number }) {
  const [lista, setLista] = useState<Stakeholder[] | null>(null);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [editing, setEditing] = useState<Partial<Stakeholder> | null>(null);
  const [busca, setBusca] = useState("");
  const [erroSt, setErroSt] = useState("");

  const load = useCallback(() => {
    api.get<Stakeholder[]>("/api/stakeholders/").then(setLista).catch(() => setLista([]));
    api.get<any>("/api/org-units/").then((d) => setUnidades(d.results ?? d)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);
  // O botão "Novo stakeholder" fica no cabeçalho da página; cada clique muda o contador.
  useEffect(() => { if (novo > 0) setEditing({ kind: "interno", influence: 3, interest: 3, is_active: true }); }, [novo]);

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (lista ?? []).filter((s) => !q || `${s.name} ${s.organization} ${s.role}`.toLowerCase().includes(q));
  }, [lista, busca]);

  const save = async () => {
    if (!editing?.name?.trim()) return;
    const body = { ...editing, org_unit: editing.org_unit || null, user: editing.user || null };
    try {
      if (editing.id) await api.patch(`/api/stakeholders/${editing.id}/`, body);
      else await api.post("/api/stakeholders/", body);
      setEditing(null);
      load();
    } catch (e) { setErroSt(erroDaApi(e)); }
  };
  const remove = async () => {
    if (!editing?.id) return;
    try {
      await api.del(`/api/stakeholders/${editing.id}/`);
      setEditing(null);
      load();
    } catch (e) { setErroSt(erroDaApi(e)); }
  };

  if (lista === null) return <Panel><Skeleton height={300} /></Panel>;

  const quadrante = (inf: (s: Stakeholder) => boolean, int: (s: Stakeholder) => boolean) => visiveis.filter((s) => s.is_active && inf(s) && int(s));

  return (
    <div className="d-grid gap-3">
      <Panel
        title="Lista de stakeholders"
        subtitle="Quem influencia ou é afetado pelo planejamento: sócios, diretoria, consultores, fornecedores e clientes-chave."
        actions={<Form.Control size="sm" placeholder="Buscar stakeholders…" value={busca} onChange={(e) => setBusca(e.target.value)} style={{ width: 220 }} />}
      >
        {lista.length === 0 ? (
          <EmptyState icon="bi-people" title="Nenhum stakeholder cadastrado" hint="Comece pelos sócios e pela diretoria; depois consultores, fornecedores e clientes-chave." />
        ) : (
          <div className="table-responsive">
            <table className="table table-sm table-hover align-middle mb-0">
              <thead><tr><th>Stakeholder</th><th>Cargo</th><th>Empresa relacionada</th><th>Tipo</th><th>Contato</th><th className="text-center">Influência</th><th className="text-center">Interesse</th><th>Estratégia</th><th>Situação</th></tr></thead>
              <tbody>
                {visiveis.map((s) => (
                  <tr key={s.id} role={podeEditar ? "button" : undefined} onClick={() => podeEditar && setEditing(s)} className={s.is_active ? "" : "text-muted-2"}>
                    <td className="fw-semibold">{s.name}</td>
                    <td className="small">{s.role || "—"}</td>
                    <td className="small">{s.organization || s.org_unit_name || "—"}</td>
                    <td><span className={`badge ${s.kind === "interno" ? "text-bg-primary" : "text-bg-secondary"}`}>{s.kind}</span></td>
                    <td className="small text-muted-2">{[s.email, s.phone].filter(Boolean).join(" · ") || "—"}</td>
                    <td className="text-center">{s.influence}</td>
                    <td className="text-center">{s.interest}</td>
                    <td><span className={`badge ${ESTRATEGIA_COR[s.strategy] ?? "text-bg-light"}`}>{s.strategy}</span></td>
                    <td><Situacao ativo={s.is_active} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="small text-muted-2 mt-2">Mostrando {visiveis.length} stakeholder(s)</div>
          </div>
        )}
      </Panel>

      {lista.length > 0 && (
        <Panel title="Matriz influência × interesse" subtitle="Quem tem poder e interesse altos é gerenciado de perto; poder alto e interesse baixo é mantido satisfeito; interesse alto e poder baixo é mantido informado; o resto é monitorado.">
          <div className="row g-2">
            {[
              { titulo: "Manter satisfeito", cor: "#f59f00", itens: quadrante((s) => s.influence >= 4, (s) => s.interest < 4) },
              { titulo: "Gerenciar de perto", cor: "#dc3545", itens: quadrante((s) => s.influence >= 4, (s) => s.interest >= 4) },
              { titulo: "Monitorar", cor: "#adb5bd", itens: quadrante((s) => s.influence < 4, (s) => s.interest < 4) },
              { titulo: "Manter informado", cor: "#15aabf", itens: quadrante((s) => s.influence < 4, (s) => s.interest >= 4) },
            ].map((q) => (
              <div className="col-md-6" key={q.titulo}>
                <div className="p-3 rounded h-100" style={{ border: "1px solid var(--border)", borderTop: `4px solid ${q.cor}`, minHeight: 120 }}>
                  <div className="fw-semibold small mb-2">{q.titulo} <span className="text-muted-2 fw-normal">({q.itens.length})</span></div>
                  <div className="d-flex flex-wrap gap-1">
                    {q.itens.map((s) => <span key={s.id} className="badge text-bg-light border fw-normal" role="button" onClick={() => setEditing(s)}>{s.name}</span>)}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="small text-muted-2 mt-2">Linha de cima: influência alta. Coluna da direita: interesse alto.</div>
        </Panel>
      )}

      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg">
        <Modal.Header closeButton><Modal.Title>{editing?.id ? "Editar stakeholder" : "Novo stakeholder"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="row g-3">
              {erroSt && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erroSt}</Alert></div>}
              <div className="col-md-6"><Form.Label>Nome</Form.Label><Form.Control autoFocus value={editing.name ?? ""} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></div>
              <div className="col-md-3"><Form.Label>Tipo</Form.Label>
                <Form.Select value={editing.kind} onChange={(e) => setEditing({ ...editing, kind: e.target.value as any })}><option value="interno">Interno</option><option value="externo">Externo</option></Form.Select></div>
              <div className="col-md-3"><Form.Label>Cargo / papel</Form.Label><Form.Control value={editing.role ?? ""} onChange={(e) => setEditing({ ...editing, role: e.target.value })} placeholder="Sócio, consultor…" /></div>
              <div className="col-md-6"><Form.Label>Empresa relacionada</Form.Label><Form.Control value={editing.organization ?? ""} onChange={(e) => setEditing({ ...editing, organization: e.target.value })} /></div>
              <div className="col-md-6"><Form.Label>Área (interno)</Form.Label>
                <Form.Select value={editing.org_unit ?? ""} onChange={(e) => setEditing({ ...editing, org_unit: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Form.Select></div>
              <div className="col-md-6"><Form.Label>E-mail</Form.Label><Form.Control value={editing.email ?? ""} onChange={(e) => setEditing({ ...editing, email: e.target.value })} /></div>
              <div className="col-md-6"><Form.Label>Telefone</Form.Label><Form.Control value={editing.phone ?? ""} onChange={(e) => setEditing({ ...editing, phone: e.target.value })} /></div>
              <div className="col-md-3"><Form.Label>Influência (1–5)</Form.Label><Form.Select value={editing.influence ?? 3} onChange={(e) => setEditing({ ...editing, influence: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</Form.Select></div>
              <div className="col-md-3"><Form.Label>Interesse (1–5)</Form.Label><Form.Select value={editing.interest ?? 3} onChange={(e) => setEditing({ ...editing, interest: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</Form.Select></div>
              <div className="col-md-6 d-flex align-items-end"><Form.Check type="switch" label="Ativo" checked={editing.is_active ?? true} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} /></div>
              <div className="col-12"><Form.Label>Expectativas / o que espera do planejamento</Form.Label><Form.Control as="textarea" rows={3} value={editing.expectations ?? ""} onChange={(e) => setEditing({ ...editing, expectations: e.target.value })} /></div>
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

/** Aba Departamentos: as áreas da empresa em lista (a árvore continua em Administração → Organograma). */
function AbaDepartamentos({ podeEditar, novo }: { podeEditar: boolean; novo: number }) {
  const [lista, setLista] = useState<Departamento[] | null>(null);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [busca, setBusca] = useState("");
  const [editing, setEditing] = useState<Partial<Departamento> | null>(null);
  const [erro, setErro] = useState("");

  const load = useCallback(() => {
    api.get<any>("/api/org-units/").then((d) => setLista(d.results ?? d)).catch(() => setLista([]));
  }, []);
  useEffect(() => { load(); api.get<any>("/api/users/").then((d) => setUsuarios(d.results ?? d)).catch(() => {}); }, [load]);
  useEffect(() => { if (novo > 0) { setErro(""); setEditing({ kind: "area", is_active: true }); } }, [novo]);

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (lista ?? []).filter((d) => !q || d.name.toLowerCase().includes(q)).sort((a, b) => Number(b.is_active) - Number(a.is_active) || a.name.localeCompare(b.name));
  }, [lista, busca]);

  const save = async () => {
    if (!editing?.name?.trim()) { setErro("Dê um nome ao departamento."); return; }
    const body = { name: editing.name, kind: editing.kind, parent: editing.parent || null, manager: editing.manager || null, is_active: editing.is_active ?? true };
    try {
      if (editing.id) await api.patch(`/api/org-units/${editing.id}/`, body);
      else await api.post("/api/org-units/", body);
      setEditing(null);
      load();
    } catch (e) { setErro(erroDaApi(e)); }
  };

  if (lista === null) return <Panel><Skeleton height={300} /></Panel>;

  return (
    <>
      <Panel title="Lista de departamentos" subtitle="As áreas e os times da empresa. Departamento inativo some das escolhas, mas o histórico fica."
        actions={<Form.Control size="sm" placeholder="Buscar departamentos…" value={busca} onChange={(e) => setBusca(e.target.value)} style={{ width: 220 }} />}>
        {lista.length === 0 ? <EmptyState icon="bi-diagram-2" title="Nenhum departamento cadastrado" /> : (
          <div className="table-responsive">
            <table className="table table-sm table-hover align-middle mb-0">
              <thead><tr><th>Departamento</th><th>Tipo</th><th>Fica em</th><th>Gestor</th><th className="num">Pessoas</th><th>Situação</th></tr></thead>
              <tbody>
                {visiveis.map((d) => (
                  <tr key={d.id} role={podeEditar ? "button" : undefined} onClick={() => { if (podeEditar) { setErro(""); setEditing(d); } }} className={d.is_active ? "" : "text-muted-2"}>
                    <td className="fw-semibold">{d.name}</td>
                    <td className="small">{d.kind_label}</td>
                    <td className="small">{d.parent_name || "—"}</td>
                    <td className="small">{d.manager_name || "—"}</td>
                    <td className="num">{d.users_count}</td>
                    <td><Situacao ativo={d.is_active} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="small text-muted-2 mt-2">Mostrando {visiveis.length} departamento(s)</div>
          </div>
        )}
      </Panel>

      <Modal show={!!editing} onHide={() => setEditing(null)}>
        <Modal.Header closeButton><Modal.Title>{editing?.id ? "Editar departamento" : "Novo departamento"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="row g-3">
              {erro && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erro}</Alert></div>}
              <div className="col-12"><Form.Label>Nome *</Form.Label><Form.Control autoFocus value={editing.name ?? ""} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></div>
              <div className="col-md-6"><Form.Label>Tipo</Form.Label>
                <Form.Select value={editing.kind} onChange={(e) => setEditing({ ...editing, kind: e.target.value })}><option value="empresa">Empresa</option><option value="area">Área</option><option value="time">Time</option></Form.Select></div>
              <div className="col-md-6"><Form.Label>Fica em</Form.Label>
                <Form.Select value={editing.parent ?? ""} onChange={(e) => setEditing({ ...editing, parent: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>{lista.filter((d) => d.id !== editing.id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </Form.Select></div>
              <div className="col-md-8"><Form.Label>Gestor</Form.Label>
                <Form.Select value={editing.manager ?? ""} onChange={(e) => setEditing({ ...editing, manager: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{[u.first_name, u.last_name].filter(Boolean).join(" ") || u.email}</option>)}
                </Form.Select></div>
              <div className="col-md-4 d-flex align-items-end"><Form.Check type="switch" id="dep-ativo" label="Ativo" checked={editing.is_active ?? true} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} /></div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save}>Salvar</Button>
        </Modal.Footer>
      </Modal>
    </>
  );
}

/** Aba Empresas: as empresas do cliente (ele pode ter várias) e os dados cadastrais da que está em uso. */
function AbaEmpresa({ podeEditar, novo }: { podeEditar: boolean; novo: number }) {
  const { me, actAsTenant } = useAuth();
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [nova, setNova] = useState<Partial<Empresa> | null>(null);
  const [erroNova, setErroNova] = useState("");
  const [empresa, setEmpresa] = useState<Empresa | null>(null);
  const isRoot = me?.role === "root";

  const loadEmpresas = useCallback(() => { api.get<Empresa[]>("/api/empresas/").then(setEmpresas).catch(() => setEmpresas([])); }, []);
  useEffect(() => { loadEmpresas(); }, [loadEmpresas]);
  useEffect(() => { if (novo > 0) { setErroNova(""); setNova({}); } }, [novo]);

  const criar = async () => {
    if (!nova?.name?.trim()) { setErroNova("Informe o nome fantasia."); return; }
    try {
      const criada = await api.post<Empresa>("/api/empresas/", nova);
      setNova(null);
      await actAsTenant(criada.id); // já entra na empresa nova: a tela remonta nela
    } catch (e) { setErroNova(erroDaApi(e)); }
  };

  const [msg, setMsg] = useState<{ tipo: "success" | "danger"; texto: string } | null>(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => { api.get<Empresa>("/api/empresa/").then(setEmpresa).catch((e) => setMsg({ tipo: "danger", texto: e.message })); }, []);

  const save = async () => {
    if (!empresa) return;
    setSalvando(true);
    try {
      setEmpresa(await api.patch<Empresa>("/api/empresa/", empresa));
      setMsg({ tipo: "success", texto: "Dados da empresa salvos." });
    } catch (e) { setMsg({ tipo: "danger", texto: erroDaApi(e) }); }
    setSalvando(false);
  };

  if (!empresa) return <Panel>{msg ? <Alert variant="danger" className="mb-0">{msg.texto}</Alert> : <Skeleton height={260} />}</Panel>;

  const campo = (rotulo: string, chave: keyof Empresa, col: string, extra: Record<string, unknown> = {}) => (
    <div className={col}><Form.Label>{rotulo}</Form.Label>
      <Form.Control disabled={!podeEditar} value={String(empresa[chave] ?? "")} onChange={(e) => setEmpresa({ ...empresa, [chave]: e.target.value })} {...extra} /></div>
  );

  return (
    <>
    {!isRoot && (
      <Panel title="Lista de empresas" subtitle="As empresas a que você tem acesso. Cada uma tem os seus planejamentos, indicadores, projetos e usuários.">
        <div className="table-responsive">
          <table className="table table-sm table-hover align-middle mb-0">
            <thead><tr><th>Razão social</th><th>Nome fantasia</th><th>CNPJ</th><th>E-mail</th><th>Situação</th><th /></tr></thead>
            <tbody>
              {empresas.map((e) => (
                <tr key={e.id}>
                  <td className="fw-semibold">{e.legal_name || e.name}</td>
                  <td className="small">{e.name}</td>
                  <td className="small">{e.cnpj || "—"}</td>
                  <td className="small">{e.email || "—"}</td>
                  <td><Situacao ativo={e.is_active} /></td>
                  <td className="text-end">
                    {e.id === empresa.id
                      ? <span className="status-pill st-verde"><i className="bi bi-check2" />em uso</span>
                      : <Button size="sm" variant="outline-secondary" onClick={() => actAsTenant(e.id)}>Abrir</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="small text-muted-2 mt-2">Mostrando {empresas.length} empresa(s)</div>
        </div>
      </Panel>
    )}
    <Panel title={`Dados da empresa em uso · ${empresa.name}`} subtitle="Cadastro usado nos relatórios e na comunicação com o suporte."
      actions={<Situacao ativo={empresa.is_active} />}>
      <div className="row g-3">
        {msg && <div className="col-12"><Alert variant={msg.tipo} className="mb-0 py-2 small" dismissible onClose={() => setMsg(null)}>{msg.texto}</Alert></div>}
        {campo("Razão social", "legal_name", "col-md-5")}
        {campo("Nome fantasia *", "name", "col-md-4")}
        {campo("CNPJ", "cnpj", "col-md-3", { placeholder: "00.000.000/0000-00", maxLength: 18 })}
        {campo("Endereço", "address", "col-md-6")}
        {campo("Número", "address_number", "col-md-2")}
        {campo("Complemento", "address_complement", "col-md-4")}
        {campo("Bairro", "district", "col-md-4")}
        {campo("Município", "city", "col-md-4")}
        <div className="col-md-2"><Form.Label>UF</Form.Label>
          <Form.Select disabled={!podeEditar} value={empresa.state} onChange={(e) => setEmpresa({ ...empresa, state: e.target.value })}><option value="">—</option>{UFS.map((uf) => <option key={uf}>{uf}</option>)}</Form.Select></div>
        {campo("CEP", "zip_code", "col-md-2", { placeholder: "00000-000", maxLength: 9 })}
        {campo("Responsável", "contact_name", "col-md-4")}
        {campo("E-mail", "email", "col-md-4", { type: "email" })}
        {campo("Telefone", "phone", "col-md-4", { placeholder: "(00) 00000-0000" })}
        {podeEditar && <div className="col-12 text-end"><Button onClick={save} disabled={salvando || !empresa.name.trim()}>{salvando ? "Salvando…" : "Salvar"}</Button></div>}
      </div>
    </Panel>

    <Modal show={!!nova} onHide={() => setNova(null)}>
      <Modal.Header closeButton><Modal.Title>Nova empresa</Modal.Title></Modal.Header>
      <Modal.Body>
        {nova && (
          <div className="row g-3">
            {erroNova && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erroNova}</Alert></div>}
            <div className="col-12 small text-muted-2">A empresa nasce pronta para uso (departamento raiz, planejamento do ano e perfis de acesso) e você já entra nela. Os demais dados cadastrais você completa em seguida.</div>
            <div className="col-12"><Form.Label>Razão social</Form.Label><Form.Control autoFocus value={nova.legal_name ?? ""} onChange={(e) => setNova({ ...nova, legal_name: e.target.value })} /></div>
            <div className="col-md-7"><Form.Label>Nome fantasia *</Form.Label><Form.Control value={nova.name ?? ""} onChange={(e) => setNova({ ...nova, name: e.target.value })} /></div>
            <div className="col-md-5"><Form.Label>CNPJ</Form.Label><Form.Control value={nova.cnpj ?? ""} maxLength={18} placeholder="00.000.000/0000-00" onChange={(e) => setNova({ ...nova, cnpj: e.target.value })} /></div>
          </div>
        )}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="outline-secondary" onClick={() => setNova(null)}>Cancelar</Button>
        <Button onClick={criar}>Criar empresa</Button>
      </Modal.Footer>
    </Modal>
    </>
  );
}

type Aba = "stakeholders" | "departamentos" | "empresa";

/** Stakeholders, departamentos e empresa numa página só, em abas. */
export function Stakeholders() {
  const { me } = useAuth();
  const [aba, setAba] = useState<Aba>("stakeholders");
  const [novo, setNovo] = useState(0);
  const gestor = me?.role !== "colaborador";
  const admin = me?.role === "admin" || me?.role === "root";
  const trocar = (k: Aba) => { setNovo(0); setAba(k); };

  return (
    <div className="d-grid gap-3">
      <div className="d-flex flex-wrap align-items-center gap-2">
        <Nav variant="pills" activeKey={aba} onSelect={(k) => trocar(k as Aba)} className="me-auto">
          <Nav.Item><Nav.Link eventKey="stakeholders" className="py-1 px-3 small"><i className="bi bi-people me-1" />Stakeholders</Nav.Link></Nav.Item>
          <Nav.Item><Nav.Link eventKey="departamentos" className="py-1 px-3 small"><i className="bi bi-diagram-2 me-1" />Departamentos</Nav.Link></Nav.Item>
          <Nav.Item><Nav.Link eventKey="empresa" className="py-1 px-3 small"><i className="bi bi-building me-1" />Empresas</Nav.Link></Nav.Item>
        </Nav>
        <Button size="sm" variant="outline-secondary" onClick={() => window.print()}><i className="bi bi-printer me-1" />Imprimir</Button>
        {aba === "stakeholders" && gestor && <Button size="sm" onClick={() => setNovo((n) => n + 1)}><i className="bi bi-plus-lg me-1" />Novo stakeholder</Button>}
        {aba === "empresa" && me?.role === "admin" && <Button size="sm" onClick={() => setNovo((n) => n + 1)}><i className="bi bi-plus-lg me-1" />Nova empresa</Button>}
        {aba === "departamentos" && admin && <Button size="sm" onClick={() => setNovo((n) => n + 1)}><i className="bi bi-plus-lg me-1" />Novo departamento</Button>}
      </div>
      {aba === "stakeholders" && <AbaStakeholders podeEditar={gestor} novo={novo} />}
      {aba === "departamentos" && <AbaDepartamentos podeEditar={admin} novo={novo} />}
      {aba === "empresa" && <AbaEmpresa podeEditar={admin} novo={novo} />}
    </div>
  );
}
