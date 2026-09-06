import { useCallback, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton } from "../components/ui";

interface Perfil { id: number; key: string; name: string; description: string; sectors: string[]; modules: string[]; is_system: boolean; users_count: number; sectors_labels: string[] }
interface Opcao { key: string; label: string }

/** Perfis de acesso por setor (RBAC): quais indicadores e módulos cada grupo de usuários enxerga. */
export function PerfisAcesso() {
  const [perfis, setPerfis] = useState<Perfil[] | null>(null);
  const [setores, setSetores] = useState<Opcao[]>([]);
  const [modulos, setModulos] = useState<Opcao[]>([]);
  const [editing, setEditing] = useState<Partial<Perfil> | null>(null);
  const [erro, setErro] = useState("");

  const load = useCallback(() => {
    api.get<Perfil[]>("/api/access-profiles/").then(setPerfis).catch((e) => { setErro(e.message); setPerfis([]); });
  }, []);
  useEffect(() => {
    load();
    api.get<{ setores: Opcao[]; modulos: Opcao[] }>("/api/access-profiles/opcoes/").then((d) => { setSetores(d.setores); setModulos(d.modulos); }).catch(() => {});
  }, [load]);

  const save = async () => {
    if (!editing?.name?.trim()) return;
    const body = { name: editing.name.trim(), key: editing.key || editing.name.trim().toLowerCase().normalize("NFD").replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""), description: editing.description ?? "", sectors: editing.sectors ?? [], modules: editing.modules ?? [] };
    try {
      if (editing.id) await api.patch(`/api/access-profiles/${editing.id}/`, body);
      else await api.post("/api/access-profiles/", body);
      setEditing(null);
      load();
    } catch (e: any) {
      setErro(e.data ? Object.entries(e.data).map(([k, v]) => `${k}: ${v}`).join(" · ") : e.message);
    }
  };
  const remove = async () => {
    if (!editing?.id) return;
    await api.del(`/api/access-profiles/${editing.id}/`);
    setEditing(null);
    load();
  };
  const recriar = async () => { await api.post("/api/access-profiles/padrao/"); load(); };
  const toggle = (lista: string[] | undefined, key: string) => { const s = new Set(lista ?? []); s.has(key) ? s.delete(key) : s.add(key); return Array.from(s); };

  if (perfis === null) return <Panel><Skeleton height={260} /></Panel>;
  const rotuloModulo = (k: string) => modulos.find((m) => m.key === k)?.label ?? k;

  return (
    <div className="d-grid gap-3">
      <Panel
        title="Perfis de acesso por setor"
        subtitle="Cada perfil define os setores cujos indicadores o usuário vê e os módulos do menu que ficam disponíveis. Admin da empresa vê tudo sempre. Lista vazia = tudo."
        actions={
          <div className="d-flex gap-2">
            <Button size="sm" variant="outline-secondary" onClick={recriar} title="Recria os perfis padrão que tiverem sido excluídos"><i className="bi bi-arrow-counterclockwise me-1" />Padrões</Button>
            <Button size="sm" onClick={() => setEditing({ sectors: [], modules: [] })}><i className="bi bi-plus-lg me-1" />Novo perfil</Button>
          </div>
        }
      >
        {erro && <div className="alert alert-warning py-2 small">{erro}</div>}
        {perfis.length === 0 ? (
          <EmptyState icon="bi-shield-lock" title="Nenhum perfil" hint="Clique em Padrões para criar Diretoria, Comercial, Financeiro, Logística, Suprimentos e Pessoas." />
        ) : (
          <div className="table-responsive">
            <table className="table table-sm align-middle mb-0">
              <thead><tr><th>Perfil</th><th>Setores dos indicadores</th><th>Módulos</th><th className="num">Usuários</th></tr></thead>
              <tbody>
                {perfis.map((p) => (
                  <tr key={p.id} role="button" onClick={() => setEditing(p)}>
                    <td>
                      <div className="fw-semibold">{p.name}{p.is_system && <span className="badge text-bg-light border ms-2 fw-normal">padrão</span>}</div>
                      <div className="small text-muted-2">{p.description}</div>
                    </td>
                    <td className="small">{p.sectors.length ? p.sectors_labels.join(", ") : <span className="text-muted-2">todos</span>}</td>
                    <td className="small">{p.modules.length ? p.modules.map(rotuloModulo).join(", ") : <span className="text-muted-2">todos</span>}</td>
                    <td className="num">{p.users_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg">
        <Modal.Header closeButton><Modal.Title>{editing?.id ? "Editar perfil" : "Novo perfil"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="d-grid gap-3">
              <div className="row g-2">
                <div className="col-md-5"><Form.Label>Nome</Form.Label><Form.Control autoFocus value={editing.name ?? ""} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></div>
                <div className="col-md-7"><Form.Label>Descrição</Form.Label><Form.Control value={editing.description ?? ""} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></div>
              </div>
              <div>
                <div className="d-flex align-items-center mb-1"><Form.Label className="mb-0">Setores dos indicadores</Form.Label><span className="small text-muted-2 ms-2">nenhum marcado = todos</span></div>
                <div className="d-flex flex-wrap gap-1">
                  {setores.map((s) => (
                    <button type="button" key={s.key} className={`btn btn-sm ${editing.sectors?.includes(s.key) ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setEditing({ ...editing, sectors: toggle(editing.sectors, s.key) })}>{s.label}</button>
                  ))}
                </div>
              </div>
              <div>
                <div className="d-flex align-items-center mb-1"><Form.Label className="mb-0">Módulos liberados</Form.Label><span className="small text-muted-2 ms-2">nenhum marcado = todos</span></div>
                <div className="d-flex flex-wrap gap-1">
                  {modulos.map((m) => (
                    <button type="button" key={m.key} className={`btn btn-sm ${editing.modules?.includes(m.key) ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setEditing({ ...editing, modules: toggle(editing.modules, m.key) })}>{m.label}</button>
                  ))}
                </div>
              </div>
              <div className="small text-muted-2">Indicadores criados à mão (sem setor) ficam visíveis a todos os perfis. Usuários com papel admin não são limitados por perfil.</div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          {editing?.id && !editing.is_system && <Button variant="outline-danger" className="me-auto" onClick={remove}>Excluir</Button>}
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save}>Salvar</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
