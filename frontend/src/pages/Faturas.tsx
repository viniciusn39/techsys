import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Form, Modal } from "react-bootstrap";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { EmptyState, Panel, Skeleton, StatCard } from "../components/ui";
import type { Tenant } from "../types";
import { fmtDate, fmtPeriod } from "../utils/format";

interface Fatura {
  id: number; tenant: number; tenant_name: string; number: string; description: string; reference: string; amount: string;
  due_date: string; status: "aberta" | "paga" | "cancelada"; status_label: string; overdue: boolean; paid_at: string | null;
  payment_url: string; notes: string; has_file: boolean;
}
interface Resumo { total: string; em_aberto: string; pagas: number; abertas: number; atrasadas: number }

const brl = (v: string | number) => Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const erroDaApi = (e: unknown) => {
  const d = (e as ApiError).data;
  return d && typeof d === "object" ? Object.values(d).flat().join(" ") : (e as Error).message;
};

function Situacao({ f }: { f: Fatura }) {
  if (f.status === "paga") return <span className="status-pill st-verde"><i className="bi bi-check-circle" />Paga</span>;
  if (f.status === "cancelada") return <span className="status-pill st-neutro"><i className="bi bi-x-circle" />Cancelada</span>;
  return f.overdue
    ? <span className="status-pill st-vermelho"><i className="bi bi-exclamation-triangle" />Atrasada</span>
    : <span className="status-pill st-amarelo"><i className="bi bi-hourglass-split" />Aberta</span>;
}

/**
 * Faturas. Para a empresa (admin): consulta e download do que a plataforma lançou para ela.
 * Para o root (rota /root/faturas): lança, altera e exclui as faturas de qualquer empresa.
 */
