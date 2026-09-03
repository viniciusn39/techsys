import { useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton } from "../components/ui";
import type { Tenant } from "../types";

interface Bundle {
  tenant: { id: number; name: string; slug: string };
  connector: { id: number; online: boolean; agent_version: string; last_seen_at: string | null; health: Record<string, any> };
  server: string;
  token: string;
  agent_version: string;
  linux: { oneliner: string; script_url: string; script_name: string; run: string; check: string; uninstall: string };
  windows: { script_url: string; script_name: string; run: string; check: string; uninstall: string };
  dba_script: string;
  entities: string[];
}

function Cmd({ label, value, hint }: { label: string; value: string; hint?: string }) {
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
        className="p-2 rounded mb-1"
        style={{
          background: "var(--surface-sunken)", border: "1px solid var(--border)",
          fontSize: "0.76rem", whiteSpace: "pre-wrap", wordBreak: "break-all",
        }}
      >
        {value}
      </pre>
      {hint && <div className="text-muted-2" style={{ fontSize: "0.74rem" }}>{hint}</div>}
    </div>
  );
}

export function Instalador() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [sel, setSel] = useState<number | "">("");
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [os, setOs] = useState<"linux" | "windows">("linux");
  const [showDba, setShowDba] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/tenants/").then((d) => setTenants((d.results ?? d).filter((t: Tenant) => t.is_active))).catch(() => {});
  }, []);

  useEffect(() => {
    if (!sel) {
      setBundle(null);
      return;
    }
    setLoading(true);
    setError("");
    api.get<Bundle>(`/api/erp/instalador/?tenant=${sel}`)
      .then(setBundle)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sel]);

  const rotate = async () => {
    if (!bundle || !confirm(`Gerar nova chave para ${bundle.tenant.name}? O agente já instalado deixa de autenticar até ser reinstalado com a chave nova.`)) return;
    await api.post("/api/erp/instalador/", { tenant: bundle.tenant.id });
    setBundle(await api.get<Bundle>(`/api/erp/instalador/?tenant=${bundle.tenant.id}`));
  };

  const osData = bundle ? bundle[os] : null;
  const publicWarning = bundle && /localhost|127\.0\.0\.1|backend:8000/.test(bundle.server);

  return (
    <div>
      <div className="row g-3">
        <div className="col-xl-4">
          <Panel title="1. Escolha a empresa" subtitle="A chave é gerada na hora e vale para o agente dessa empresa.">
            <Form.Select value={sel} onChange={(e) => setSel(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Selecione o cliente…</option>
              {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </Form.Select>

            {bundle && (
              <div className="mt-3">
                <div className="stat-label mb-1"><i className="bi bi-key" />Chave do agente</div>
                <div className="input-group input-group-sm">
                  <Form.Control readOnly value={bundle.token} className="font-monospace" onFocus={(e) => e.target.select()} />
                  <Button variant="outline-secondary" onClick={() => navigator.clipboard.writeText(bundle.token)}>
                    <i className="bi bi-clipboard" />
                  </Button>
                </div>
                <div className="d-flex align-items-center gap-2 mt-2 flex-wrap">
                  <span className={`status-pill ${bundle.connector.online ? "st-verde" : "st-neutro"}`}>
                    <i className={`bi ${bundle.connector.online ? "bi-check-circle-fill" : "bi-circle"}`} />
                    {bundle.connector.online ? `Agente online · v${bundle.connector.agent_version}` : "Agente ainda não conectou"}
                  </span>
                  <Button size="sm" variant="link" className="p-0" onClick={rotate}>gerar nova chave</Button>
                </div>
              </div>
            )}

            {bundle && (
              <div className="mt-4">
                <div className="stat-label mb-1"><i className="bi bi-shield-lock" />Antes de instalar</div>
                <div className="small text-secondary-2 mb-2">
                  O DBA cria o usuário Oracle <code>TECHSYS</code> somente-leitura nas {bundle.entities.length} entidades do plano.
                </div>
                <Button size="sm" variant="outline-secondary" onClick={() => setShowDba(true)}>
                  <i className="bi bi-file-earmark-code me-1" />Ver script do DBA
                </Button>
              </div>
            )}
          </Panel>
        </div>

        <div className="col-xl-8">
          {!sel ? (
            <Panel>
              <EmptyState
                icon="bi-robot"
                title="Instalador do agente TechSys"
                hint="Escolha o cliente à esquerda. A chave, o script pronto e os comandos aparecem aqui."
              />
            </Panel>
          ) : loading || !bundle ? (
            <Panel>{error ? <div className="alert alert-danger py-2 small">{error}</div> : <Skeleton height={320} />}</Panel>
          ) : (
            <Panel
              title={`2. Instalar em ${bundle.tenant.name}`}
              subtitle={`Servidor: ${bundle.server} · agente v${bundle.agent_version || "?"} · só leitura no ERP`}
              actions={
                <div className="btn-group btn-group-sm">
                  <button className={`btn btn-outline-secondary ${os === "linux" ? "active" : ""}`} onClick={() => setOs("linux")}>
                    <i className="bi bi-ubuntu me-1" />Linux
                  </button>
                  <button className={`btn btn-outline-secondary ${os === "windows" ? "active" : ""}`} onClick={() => setOs("windows")}>
                    <i className="bi bi-windows me-1" />Windows
                  </button>
                </div>
              }
            >
              {publicWarning && (
                <div className="alert alert-warning py-2 small">
                  <i className="bi bi-exclamation-triangle-fill me-1" />
                  O servidor está como <code>{bundle.server}</code> — a máquina do cliente não vai alcançar esse endereço.
                  Publique a plataforma e defina <code>PUBLIC_URL</code> (ex.: <code>https://gestao.suaempresa.com.br</code>) antes de instalar.
                </div>
              )}

              <div className="d-flex align-items-start gap-3 p-3 rounded mb-3" style={{ background: "var(--brand-soft)", border: "1px solid var(--border)" }}>
                <span style={{ width: 40, height: 40, borderRadius: 10, display: "grid", placeItems: "center", background: "var(--surface)", color: "var(--brand)", flex: "none", fontSize: "1.2rem" }}>
                  <i className="bi bi-download" />
                </span>
                <div className="flex-grow-1">
                  <div className="fw-semibold">Script pronto — chave e servidor já embutidos</div>
                  <div className="small text-secondary-2 mb-2">
                    Baixe, leve para a máquina que enxerga o Oracle e rode informando só o usuário e a senha do banco.
                  </div>
                  <a className="btn btn-primary btn-sm" href={osData!.script_url} download={osData!.script_name}>
                    <i className={`bi ${os === "linux" ? "bi-ubuntu" : "bi-windows"} me-1`} />Baixar {osData!.script_name}
                  </a>
                </div>
              </div>

              <Cmd label={os === "linux" ? "Rodar (como root)" : "Rodar (PowerShell como administrador)"} value={osData!.run}
                   hint={`Troque SENHA_DO_ORACLE pela senha do usuário TECHSYS. ${os === "linux" ? "--dsn host:1521/SERVICO" : "-Dsn host:1521/SERVICO"} é opcional: sem ele o agente descobre o Oracle sozinho.`} />

              {os === "linux" && (
                <Cmd label="Alternativa: one-liner (baixa e instala direto)" value={bundle.linux.oneliner} />
              )}

              <Cmd label="Conferir se está rodando" value={osData!.check} />
              <Cmd label="Desinstalar" value={osData!.uninstall} />

              <div className="text-muted-2" style={{ fontSize: "0.76rem" }}>
                <i className="bi bi-info-circle me-1" />
                Depois de instalado, acompanhe a carga em <strong>Conector ERP</strong> dentro da empresa: a máquina aparece online em até 60 s
                e as primeiras entidades (filiais, vendedores, clientes) chegam nos primeiros minutos.
              </div>
            </Panel>
          )}
        </div>
      </div>

      <Modal show={showDba} onHide={() => setShowDba(false)} size="lg" centered>
        <Modal.Header closeButton><Modal.Title className="fs-6">Script do DBA — usuário Oracle somente leitura</Modal.Title></Modal.Header>
        <Modal.Body>
          {bundle && (
            <>
              <div className="text-muted-2 small mb-2">
                Substitua <code>__DONO__</code> pelo schema dono das tabelas PC* e <code>__SENHA__</code> por uma senha forte.
                Se o DBA preferir <code>GRANT SELECT ANY TABLE</code>, também funciona — mas nada de privilégios de criação.
              </div>
              <Cmd label="grants.sql" value={bundle.dba_script} />
            </>
          )}
        </Modal.Body>
      </Modal>
    </div>
  );
}
