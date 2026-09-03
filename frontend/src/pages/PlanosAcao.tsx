import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { EmptyState, Meter, Panel, Skeleton, StatCard } from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import type { ActionItem, ActionPlan, Indicator, OrgUnit, UserRow } from "../types";
import { fmtDate } from "../utils/format";

const KANBAN_COLS: { key: ActionItem["status"]; label: string; icon: string }[] = [
  { key: "a_fazer", label: "A fazer", icon: "bi-circle" },
  { key: "fazendo", label: "Fazendo", icon: "bi-arrow-repeat" },
  { key: "feito", label: "Feito", icon: "bi-check-circle-fill" },
];

const PDCA = ["plan", "do", "check", "act"] as const;

const STATUS_META: Record<string, { label: string; cls: string; icon: string }> = {
  rascunho: { label: "Rascunho", cls: "st-neutro", icon: "bi-file-earmark" },
  em_andamento: { label: "Em andamento", cls: "st-amarelo", icon: "bi-arrow-repeat" },
  concluido: { label: "Concluído", cls: "st-verde", icon: "bi-check-circle-fill" },
  cancelado: { label: "Cancelado", cls: "st-neutro", icon: "bi-slash-circle" },
};

const PRIORITY_META: Record<string, { label: string; cls: string }> = {
  baixa: { label: "Baixa", cls: "st-neutro" },
  media: { label: "Média", cls: "st-amarelo" },
  alta: { label: "Alta", cls: "st-vermelho" },
};

