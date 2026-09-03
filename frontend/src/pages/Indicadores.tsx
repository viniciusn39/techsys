import { useCallback, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { Link } from "react-router-dom";
import { statusKey, vizTokens } from "../charts/theme";
import {
  EmptyState,
  Meter,
  Panel,
  Skeleton,
  Sparkline,
  StatusPill,
} from "../components/ui";
import { api } from "../api/client";
import { useTheme } from "../hooks/useTheme";
import type { Indicator, Objective, OrgUnit, UserRow } from "../types";
import { fmtNumber, fmtPct, fmtPeriod } from "../utils/format";

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

/** Métrica do ERP disponível para vincular a um indicador. */
interface ErpMetric {
  key: string;
  label: string;
  unit: string;
  polarity: string;
  aggregation: string;
  group: string;
  description: string;
  entities: string[];
  decimals: number;
}

const EMPTY: Partial<Indicator> = {
  code: "", name: "", unit: "", polarity: "maior_melhor", aggregation: "soma",
  frequency: "mensal", yellow_threshold_pct: "90", decimals: 2,
};

export function Indicadores() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);

  const [rows, setRows] = useState<Indicator[]>([]);
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [objectives, setObjectives] = useState<Objective[]>([]);
  const [filterUnit, setFilterUnit] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Partial<Indicator> | null>(null);
  const [launching, setLaunching] = useState(false);
  const [launchPeriod, setLaunchPeriod] = useState(currentPeriod());
  const [launchValues, setLaunchValues] = useState<Record<number, string>>({});
  const [loadingDefaults, setLoadingDefaults] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [metrics, setMetrics] = useState<ErpMetric[]>([]);
  const [preview, setPreview] = useState<{ value: string | null; loading: boolean } | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    const params = filterUnit ? `?org_unit=${filterUnit}` : "";
    api
      .get<Indicator[]>(`/api/indicators/${params}`)
      .then(setRows)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [filterUnit]);

  useEffect(() => {
    load();
    api.get("/api/org-units/").then(setUnits).catch(() => {});
    api.get("/api/users/").then((d) => setUsers(d.results ?? d)).catch(() => {});
    api.get("/api/objectives/").then(setObjectives).catch(() => {});
    api.get<ErpMetric[]>("/api/erp/metrics/").then(setMetrics).catch(() => {});
  }, [load]);

  /** Vincular métrica do ERP: adota unidade, polaridade e agregação dela. */
  const pickMetric = (key: string) => {
    const m = metrics.find((x) => x.key === key);
    setPreview(null);
    if (!m) {
      setEditing({ ...editing!, erp_metric: "" });
      return;
    }
    setEditing({
      ...editing!,
      erp_metric: m.key,
      unit: m.unit,
      polarity: m.polarity as any,
      aggregation: m.aggregation as any,
      decimals: m.decimals,
      description: editing?.description || m.description,
      name: editing?.name || m.label,
    });
  };

  const previewMetric = async () => {
    if (!editing?.erp_metric) return;
    setPreview({ value: null, loading: true });
    try {
      const params = new URLSearchParams({ metric: editing.erp_metric });
      const branch = ([] as string[]).concat((editing.erp_filters as any)?.branch ?? []).join(",");
      if (branch) params.set("branch", branch);
      const r = await api.get<{ value: string | null }>(`/api/erp/metrics/preview/?${params}`);
      setPreview({ value: r.value, loading: false });
    } catch {
      setPreview({ value: null, loading: false });
    }
  };

  const save = async () => {
    if (!editing) return;
    setError("");
    try {
      if (editing.id) await api.patch(`/api/indicators/${editing.id}/`, editing);
      else await api.post("/api/indicators/", editing);
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

  const loadDefaults = async () => {
    setLoadingDefaults(true);
    try {
      const r = await api.post<{ created: number }>("/api/indicators/load-defaults/");
      setNotice(
        r.created > 0
          ? `${r.created} indicador(es) do catálogo padrão adicionados. Defina as metas de cada um.`
          : "O catálogo padrão já está todo cadastrado."
      );
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingDefaults(false);
    }
  };

  const submitLaunch = async () => {
    const values = Object.entries(launchValues)
      .filter(([, v]) => v !== "")
      .map(([indicator, value]) => ({ indicator: Number(indicator), period: launchPeriod, value }));
    await api.post("/api/indicator-values/bulk/", { values });
    setLaunching(false);
    setLaunchValues({});
    load();
  };

  const visible = rows.filter((r) => {
    if (filterStatus && statusKey(r.last_value?.status) !== filterStatus) return false;
    if (search && !`${r.code} ${r.name}`.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div>
      <div className="filter-bar">
        <div className="position-relative">
          <i
            className="bi bi-search position-absolute text-muted-2"
            style={{ left: 10, top: 7, fontSize: "0.8rem" }}
          />
          <Form.Control
            size="sm"
            placeholder="Buscar indicador..."
            style={{ width: 230, paddingLeft: 30 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Form.Select size="sm" style={{ width: 180 }} value={filterUnit} onChange={(e) => setFilterUnit(e.target.value)}>
          <option value="">Todas as áreas</option>
          {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </Form.Select>
        <Form.Select size="sm" style={{ width: 175 }} value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="">Todos os faróis</option>
          <option value="verde">Meta atingida</option>
          <option value="amarelo">Atenção</option>
          <option value="vermelho">Crítico</option>
          <option value="sem_lancamento">Sem lançamento</option>
        </Form.Select>
        <div className="ms-auto d-flex gap-2">
          <Button size="sm" variant="outline-secondary" onClick={loadDefaults} disabled={loadingDefaults}>
            <i className="bi bi-collection me-1" />
            {loadingDefaults ? "Carregando..." : "Catálogo padrão"}
          </Button>
          <Button size="sm" variant="outline-secondary" onClick={() => setLaunching(true)}>
            <i className="bi bi-pencil-square me-1" />Lançar resultados
          </Button>
          <Button size="sm" onClick={() => setEditing({ ...EMPTY })}>
            <i className="bi bi-plus-lg me-1" />Novo indicador
          </Button>
        </div>
      </div>

      {error && <div className="alert alert-danger py-2 small">{error}</div>}
      {notice && (
        <div className="alert alert-success py-2 small d-flex align-items-center gap-2">
          <i className="bi bi-check-circle-fill" />
          {notice}
          <button className="btn-close ms-auto" style={{ fontSize: "0.6rem" }} onClick={() => setNotice("")} />
        </div>
      )}

      <Panel>
        {loading ? (
          <div className="d-flex flex-column gap-2 py-2">
            {[...Array(6)].map((_, i) => <Skeleton key={i} height={38} />)}
          </div>
        ) : visible.length === 0 ? (
          <EmptyState
            icon="bi-graph-up-arrow"
            title="Nenhum indicador encontrado"
            hint={
              rows.length
                ? "Ajuste os filtros acima."
                : "Comece pelo catálogo padrão de KPIs ou cadastre os seus do zero."
            }
            action={
              rows.length ? undefined : (
                <div className="d-flex gap-2 justify-content-center">
                  <Button size="sm" variant="outline-secondary" onClick={loadDefaults} disabled={loadingDefaults}>
                    <i className="bi bi-collection me-1" />Carregar catálogo padrão
                  </Button>
                  <Button size="sm" onClick={() => setEditing({ ...EMPTY })}>Novo indicador</Button>
                </div>
              )
            }
          />
        ) : (
          <div className="table-responsive">
            <table className="table table-hover align-middle">
              <thead>
                <tr>
                  <th>Indicador</th>
                  <th>Área</th>
                  <th>Dono</th>
                  <th>Período</th>
                  <th className="num">Realizado</th>
                  <th className="num">Atingimento</th>
                  <th style={{ width: 120 }}>Tendência</th>
                  <th>Farol</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => {
                  const st = statusKey(r.last_value?.status);
                  return (
                    <tr key={r.id}>
                      <td>
                        <Link to={`/indicadores/${r.id}`} className="text-decoration-none">
                          <span className="fw-semibold">{r.code}</span>
                          <span className="text-secondary-2"> · {r.name}</span>
                        </Link>
                        {r.erp_metric ? (
                          <i
                            className="bi bi-robot ms-2"
                            style={{ color: "var(--brand)", fontSize: "0.78rem" }}
                            title={`Calculado do ERP: ${r.erp_metric_label}`}
                          />
                        ) : (
                          <i
                            className="bi bi-pencil ms-2 text-muted-2"
                            style={{ fontSize: "0.72rem" }}
                            title="Lançamento manual"
                          />
                        )}
                        <div className="mt-1" style={{ maxWidth: 220 }}>
                          <Meter pct={Number(r.last_value?.achievement_pct ?? 0)} status={r.last_value?.status} />
                        </div>
                      </td>
                      <td className="text-secondary-2">{r.org_unit_name || "—"}</td>
                      <td className="text-secondary-2">{r.owner_name || "—"}</td>
                      <td className="text-muted-2">{fmtPeriod(r.last_value?.period)}</td>
                      <td className="num">
                        {r.last_value ? `${fmtNumber(r.last_value.value, r.decimals)} ${r.unit}` : "—"}
                      </td>
                      <td className="num fw-semibold">{fmtPct(r.last_value?.achievement_pct)}</td>
                      <td>
                        <Sparkline data={r.spark ?? []} color={t.status[st]} />
                        <div className="text-muted-2" style={{ fontSize: "0.72rem" }}>
                          {r.polarity === "menor_melhor" ? "↓ menor melhor" : "↑ maior melhor"}
                        </div>
                      </td>
                      <td><StatusPill status={r.last_value?.status ?? null} /></td>
                      <td className="text-end">
                        <Button
                          size="sm"
                          variant="outline-secondary"
                          title="Editar indicador"
                          onClick={() => {
                            setPreview(null);
                            setEditing(r);
                          }}
                        >
                          <i className="bi bi-pencil" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* --- Modal do indicador --- */}
      <Modal show={!!editing} onHide={() => setEditing(null)} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title className="fs-6">{editing?.id ? "Editar indicador" : "Novo indicador"}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <div className="row g-3">
            <div className="col-md-3">
              <Form.Label>Código</Form.Label>
              <Form.Control value={editing?.code || ""} onChange={(e) => setEditing({ ...editing!, code: e.target.value.toUpperCase() })} />
            </div>
            <div className="col-md-6">
              <Form.Label>Nome</Form.Label>
              <Form.Control value={editing?.name || ""} onChange={(e) => setEditing({ ...editing!, name: e.target.value })} />
            </div>
            <div className="col-md-3">
              <Form.Label>Unidade</Form.Label>
              <Form.Control placeholder="%, R$, un..." value={editing?.unit || ""} onChange={(e) => setEditing({ ...editing!, unit: e.target.value })} />
            </div>
            <div className="col-md-4">
              <Form.Label>Polaridade</Form.Label>
              <Form.Select value={editing?.polarity} onChange={(e) => setEditing({ ...editing!, polarity: e.target.value as any })}>
                <option value="maior_melhor">Maior é melhor</option>
                <option value="menor_melhor">Menor é melhor</option>
              </Form.Select>
            </div>
            <div className="col-md-4">
              <Form.Label>Agregação (acumulado)</Form.Label>
              <Form.Select value={editing?.aggregation} onChange={(e) => setEditing({ ...editing!, aggregation: e.target.value as any })}>
                <option value="soma">Soma</option>
                <option value="media">Média</option>
                <option value="ultimo">Último valor</option>
              </Form.Select>
            </div>
            <div className="col-md-4">
              <Form.Label>Limite do farol amarelo (%)</Form.Label>
              <Form.Control type="number" value={editing?.yellow_threshold_pct || "90"} onChange={(e) => setEditing({ ...editing!, yellow_threshold_pct: e.target.value })} />
            </div>
            <div className="col-md-4">
              <Form.Label>Área</Form.Label>
              <Form.Select value={editing?.org_unit ?? ""} onChange={(e) => setEditing({ ...editing!, org_unit: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </Form.Select>
            </div>
            <div className="col-md-4">
              <Form.Label>Dono</Form.Label>
              <Form.Select value={editing?.owner ?? ""} onChange={(e) => setEditing({ ...editing!, owner: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
              </Form.Select>
            </div>
            <div className="col-md-4">
              <Form.Label>Objetivo estratégico</Form.Label>
              <Form.Select value={editing?.objective ?? ""} onChange={(e) => setEditing({ ...editing!, objective: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {objectives.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </Form.Select>
            </div>
            <div className="col-12">
              <Form.Label>Descrição</Form.Label>
              <Form.Control as="textarea" rows={2} value={editing?.description || ""} onChange={(e) => setEditing({ ...editing!, description: e.target.value })} />
            </div>

            {/* --- Origem do valor: manual ou calculado do ERP --- */}
            <div className="col-12">
              <hr className="my-2" style={{ borderColor: "var(--border)" }} />
              <div className="stat-label mb-2"><i className="bi bi-robot" />Origem do valor</div>
              <div className="row g-2">
                <div className="col-md-7">
                  <Form.Label>Métrica do ERP</Form.Label>
                  <Form.Select value={editing?.erp_metric || ""} onChange={(e) => pickMetric(e.target.value)}>
                    <option value="">Lançamento manual (sem ERP)</option>
                    {Array.from(new Set(metrics.map((m) => m.group))).map((group) => (
                      <optgroup key={group} label={group}>
                        {metrics.filter((m) => m.group === group).map((m) => (
                          <option key={m.key} value={m.key}>{m.label} ({m.unit})</option>
                        ))}
                      </optgroup>
                    ))}
                  </Form.Select>
                </div>
                <div className="col-md-5">
                  <Form.Label>Filial (opcional)</Form.Label>
                  <Form.Control
                    placeholder="código no ERP, ex.: 10 — ou várias: 11,12"
                    value={([] as string[]).concat((editing?.erp_filters as any)?.branch ?? []).join(",")}
                    onChange={(e) => {
                      const branch = e.target.value.replace(/[^0-9A-Za-z,\s]/g, "");
                      setEditing({ ...editing!, erp_filters: branch.trim() ? { branch } : {} });
                      setPreview(null);
                    }}
                    disabled={!editing?.erp_metric}
                  />
                </div>
              </div>
              {editing?.erp_metric && (
                <div className="mt-2 p-2 rounded" style={{ background: "var(--surface-sunken)", border: "1px solid var(--border)" }}>
                  <div className="small text-secondary-2">
                    {metrics.find((m) => m.key === editing.erp_metric)?.description}
                  </div>
                  <div className="d-flex align-items-center gap-2 mt-2 flex-wrap">
                    <Button size="sm" variant="outline-secondary" onClick={previewMetric} disabled={preview?.loading}>
                      <i className="bi bi-calculator me-1" />
                      {preview?.loading ? "Calculando..." : "Testar com os dados de hoje"}
                    </Button>
                    {preview && !preview.loading && (
                      <span className={`status-pill ${preview.value !== null ? "st-verde" : "st-amarelo"}`}>
                        <i className={`bi ${preview.value !== null ? "bi-check-circle-fill" : "bi-exclamation-circle-fill"}`} />
                        {preview.value !== null
                          ? `${fmtNumber(preview.value, editing.decimals ?? 2)} ${editing.unit || ""}`
                          : "sem dados do ERP ainda"}
                      </span>
                    )}
                    <span className="text-muted-2" style={{ fontSize: "0.74rem" }}>
                      precisa de: {metrics.find((m) => m.key === editing.erp_metric)?.entities.join(", ")}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
          <Button onClick={save} disabled={!editing?.code || !editing?.name}>Salvar</Button>
        </Modal.Footer>
      </Modal>

      {/* --- Modal de lançamento em lote --- */}
      <Modal show={launching} onHide={() => setLaunching(false)} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title className="fs-6">Lançar resultados do mês</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group className="mb-3" style={{ maxWidth: 200 }}>
            <Form.Label>Período</Form.Label>
            <Form.Control
              type="month"
              value={launchPeriod.slice(0, 7)}
              onChange={(e) => e.target.value && setLaunchPeriod(`${e.target.value}-01`)}
            />
          </Form.Group>
          <table className="table table-sm align-middle">
            <thead><tr><th>Indicador</th><th style={{ width: 190 }}>Valor</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <span className="fw-semibold">{r.code}</span>
                    <span className="text-secondary-2"> — {r.name}</span>
                    {r.unit && <span className="text-muted-2 small"> ({r.unit})</span>}
                  </td>
                  <td>
                    <Form.Control
                      size="sm" type="number" step="any" className="num"
                      value={launchValues[r.id] ?? ""}
                      onChange={(e) => setLaunchValues({ ...launchValues, [r.id]: e.target.value })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setLaunching(false)}>Cancelar</Button>
          <Button onClick={submitLaunch}>Salvar lançamentos</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
