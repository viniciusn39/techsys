import { useCallback, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton, StatCard } from "../components/ui";
import { CATEGORIAS, ConversaChamado, PRIORIDADES, STATUS_CH, fmtDt, type Chamado } from "./Chamados";

/** Root: fila de chamados de todas as empresas. Atribuir, responder, mudar situação, nota interna. */
export function SuporteChamados() {
  const [lista, setLista] = useState<Chamado[] | null>(null);
  const [resumo, setResumo] = useState<any>(null);
  const [filtro, setFiltro] = useState("abertos");
  const [empresa, setEmpresa] = useState("");
  const [categoria, setCategoria] = useState("");
  const [aberto, setAberto] = useState<Chamado | null>(null);

  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (filtro !== "todos") p.set("status", filtro);
    if (empresa) p.set("tenant", empresa);
    if (categoria) p.set("category", categoria);
    api.get<Chamado[]>(`/api/tickets/?${p}`).then(setLista).catch(() => setLista([]));
    api.get("/api/tickets/resumo/").then(setResumo).catch(() => {});
  }, [filtro, empresa, categoria]);
  useEffect(() => { load(); }, [load]);

  const abrir = async (id: number) => setAberto(await api.get<Chamado>(`/api/tickets/${id}/`));
  const recarregar = async () => { if (aberto) { setAberto(await api.get<Chamado>(`/api/tickets/${aberto.id}/`)); load(); } };
  const mudar = async (dados: Record<string, any>) => { if (aberto) { await api.patch(`/api/tickets/${aberto.id}/`, dados); recarregar(); } };

  if (lista === null) return <Panel><Skeleton height={300} /></Panel>;
  const atendentes: { id: number; name: string }[] = resumo?.atendentes ?? [];

  return (
    <div className="d-grid gap-3">
      <div className="row g-3">
        <div className="col-6 col-xl-3"><StatCard icon="bi-life-preserver" label="Abertos (todas as empresas)" value={resumo?.abertos ?? 0} foot={`${resumo?.total ?? 0} no total`} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-hourglass" label="Sem primeira resposta" value={resumo?.sem_resposta ?? 0} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-exclamation-octagon" label="Urgentes" value={resumo?.urgentes ?? 0} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-buildings" label="Empresas com chamado aberto" value={resumo?.por_empresa?.length ?? 0} /></div>
      </div>

      <Panel
        title="Fila de suporte e consultoria"
        subtitle="Chamados de todos os clientes. Responder muda para 'em atendimento' e atribui a você; use 'aguardando cliente' quando a bola está com ele."
        actions={
          <div className="d-flex gap-2 flex-wrap">
            <Form.Select size="sm" style={{ width: 170 }} value={empresa} onChange={(e) => setEmpresa(e.target.value)}>
              <option value="">Todas as empresas</option>
              {(resumo?.por_empresa ?? []).map((e: any) => <option key={e.tenant_id} value={e.tenant_id}>{e.tenant_name} ({e.abertos})</option>)}
            </Form.Select>
            <Form.Select size="sm" style={{ width: 170 }} value={categoria} onChange={(e) => setCategoria(e.target.value)}>
              <option value="">Todas as categorias</option>
              {CATEGORIAS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </Form.Select>
            <Form.Select size="sm" style={{ width: 160 }} value={filtro} onChange={(e) => setFiltro(e.target.value)}>
              <option value="abertos">Em aberto</option>
              <option value="todos">Todos</option>
              {Object.entries(STATUS_CH).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Form.Select>
          </div>
        }
      >
        {lista.length === 0 ? <EmptyState icon="bi-inbox" title="Fila vazia" /> : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0">
              <thead><tr><th>Empresa</th><th>#</th><th>Chamado</th><th>Categoria</th><th>Prioridade</th><th>Situação</th><th>Atendente</th><th>Última msg</th></tr></thead>
              <tbody>
                {lista.map((c) => (
                  <tr key={c.id} role="button" onClick={() => abrir(c.id)} style={c.priority === "urgente" && c.status !== "fechado" ? { borderLeft: "3px solid var(--st-vermelho)" } : undefined}>
                    <td className="fw-semibold">{c.tenant_name}</td>
                    <td className="text-muted-2">{c.number}</td>
                    <td><div className="fw-semibold">{c.title}</div><div className="small text-muted-2">{c.opened_by_name} · {fmtDt(c.created_at)}</div></td>
                    <td className="small">{c.category_label}</td>
                    <td className="small">{c.priority_label}</td>
                    <td><span className={`status-pill ${STATUS_CH[c.status]?.cls}`}><i className={`bi ${STATUS_CH[c.status]?.icon}`} />{STATUS_CH[c.status]?.label}</span></td>
                    <td className="small">{c.assigned_to_name || <span className="text-muted-2">—</span>}</td>
                    <td className="small text-muted-2">{fmtDt(c.last_message_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal show={!!aberto} onHide={() => setAberto(null)} size="lg">
        {aberto && (
          <>
            <Modal.Header closeButton>
              <Modal.Title className="fs-6"><span className="text-muted-2">{aberto.tenant_name} · #{aberto.number}</span> {aberto.title}</Modal.Title>
            </Modal.Header>
            <Modal.Body>
              <div className="row g-2 mb-3">
                <div className="col-md-3"><Form.Label className="small mb-0">Situação</Form.Label>
                  <Form.Select size="sm" value={aberto.status} onChange={(e) => mudar({ status: e.target.value })}>{Object.entries(STATUS_CH).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Form.Select></div>
                <div className="col-md-3"><Form.Label className="small mb-0">Prioridade</Form.Label>
                  <Form.Select size="sm" value={aberto.priority} onChange={(e) => mudar({ priority: e.target.value })}>{PRIORIDADES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Form.Select></div>
                <div className="col-md-3"><Form.Label className="small mb-0">Categoria</Form.Label>
                  <Form.Select size="sm" value={aberto.category} onChange={(e) => mudar({ category: e.target.value })}>{CATEGORIAS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Form.Select></div>
                <div className="col-md-3"><Form.Label className="small mb-0">Atendente</Form.Label>
                  <Form.Select size="sm" value={aberto.assigned_to ?? ""} onChange={(e) => mudar({ assigned_to: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{atendentes.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</Form.Select></div>
              </div>
              <div className="small text-muted-2 mb-2">Aberto por {aberto.opened_by_name} em {fmtDt(aberto.created_at)}{aberto.rating ? ` · avaliação do cliente ${aberto.rating}/5${aberto.rating_comment ? ` (${aberto.rating_comment})` : ""}` : ""}</div>
              <ConversaChamado chamado={aberto} souSuporte onChange={recarregar} />
            </Modal.Body>
            <Modal.Footer>
              <Button size="sm" variant="outline-secondary" onClick={() => mudar({ status: "aguardando_cliente" })}>Aguardando cliente</Button>
              <Button size="sm" variant="outline-success" onClick={() => mudar({ status: "resolvido" })}><i className="bi bi-check2 me-1" />Resolvido</Button>
            </Modal.Footer>
          </>
        )}
      </Modal>
    </div>
  );
}
