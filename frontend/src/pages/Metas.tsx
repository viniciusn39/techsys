import { useCallback, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton, StatusPill } from "../components/ui";
import type { Goal, Indicator, Objective, OrgUnit, UserRow } from "../types";

const LEVEL_LABELS: Record<string, string> = {
  empresa: "Empresa", area: "Área", time: "Time", pessoa: "Pessoa",
};
const LEVEL_ICONS: Record<string, string> = {
  empresa: "bi-building", area: "bi-diagram-2", time: "bi-people", pessoa: "bi-person",
};
const NEXT_LEVEL: Record<string, Goal["level"]> = {
  empresa: "area", area: "time", time: "pessoa", pessoa: "pessoa",
};

function GoalNode({ goal, depth, onEdit, onAddChild }: {
  goal: Goal;
  depth: number;
  onEdit: (g: Goal) => void;
  onAddChild: (parent: Goal) => void;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = (goal.children?.length ?? 0) > 0;

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
          className="badge rounded-pill text-uppercase"
          style={{
            background: "var(--surface-sunken)",
            color: "var(--ink-muted)",
            fontSize: "0.62rem",
            letterSpacing: "0.05em",
          }}
        >
          <i className={`bi ${LEVEL_ICONS[goal.level]} me-1`} />
          {LEVEL_LABELS[goal.level]}
        </span>

        <span
          className="fw-semibold flex-grow-1 text-truncate"
          role="button"
          style={{ fontSize: "0.88rem" }}
          onClick={() => onEdit(goal)}
        >
          {goal.name}
        </span>

        {goal.indicator_status && <StatusPill status={goal.indicator_status} />}
        {goal.org_unit_name && (
          <span className="badge text-bg-light border fw-normal">{goal.org_unit_name}</span>
        )}
        {goal.owner_name && (
          <span className="text-muted-2 small d-none d-lg-inline">
            <i className="bi bi-person me-1" />{goal.owner_name}
          </span>
        )}
        <Button size="sm" variant="outline-secondary" onClick={() => onAddChild(goal)} title="Desdobrar meta">
          <i className="bi bi-plus" />
        </Button>
      </div>

      {open && hasChildren && (
        <div className="tree-children">
          {goal.children!.map((c) => (
            <GoalNode key={c.id} goal={c} depth={depth + 1} onEdit={onEdit} onAddChild={onAddChild} />
          ))}
        </div>
      )}
    </div>
  );
}

export function Metas() {
  const [tree, setTree] = useState<Goal[] | null>(null);
  const [editing, setEditing] = useState<Partial<Goal> | null>(null);
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [objectives, setObjectives] = useState<Objective[]>([]);
  const [indicators, setIndicators] = useState<Indicator[]>([]);

  const load = useCallback(() => {
    api.get<Goal[]>("/api/goals/tree/").then(setTree).catch(() => setTree([]));
  }, []);

  useEffect(() => {
    load();
    api.get("/api/org-units/").then(setUnits).catch(() => {});
    api.get("/api/users/").then((d) => setUsers(d.results ?? d)).catch(() => {});
    api.get("/api/objectives/").then(setObjectives).catch(() => {});
    api.get("/api/indicators/").then(setIndicators).catch(() => {});
  }, [load]);

  const save = async () => {
    if (!editing) return;
    const body = {
      name: editing.name,
      level: editing.level,
      parent: editing.parent ?? null,
      objective: editing.objective ?? null,
      org_unit: editing.org_unit ?? null,
      owner: editing.owner ?? null,
      indicator: editing.indicator ?? null,
      description: editing.description || "",
    };
    if (editing.id) await api.patch(`/api/goals/${editing.id}/`, body);
    else await api.post("/api/goals/", body);
    setEditing(null);
    load();
  };

  const remove = async () => {
    if (editing?.id && confirm("Excluir esta meta e todos os seus desdobramentos?")) {
      await api.del(`/api/goals/${editing.id}/`);
      setEditing(null);
      load();
    }
  };

  const count = (nodes: Goal[]): number =>
    nodes.reduce((acc, n) => acc + 1 + count(n.children ?? []), 0);

  return (
    <div>
      <div className="filter-bar">
        <span className="text-muted-2 small">
          {tree ? `${count(tree)} metas em cascata` : "Carregando..."}
        </span>
        <Button size="sm" className="ms-auto" onClick={() => setEditing({ level: "empresa" })}>
          <i className="bi bi-plus-lg me-1" />Nova meta da empresa
        </Button>
      </div>

      <Panel>
        {tree === null ? (
          <div className="d-flex flex-column gap-2 py-2">
            {[...Array(4)].map((_, i) => <Skeleton key={i} height={40} />)}
          </div>
        ) : tree.length === 0 ? (
          <EmptyState
            icon="bi-bullseye"
            title="Nenhuma meta cadastrada"
            hint="Comece pela meta da empresa e desdobre para áreas, times e pessoas."
            action={<Button size="sm" onClick={() => setEditing({ level: "empresa" })}>Criar meta da empresa</Button>}
          />
        ) : (
          tree.map((g) => (
            <GoalNode
              key={g.id}
              goal={g}
              depth={0}
              onEdit={setEditing}
              onAddChild={(parent) =>
                setEditing({
                  parent: parent.id,
                  level: NEXT_LEVEL[parent.level],
                  objective: parent.objective,
                  org_unit: parent.org_unit,
                })
              }
            />
          ))
        )}
      </Panel>

      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title className="fs-6">{editing?.id ? "Editar meta" : "Nova meta"}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <div className="row g-3">
            <div className="col-md-8">
              <Form.Label>Nome da meta</Form.Label>
              <Form.Control
                placeholder="Ex.: Crescer receita 20% em 2026"
                value={editing?.name || ""}
                onChange={(e) => setEditing({ ...editing!, name: e.target.value })}
              />
            </div>
            <div className="col-md-4">
              <Form.Label>Nível</Form.Label>
              <Form.Select value={editing?.level} onChange={(e) => setEditing({ ...editing!, level: e.target.value as any })}>
                {Object.entries(LEVEL_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Form.Select>
            </div>
            <div className="col-md-6">
              <Form.Label>Objetivo estratégico</Form.Label>
              <Form.Select value={editing?.objective ?? ""} onChange={(e) => setEditing({ ...editing!, objective: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {objectives.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </Form.Select>
            </div>
            <div className="col-md-6">
              <Form.Label>Indicador que mede a meta (farol)</Form.Label>
              <Form.Select value={editing?.indicator ?? ""} onChange={(e) => setEditing({ ...editing!, indicator: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {indicators.map((i) => <option key={i.id} value={i.id}>{i.code} — {i.name}</option>)}
              </Form.Select>
            </div>
            <div className="col-md-6">
              <Form.Label>Unidade organizacional</Form.Label>
              <Form.Select value={editing?.org_unit ?? ""} onChange={(e) => setEditing({ ...editing!, org_unit: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </Form.Select>
            </div>
            <div className="col-md-6">
              <Form.Label>Responsável</Form.Label>
              <Form.Select value={editing?.owner ?? ""} onChange={(e) => setEditing({ ...editing!, owner: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
              </Form.Select>
            </div>
            <div className="col-12">
              <Form.Label>Descrição</Form.Label>
              <Form.Control as="textarea" rows={2} value={editing?.description || ""} onChange={(e) => setEditing({ ...editing!, description: e.target.value })} />
            </div>
          </div>
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
