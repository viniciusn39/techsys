import { useCallback, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { EmptyState, Panel, Skeleton } from "../components/ui";
import type { Tenant } from "../types";

interface TenantForm extends Partial<Tenant> {
  admin_email?: string;
  admin_password?: string;
  admin_name?: string;
}

const slugify = (s: string) =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

export function Tenants() {
  const { actAsTenant } = useAuth();
  const [rows, setRows] = useState<Tenant[] | null>(null);
  const [editing, setEditing] = useState<TenantForm | null>(null);
  const [error, setError] = useState("");

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
    </div>
  );
}
