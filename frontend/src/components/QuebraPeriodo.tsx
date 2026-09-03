import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_V, statusKey, vizTokens } from "../charts/theme";
import { useTheme } from "../hooks/useTheme";
import { fmtNumber, fmtPct } from "../utils/format";
import { EChart } from "./EChart";
import { ChartLegend, EmptyState, Panel, Skeleton, StatusPill } from "./ui";

type Gran = "dia" | "semana" | "mes" | "semestre" | "ano";

interface Periodo {
  label: string;
  ini: string;
  fim: string;
  value: number | null;
  target: number | null;
  achievement_pct: number | null;
  status: string | null;
  parcial: boolean;
}

interface Quebra {
  granularidade: Gran;
  ate: string;
  n: number;
  fonte: "erp" | "manual";
  disponivel: boolean;
  periodos: Periodo[];
}

const GRANS: { key: Gran; label: string }[] = [
  { key: "dia", label: "Dia" },
  { key: "semana", label: "Semana" },
  { key: "mes", label: "Mês" },
  { key: "semestre", label: "Semestre" },
  { key: "ano", label: "Ano" },
];

const N_OPCOES: Record<Gran, number[]> = {
  dia: [7, 15, 31, 62],
  semana: [4, 8, 13, 26],
  mes: [3, 6, 12, 24],
  semestre: [2, 4, 6],
  ano: [2, 3, 5],
};

const hojeIso = () => new Date().toISOString().slice(0, 10);

/** Quebra de um indicador por dia / semana / mês / semestre / ano — valores e metas. */
export function QuebraPeriodo({ indicatorId, unit, decimals, erp }: {
  indicatorId: number | string;
  unit: string;
  decimals: number;
  erp: boolean;
}) {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [gran, setGran] = useState<Gran>(erp ? "dia" : "mes");
  const [n, setN] = useState<number>(erp ? 31 : 12);
  const [ate, setAte] = useState(hojeIso());
  const [data, setData] = useState<Quebra | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ gran, ate, n: String(n) });
    api
      .get<Quebra>(`/api/indicators/${indicatorId}/breakdown/?${params}`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [indicatorId, gran, ate, n]);

  const trocarGran = (g: Gran) => {
    setGran(g);
    setN(N_OPCOES[g][2] ?? N_OPCOES[g][N_OPCOES[g].length - 1]);
  };

  const option = useMemo(() => {
    const ps = data?.periodos ?? [];
    return {
      grid: { left: 4, right: 16, top: 16, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis" as const,
        axisPointer: { type: "shadow" as const },
        formatter: (params: any[]) => {
          const p = ps[params[0].dataIndex];
          if (!p) return "";
          return `<div style="font-weight:600;margin-bottom:2px">${p.label}${p.parcial ? " (parcial)" : ""}</div>
            <div>Realizado <strong>${fmtNumber(p.value, decimals)}</strong> ${unit}</div>
            <div>Meta <strong>${fmtNumber(p.target, decimals)}</strong> ${unit}</div>
            <div style="color:${t.inkMuted}">${p.achievement_pct ? fmtPct(p.achievement_pct) + " da meta" : "sem meta"}</div>`;
        },
      },
      xAxis: {
        type: "category" as const,
        data: ps.map((p) => p.label),
        axisLabel: { interval: Math.max(0, Math.floor(ps.length / 16) - 1), fontSize: 11 },
      },
      yAxis: { type: "value" as const },
      series: [
        {
          name: "Realizado",
          type: "bar" as const,
          barMaxWidth: BAR_MAX_WIDTH,
          data: ps.map((p) => ({
            value: p.value === null ? null : Number(p.value),
            itemStyle: {
              color: p.status ? t.status[statusKey(p.status)] : t.series[0],
              borderRadius: BAR_RADIUS_V,
              opacity: p.parcial ? 0.55 : 1,
            },
          })),
        },
        {
          name: "Meta",
          type: "line" as const,
          step: "middle" as const,
          symbol: "none",
          lineStyle: { width: 2, color: t.series[0], type: "dashed" as const },
          data: ps.map((p) => (p.target === null ? null : Number(p.target))),
        },
      ],
    };
  }, [data, t, unit, decimals]);

  return (
    <Panel
      title="Quebra por período"
      subtitle={erp ? "Recalculado do ERP para cada período; dia e semana são exatos." : "Lançamentos mensais; semestre e ano agregam pela regra do indicador."}
      actions={
        <div className="d-flex flex-wrap gap-2 align-items-center">
          <div className="btn-group btn-group-sm">
            {GRANS.map((g) => (
              <button key={g.key} type="button" className={`btn ${gran === g.key ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => trocarGran(g.key)}>
                {g.label}
              </button>
            ))}
          </div>
          <select className="form-select form-select-sm" style={{ width: 110 }} value={n} onChange={(e) => setN(Number(e.target.value))}>
            {N_OPCOES[gran].map((k) => <option key={k} value={k}>últimos {k}</option>)}
          </select>
          <input type="date" className="form-control form-control-sm" style={{ width: 150 }} value={ate} max={hojeIso()} onChange={(e) => e.target.value && setAte(e.target.value)} />
        </div>
      }
    >
      {loading && !data ? (
        <Skeleton height={260} />
      ) : !data ? (
        <EmptyState icon="bi-exclamation-triangle" title="Não foi possível carregar a quebra" />
      ) : !data.disponivel ? (
        <EmptyState
          icon="bi-calendar-x"
          title={`Visão por ${gran} só existe para indicadores calculados do ERP`}
          hint="Este indicador é lançado por mês. Vincule-o a uma métrica do ERP para ver dia e semana."
        />
      ) : (
        <>
          <ChartLegend items={[{ color: t.series[0], label: "Meta", shape: "line" }, { color: t.status.verde, label: "Realizado (cor = farol)" }]} />
          <EChart option={option} height={260} />
          <div className="table-responsive mt-3">
            <table className="table table-sm mb-0">
              <thead>
                <tr><th>Período</th><th className="num">Meta</th><th className="num">Realizado</th><th className="num">Atingimento</th><th>Farol</th></tr>
              </thead>
              <tbody>
                {[...data.periodos].reverse().map((p) => (
                  <tr key={p.ini} className={p.value === null ? "text-muted-2" : ""}>
                    <td>
                      <span className="fw-semibold">{p.label}</span>
                      {p.parcial && <span className="badge text-bg-light border ms-2">parcial</span>}
                      {gran !== "dia" && <div className="small text-muted-2">{p.ini.split("-").reverse().join("/")} → {p.fim.split("-").reverse().join("/")}</div>}
                    </td>
                    <td className="num text-muted-2">{p.target === null ? "—" : `${fmtNumber(p.target, decimals)} ${unit}`}</td>
                    <td className="num fw-semibold">{p.value === null ? "—" : `${fmtNumber(p.value, decimals)} ${unit}`}</td>
                    <td className="num">{fmtPct(p.achievement_pct)}</td>
                    <td>{p.status ? <StatusPill status={p.status} compact /> : <span className="text-muted-2">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}
