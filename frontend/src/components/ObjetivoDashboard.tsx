import { useEffect, useMemo, useState } from "react";
import { Button, Modal } from "react-bootstrap";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, STATUS_LABEL, statusKey, vizTokens } from "../charts/theme";
import { useTheme } from "../hooks/useTheme";
import type { ActionPlan, Deviation, Indicator, Objective } from "../types";
import { fmtDate, fmtNumber, fmtPct, fmtPeriod } from "../utils/format";
import { EChart } from "./EChart";
import { IndicadorResumoModal } from "./IndicadorResumoModal";
import { EmptyState, Skeleton, Sparkline, StatusPill } from "./ui";

interface SwotItem { id: number; quadrant: string; quadrant_label: string; text: string; impact: number; objective: number | null }
interface Estrategia { id: number; kind: string; kind_label: string; text: string; objective: number | null }

/** Painel de um objetivo do mapa: os indicadores dele, farol, atingimento, desvios, planos e SWOT ligados. */
export function ObjetivoDashboard({ objective, perspectiveName, perspectiveColor, onEdit, onClose }: {
  objective: Objective; perspectiveName?: string; perspectiveColor?: string; onEdit: () => void; onClose: () => void;
}) {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [inds, setInds] = useState<Indicator[] | null>(null);
  const [desvios, setDesvios] = useState<Deviation[]>([]);
  const [planos, setPlanos] = useState<ActionPlan[]>([]);
  const [swot, setSwot] = useState<SwotItem[]>([]);
  const [estrategias, setEstrategias] = useState<Estrategia[]>([]);
  const [indAberto, setIndAberto] = useState<Indicator | null>(null);

  useEffect(() => {
    setInds(null);
    api.get<any>(`/api/indicators/?objective=${objective.id}`).then((d) => setInds(d.results ?? d)).catch(() => setInds([]));
    api.get<any>("/api/deviations/?status=aberto").then((d) => setDesvios(d.results ?? d)).catch(() => {});
    api.get<any>("/api/action-plans/").then((d) => setPlanos((d.results ?? d).filter((p: ActionPlan) => (p as any).objective === objective.id))).catch(() => {});
    api.get<SwotItem[]>("/api/swot/").then((d) => setSwot(d.filter((s) => s.objective === objective.id))).catch(() => {});
    api.get<Estrategia[]>("/api/swot-estrategias/").then((d) => setEstrategias(d.filter((s) => s.objective === objective.id))).catch(() => {});
  }, [objective.id]);

  const ids = new Set((inds ?? []).map((i) => i.id));
  const desviosDoObjetivo = desvios.filter((d) => ids.has(d.indicator));
  const comMeta = (inds ?? []).filter((i) => i.last_value && i.last_value.status && i.last_value.status !== "sem_meta");
  const verdes = comMeta.filter((i) => i.last_value!.status === "verde").length;

  const option = useMemo(() => {
    const rows = [...(inds ?? [])].filter((i) => i.last_value?.achievement_pct !== null && i.last_value?.achievement_pct !== undefined)
      .sort((a, b) => Number(b.last_value!.achievement_pct) - Number(a.last_value!.achievement_pct)).reverse();
    return {
      grid: { left: 4, right: 56, top: 22, bottom: 4, containLabel: true },
      xAxis: { type: "value" as const, axisLabel: { formatter: "{value}%" }, max: (v: { max: number }) => Math.max(120, Math.min(150, Math.ceil(v.max / 10) * 10)) },
      yAxis: { type: "category" as const, data: rows.map((r) => r.code), axisLabel: { fontWeight: 500, color: t.inkSecondary } },
      tooltip: { trigger: "item" as const, formatter: (p: any) => { const r = rows[p.dataIndex]; return `<strong>${fmtPct(r.last_value!.achievement_pct)}</strong> da meta<br/><span style="color:${t.inkSecondary}">${r.code} — ${r.name}</span><br/><span style="color:${t.inkMuted}">${fmtNumber(r.last_value!.value, r.decimals)} ${r.unit} · ${STATUS_LABEL[statusKey(r.last_value!.status)]}</span>`; } },
      series: [{
        type: "bar" as const, barMaxWidth: BAR_MAX_WIDTH,
        data: rows.map((r) => ({ value: Math.min(Number(r.last_value!.achievement_pct), 150), real: Number(r.last_value!.achievement_pct), itemStyle: { color: t.status[statusKey(r.last_value!.status)], borderRadius: BAR_RADIUS_H } })),
        label: { show: true, position: "right" as const, fontSize: 11, color: t.inkSecondary, formatter: (p: any) => `${fmtNumber(p.data?.real ?? p.value, 0)}%` },
        markLine: { silent: true, symbol: "none", label: { formatter: "meta", position: "end" as const, color: t.inkMuted, fontSize: 10 }, lineStyle: { color: t.axis, width: 1, type: "solid" as const }, data: [{ xAxis: 100 }] },
      }],
    };
  }, [inds, t]);

  return (
    <Modal show onHide={onClose} size="xl" centered>
      <Modal.Header closeButton>
        <div className="d-flex align-items-start gap-3 flex-grow-1">
          <div className="rounded-3 flex-shrink-0" style={{ width: 6, alignSelf: "stretch", background: perspectiveColor || "var(--brand)" }} />
          <div className="flex-grow-1">
            {perspectiveName && <div className="small text-muted-2 text-uppercase fw-semibold" style={{ letterSpacing: 0.4 }}>{perspectiveName}</div>}
            <Modal.Title className="fs-5 fw-bold">{objective.name}</Modal.Title>
            {objective.description && <div className="small text-muted-2 mt-1">{objective.description}</div>}
            <div className="small text-muted-2 mt-1 d-flex flex-wrap gap-3">
              {objective.owner_name && <span><i className="bi bi-person me-1" />{objective.owner_name}</span>}
              <span><i className="bi bi-graph-up-arrow me-1" />{inds?.length ?? "…"} indicador(es)</span>
              {(objective.contributes_to?.length ?? 0) > 0 && <span><i className="bi bi-arrow-up-right me-1" />contribui para {objective.contributes_to.length} objetivo(s)</span>}
            </div>
          </div>
          <Button size="sm" variant="outline-secondary" className="flex-shrink-0 me-2" onClick={onEdit}><i className="bi bi-pencil me-1" />Editar objetivo</Button>
        </div>
      </Modal.Header>
      <Modal.Body>
        {inds === null ? <Skeleton height={260} /> : (
          <div className="d-grid gap-3">
            <div className="row g-2">
              {[
                ["Meta atingida", comMeta.length ? `${verdes} de ${comMeta.length}` : "—", "bi-check2-circle"],
                ["Em atenção", comMeta.filter((i) => i.last_value!.status === "amarelo").length, "bi-exclamation-circle"],
                ["Críticos", comMeta.filter((i) => i.last_value!.status === "vermelho").length, "bi-x-circle"],
                ["Desvios abertos", desviosDoObjetivo.length, "bi-exclamation-triangle"],
                ["Planos de ação", planos.length, "bi-kanban"],
              ].map(([l, v, ic]) => (
                <div className="col-6 col-md" key={l as string}>
                  <div className="p-2 rounded h-100" style={{ background: "var(--surface-sunken)" }}>
                    <div className="small text-muted-2"><i className={`bi ${ic} me-1`} />{l}</div>
                    <div className="fw-bold fs-5">{v as any}</div>
                  </div>
                </div>
              ))}
            </div>

            {inds.length === 0 ? (
              <EmptyState icon="bi-graph-up-arrow" title="Nenhum indicador ligado a este objetivo" hint="Em Indicadores, edite o indicador e escolha este objetivo; ou plugue um KPI do catálogo do ERP já apontando para ele." />
            ) : (
              <div className="row g-3">
                <div className="col-lg-5">
                  <div className="fw-semibold small mb-1">Atingimento da meta no mês</div>
                  {comMeta.length === 0 ? <div className="small text-muted-2">Sem metas cadastradas ainda.</div> : <EChart option={option} height={Math.max(140, comMeta.length * 30 + 40)} />}
                </div>
                <div className="col-lg-7">
                  <div className="fw-semibold small mb-1">Indicadores</div>
                  <div className="table-responsive">
                    <table className="table table-sm align-middle mb-0">
                      <thead><tr><th>Indicador</th><th className="num">Último resultado</th><th className="num">Atingimento</th><th>Farol</th><th>Tendência</th></tr></thead>
                      <tbody>
                        {inds.map((i) => (
                          <tr key={i.id} role="button" onClick={() => setIndAberto(i)} title="Ver os últimos meses">
                            <td>
                              <span className="fw-semibold" style={{ color: "var(--brand)" }}>{i.code}</span> <span className="small">· {i.name}</span>
                              {i.erp_metric && <i className="bi bi-robot ms-1 text-muted-2 small" title="calculado do ERP" />}
                            </td>
                            <td className="num small">{i.last_value ? <>{fmtNumber(i.last_value.value, i.decimals)} {i.unit}<div className="text-muted-2" style={{ fontSize: "0.7rem" }}>{fmtPeriod(i.last_value.period)}</div></> : "—"}</td>
                            <td className="num small">{i.last_value ? fmtPct(i.last_value.achievement_pct) : "—"}</td>
                            <td><StatusPill status={i.last_value?.status ?? null} compact /></td>
                            <td>{i.spark && i.spark.length > 1 ? <Sparkline data={i.spark} color={t.status[statusKey(i.last_value?.status)]} /> : <span className="text-muted-2">—</span>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            <div className="row g-3">
              <div className="col-lg-6">
                <div className="fw-semibold small mb-1"><i className="bi bi-exclamation-triangle me-1" />Desvios abertos</div>
                {desviosDoObjetivo.length === 0 ? <div className="small text-muted-2">Nenhum desvio aberto nos indicadores deste objetivo.</div> : desviosDoObjetivo.map((d) => (
                  <div key={d.id} className="small py-1 border-bottom" style={{ borderColor: "var(--grid)" }}>
                    <Link to="/desvios" className="fw-semibold text-decoration-none">{(d as any).indicator_code ?? d.indicator}</Link> · {fmtPeriod((d as any).period ?? (d as any).indicator_value_period)} <span className="text-muted-2">· {(d as any).status_label ?? d.status}</span>
                  </div>
                ))}
              </div>
              <div className="col-lg-6">
                <div className="fw-semibold small mb-1"><i className="bi bi-kanban me-1" />Planos de ação</div>
                {planos.length === 0 ? <div className="small text-muted-2">Nenhum plano ligado a este objetivo.</div> : planos.map((p) => (
                  <div key={p.id} className="small py-1 border-bottom d-flex gap-2" style={{ borderColor: "var(--grid)" }}>
                    <Link to="/planos-acao" className="fw-semibold text-decoration-none flex-grow-1">{p.title}</Link>
                    <span className="text-muted-2">{p.items_done}/{p.items_total} · {p.status.replace("_", " ")}{p.when_end ? ` · até ${fmtDate(p.when_end)}` : ""}</span>
                  </div>
                ))}
              </div>
            </div>

            {(swot.length > 0 || estrategias.length > 0) && (
              <div>
                <div className="fw-semibold small mb-1"><i className="bi bi-grid-3x3-gap me-1" />Diagnóstico ligado (SWOT)</div>
                <div className="d-flex flex-wrap gap-1">
                  {swot.map((s) => <span key={`s${s.id}`} className="badge text-bg-light border fw-normal" title={s.quadrant_label}>{s.quadrant_label}: {s.text}</span>)}
                  {estrategias.map((e) => <span key={`e${e.id}`} className="badge fw-normal" style={{ background: "var(--brand-soft)", color: "var(--brand)" }} title={e.kind_label}>{e.kind}: {e.text}</span>)}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal.Body>
      {indAberto && <IndicadorResumoModal indicator={indAberto} onClose={() => setIndAberto(null)} />}
    </Modal>
  );
}