export function PlanosAcao() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);

  const [plans, setPlans] = useState<ActionPlan[] | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [view, setView] = useState<"lista" | "kanban">("kanban");
  const [editing, setEditing] = useState<Partial<ActionPlan> | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [newItem, setNewItem] = useState("");
  const [dragging, setDragging] = useState<ActionItem | null>(null);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState("");

  const load = useCallback(async () => {
    const data = await api.get<ActionPlan[]>("/api/action-plans/");
    setPlans(data);
  }, []);

  useEffect(() => {
    load();
    api.get("/api/users/").then((d) => setUsers(d.results ?? d)).catch(() => {});
    api.get("/api/org-units/").then(setUnits).catch(() => {});
    api.get("/api/indicators/").then(setIndicators).catch(() => {});
  }, [load]);

  const detail = plans?.find((p) => p.id === detailId) ?? null;
  const list = (plans ?? []).filter((p) => !filterStatus || p.status === filterStatus);

  const save = async () => {
    if (!editing) return;
    const { items, ...body } = editing as any;
    if (editing.id) await api.patch(`/api/action-plans/${editing.id}/`, body);
    else await api.post("/api/action-plans/", body);
    setEditing(null);
    load();
  };

  const allItems = list.flatMap((p) =>
    p.items.map((i) => ({ ...i, planTitle: p.title, planPriority: p.priority }))
  );

  const moveItem = async (item: ActionItem, status: ActionItem["status"]) => {
    if (item.status === status) return;
    await api.patch(`/api/action-items/${item.id}/move/`, { status });
    load();
  };

  const addItem = async () => {
    if (!detail || !newItem.trim()) return;
    await api.post("/api/action-items/", { plan: detail.id, title: newItem.trim() });
    setNewItem("");
    load();
  };

  const advancePdca = async (plan: ActionPlan) => {
    await api.post(`/api/action-plans/${plan.id}/advance-pdca/`);
    load();
  };

  const setPlanStatus = async (plan: ActionPlan, status: string) => {
    await api.patch(`/api/action-plans/${plan.id}/`, { status });
    load();
  };

  // Progresso por plano: barra única de magnitude (uma matiz, não status).
  const progressOption = useMemo(() => {
    const open = list.filter((p) => p.status !== "cancelado" && p.items_total > 0).slice(0, 8);
    return {
      grid: { left: 8, right: 48, top: 6, bottom: 4, containLabel: true },
      xAxis: { type: "value" as const, max: 100, axisLabel: { formatter: "{value}%" } },
      yAxis: {
        type: "category" as const,
        data: open.map((p) => (p.title.length > 26 ? `${p.title.slice(0, 25)}…` : p.title)),
        axisLabel: { fontSize: 11, color: t.inkSecondary },
      },
      tooltip: {
        trigger: "item" as const,
        formatter: (p: any) => {
          const plan = open[p.dataIndex];
          return `<strong>${plan.items_done}/${plan.items_total} atividades</strong><br/>
            <span style="color:${t.inkSecondary}">${plan.title}</span>`;
        },
      },
      series: [
        {
          type: "bar" as const,
          barMaxWidth: BAR_MAX_WIDTH,
          itemStyle: { color: t.series[0], borderRadius: BAR_RADIUS_H },
          label: {
            show: true,
            position: "right" as const,
            formatter: (p: any) => `${Math.round(p.value)}%`,
            color: t.inkSecondary,
            fontSize: 11,
          },
          data: open.map((p) => Math.round((p.items_done / p.items_total) * 100)),
        },
      ],
    };
  }, [list, t]);

  const doneCount = (plans ?? []).filter((p) => p.status === "concluido").length;
  const lateCount = (plans ?? []).filter(
    (p) => p.when_end && new Date(p.when_end) < new Date() && !["concluido", "cancelado"].includes(p.status)
  ).length;

  return (
    <div>
      <div className="row g-3 mb-3">
        <div className="col-6 col-xl-3">
          <StatCard icon="bi-kanban" label="Planos ativos" value={(plans ?? []).filter((p) => p.status === "em_andamento").length} foot={`${plans?.length ?? 0} no total`} />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard icon="bi-check2-circle" label="Concluídos" value={doneCount} />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard
            icon="bi-clock-history"
            label="Atrasados"
            value={lateCount}
            foot={lateCount > 0 ? "prazo vencido sem conclusão" : "nenhum plano vencido"}
          />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard
            icon="bi-exclamation-triangle"
            label="Originados de desvio"
            value={(plans ?? []).filter((p) => p.origin === "desvio").length}
          />
        </div>
      </div>

      <div className="filter-bar">
        <div className="btn-group btn-group-sm">
          {(["kanban", "lista"] as const).map((v) => (
            <button
              key={v}
              className={`btn btn-outline-secondary ${view === v ? "active" : ""}`}
              onClick={() => setView(v)}
            >
              <i className={`bi ${v === "kanban" ? "bi-kanban" : "bi-list-ul"} me-1`} />
              {v === "kanban" ? "Kanban" : "Lista"}
            </button>
          ))}
        </div>
        <Form.Select size="sm" style={{ width: 175 }} value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="">Todos os status</option>
          {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </Form.Select>
        <Button
          size="sm"
          className="ms-auto"
          onClick={() => setEditing({ status: "rascunho", pdca_stage: "plan", priority: "media", origin: "manual" })}
        >
          <i className="bi bi-plus-lg me-1" />Novo plano (5W2H)
        </Button>
      </div>

      {plans === null ? (
        <Panel><Skeleton height={320} /></Panel>
      ) : view === "kanban" ? (
        <>
          <div className="row g-3">
            {KANBAN_COLS.map((col) => {
              const items = allItems.filter((i) => i.status === col.key);
              return (
                <div className="col-md-4" key={col.key}>
                  <div
                    className={`kanban-col ${dragOver === col.key ? "is-over" : ""}`}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragOver(col.key);
                    }}
                    onDragLeave={() => setDragOver(null)}
                    onDrop={() => {
                      if (dragging) moveItem(dragging, col.key);
                      setDragOver(null);
                    }}
                  >
                    <div className="kanban-head">
                      <span><i className={`bi ${col.icon} me-1`} />{col.label}</span>
                      <span className="badge rounded-pill text-bg-light border">{items.length}</span>
                    </div>
                    {items.map((i) => (
                      <div
                        key={i.id}
                        className="kanban-card"
                        draggable
                        onDragStart={() => setDragging(i)}
                        onDragEnd={() => {
                          setDragging(null);
                          setDragOver(null);
                        }}
                      >
                        <div className="title">{i.title}</div>
                        <div className="meta mt-1">{(i as any).planTitle}</div>
                        <div className="d-flex justify-content-between align-items-center mt-2">
                          <span className="meta">
                            {i.responsible_name && <><i className="bi bi-person me-1" />{i.responsible_name}</>}
                          </span>
                          {i.due_date && (
                            <span className="meta"><i className="bi bi-calendar3 me-1" />{fmtDate(i.due_date)}</span>
                          )}
                        </div>
                      </div>
                    ))}
                    {items.length === 0 && (
                      <div className="text-muted-2 small text-center py-4">Arraste atividades para cá</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-3">
            <Panel title="Progresso dos planos" subtitle="Percentual de atividades concluídas">
              {list.filter((p) => p.items_total > 0).length === 0 ? (
                <EmptyState icon="bi-bar-chart" title="Nenhum plano com atividades" />
              ) : (
                <EChart option={progressOption} height={Math.max(160, Math.min(8, list.filter((p) => p.items_total > 0).length) * 34 + 30)} />
              )}
            </Panel>
          </div>
        </>
      ) : (
        <Panel>
          {list.length === 0 ? (
            <EmptyState
              icon="bi-kanban"
              title="Nenhum plano de ação"
              hint="Crie um plano 5W2H ou trate um desvio para gerar um automaticamente."
            />
          ) : (
            <div className="table-responsive">
              <table className="table table-hover align-middle">
                <thead>
                  <tr>
                    <th>Plano</th><th>Responsável</th><th>Prazo</th>
                    <th>PDCA</th><th style={{ width: 150 }}>Progresso</th>
                    <th>Prioridade</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((p) => {
                    const late = p.when_end && new Date(p.when_end) < new Date() && !["concluido", "cancelado"].includes(p.status);
                    return (
                      <tr key={p.id} role="button" onClick={() => setDetailId(p.id)}>
                        <td>
                          <div className="d-flex align-items-center gap-2">
                            {p.origin === "desvio" && (
                              <i className="bi bi-exclamation-triangle-fill" style={{ color: "var(--st-vermelho)" }} title="Originado de um desvio" />
                            )}
                            <span className="fw-semibold">{p.title}</span>
                          </div>
                          {p.indicator_code && <span className="text-muted-2 small">KPI {p.indicator_code}</span>}
                        </td>
                        <td className="text-secondary-2">{p.who_name || "—"}</td>
                        <td className={late ? "fw-semibold" : "text-secondary-2"} style={late ? { color: "var(--st-vermelho)" } : undefined}>
                          {late && <i className="bi bi-clock-history me-1" />}
                          {fmtDate(p.when_end)}
                        </td>
                        <td>
                          <span className="pdca-step current">{p.pdca_stage}</span>
                        </td>
                        <td>
                          <Meter pct={p.items_total ? (p.items_done / p.items_total) * 100 : 0} />
                          <span className="text-muted-2" style={{ fontSize: "0.72rem" }}>
                            {p.items_done}/{p.items_total} atividades
                          </span>
                        </td>
                        <td>
                          <span className={`status-pill ${PRIORITY_META[p.priority].cls}`}>
                            <i className="bi bi-flag-fill" />{PRIORITY_META[p.priority].label}
                          </span>
                        </td>
                        <td>
                          <span className={`status-pill ${STATUS_META[p.status].cls}`}>
                            <i className={`bi ${STATUS_META[p.status].icon}`} />{STATUS_META[p.status].label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}

      {/* --- Modal 5W2H --- */}
      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title className="fs-6">{editing?.id ? "Editar plano de ação" : "Novo plano de ação (5W2H)"}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <div className="row g-3">
            <div className="col-12">
              <Form.Label>Título</Form.Label>
              <Form.Control value={editing?.title || ""} onChange={(e) => setEditing({ ...editing!, title: e.target.value })} />
            </div>
            <div className="col-md-6">
              <Form.Label>O quê <span className="text-muted-2">(What)</span></Form.Label>
              <Form.Control as="textarea" rows={2} value={editing?.what || ""} onChange={(e) => setEditing({ ...editing!, what: e.target.value })} />
            </div>
            <div className="col-md-6">
              <Form.Label>Por quê <span className="text-muted-2">(Why)</span></Form.Label>
              <Form.Control as="textarea" rows={2} value={editing?.why || ""} onChange={(e) => setEditing({ ...editing!, why: e.target.value })} />
            </div>
            <div className="col-md-4">
              <Form.Label>Quem <span className="text-muted-2">(Who)</span></Form.Label>
              <Form.Select value={editing?.who ?? ""} onChange={(e) => setEditing({ ...editing!, who: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
              </Form.Select>
            </div>
            <div className="col-md-4">
              <Form.Label>Onde <span className="text-muted-2">(Where)</span></Form.Label>
              <Form.Control value={editing?.where || ""} onChange={(e) => setEditing({ ...editing!, where: e.target.value })} />
            </div>
            <div className="col-md-4">
              <Form.Label>Quanto custa <span className="text-muted-2">(How much)</span></Form.Label>
              <Form.Control type="number" step="any" value={editing?.how_much ?? ""} onChange={(e) => setEditing({ ...editing!, how_much: e.target.value })} />
            </div>
            <div className="col-md-4">
              <Form.Label>Início <span className="text-muted-2">(When)</span></Form.Label>
              <Form.Control type="date" value={editing?.when_start || ""} onChange={(e) => setEditing({ ...editing!, when_start: e.target.value })} />
            </div>
            <div className="col-md-4">
              <Form.Label>Fim <span className="text-muted-2">(When)</span></Form.Label>
              <Form.Control type="date" value={editing?.when_end || ""} onChange={(e) => setEditing({ ...editing!, when_end: e.target.value })} />
            </div>
            <div className="col-md-4">
              <Form.Label>Prioridade</Form.Label>
              <Form.Select value={editing?.priority} onChange={(e) => setEditing({ ...editing!, priority: e.target.value as any })}>
                <option value="baixa">Baixa</option>
                <option value="media">Média</option>
                <option value="alta">Alta</option>
              </Form.Select>
            </div>
            <div className="col-12">
              <Form.Label>Como <span className="text-muted-2">(How)</span></Form.Label>
              <Form.Control as="textarea" rows={2} value={editing?.how || ""} onChange={(e) => setEditing({ ...editing!, how: e.target.value })} />
            </div>
            <div className="col-md-6">
              <Form.Label>Indicador vinculado</Form.Label>
              <Form.Select value={editing?.indicator ?? ""} onChange={(e) => setEditing({ ...editing!, indicator: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {indicators.map((i) => <option key={i.id} value={i.id}>{i.code} — {i.name}</option>)}
              </Form.Select>
            </div>
            <div className="col-md-6">
              <Form.Label>Área</Form.Label>
              <Form.Select value={editing?.org_unit ?? ""} onChange={(e) => setEditing({ ...editing!, org_unit: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </Form.Select>
            </div>
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save} disabled={!editing?.title}>Salvar</Button>
        </Modal.Footer>
      </Modal>

      {/* --- Detalhe do plano --- */}
      <Modal show={!!detail} onHide={() => setDetailId(null)} size="lg" centered>
        {detail && (
          <>
            <Modal.Header closeButton>
              <Modal.Title className="fs-6">{detail.title}</Modal.Title>
            </Modal.Header>
            <Modal.Body>
              <div className="d-flex gap-2 mb-3 flex-wrap align-items-center">
                <span className={`status-pill ${STATUS_META[detail.status].cls}`}>
                  <i className={`bi ${STATUS_META[detail.status].icon}`} />{STATUS_META[detail.status].label}
                </span>
                <span className={`status-pill ${PRIORITY_META[detail.priority].cls}`}>
                  <i className="bi bi-flag-fill" />{PRIORITY_META[detail.priority].label}
                </span>
                {detail.indicator_code && (
                  <span className="badge text-bg-light border fw-normal">KPI {detail.indicator_code}</span>
                )}
                <div className="ms-auto d-flex gap-2">
                  {detail.status !== "concluido" && (
                    <Button size="sm" variant="outline-secondary" onClick={() => setPlanStatus(detail, "concluido")}>
                      <i className="bi bi-check2-circle me-1" />Concluir plano
                    </Button>
                  )}
                  <Button size="sm" variant="outline-secondary" onClick={() => { setDetailId(null); setEditing(detail); }}>
                    <i className="bi bi-pencil me-1" />Editar
                  </Button>
                </div>
              </div>

              <div className="d-flex align-items-center gap-1 mb-3 flex-wrap">
                {PDCA.map((s, i) => {
                  const idx = PDCA.indexOf(detail.pdca_stage);
                  return (
                    <span key={s} className="d-inline-flex align-items-center gap-1">
                      <span className={`pdca-step ${detail.pdca_stage === s ? "current" : idx > i ? "done" : ""}`}>
                        {idx > i && <i className="bi bi-check" />}{s}
                      </span>
                      {i < 3 && <i className="bi bi-chevron-right text-muted-2 small" />}
                    </span>
                  );
                })}
                {detail.pdca_stage !== "act" && (
                  <Button size="sm" variant="link" className="ms-1 p-0" onClick={() => advancePdca(detail)}>
                    avançar etapa
                  </Button>
                )}
              </div>

              <div className="row g-2 mb-3">
                {([["O quê", detail.what], ["Por quê", detail.why], ["Onde", detail.where], ["Como", detail.how]] as const)
                  .filter(([, v]) => v)
                  .map(([label, value]) => (
                    <div className="col-md-6" key={label}>
                      <div className="panel h-100 p-2" style={{ background: "var(--surface-sunken)", boxShadow: "none" }}>
                        <div className="stat-label">{label}</div>
                        <div className="small text-secondary-2">{value}</div>
                      </div>
                    </div>
                  ))}
              </div>

              <div className="text-muted-2 small mb-3 d-flex gap-3 flex-wrap">
                <span><i className="bi bi-person me-1" />{detail.who_name || "—"}</span>
                <span><i className="bi bi-calendar3 me-1" />{fmtDate(detail.when_start)} → {fmtDate(detail.when_end)}</span>
                {detail.how_much && <span><i className="bi bi-cash me-1" />R$ {detail.how_much}</span>}
              </div>

              <div className="d-flex justify-content-between align-items-center mb-2">
                <strong className="small">Checklist</strong>
                <span className="text-muted-2 small">{detail.items_done}/{detail.items_total} concluídas</span>
              </div>
              <Meter pct={detail.items_total ? (detail.items_done / detail.items_total) * 100 : 0} />

              <div className="mt-2">
                {detail.items.map((i) => (
                  <div key={i.id} className="d-flex align-items-center gap-2 py-2 border-bottom" style={{ borderColor: "var(--grid)" }}>
                    <Form.Check
                      checked={i.status === "feito"}
                      onChange={(e) => moveItem(i, e.target.checked ? "feito" : "a_fazer")}
                    />
                    <span className={`small flex-grow-1 ${i.status === "feito" ? "text-decoration-line-through text-muted-2" : ""}`}>
                      {i.title}
                    </span>
                    <Form.Select
                      size="sm" style={{ width: 120 }}
                      value={i.status}
                      onChange={(e) => moveItem(i, e.target.value as any)}
                    >
                      {KANBAN_COLS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                    </Form.Select>
                  </div>
                ))}
                {detail.items.length === 0 && (
                  <div className="text-muted-2 small py-2">Nenhuma atividade ainda.</div>
                )}
              </div>

              <div className="d-flex gap-2 mt-3">
                <Form.Control
                  size="sm"
                  placeholder="Nova atividade..."
                  value={newItem}
                  onChange={(e) => setNewItem(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addItem()}
                />
                <Button size="sm" onClick={addItem}><i className="bi bi-plus-lg" /></Button>
              </div>
            </Modal.Body>
          </>
        )}
      </Modal>
    </div>
  );
}