export function Faturas({ gestao = false }: { gestao?: boolean }) {
  const { me } = useAuth();
  const [lista, setLista] = useState<Fatura[] | null>(null);
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [fTenant, setFTenant] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [editing, setEditing] = useState<Partial<Fatura> | null>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [erro, setErro] = useState("");

  const load = useCallback(() => {
    const q = new URLSearchParams();
    if (gestao && fTenant) q.set("tenant", fTenant);
    if (fStatus) q.set("status", fStatus);
    api.get<Fatura[]>(`/api/faturas/?${q}`).then(setLista).catch((e) => { setErro(e.message); setLista([]); });
    api.get<Resumo>(`/api/faturas/resumo/?${q}`).then(setResumo).catch(() => {});
  }, [gestao, fTenant, fStatus]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (gestao) api.get<any>("/api/tenants/").then((d) => setTenants(d.results ?? d)).catch(() => {}); }, [gestao]);

  const nova = () => {
    const hoje = new Date();
    const mes = `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}`;
    setErro(""); setArquivo(null);
    setEditing({ tenant: fTenant ? Number(fTenant) : undefined, status: "aberta", reference: `${mes}-01`, description: "Mensalidade TechSys Gestão" });
  };

  const save = async () => {
    if (!editing) return;
    if (!editing.tenant || !editing.number?.trim() || !editing.description?.trim() || !editing.amount || !editing.due_date || !editing.reference) {
      setErro("Preencha empresa, número, descrição, competência, valor e vencimento."); return;
    }
    const form = new FormData();
    Object.entries({ tenant: editing.tenant, number: editing.number, description: editing.description, reference: editing.reference, amount: editing.amount,
      due_date: editing.due_date, status: editing.status, payment_url: editing.payment_url ?? "", notes: editing.notes ?? "" }).forEach(([k, v]) => form.append(k, String(v)));
    if (arquivo) form.append("file", arquivo);
    try {
      await api.upload(editing.id ? `/api/faturas/${editing.id}/` : "/api/faturas/", form, editing.id ? "PATCH" : "POST");
      setEditing(null);
      load();
    } catch (e) { setErro(erroDaApi(e)); }
  };
  const excluir = async () => {
    if (!editing?.id) return;
    try { await api.del(`/api/faturas/${editing.id}/`); setEditing(null); load(); } catch (e) { setErro(erroDaApi(e)); }
  };

  if (!gestao && me && me.role !== "admin" && me.role !== "root") {
    return <Panel><EmptyState icon="bi-receipt" title="Faturas são visíveis só para o administrador da empresa" /></Panel>;
  }
  if (lista === null) return <Panel><Skeleton height={300} /></Panel>;

  return (
    <div className="d-grid gap-3">
      {resumo && (
        <div className="row g-3">
          <div className="col-6 col-xl-3"><StatCard icon="bi-cash-stack" label="Total" value={brl(resumo.total)} foot={`${brl(resumo.em_aberto)} em aberto`} /></div>
          <div className="col-6 col-xl-3"><StatCard icon="bi-check-circle" label="Pagas" value={resumo.pagas} /></div>
          <div className="col-6 col-xl-3"><StatCard icon="bi-hourglass-split" label="Abertas" value={resumo.abertas} /></div>
          <div className="col-6 col-xl-3"><StatCard icon="bi-exclamation-triangle" label="Atrasadas" value={resumo.atrasadas} /></div>
        </div>
      )}

      <Panel
        title={gestao ? "Faturas dos clientes" : "Suas faturas"}
        subtitle={gestao ? "Lance as faturas de cada empresa; ela consulta e baixa em Faturas." : "Visualize e baixe as faturas lançadas pela TechSys para a sua empresa."}
        actions={
          <div className="d-flex flex-wrap gap-2">
            {gestao && (
              <Form.Select size="sm" value={fTenant} onChange={(e) => setFTenant(e.target.value)} style={{ width: 220 }}>
                <option value="">Todas as empresas</option>{tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Form.Select>
            )}
            {!gestao && (
              <Form.Select size="sm" value={fStatus} onChange={(e) => setFStatus(e.target.value)} style={{ width: 150 }}>
                <option value="">Todas</option><option value="aberta">Abertas</option><option value="paga">Pagas</option><option value="cancelada">Canceladas</option>
              </Form.Select>
            )}
            {gestao && <Button size="sm" onClick={nova}><i className="bi bi-plus-lg me-1" />Nova fatura</Button>}
          </div>
        }
      >
        {erro && !editing && <Alert variant="warning" className="py-2 small">{erro}</Alert>}
        {lista.length === 0 ? <EmptyState icon="bi-receipt" title="Nenhuma fatura registrada ainda" /> : (
          <div className="table-responsive">
            <table className="table table-sm table-hover align-middle mb-0">
              <thead><tr>{gestao && <th>Empresa</th>}<th>Número</th><th>Descrição</th><th>Competência</th><th>Vencimento</th><th className="num">Valor</th><th>Situação</th><th /></tr></thead>
              <tbody>
                {lista.map((f) => (
                  <tr key={f.id} role={gestao ? "button" : undefined} onClick={() => { if (gestao) { setErro(""); setArquivo(null); setEditing(f); } }}>
                    {gestao && <td className="small">{f.tenant_name}</td>}
                    <td className="fw-semibold">{f.number}</td>
                    <td className="small">{f.description}{f.notes && !gestao && <div className="text-muted-2">{f.notes}</div>}</td>
                    <td className="small">{fmtPeriod(f.reference)}</td>
                    <td className="small">{fmtDate(f.due_date)}{f.paid_at && <div className="text-muted-2">paga em {fmtDate(f.paid_at)}</div>}</td>
                    <td className="num">{brl(f.amount)}</td>
                    <td><Situacao f={f} /></td>
                    <td className="text-end text-nowrap" onClick={(e) => e.stopPropagation()}>
                      {f.payment_url && f.status === "aberta" && <a className="btn btn-sm btn-outline-secondary me-1" href={f.payment_url} target="_blank" rel="noreferrer"><i className="bi bi-credit-card me-1" />Pagar</a>}
                      {f.has_file && <Button size="sm" variant="outline-secondary" title="Baixar" onClick={() => api.download(`/api/faturas/${f.id}/download/`, `fatura-${f.number}.pdf`).catch((e) => setErro(erroDaApi(e)))}><i className="bi bi-download" /></Button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg">
        <Modal.Header closeButton><Modal.Title>{editing?.id ? `Fatura ${editing.number}` : "Nova fatura"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editing && (
            <div className="row g-3">
              {erro && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erro}</Alert></div>}
              <div className="col-md-6"><Form.Label>Empresa *</Form.Label>
                <Form.Select disabled={!!editing.id} value={editing.tenant ?? ""} onChange={(e) => setEditing({ ...editing, tenant: Number(e.target.value) })}>
                  <option value="">Selecione…</option>{tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </Form.Select></div>
              <div className="col-md-3"><Form.Label>Número *</Form.Label><Form.Control value={editing.number ?? ""} onChange={(e) => setEditing({ ...editing, number: e.target.value })} placeholder="2026-0001" /></div>
              <div className="col-md-3"><Form.Label>Competência *</Form.Label><Form.Control type="month" value={(editing.reference ?? "").slice(0, 7)} onChange={(e) => setEditing({ ...editing, reference: e.target.value ? `${e.target.value}-01` : "" })} /></div>
              <div className="col-12"><Form.Label>Descrição *</Form.Label><Form.Control value={editing.description ?? ""} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Valor (R$) *</Form.Label><Form.Control type="number" step="0.01" min="0" value={editing.amount ?? ""} onChange={(e) => setEditing({ ...editing, amount: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Vencimento *</Form.Label><Form.Control type="date" value={editing.due_date ?? ""} onChange={(e) => setEditing({ ...editing, due_date: e.target.value })} /></div>
              <div className="col-md-4"><Form.Label>Situação</Form.Label>
                <Form.Select value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value as Fatura["status"] })}><option value="aberta">Aberta</option><option value="paga">Paga</option><option value="cancelada">Cancelada</option></Form.Select></div>
              <div className="col-md-6"><Form.Label>Link de pagamento</Form.Label><Form.Control type="url" value={editing.payment_url ?? ""} onChange={(e) => setEditing({ ...editing, payment_url: e.target.value })} placeholder="https://…" /></div>
              <div className="col-md-6"><Form.Label>PDF / boleto{editing.has_file && " (já tem; enviar outro substitui)"}</Form.Label><Form.Control type="file" accept=".pdf,image/*" onChange={(e) => setArquivo((e.target as HTMLInputElement).files?.[0] ?? null)} /></div>
              <div className="col-12"><Form.Label>Observações (o cliente vê)</Form.Label><Form.Control as="textarea" rows={2} value={editing.notes ?? ""} onChange={(e) => setEditing({ ...editing, notes: e.target.value })} /></div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          {editing?.id && <Button variant="outline-danger" className="me-auto" onClick={excluir}>Excluir</Button>}
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save}>Salvar</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
