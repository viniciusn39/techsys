import { useCallback, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { EmptyState, Panel, Skeleton, StatCard } from "../components/ui";

export interface Mensagem { id: number; author_name: string; body: string; is_internal: boolean; from_support: boolean; created_at: string }
export interface Chamado {
  id: number; number: number; title: string; description: string; category: string; category_label: string;
  priority: string; priority_label: string; status: string; status_label: string; module: string;
  opened_by_name: string; assigned_to: number | null; assigned_to_name: string; tenant_id: number; tenant_name: string;
  first_response_at: string | null; resolved_at: string | null; closed_at: string | null; rating: number | null; rating_comment: string;
  messages_count: number; last_message_at: string | null; created_at: string; updated_at: string; messages?: Mensagem[];
}

export const CATEGORIAS = [["suporte", "Suporte técnico"], ["consultoria", "Consultoria de gestão"], ["duvida", "Dúvida de uso"], ["erro", "Erro no sistema"], ["melhoria", "Sugestão de melhoria"], ["dados", "Dados do ERP / indicador"]];
export const PRIORIDADES = [["baixa", "Baixa"], ["media", "Média"], ["alta", "Alta"], ["urgente", "Urgente"]];
export const STATUS_CH: Record<string, { label: string; cls: string; icon: string }> = {
  aberto: { label: "Aberto", cls: "st-amarelo", icon: "bi-envelope" },
  em_atendimento: { label: "Em atendimento", cls: "st-neutro", icon: "bi-arrow-repeat" },
  aguardando_cliente: { label: "Aguardando você", cls: "st-vermelho", icon: "bi-person-exclamation" },
  resolvido: { label: "Resolvido", cls: "st-verde", icon: "bi-check-circle-fill" },
  fechado: { label: "Fechado", cls: "st-neutro", icon: "bi-archive" },
};
const PRIO_CLS: Record<string, string> = { baixa: "st-neutro", media: "st-amarelo", alta: "st-vermelho", urgente: "st-vermelho" };
export const fmtDt = (iso: string | null) => (iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—");

/** Conversa de um chamado (usada pelo cliente e pelo suporte). */
export function ConversaChamado({ chamado, souSuporte, onChange }: { chamado: Chamado; souSuporte: boolean; onChange: () => void }) {
  const [texto, setTexto] = useState("");
  const [interna, setInterna] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const enviar = async () => {
    if (!texto.trim()) return;
    setEnviando(true);
    try {
      await api.post(`/api/tickets/${chamado.id}/messages/`, { body: texto.trim(), is_internal: interna });
      setTexto(""); setInterna(false);
      onChange();
    } finally { setEnviando(false); }
  };
  return (
    <div>
      <div className="d-grid gap-2" style={{ maxHeight: 380, overflow: "auto" }}>
        {(chamado.messages ?? []).map((m) => (
          <div key={m.id} className="p-2 rounded" style={{
            background: m.is_internal ? "var(--st-amarelo-soft)" : m.from_support ? "var(--brand-soft)" : "var(--surface-sunken)",
            marginLeft: m.from_support ? 24 : 0, marginRight: m.from_support ? 0 : 24,
          }}>
            <div className="small text-muted-2 d-flex gap-2">
              <span className="fw-semibold">{m.author_name}{m.from_support ? " · suporte" : ""}</span>
              {m.is_internal && <span className="badge text-bg-warning">nota interna</span>}
              <span className="ms-auto">{fmtDt(m.created_at)}</span>
            </div>
            <div className="small mt-1" style={{ whiteSpace: "pre-wrap" }}>{m.body}</div>
          </div>
        ))}
      </div>
      {chamado.status !== "fechado" && (
        <div className="mt-2 d-grid gap-2">
          <Form.Control as="textarea" rows={3} placeholder={souSuporte ? "Responder ao cliente…" : "Escreva sua mensagem para o suporte…"} value={texto} onChange={(e) => setTexto(e.target.value)} />
          <div className="d-flex align-items-center gap-2">
            {souSuporte && <Form.Check type="checkbox" id="nota-interna" label="Nota interna (o cliente não vê)" checked={interna} onChange={(e) => setInterna(e.target.checked)} className="small" />}
            <Button size="sm" className="ms-auto" onClick={enviar} disabled={enviando || !texto.trim()}><i className="bi bi-send me-1" />Enviar</Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Chamados da empresa: abrir, acompanhar, conversar com o suporte/consultoria e avaliar. */
export function Chamados() {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const [lista, setLista] = useState<Chamado[] | null>(null);
  const [resumo, setResumo] = useState<any>(null);
  const [filtro, setFiltro] = useState("abertos");
  const [novo, setNovo] = useState<Partial<Chamado> | null>(params.get("novo") ? { category: params.get("categoria") || "suporte", priority: "media", title: "", description: "" } : null);
  const [aberto, setAberto] = useState<Chamado | null>(null);
  const [erro, setErro] = useState("");

  const load = useCallback(() => {
    api.get<Chamado[]>(`/api/tickets/?status=${filtro === "todos" ? "" : filtro}`).then(setLista).catch((e) => { setErro(e.message); setLista([]); });
    api.get("/api/tickets/resumo/").then(setResumo).catch(() => {});
  }, [filtro]);
  useEffect(() => { load(); }, [load]);

  const abrir = async (id: number) => setAberto(await api.get<Chamado>(`/api/tickets/${id}/`));
  const recarregarAberto = async () => { if (aberto) { setAberto(await api.get<Chamado>(`/api/tickets/${aberto.id}/`)); load(); } };

  const criar = async () => {
    if (!novo?.title?.trim() || !novo.description?.trim()) return;
    try {
      const t = await api.post<Chamado>("/api/tickets/", { title: novo.title.trim(), description: novo.description.trim(), category: novo.category, priority: novo.priority, module: novo.module ?? "" });
      setNovo(null); setParams({});
      load();
      abrir(t.id);
    } catch (e: any) { setErro(e.message); }
  };
  const mudar = async (dados: Record<string, any>) => { if (aberto) { await api.patch(`/api/tickets/${aberto.id}/`, dados); recarregarAberto(); } };

  if (lista === null) return <Panel><Skeleton height={300} /></Panel>;

  return (
    <div className="d-grid gap-3">
      <div className="row g-3">
        <div className="col-6 col-xl-3"><StatCard icon="bi-life-preserver" label="Chamados abertos" value={resumo?.abertos ?? 0} foot={`${resumo?.total ?? 0} no total`} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-person-exclamation" label="Aguardando você" value={resumo?.por_status?.aguardando_cliente ?? 0} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-check2-circle" label="Resolvidos" value={resumo?.por_status?.resolvido ?? 0} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-hourglass" label="Sem resposta ainda" value={resumo?.sem_resposta ?? 0} /></div>
      </div>

      <Panel
        title="Chamados"
        subtitle="Fale com o suporte técnico ou com a consultoria de gestão. Cada chamado tem uma conversa e você acompanha a situação aqui."
        actions={
          <div className="d-flex gap-2">
            <Form.Select size="sm" style={{ width: 160 }} value={filtro} onChange={(e) => setFiltro(e.target.value)}>
              <option value="abertos">Em aberto</option>
              <option value="todos">Todos</option>
              {Object.entries(STATUS_CH).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Form.Select>
            <Button size="sm" onClick={() => setNovo({ category: "suporte", priority: "media", title: "", description: "" })}><i className="bi bi-plus-lg me-1" />Abrir chamado</Button>
          </div>
        }
      >
        {erro && <div className="alert alert-warning py-2 small">{erro}</div>}
        {lista.length === 0 ? (
          <EmptyState icon="bi-life-preserver" title="Nenhum chamado" hint="Abra um chamado para suporte técnico, dúvida de uso, erro, dados do ERP ou consultoria de gestão." />
        ) : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0">
              <thead><tr><th>#</th><th>Chamado</th><th>Categoria</th><th>Prioridade</th><th>Situação</th><th>Atendente</th><th>Última mensagem</th></tr></thead>
              <tbody>
                {lista.map((c) => (
                  <tr key={c.id} role="button" onClick={() => abrir(c.id)}>
                    <td className="text-muted-2">{c.number}</td>
                    <td><div className="fw-semibold">{c.title}</div><div className="small text-muted-2">por {c.opened_by_name} · {fmtDt(c.created_at)}</div></td>
                    <td className="small">{c.category_label}</td>
                    <td><span className={`status-pill ${PRIO_CLS[c.priority]}`}><i className="bi bi-flag-fill" />{c.priority_label}</span></td>
                    <td><span className={`status-pill ${STATUS_CH[c.status]?.cls}`}><i className={`bi ${STATUS_CH[c.status]?.icon}`} />{STATUS_CH[c.status]?.label}</span></td>
                    <td className="small">{c.assigned_to_name || <span className="text-muted-2">—</span>}</td>
                    <td className="small text-muted-2">{fmtDt(c.last_message_at)} · {c.messages_count} msg</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal show={!!novo} onHide={() => { setNovo(null); setParams({}); }} size="lg">
        <Modal.Header closeButton><Modal.Title>Abrir chamado</Modal.Title></Modal.Header>
        <Modal.Body>
          {novo && (
            <div className="row g-3">
              <div className="col-md-6"><Form.Label>Categoria</Form.Label><Form.Select value={novo.category} onChange={(e) => setNovo({ ...novo, category: e.target.value })}>{CATEGORIAS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Form.Select></div>
              <div className="col-md-6"><Form.Label>Prioridade</Form.Label><Form.Select value={novo.priority} onChange={(e) => setNovo({ ...novo, priority: e.target.value })}>{PRIORIDADES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Form.Select></div>
              <div className="col-12"><Form.Label>Título</Form.Label><Form.Control autoFocus value={novo.title ?? ""} onChange={(e) => setNovo({ ...novo, title: e.target.value })} placeholder="Resuma em uma linha" /></div>
              <div className="col-12"><Form.Label>Descrição</Form.Label><Form.Control as="textarea" rows={5} value={novo.description ?? ""} onChange={(e) => setNovo({ ...novo, description: e.target.value })} placeholder="O que aconteceu, em qual tela, o que você esperava. Para consultoria: qual decisão ou análise você precisa." /></div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => { setNovo(null); setParams({}); }}>Cancelar</Button>
          <Button onClick={criar} disabled={!novo?.title?.trim() || !novo?.description?.trim()}>Abrir chamado</Button>
        </Modal.Footer>
      </Modal>

      <Modal show={!!aberto} onHide={() => setAberto(null)} size="lg">
        {aberto && (
          <>
            <Modal.Header closeButton>
              <Modal.Title className="fs-6">
                <span className="text-muted-2">#{aberto.number}</span> {aberto.title}
                <span className={`status-pill ${STATUS_CH[aberto.status]?.cls} ms-2`}><i className={`bi ${STATUS_CH[aberto.status]?.icon}`} />{STATUS_CH[aberto.status]?.label}</span>
              </Modal.Title>
            </Modal.Header>
            <Modal.Body>
              <div className="small text-muted-2 mb-2 d-flex flex-wrap gap-3">
                <span>{aberto.category_label}</span><span>prioridade {aberto.priority_label}</span>
                <span>aberto em {fmtDt(aberto.created_at)} por {aberto.opened_by_name}</span>
                {aberto.assigned_to_name && <span>atendente {aberto.assigned_to_name}</span>}
                {aberto.first_response_at && <span>1ª resposta {fmtDt(aberto.first_response_at)}</span>}
              </div>
              <ConversaChamado chamado={aberto} souSuporte={me?.role === "root"} onChange={recarregarAberto} />
              {aberto.status === "resolvido" && (
                <div className="mt-3 p-3 rounded" style={{ background: "var(--surface-sunken)" }}>
                  <div className="fw-semibold small mb-1">O chamado foi resolvido. Como foi o atendimento?</div>
                  <div className="d-flex gap-1 align-items-center">
                    {[1, 2, 3, 4, 5].map((n) => <button key={n} className={`btn btn-sm ${aberto.rating === n ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => mudar({ rating: n })}>{n}</button>)}
                    <Button size="sm" variant="outline-secondary" className="ms-auto" onClick={() => mudar({ status: "fechado" })}>Fechar chamado</Button>
                    <Button size="sm" variant="link" onClick={() => mudar({ status: "aberto" })}>Ainda não resolveu</Button>
                  </div>
                </div>
              )}
              {aberto.status === "fechado" && <div className="small text-muted-2 mt-2">Chamado fechado{aberto.rating ? ` · avaliação ${aberto.rating}/5` : ""}. <Button size="sm" variant="link" className="p-0" onClick={() => mudar({ status: "aberto" })}>Reabrir</Button></div>}
            </Modal.Body>
          </>
        )}
      </Modal>
    </div>
  );
}
