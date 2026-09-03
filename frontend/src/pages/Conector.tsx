import { useCallback, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton, StatCard } from "../components/ui";

interface Connector {
  id: number;
  name: string;
  erp: string;
  perfil: string;
  ingest_token: string;
  config: Record<string, any>;
  health: Record<string, any>;
  last_seen_at: string | null;
  is_active: boolean;
  online: boolean;
  agent_version: string;
}

interface EntityState {
  entity: string;
  last_ingest_at: string | null;
  rows_received: number;
  rows_imported: number;
  total_imported: number;
  last_error: string;
}

interface Status {
  connector: Connector;
  entities: EntityState[];
  logs: { id: number; kind: string; summary: string; data: any; created_at: string }[];
  commands: { id: number; command: string; status: string; result: any; error: string; created_at: string }[];
}

interface Install {
  server: string;
  token: string;
  linux: string;
  windows: string;
  dba_script: string;
  entities: string[];
}

const ENTITY_LABEL: Record<string, string> = {
  branch: "Filiais", salesrep: "Vendedores (RCA)", supplier: "Fornecedores", employee: "Funcionários",
  customer: "Clientes", product: "Produtos", sales_invoice: "Notas de venda",
  sales_invoice_item: "Itens de nota (custo/margem)", title_receivable: "Contas a receber",
  title_payable: "Contas a pagar", financial_snapshot: "Fotografia financeira diária",
  bank_account: "Contas bancárias", cash_movement: "Extrato bancário", stock: "Estoque por filial",
  order: "Pedidos de venda", purchase: "Notas de entrada (compras)", load: "Carregamentos",
};

const KIND_ICON: Record<string, string> = {
  ingest: "bi-cloud-arrow-down", heartbeat: "bi-heart-pulse", error: "bi-exclamation-triangle-fill",
  update: "bi-arrow-repeat", plan: "bi-list-check", command: "bi-terminal", result: "bi-reply",
};

