import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton } from "../components/ui";

interface Stakeholder {
  id: number; name: string; kind: "interno" | "externo"; organization: string; role: string; email: string; phone: string;
  influence: number; interest: number; expectations: string; org_unit: number | null; org_unit_name: string; user: number | null; is_active: boolean; strategy: string;
}
interface Unidade { id: number; name: string }

const ESTRATEGIA_COR: Record<string, string> = {
  "gerenciar de perto": "text-bg-danger", "manter satisfeito": "text-bg-warning", "manter informado": "text-bg-info", "monitorar": "text-bg-light border",
};

/** Partes interessadas do planejamento, com matriz influência × interesse. */
export function Stakeholders() {
  const [lista, setLista] = useState<Stakeholder[] | null>(null);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [editing, setEditing] = useState<Partial<Stakeholder> | null>(null);
  const [busca, setBusca] = useState("");

  const load = useCallback(() => {
    api.get<Stakeholder[]>("/api/stakeholders/").then(setLista).catch(() => setLista([]));
    api.get<any>("/api/org-units/").then((d) => setUnidades(d.results ?? d)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (lista ?? []).filter((s) => !q || `${s.name} ${s.organization} ${s.role}`.toLowerCase().includes(q));
  }, [lista, busca]);

  const save = async () => {
    if (!editing?.name?.trim()) return;
    const body = { ...editing, org_unit: editing.org_unit || null, user: editing.user || null };
    if (editing.id) await api.patch(`/api/stakeholders/${editing.id}/`, body);
    else await api.post("/api/stakeholders/", body);
    setEditing(null);
    load();
  };
  const remove = async () => {
    if (!editing?.id) return;
    await api.del(`/api/stakeholders/${editing.id}/`);
    setEditing(null);
    load();
  };

  if (lista === null) return <Panel><Skeleton height={300} /></Panel>;

  const quadrante = (inf: (s: Stakeholder) => boolean, int: (s: Stakeholder) => boolean) => visiveis.filter((s) => s.is_active && inf(s) && int(s));

  return (
    <div className="d-grid gap-3">
      <Panel
        title="Stakeholders"
        subtitle="Quem influencia ou é afetado pelo planejamento: sócios, diretoria, consultores, fornecedores e clientes-chave."
        actions={
          <div className="d-flex gap-2">
            <Form.Control size="sm" placeholder="Buscar…" value={busca} onChange={(e) => setBusca(e.target.value)} style={{ width: 200 }} />
            <Button size="sm" onClick={() => setEditing({ kind: "interno", influence: 3, interest: 3, is_active: true })}><i className="bi bi-plus-lg me-1" />Novo</Button>
          </div>
        }
      >
        {lista.length === 0 ? (
          <EmptyState icon="bi-people" title="Nenhum stakeholder cadastrado" hint="Comece pelos sócios e pela diretoria; depois consultores, fornecedores e clientes-chave." />
        ) : (
          <div className="table-responsive">
            <table className="table table-sm align-middle mb-0">
              <thead><tr><th>Nome</th><th>Tipo</th><th>Organização / área</th><th>Papel</th><th>Contato</th><th className="text-center">Influência</th><th className="text-center">Interesse</th><th>Estratégia</th></tr></thead>
              <tbody>
                {visiveis.map((s) => (
                  <tr key={s.id} role="button" onClick={() => setEditing(s)} className={s.is_active ? "" : "text-muted-2"}>
                    <td className="fw-semibold">{s.name}{!s.is_active && <span className="badge text-bg-light border ms-2">inativo</span>}</td>
                    <td><span className={`badge ${s.kind === "interno" ? "text-bg-primary" : "text-bg-secondary"}`}>{s.kind}</span></td>
                    <td className="small">{s.organization || s.org_unit_name || "—"}</td>
                    <td className="small">{s.role || "—"}</td>
                    <td className="small text-muted-2">{[s.email, s.phone].filter(Boolean).join(" · ") || "—"}</td>
                    <td className="text-center">{s.influence}</td>
                    <td className="text-center">{s.interest}</td>
                    <td><span className={`badge ${ESTRATEGIA_COR[s.strategy] ?? "text-bg-light"}`}>{s.strategy}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
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
              <div className="col-md-6"><Form.Label>Nome</Form.Label><Form.Control autoFocus value={editing.name ?? ""} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></div>
              <div className="col-md-3"><Form.Label>Tipo</Form.Label>
                <Form.Select value={editing.kind} onChange={(e) => setEditing({ ...editing, kind: e.target.value as any })}><option value="interno">Interno</option><option value="externo">Externo</option></Form.Select></div>
              <div className="col-md-3"><Form.Label>Papel</Form.Label><Form.Control value={editing.role ?? ""} onChange={(e) => setEditing({ ...editing, role: e.target.value })} placeholder="Sócio, consultor…" /></div>
              <div className="col-md-6"><Form.Label>Organização (externo)</Form.Label><Form.Control value={editing.organization ?? ""} onChange={(e) => setEditing({ ...editing, organization: e.target.value })} /></div>
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
