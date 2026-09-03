import { useCallback, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton } from "../components/ui";
import type { OrgUnit, UserRow } from "../types";

const ROLE_META: Record<string, { label: string; icon: string; hint: string }> = {
  admin: { label: "Administrador", icon: "bi-shield-check", hint: "Gerencia usuários, organograma e mapa" },
  gestor: { label: "Gestor", icon: "bi-clipboard-data", hint: "Cria objetivos, metas, KPIs e planos" },
  colaborador: { label: "Colaborador", icon: "bi-person", hint: "Consulta e lança os seus resultados" },
  root: { label: "Root", icon: "bi-key", hint: "Acesso global a todas as empresas" },
};

export function Usuarios() {
  const [rows, setRows] = useState<UserRow[] | null>(null);
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [editing, setEditing] = useState<Partial<UserRow & { password?: string }> | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get("/api/users/").then((d) => setRows(d.results ?? d)).catch(() => setRows([]));
  }, []);

  useEffect(() => {
    load();
    api.get("/api/org-units/").then(setUnits).catch(() => {});
  }, [load]);

  const save = async () => {
    if (!editing) return;
    setError("");
    try {
      if (editing.id) await api.patch(`/api/users/${editing.id}/`, editing);
      else await api.post("/api/users/", editing);
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
        <span className="text-muted-2 small">{rows?.length ?? 0} usuário(s) nesta empresa</span>
        <Button size="sm" className="ms-auto" onClick={() => setEditing({ role: "colaborador", is_active: true })}>
          <i className="bi bi-plus-lg me-1" />Novo usuário
        </Button>
      </div>

      <Panel>
        {rows === null ? (
          <div className="d-flex flex-column gap-2 py-2">
            {[...Array(4)].map((_, i) => <Skeleton key={i} height={40} />)}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon="bi-people" title="Nenhum usuário cadastrado" />
        ) : (
          <div className="table-responsive">
            <table className="table table-hover align-middle">
              <thead>
                <tr><th>Usuário</th><th>Papel</th><th>Cargo</th><th>Unidade</th><th>Status</th></tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.id} role="button" onClick={() => setEditing({ ...u, password: "" })}>
                    <td>
                      <div className="d-flex align-items-center gap-2">
                        <span
                          style={{
                            width: 30, height: 30, borderRadius: "50%", display: "grid", placeItems: "center",
                            background: "var(--brand-soft)", color: "var(--brand)", fontWeight: 600, flex: "none",
                          }}
                        >
                          {u.first_name?.[0]?.toUpperCase() ?? "?"}
                        </span>
                        <div>
                          <div className="fw-semibold">{u.first_name} {u.last_name}</div>
                          <div className="text-muted-2" style={{ fontSize: "0.74rem" }}>{u.email}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="badge text-bg-light border fw-normal">
                        <i className={`bi ${ROLE_META[u.role]?.icon} me-1`} />{ROLE_META[u.role]?.label ?? u.role}
                      </span>
                    </td>
                    <td className="text-secondary-2">{u.cargo || "—"}</td>
                    <td className="text-secondary-2">{u.org_unit_name || "—"}</td>
                    <td>
                      <span className={`status-pill ${u.is_active ? "st-verde" : "st-neutro"}`}>
                        <i className={`bi ${u.is_active ? "bi-check-circle-fill" : "bi-slash-circle"}`} />
                        {u.is_active ? "Ativo" : "Inativo"}
                      </span>
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
          <Modal.Title className="fs-6">{editing?.id ? "Editar usuário" : "Novo usuário"}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {error && <div className="alert alert-danger py-2 small">{error}</div>}
          <div className="row g-3">
            <div className="col-md-6">
              <Form.Label>Nome</Form.Label>
              <Form.Control value={editing?.first_name || ""} onChange={(e) => setEditing({ ...editing!, first_name: e.target.value })} />
            </div>
            <div className="col-md-6">
              <Form.Label>Sobrenome</Form.Label>
              <Form.Control value={editing?.last_name || ""} onChange={(e) => setEditing({ ...editing!, last_name: e.target.value })} />
            </div>
            <div className="col-12">
              <Form.Label>E-mail</Form.Label>
              <Form.Control type="email" value={editing?.email || ""} onChange={(e) => setEditing({ ...editing!, email: e.target.value })} />
            </div>
            <div className="col-12">
              <Form.Label>Papel</Form.Label>
              <div className="d-flex flex-column gap-2">
                {(["admin", "gestor", "colaborador"] as const).map((r) => (
                  <label
                    key={r}
                    className="d-flex align-items-center gap-2 p-2 rounded"
                    style={{
                      cursor: "pointer",
                      background: editing?.role === r ? "var(--brand-soft)" : "var(--surface-sunken)",
                      border: `1px solid ${editing?.role === r ? "var(--brand)" : "transparent"}`,
                    }}
                  >
                    <input
                      type="radio"
                      className="form-check-input mt-0"
                      checked={editing?.role === r}
                      onChange={() => setEditing({ ...editing!, role: r })}
                    />
                    <i className={`bi ${ROLE_META[r].icon}`} />
                    <span className="flex-grow-1">
                      <span className="fw-semibold small d-block">{ROLE_META[r].label}</span>
                      <span className="text-muted-2" style={{ fontSize: "0.74rem" }}>{ROLE_META[r].hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <div className="col-md-6">
              <Form.Label>Cargo</Form.Label>
              <Form.Control value={editing?.cargo || ""} onChange={(e) => setEditing({ ...editing!, cargo: e.target.value })} />
            </div>
            <div className="col-md-6">
              <Form.Label>Unidade</Form.Label>
              <Form.Select value={editing?.org_unit ?? ""} onChange={(e) => setEditing({ ...editing!, org_unit: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </Form.Select>
            </div>
            <div className="col-md-6">
              <Form.Label>{editing?.id ? "Nova senha (opcional)" : "Senha"}</Form.Label>
              <Form.Control
                type="password"
                autoComplete="new-password"
                value={editing?.password || ""}
                onChange={(e) => setEditing({ ...editing!, password: e.target.value })}
              />
            </div>
            {editing?.id && (
              <div className="col-md-6 d-flex align-items-end">
                <Form.Check
                  label="Usuário ativo"
                  checked={editing?.is_active ?? true}
                  onChange={(e) => setEditing({ ...editing!, is_active: e.target.checked })}
                />
              </div>
            )}
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save} disabled={!editing?.email || !editing?.first_name}>Salvar</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