function Copiavel({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  const [ok, setOk] = useState(false);
  return (
    <div className="mb-3">
      <div className="d-flex justify-content-between align-items-center mb-1">
        <Form.Label className="mb-0">{label}</Form.Label>
        <Button
          size="sm" variant="outline-secondary"
          onClick={async () => {
            await navigator.clipboard.writeText(value);
            setOk(true);
            window.setTimeout(() => setOk(false), 1500);
          }}
        >
          <i className={`bi ${ok ? "bi-check-lg" : "bi-clipboard"} me-1`} />{ok ? "Copiado" : "Copiar"}
        </Button>
      </div>
      <pre
        className="p-2 rounded mb-0"
        style={{
          background: "var(--surface-sunken)", border: "1px solid var(--border)",
          fontSize: mono ? "0.76rem" : "0.85rem", whiteSpace: "pre-wrap", wordBreak: "break-all",
          maxHeight: 260, overflow: "auto",
        }}
      >
        {value}
      </pre>
    </div>
  );
}

export function Conector() {
  const [connectors, setConnectors] = useState<Connector[] | null>(null);
  const [current, setCurrent] = useState<Connector | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [install, setInstall] = useState<Install | null>(null);
  const [showInstall, setShowInstall] = useState(false);
  const [showDba, setShowDba] = useState(false);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  const loadStatus = useCallback(async (id: number) => {
    setStatus(await api.get<Status>(`/api/erp/connectors/${id}/status/`));
  }, []);

  const load = useCallback(async () => {
    const list = await api.get<Connector[]>("/api/erp/connectors/");
    setConnectors(list);
    if (list.length > 0) {
      setCurrent(list[0]);
      loadStatus(list[0].id);
    }
  }, [loadStatus]);

  useEffect(() => {
    load().catch(() => setConnectors([]));
  }, [load]);

  // Atualiza o status a cada 30 s enquanto a tela está aberta.
  useEffect(() => {
    if (!current) return;
    const t = window.setInterval(() => loadStatus(current.id).catch(() => {}), 30000);
    return () => window.clearInterval(t);
  }, [current, loadStatus]);

  const create = async () => {
    setBusy("create");
    try {
      await api.post("/api/erp/connectors/", { name: "WinThor", erp: "winthor", perfil: "misto" });
      await load();
    } finally {
      setBusy("");
    }
  };

  const openInstall = async () => {
    if (!current) return;
    setInstall(await api.get<Install>(`/api/erp/connectors/${current.id}/install/`));
    setShowInstall(true);
  };

  const openDba = async () => {
    if (!current) return;
    if (!install) setInstall(await api.get<Install>(`/api/erp/connectors/${current.id}/install/`));
    setShowDba(true);
  };

  const command = async (cmd: string, payload: any = {}) => {
    if (!current) return;
    setBusy(cmd);
    try {
      await api.post(`/api/erp/connectors/${current.id}/command/`, { command: cmd, payload });
      setNotice(`Comando "${cmd}" enfileirado — o agente responde no próximo long-poll (até 30 s).`);
      window.setTimeout(() => loadStatus(current.id), 8000);
    } finally {
      setBusy("");
    }
  };

  const recalcular = async () => {
    if (!current) return;
    setBusy("recalc");
    try {
      await api.post(`/api/erp/connectors/${current.id}/recalcular/`, { meses: 12 });
      setNotice("Recálculo dos indicadores ligados ao ERP enfileirado (últimos 12 meses).");
    } finally {
      setBusy("");
    }
  };

  const rotate = async () => {
    if (!current || !confirm("Gerar nova chave? O agente já instalado deixa de autenticar até ser reinstalado com a chave nova.")) return;
    await api.post(`/api/erp/connectors/${current.id}/rotate-token/`);
    setInstall(null);
    await load();
  };

  if (connectors === null) return <Panel><Skeleton height={300} /></Panel>;

  if (connectors.length === 0) {
    return (
      <Panel>
        <EmptyState
          icon="bi-robot"
          title="Nenhum conector configurado"
          hint="Crie o conector para gerar a chave do agente e o script do DBA. O agente roda na rede do cliente e só lê o ERP."
          action={<Button onClick={create} disabled={!!busy}><i className="bi bi-plus-lg me-1" />Criar conector WinThor</Button>}
        />
      </Panel>
    );
  }

  const c = status?.connector ?? current!;
  const h = c.health || {};
  const totalImportado = (status?.entities ?? []).reduce((a, e) => a + (e.total_imported || 0), 0);
  const comCarga = (status?.entities ?? []).filter((e) => e.last_ingest_at).length;
  const lastSeen = c.last_seen_at ? new Date(c.last_seen_at).toLocaleString("pt-BR") : "nunca";

  return (
    <div>
      {notice && (
        <div className="alert alert-info py-2 small d-flex align-items-center gap-2">
          <i className="bi bi-info-circle-fill" />{notice}
          <button className="btn-close ms-auto" style={{ fontSize: "0.6rem" }} onClick={() => setNotice("")} />
        </div>
      )}

      <div className="row g-3 mb-3">
        <div className="col-6 col-xl-3">
          <StatCard
            icon={c.online ? "bi-wifi" : "bi-wifi-off"}
            label="Agente"
            value={
              <span className={`status-pill ${c.online ? "st-verde" : "st-vermelho"}`} style={{ fontSize: "0.95rem" }}>
                <i className={`bi ${c.online ? "bi-check-circle-fill" : "bi-x-circle-fill"}`} />
                {c.online ? "Online" : "Offline"}
              </span>
            }
            foot={`último contato: ${lastSeen}`}
          />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard
            icon="bi-database"
            label="Oracle do WinThor"
            value={
              <span className={`status-pill ${h.oracle_ok ? "st-verde" : h.oracle_ok === false ? "st-vermelho" : "st-neutro"}`} style={{ fontSize: "0.95rem" }}>
                <i className={`bi ${h.oracle_ok ? "bi-check-circle-fill" : "bi-dash-circle"}`} />
                {h.oracle_ok ? "Conectado" : h.oracle_ok === false ? "Sem conexão" : "Sem informação"}
              </span>
            }
            foot={h.oracle_erro ? <span className="text-danger">{String(h.oracle_erro).slice(0, 90)}</span> : h.schema ? `schema ${h.schema}` : "aguardando primeiro heartbeat"}
          />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard icon="bi-cloud-arrow-down" label="Registros importados" value={totalImportado.toLocaleString("pt-BR")} foot={`${comCarga} de ${status?.entities.length ?? 0} entidades com carga`} />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard icon="bi-cpu" label="Versão do agente" value={c.agent_version || "—"} foot={h.host ? `${h.host} · Python ${h.python ?? ""}` : "ainda não instalado"} />
        </div>
      </div>

      <div className="filter-bar">
        <span className="fw-semibold">{c.name}</span>
        <span className="badge text-bg-light border fw-normal text-capitalize">{c.perfil}</span>
        <div className="ms-auto d-flex gap-2 flex-wrap">
          <Button size="sm" onClick={openInstall}><i className="bi bi-download me-1" />Instalar agente</Button>
          <Button size="sm" variant="outline-secondary" onClick={openDba}><i className="bi bi-shield-lock me-1" />Script do DBA</Button>
          <Button size="sm" variant="outline-secondary" onClick={() => command("validar_schema")} disabled={!!busy || !c.online}>
            <i className="bi bi-clipboard-check me-1" />Validar schema
          </Button>
          <Button size="sm" variant="outline-secondary" onClick={() => command("coletar")} disabled={!!busy || !c.online}>
            <i className="bi bi-play-circle me-1" />Coletar agora
          </Button>
          <Button size="sm" variant="outline-secondary" onClick={recalcular} disabled={!!busy}>
            <i className="bi bi-calculator me-1" />Recalcular indicadores
          </Button>
          <Button size="sm" variant="outline-secondary" onClick={rotate}><i className="bi bi-key me-1" />Nova chave</Button>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-xl-7">
          <Panel title="Sincronização por entidade" subtitle="O que já chegou do ERP e quando">
            <div className="table-responsive">
              <table className="table table-sm align-middle">
                <thead>
                  <tr><th>Entidade</th><th>Última carga</th><th className="num">Último lote</th><th className="num">Total</th><th>Situação</th></tr>
                </thead>
                <tbody>
                  {(status?.entities ?? []).map((e) => (
                    <tr key={e.entity}>
                      <td>
                        <div className="fw-semibold small">{ENTITY_LABEL[e.entity] ?? e.entity}</div>
                        <div className="text-muted-2" style={{ fontSize: "0.72rem" }}>{e.entity}</div>
                      </td>
                      <td className="small text-secondary-2">{e.last_ingest_at ? new Date(e.last_ingest_at).toLocaleString("pt-BR") : "—"}</td>
                      <td className="num small">{e.last_ingest_at ? `${e.rows_imported}/${e.rows_received}` : "—"}</td>
                      <td className="num small">{e.total_imported.toLocaleString("pt-BR")}</td>
                      <td>
                        {e.last_error ? (
                          <span className="status-pill st-vermelho" title={e.last_error}><i className="bi bi-x-circle-fill" />erro</span>
                        ) : e.last_ingest_at ? (
                          <span className="status-pill st-verde"><i className="bi bi-check-circle-fill" />ok</span>
                        ) : (
                          <span className="status-pill st-neutro"><i className="bi bi-hourglass-split" />aguardando</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
        <div className="col-xl-5">
          <Panel title="Atividade recente" subtitle="Comunicação do agente com a plataforma">
            {(status?.commands ?? []).length > 0 && (
              <div className="mb-3">
                {status!.commands.slice(0, 3).map((cmd) => (
                  <div key={cmd.id} className="suggestion-row">
                    <i className="bi bi-terminal mt-1" />
                    <div className="flex-grow-1 small">
                      <div className="d-flex justify-content-between">
                        <span className="fw-semibold">{cmd.command}</span>
                        <span className={`status-pill ${cmd.status === "done" ? "st-verde" : cmd.status === "error" ? "st-vermelho" : "st-amarelo"}`}>
                          <i className={`bi ${cmd.status === "done" ? "bi-check-circle-fill" : cmd.status === "error" ? "bi-x-circle-fill" : "bi-hourglass-split"}`} />{cmd.status}
                        </span>
                      </div>
                      {cmd.error && <div className="text-danger" style={{ fontSize: "0.74rem" }}>{cmd.error.slice(0, 200)}</div>}
                      {cmd.status === "done" && cmd.result?.resumo && (
                        <div className="text-muted-2" style={{ fontSize: "0.74rem" }}>
                          {cmd.result.resumo.ok} ok · {cmd.result.resumo.parcial} parcial · {cmd.result.resumo.falha} falha
                          {Object.keys(cmd.result.tabelas_inacessiveis || {}).length > 0 && (
                            <div className="mt-1">{Object.entries(cmd.result.tabelas_inacessiveis).map(([t, m]) => <div key={t}><code>{t}</code> — {String(m)}</div>)}</div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {(status?.logs ?? []).length === 0 ? (
              <EmptyState icon="bi-activity" title="Nenhuma comunicação ainda" hint="Instale o agente na rede do cliente para começar." />
            ) : (
              <div style={{ maxHeight: 420, overflow: "auto" }}>
                {status!.logs.map((l) => (
                  <div key={l.id} className="d-flex gap-2 py-1 border-bottom small" style={{ borderColor: "var(--grid)" }}>
                    <i className={`bi ${KIND_ICON[l.kind] ?? "bi-dot"} ${l.kind === "error" ? "text-danger" : "text-muted-2"}`} />
                    <span className="text-muted-2" style={{ minWidth: 118, fontSize: "0.72rem" }}>{new Date(l.created_at).toLocaleString("pt-BR")}</span>
                    <span className="flex-grow-1">{l.summary}</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </div>

      <Modal show={showInstall} onHide={() => setShowInstall(false)} size="lg" centered>
        <Modal.Header closeButton><Modal.Title className="fs-6">Instalar o agente na rede do cliente</Modal.Title></Modal.Header>
        <Modal.Body>
          {install ? (
            <>
              <div className="alert alert-warning py-2 small">
                <i className="bi bi-exclamation-triangle-fill me-1" />
                Antes, o DBA precisa criar o usuário Oracle somente-leitura (botão <strong>Script do DBA</strong>).
                Troque <code>SENHA_DO_ORACLE</code> pela senha desse usuário. Sem <code>--dsn</code> o agente descobre o Oracle sozinho.
              </div>
              <Copiavel label="Linux (rode como root na máquina que enxerga o Oracle)" value={install.linux} />
              <Copiavel label="Windows (PowerShell como administrador)" value={install.windows} />
              <Copiavel label="Chave do agente" value={install.token} />
              <div className="text-muted-2 small">
                Servidor: <code>{install.server}</code> — se o cliente acessa a plataforma por outro endereço, defina <code>PUBLIC_URL</code> no servidor.
                Entidades coletadas: {install.entities.length}.
              </div>
            </>
          ) : <Skeleton height={200} />}
        </Modal.Body>
      </Modal>

      <Modal show={showDba} onHide={() => setShowDba(false)} size="lg" centered>
        <Modal.Header closeButton><Modal.Title className="fs-6">Script do DBA — usuário Oracle somente leitura</Modal.Title></Modal.Header>
        <Modal.Body>
          {install ? (
            <>
              <div className="text-muted-2 small mb-2">
                Substitua <code>__DONO__</code> pelo schema dono das tabelas PC* e <code>__SENHA__</code> por uma senha forte.
                Só <code>GRANT SELECT</code>, tabela a tabela — o agente nunca grava no ERP.
              </div>
              <Copiavel label="grants.sql" value={install.dba_script} />
            </>
          ) : <Skeleton height={200} />}
        </Modal.Body>
      </Modal>
    </div>
  );
}
