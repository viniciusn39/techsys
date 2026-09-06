import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton } from "../components/ui";

interface Item {
  id: number;
  quadrant: "S" | "W" | "O" | "T";
  quadrant_label: string;
  text: string;
  detail: string;
  impact: number;
  objective: number | null;
  objective_name: string;
}

interface Objetivo { id: number; name: string }

const QUADRANTES: { key: Item["quadrant"]; label: string; hint: string; icon: string; color: string; lado: string }[] = [
  { key: "S", label: "Forças", hint: "O que fazemos bem e é difícil de copiar", icon: "bi-shield-check", color: "#198754", lado: "Ambiente interno" },
  { key: "W", label: "Fraquezas", hint: "O que nos limita hoje", icon: "bi-exclamation-octagon", color: "#dc3545", lado: "Ambiente interno" },
  { key: "O", label: "Oportunidades", hint: "O que o mercado abre para nós", icon: "bi-lightbulb", color: "#0d6efd", lado: "Ambiente externo" },
  { key: "T", label: "Ameaças", hint: "O que pode nos prejudicar de fora", icon: "bi-cloud-lightning", color: "#fd7e14", lado: "Ambiente externo" },
];

const Impacto = ({ n }: { n: number }) => (
  <span title={`impacto ${n} de 5`} style={{ letterSpacing: 1 }}>
    {"●".repeat(n)}<span className="text-muted-2">{"●".repeat(5 - n)}</span>
  </span>
);

/** Análise SWOT do mapa estratégico ativo: quatro quadrantes, impacto e ligação com objetivos. */
export function Swot() {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [objetivos, setObjetivos] = useState<Objetivo[]>([]);
  const [editing, setEditing] = useState<Partial<Item> | null>(null);
  const [erro, setErro] = useState("");

  const load = useCallback(() => {
    api.get<Item[]>("/api/swot/").then(setItens).catch((e) => { setErro(e.message); setItens([]); });
    api.get<any>("/api/strategic-maps/active/").then((m) => {
      const objs: Objetivo[] = [];
      (m?.perspectives ?? []).forEach((p: any) => (p.objectives ?? []).forEach((o: any) => objs.push({ id: o.id, name: o.name })));
      setObjetivos(objs);
    }).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const porQuadrante = useMemo(() => {
    const m: Record<string, Item[]> = { S: [], W: [], O: [], T: [] };
    (itens ?? []).forEach((i) => m[i.quadrant].push(i));
    return m;
  }, [itens]);

  const save = async () => {
    if (!editing?.text?.trim()) return;
    const body = { quadrant: editing.quadrant, text: editing.text, detail: editing.detail ?? "", impact: editing.impact ?? 3, objective: editing.objective ?? null };
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

  return (
    <div className="d-grid gap-3">
      <Panel
        title="Análise SWOT"
        subtitle="Forças e fraquezas (dentro da empresa), oportunidades e ameaças (fora). Ligue cada item ao objetivo do mapa que responde a ele."
        actions={<button className="btn btn-sm btn-outline-secondary no-print" onClick={() => window.print()}><i className="bi bi-printer me-1" />Imprimir</button>}
      >
        {erro && <div className="alert alert-warning py-2 small">{erro}</div>}
        <div className="row g-3">
          {QUADRANTES.map((q) => (
            <div className="col-md-6" key={q.key}>
              <div className="h-100 rounded" style={{ border: `1px solid var(--border)`, borderTop: `4px solid ${q.color}` }}>
                <div className="d-flex align-items-center gap-2 p-3 pb-2">
                  <i className={`bi ${q.icon}`} style={{ color: q.color, fontSize: "1.2rem" }} />
                  <div>
                    <div className="fw-semibold">{q.label} <span className="text-muted-2 fw-normal small">· {q.lado}</span></div>
                    <div className="small text-muted-2">{q.hint}</div>
                  </div>
                  <Button size="sm" variant="outline-secondary" className="ms-auto no-print" onClick={() => setEditing({ quadrant: q.key, impact: 3, text: "" })}>
                    <i className="bi bi-plus-lg" />
                  </Button>
                </div>
                <div className="px-3 pb-3 d-grid gap-2">
                  {porQuadrante[q.key].length === 0 && <div className="small text-muted-2">Nenhum item ainda.</div>}
                  {porQuadrante[q.key].map((i) => (
                    <div key={i.id} className="p-2 rounded d-flex gap-2 align-items-start" style={{ background: "var(--surface-sunken)", cursor: "pointer" }} onClick={() => setEditing(i)}>
                      <div className="flex-grow-1">
                        <div className="fw-semibold small">{i.text}</div>
                        {i.detail && <div className="small text-muted-2">{i.detail}</div>}
                        <div className="small text-muted-2 mt-1">
                          <Impacto n={i.impact} />
                          {i.objective_name && <span className="ms-2"><i className="bi bi-diagram-3 me-1" />{i.objective_name}</span>}
                        </div>
                      </div>
                      <button className="btn btn-sm btn-link text-danger p-0 no-print" title="Excluir" onClick={(e) => { e.stopPropagation(); remove(i.id); }}><i className="bi bi-x-lg" /></button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
        {itens.length === 0 && <div className="mt-3"><EmptyState icon="bi-grid-3x3-gap" title="Comece pelas forças" hint="Liste o que a empresa faz bem hoje; depois fraquezas, oportunidades e ameaças." /></div>}
      </Panel>

      <Modal show={!!editing} onHide={() => setEditing(null)}>
        <Modal.Header closeButton><Modal.Title>{editing?.id ? "Editar item" : "Novo item"} · {QUADRANTES.find((q) => q.key === editing?.quadrant)?.label}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="d-grid gap-3">
              <Form.Group>
                <Form.Label>Descrição</Form.Label>
                <Form.Control autoFocus value={editing.text ?? ""} onChange={(e) => setEditing({ ...editing, text: e.target.value })} placeholder="Ex.: Frota própria com entrega em 24 h" />
              </Form.Group>
              <Form.Group>
                <Form.Label>Detalhe (opcional)</Form.Label>
                <Form.Control as="textarea" rows={2} value={editing.detail ?? ""} onChange={(e) => setEditing({ ...editing, detail: e.target.value })} />
              </Form.Group>
              <div className="row g-2">
                <div className="col-6">
                  <Form.Label>Impacto (1–5)</Form.Label>
                  <Form.Select value={editing.impact ?? 3} onChange={(e) => setEditing({ ...editing, impact: Number(e.target.value) })}>
                    {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                  </Form.Select>
                </div>
                <div className="col-6">
                  <Form.Label>Quadrante</Form.Label>
                  <Form.Select value={editing.quadrant} onChange={(e) => setEditing({ ...editing, quadrant: e.target.value as Item["quadrant"] })}>
                    {QUADRANTES.map((q) => <option key={q.key} value={q.key}>{q.label}</option>)}
                  </Form.Select>
                </div>
              </div>
              <Form.Group>
                <Form.Label>Objetivo do mapa que responde a este item</Form.Label>
                <Form.Select value={editing.objective ?? ""} onChange={(e) => setEditing({ ...editing, objective: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>
                  {objetivos.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </Form.Select>
              </Form.Group>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save}>Salvar</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
