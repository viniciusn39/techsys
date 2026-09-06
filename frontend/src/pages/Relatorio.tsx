import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Panel, Skeleton, StatusPill } from "../components/ui";
import { fmtNumber, fmtPct } from "../utils/format";

interface Mapa { id: number; name: string; year_start: number; year_end: number; purpose: string; mission: string; vision: string; values_text: string; perspectives: { id: number; name: string; color: string; objectives: { id: number; name: string; description: string; indicators?: any[] }[] }[] }
interface Swot { quadrant: string; text: string; impact: number; objective_name: string }
interface CanvasItem { block: string; block_label: string; text: string }
interface Ind { id: number; code: string; name: string; unit: string; decimals: number; objective: number | null; last_value?: { period: string; value: string; achievement_pct: string | null; status: string } | null; erp_metric: string }
interface Goal { id: number; name: string; level: string; children?: Goal[]; indicator_code?: string; org_unit_name?: string }

const QUAD: Record<string, string> = { S: "Forças", W: "Fraquezas", O: "Oportunidades", T: "Ameaças" };

/** Relatório do planejamento: identidade, SWOT, canvas, mapa com objetivos e indicadores, metas desdobradas. Feito para imprimir. */
export function Relatorio() {
  const [mapa, setMapa] = useState<Mapa | null | undefined>(undefined);
  const [swot, setSwot] = useState<Swot[]>([]);
  const [canvas, setCanvas] = useState<CanvasItem[]>([]);
  const [inds, setInds] = useState<Ind[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [tenant, setTenant] = useState("");

  useEffect(() => {
    api.get<Mapa | null>("/api/strategic-maps/active/").then(setMapa).catch(() => setMapa(null));
    api.get<Swot[]>("/api/swot/").then(setSwot).catch(() => {});
    api.get<CanvasItem[]>("/api/canvas/").then(setCanvas).catch(() => {});
    api.get<any>("/api/indicators/").then((d) => setInds(d.results ?? d)).catch(() => {});
    api.get<Goal[]>("/api/goals/tree/").then(setGoals).catch(() => {});
    api.get<any>("/api/auth/me/").then((m) => setTenant(m?.tenant?.name ?? m?.acting_tenant?.name ?? "")).catch(() => {});
  }, []);

  if (mapa === undefined) return <Panel><Skeleton height={400} /></Panel>;
  if (mapa === null) return <Panel>Nenhum mapa estratégico ativo.</Panel>;

  const porObjetivo: Record<number, Ind[]> = {};
  inds.forEach((i) => { if (i.objective) (porObjetivo[i.objective] = porObjetivo[i.objective] ?? []).push(i); });
  const valores = (mapa.values_text || "").split(/\n|;/).map((v) => v.trim()).filter(Boolean);
  const hoje = new Date().toLocaleDateString("pt-BR");

  const Goals = ({ lista, nivel = 0 }: { lista: Goal[]; nivel?: number }) => (
    <ul className={nivel === 0 ? "ps-3 mb-0" : "ps-4 mb-0"}>
      {lista.map((g) => (
        <li key={g.id}>
          <span className="fw-semibold">{g.name}</span>
          <span className="text-muted-2 small"> · {g.level}{g.org_unit_name ? ` · ${g.org_unit_name}` : ""}{g.indicator_code ? ` · ${g.indicator_code}` : ""}</span>
          {g.children && g.children.length > 0 && <Goals lista={g.children} nivel={nivel + 1} />}
        </li>
      ))}
    </ul>
  );

  return (
    <div className="d-grid gap-3 relatorio">
      <style>{`@media print {
        aside.sidebar, .filter-bar, .no-print, .app-topbar, header { display: none !important; }
        .app-shell, main, .app-main { margin: 0 !important; padding: 0 !important; display: block !important; }
        .panel, .card { break-inside: avoid; box-shadow: none !important; border: 1px solid #ddd !important; }
        .quebra { break-before: page; }
        body { background: #fff !important; }
      }`}</style>

      <Panel
        title={`Relatório do planejamento estratégico · ${mapa.name}`}
        subtitle={`${tenant ? tenant + " · " : ""}${mapa.year_start}–${mapa.year_end} · gerado em ${hoje}`}
        actions={<button className="btn btn-sm btn-primary no-print" onClick={() => window.print()}><i className="bi bi-printer me-1" />Imprimir / PDF</button>}
      >
        <div className="row g-3">
          {[["Propósito", mapa.purpose], ["Missão", mapa.mission], ["Visão", mapa.vision]].map(([t, v]) => (
            <div className="col-md-4" key={t as string}><div className="fw-semibold small text-muted-2">{t}</div><div style={{ whiteSpace: "pre-wrap" }}>{(v as string) || "—"}</div></div>
          ))}
          <div className="col-12"><div className="fw-semibold small text-muted-2">Valores</div>{valores.length ? <ul className="mb-0 ps-3">{valores.map((v, i) => <li key={i}>{v}</li>)}</ul> : "—"}</div>
        </div>
      </Panel>

      {swot.length > 0 && (
        <Panel title="Análise SWOT">
          <div className="row g-3">
            {["S", "W", "O", "T"].map((q) => (
              <div className="col-md-6" key={q}>
                <div className="fw-semibold mb-1">{QUAD[q]}</div>
                <ul className="mb-0 ps-3">{swot.filter((s) => s.quadrant === q).map((s, i) => <li key={i}>{s.text} <span className="text-muted-2 small">(impacto {s.impact}{s.objective_name ? ` · ${s.objective_name}` : ""})</span></li>)}</ul>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {canvas.length > 0 && (
        <Panel title="Business Model Canvas">
          <div className="row g-3">
            {Array.from(new Set(canvas.map((c) => c.block))).map((b) => (
              <div className="col-md-4" key={b}>
                <div className="fw-semibold mb-1">{canvas.find((c) => c.block === b)?.block_label}</div>
                <ul className="mb-0 ps-3">{canvas.filter((c) => c.block === b).map((c, i) => <li key={i}>{c.text}</li>)}</ul>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="Mapa estratégico: objetivos e indicadores" subtitle="Último resultado de cada indicador e atingimento da meta">
        {mapa.perspectives.map((p) => (
          <div key={p.id} className="mb-3" style={{ borderLeft: `4px solid ${p.color}`, paddingLeft: 12 }}>
            <div className="fw-bold text-uppercase small" style={{ color: p.color }}>{p.name}</div>
            {p.objectives.map((o) => (
              <div key={o.id} className="mb-2">
                <div className="fw-semibold">{o.name}</div>
                {o.description && <div className="small text-muted-2">{o.description}</div>}
                {(porObjetivo[o.id] ?? []).length > 0 && (
                  <table className="table table-sm mb-1" style={{ fontSize: "0.85rem" }}>
                    <thead><tr><th>Indicador</th><th className="num">Último resultado</th><th className="num">Atingimento</th><th>Farol</th></tr></thead>
                    <tbody>
                      {(porObjetivo[o.id] ?? []).map((i) => (
                        <tr key={i.id}>
                          <td><span className="fw-semibold">{i.code}</span> · {i.name}{i.erp_metric && <i className="bi bi-robot ms-1 text-muted-2" title="calculado do ERP" />}</td>
                          <td className="num">{i.last_value ? `${fmtNumber(i.last_value.value, i.decimals)} ${i.unit}` : "—"}</td>
                          <td className="num">{i.last_value ? fmtPct(i.last_value.achievement_pct) : "—"}</td>
                          <td>{i.last_value ? <StatusPill status={i.last_value.status} compact /> : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </div>
        ))}
      </Panel>

      {goals.length > 0 && (
        <Panel title="Desdobramento de metas" subtitle="Empresa → área → time → pessoa">
          <Goals lista={goals} />
        </Panel>
      )}
    </div>
  );
}
