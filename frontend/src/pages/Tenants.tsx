import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { EmptyState, Panel, Skeleton } from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import type { Tenant } from "../types";

interface TenantForm extends Partial<Tenant> {
  admin_email?: string;
  admin_password?: string;
  admin_name?: string;
}

const slugify = (s: string) =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

interface Armazenamento { tenant: string; total_bytes: number; total_linhas: number; tabelas: { tabela: string; modelo: string; app: string; linhas: number; bytes: number; tabela_bytes: number }[] }

const bytes = (n: number | null | undefined) => {
  if (n === null || n === undefined) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
};

/** Modal: disco ocupado pelos dados da empresa, por tabela e no total. */
function DiscoDaEmpresa({ tenant, onHide }: { tenant: Tenant; onHide: () => void }) {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [d, setD] = useState<Armazenamento | null>(null);
  const [erro, setErro] = useState("");
  useEffect(() => { api.get<Armazenamento>(`/api/tenants/${tenant.id}/armazenamento/`).then(setD).catch((e) => setErro(e.message)); }, [tenant.id]);
  const option = useMemo(() => {
    const rows = [...(d?.tabelas ?? [])].slice(0, 14).reverse();
    return {
      grid: { left: 4, right: 70, top: 6, bottom: 4, containLabel: true },
      tooltip: { trigger: "item" as const, formatter: (p: any) => { const r = rows[p.dataIndex]; return `<strong>${bytes(r.bytes)}</strong><br/>${r.tabela}<br/><span style="color:${t.inkMuted}">${r.linhas.toLocaleString("pt-BR")} linhas · ${d && d.total_bytes ? Math.round(100 * r.bytes / d.total_bytes) : 0}% do total</span>`; } },
      xAxis: { type: "value" as const, axisLabel: { formatter: (v: number) => bytes(v) } },
      yAxis: { type: "category" as const, data: rows.map((r) => r.tabela.replace(/^(erp|indicators|strategy|plans|support|accounts|ai)_/, "")), axisLabel: { fontSize: 11, color: t.inkSecondary } },
      series: [{ type: "bar" as const, barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[0], borderRadius: BAR_RADIUS_H }, label: { show: true, position: "right" as const, fontSize: 11, color: t.inkSecondary, formatter: (p: any) => bytes(p.value) }, data: rows.map((r) => r.bytes) }],
    };
  }, [d, t]);
  return (
    <Modal show onHide={onHide} size="lg">
      <Modal.Header closeButton><Modal.Title className="fs-6"><i className="bi bi-hdd me-2" />Armazenamento · {tenant.name}</Modal.Title></Modal.Header>
      <Modal.Body>
        {erro ? <div className="alert alert-warning py-2 small">{erro}</div> : !d ? <Skeleton height={240} /> : (
          <>
            <div className="d-flex flex-wrap gap-3 mb-3">
              <div className="p-3 rounded flex-grow-1" style={{ background: "var(--surface-sunken)" }}><div className="small text-muted-2">Total ocupado (dados + índices)</div><div className="fs-4 fw-bold">{bytes(d.total_bytes)}</div></div>
              <div className="p-3 rounded flex-grow-1" style={{ background: "var(--surface-sunken)" }}><div className="small text-muted-2">Linhas da empresa</div><div className="fs-4 fw-bold">{d.total_linhas.toLocaleString("pt-BR")}</div></div>
              <div className="p-3 rounded flex-grow-1" style={{ background: "var(--surface-sunken)" }}><div className="small text-muted-2">Tabelas com dados</div><div className="fs-4 fw-bold">{d.tabelas.length}</div></div>
            </div>
            {d.tabelas.length === 0 ? <EmptyState icon="bi-hdd" title="Sem dados ainda" /> : (
              <>
                <EChart option={option} height={Math.max(200, Math.min(14, d.tabelas.length) * 24 + 20)} />
                <div className="table-responsive mt-2" style={{ maxHeight: 320, overflow: "auto" }}>
                  <table className="table table-sm mb-0" style={{ fontSize: "0.8rem" }}>
                    <thead><tr><th>Tabela</th><th className="num">Linhas</th><th className="num">Disco</th><th className="num">% do total</th></tr></thead>
                    <tbody>
                      {d.tabelas.map((r) => (
                        <tr key={r.tabela}><td><code>{r.tabela}</code></td><td className="num">{r.linhas.toLocaleString("pt-BR")}</td><td className="num">{bytes(r.bytes)}</td><td className="num text-muted-2">{d.total_bytes ? (100 * r.bytes / d.total_bytes).toFixed(1) : "0"}%</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="small text-muted-2 mt-2">Estimativa: tamanho físico de cada tabela (dados + índices) rateado pela fração de linhas da empresa.</div>
              </>
            )}
          </>
        )}
      </Modal.Body>
    </Modal>
  );
}

export function Tenants() {
  const { actAsTenant } = useAuth();
  const [rows, setRows] = useState<Tenant[] | null>(null);
  const [editing, setEditing] = useState<TenantForm | null>(null);
  const [error, setError] = useState("");
  const [disco, setDisco] = useState<Tenant | null>(null);

  const load = useCallback(() => {
    api.get("/api/tenants/").then((d) => setRows(d.results ?? d)).catch(() => setRows([]));
  }, []);

  useEffect(() => load(), [load]);

  const save = async () => {
    if (!editing) return;
    setError("");
    try {
      if (editing.id) await api.patch(`/api/tenants/${editing.id}/`, editing);
      else await api.post("/api/tenants/", editing);
      setEditing(null);
      load();
    } catch (e: any) {
      setError(
        typeof e.data === "object"
          ? Object.entries(e.data).map(([k, v]) => `${k}: ${v}`).join(" · ")
          : e.message
      );
    }
  };

  return (
    <div>
      <div className="filter-bar">
        <span className="text-muted-2 small">{rows?.length ?? 0} empresa(s) no sistema</span>
        <Button size="sm" className="ms-auto" onClick={() => setEditing({})}>
          <i className="bi bi-plus-lg me-1" />Nova empresa
        </Button>
      </div>

      <Panel>
        {rows === null ? (
          <div className="d-flex flex-column gap-2 py-2">
            {[...Array(3)].map((_, i) => <Skeleton key={i} height={44} />)}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon="bi-buildings"
            title="Nenhuma empresa cadastrada"
            hint="Crie a primeira empresa e o seu administrador inicial."
            action={<Button size="sm" onClick={() => setEditing({})}>Nova empresa</Button>}
          />
        ) : (
          <div className="table-responsive">
            <table className="table table-hover align-middle">
              <thead>
                <tr><th>Empresa</th><th>Slug</th><th>CNPJ</th><th className="num">Usuários</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.id}>
                    <td role="button" onClick={() => setEditing(t)}>
                      <div className="d-flex align-items-center gap-2">
                        <span
                          style={{
                            width: 30, height: 30, borderRadius: 8, display: "grid", placeItems: "center",
                            background: "var(--brand-soft)", color: "var(--brand)", flex: "none",
                          }}
                        >
                          <i className="bi bi-building" />
                        </span>
                        <span className="fw-semibold">{t.name}</span>
                      </div>
                    </td>
                    <td className="text-muted-2"><code>{t.slug}</code></td>
                    <td className="text-secondary-2">{t.cnpj || "—"}</td>
                    <td className="num">{t.users_count ?? "—"}</td>
                    <td>
                      <span className={`status-pill ${t.is_active ? "st-verde" : "st-neutro"}`}>
                        <i className={`bi ${t.is_active ? "bi-check-circle-fill" : "bi-slash-circle"}`} />
                        {t.is_active ? "Ativa" : "Inativa"}
                      </span>
                    </td>
                    <td className="text-end">
                      <div className="d-flex gap-2 justify-content-end">
                        <Button size="sm" variant="outline-secondary" onClick={() => setDisco(t)} title="Disco ocupado pelos dados">
                          <i className="bi bi-hdd me-1" />Disco
                        </Button>
                        <Button size="sm" variant="outline-secondary" onClick={() => actAsTenant(t.id)}>
                          <i className="bi bi-box-arrow-in-right me-1" />Acessar
                        </Button>
                        <Button
                          size="sm"
                          variant="outline-secondary"
                          onClick={async () => {
                            await api.post(`/api/tenants/${t.id}/activate/`);
                            load();
                          }}
                        >
                          {t.is_active ? "Desativar" : "Ativar"}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal show={!!editing} onHide={() => setEditing(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title className="fs-6">{editing?.id ? "Editar empresa" : "Nova empresa"}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {error && <div className="alert alert-danger py-2 small">{error}</div>}
          <div className="row g-3">
            <div className="col-md-8">
              <Form.Label>Nome</Form.Label>
              <Form.Control
                value={editing?.name || ""}
                onChange={(e) =>
                  setEditing({
                    ...editing!,
                    name: e.target.value,
                    slug: editing?.id ? editing.slug : slugify(e.target.value),
                  })
                }
              />
            </div>
            <div className="col-md-4">
              <Form.Label>Slug</Form.Label>
              <Form.Control value={editing?.slug || ""} onChange={(e) => setEditing({ ...editing!, slug: e.target.value })} />
            </div>
            <div className="col-md-6">
              <Form.Label>CNPJ</Form.Label>
              <Form.Control value={editing?.cnpj || ""} onChange={(e) => setEditing({ ...editing!, cnpj: e.target.value })} />
            </div>
          </div>

          {!editing?.id && (
            <>
              <hr style={{ borderColor: "var(--border)" }} />
              <div className="fw-semibold small mb-2">
                <i className="bi bi-person-gear me-1" />Administrador inicial
              </div>
              <div className="row g-3">
                <div className="col-md-6">
                  <Form.Label>Nome</Form.Label>
                  <Form.Control value={editing?.admin_name || ""} onChange={(e) => setEditing({ ...editing!, admin_name: e.target.value })} />
                </div>
                <div className="col-md-6">
                  <Form.Label>E-mail</Form.Label>
                  <Form.Control type="email" value={editing?.admin_email || ""} onChange={(e) => setEditing({ ...editing!, admin_email: e.target.value })} />
                </div>
                <div className="col-md-6">
                  <Form.Label>Senha</Form.Label>
                  <Form.Control
                    type="password"
                    autoComplete="new-password"
                    value={editing?.admin_password || ""}
                    onChange={(e) => setEditing({ ...editing!, admin_password: e.target.value })}
                  />
                </div>
              </div>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save} disabled={!editing?.name || !editing?.slug}>Salvar</Button>
        </Modal.Footer>
      </Modal>
      {disco && <DiscoDaEmpresa tenant={disco} onHide={() => setDisco(null)} />}
    </div>
  );
}
