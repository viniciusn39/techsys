import { useCallback, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton } from "../components/ui";
import type { OrgUnit, UserRow } from "../types";

const KIND_META: Record<string, { label: string; icon: string }> = {
  empresa: { label: "Empresa", icon: "bi-building" },
  area: { label: "Área", icon: "bi-diagram-2" },
  time: { label: "Time", icon: "bi-people" },
};

function UnitNode({ unit, onEdit, onAdd }: {
  unit: OrgUnit;
  onEdit: (u: OrgUnit) => void;
  onAdd: (parent: OrgUnit) => void;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = (unit.children?.length ?? 0) > 0;

  return (
    <div className="mb-1">
      <div className="tree-row">
        {hasChildren ? (
          <button
            className="btn btn-sm p-0 border-0 text-muted-2"
            style={{ width: 18 }}
            onClick={() => setOpen(!open)}
            aria-label={open ? "Recolher" : "Expandir"}
          >
            <i className={`bi ${open ? "bi-chevron-down" : "bi-chevron-right"}`} />
          </button>
        ) : (
          <span style={{ width: 18 }} />
        )}
        <span
          style={{
            width: 28, height: 28, borderRadius: 8, display: "grid", placeItems: "center",
            background: "var(--brand-soft)", color: "var(--brand)", flex: "none",
          }}
        >
          <i className={`bi ${KIND_META[unit.kind].icon}`} />
        </span>
        <span className="fw-semibold flex-grow-1" role="button" style={{ fontSize: "0.88rem" }} onClick={() => onEdit(unit)}>
          {unit.name}
        </span>
        <span className="badge text-bg-light border fw-normal">{KIND_META[unit.kind].label}</span>
        {unit.manager_name && (
          <span className="text-muted-2 small"><i className="bi bi-person me-1" />{unit.manager_name}</span>
        )}
        <Button size="sm" variant="outline-secondary" onClick={() => onAdd(unit)} title="Adicionar sub-unidade">
          <i className="bi bi-plus" />
        </Button>
      </div>
      {open && hasChildren && (
        <div className="tree-children">
          {unit.children!.map((c) => <UnitNode key={c.id} unit={c} onEdit={onEdit} onAdd={onAdd} />)}
        </div>
      )}
    </div>
  );
}

export function Organograma() {
  const [tree, setTree] = useState<OrgUnit[] | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [editing, setEditing] = useState<Partial<OrgUnit> | null>(null);

  const load = useCallback(() => {
    api.get<OrgUnit[]>("/api/org-units/tree/").then(setTree).catch(() => setTree([]));
  }, []);

  useEffect(() => {
    load();
    api.get("/api/users/").then((d) => setUsers(d.results ?? d)).catch(() => {});
  }, [load]);

  const save = async () => {
    if (!editing) return;
    if (editing.id) await api.patch(`/api/org-units/${editing.id}/`, editing);
    else await api.post("/api/org-units/", editing);
    setEditing(null);
    load();
  };

  const remove = async () => {
    if (editing?.id && confirm("Excluir esta unidade e todas as sub-unidades?")) {
      await api.del(`/api/org-units/${editing.id}/`);
      setEditing(null);
      load();
    }
  };

  return (
    <div>
      <div className="filter-bar">
        <span className="text-muted-2 small">Empresa → Áreas → Times</span>
        <Button size="sm" className="ms-auto" onClick={() => setEditing({ kind: "empresa", parent: null })}>
          <i className="bi bi-plus-lg me-1" />Nova unidade raiz
        </Button>
      </div>

      <Panel>
        {tree === null ? (
          <div className="d-flex flex-column gap-2 py-2">
            {[...Array(4)].map((_, i) => <Skeleton key={i} height={44} />)}
          </div>
        ) : tree.length === 0 ? (
          <EmptyState
            icon="bi-diagram-2"
            title="Nenhuma unidade cadastrada"
            hint="Comece pela empresa e vá criando áreas e times."
          />
        ) : (
          tree.map((u) => (
            <UnitNode
              key={u.id}
              unit={u}
              onEdit={setEditing}
              onAdd={(parent) => setEditing({ parent: parent.id, kind: parent.kind === "empresa" ? "area" : "time" })}
            />
          ))
        )}
      </Panel>

      <Modal show={!!editing} onHide={() => setEditing(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title className="fs-6">{editing?.id ? "Editar unidade" : "Nova unidade"}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group className="mb-3">
            <Form.Label>Nome</Form.Label>
            <Form.Control value={editing?.name || ""} onChange={(e) => setEditing({ ...editing!, name: e.target.value })} />
          </Form.Group>
          <Form.Group className="mb-3">
            <Form.Label>Tipo</Form.Label>
            <Form.Select value={editing?.kind} onChange={(e) => setEditing({ ...editing!, kind: e.target.value as any })}>
              {Object.entries(KIND_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Form.Select>
          </Form.Group>
          <Form.Group>
            <Form.Label>Gestor</Form.Label>
            <Form.Select value={editing?.manager ?? ""} onChange={(e) => setEditing({ ...editing!, manager: e.target.value ? Number(e.target.value) : null })}>
              <option value="">—</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
            </Form.Select>
          </Form.Group>
        </Modal.Body>
        <Modal.Footer className="justify-content-between">
          <div>{editing?.id && <Button variant="outline-danger" size="sm" onClick={remove}>Excluir</Button>}</div>
          <div className="d-flex gap-2">
            <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
            <Button onClick={save} disabled={!editing?.name}>Salvar</Button>
          </div>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
