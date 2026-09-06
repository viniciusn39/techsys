import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, statusKey, vizTokens } from "../charts/theme";
import { useTheme } from "../hooks/useTheme";
import { fmtNumber, fmtPct } from "../utils/format";
import { EChart } from "./EChart";
import { ChartLegend, EmptyState, Panel, Skeleton, StatusPill } from "./ui";

interface Filial {
  code: string;
  name: string;
  value: number;
  target: number | null;
  achievement_pct: number | null;
  status: string | null;
  share_pct: number | null;
}

interface Quebra {
  disponivel: boolean;
  ini: string;
  fim: string;
  parcial: boolean;
  total: number | null;
  soma: boolean;
  filiais: Filial[];
}

type Faixa = "mes" | "mes_anterior" | "30d" | "ano";

const iso = (d: Date) => d.toISOString().slice(0, 10);

function faixa(key: Faixa): { de: string; ate: string; label: string } {
  const hoje = new Date();
  const y = hoje.getFullYear();
  const m = hoje.getMonth();
  if (key === "mes") return { de: iso(new Date(y, m, 1)), ate: iso(new Date(y, m + 1, 0)), label: "mês corrente" };
  if (key === "mes_anterior") return { de: iso(new Date(y, m - 1, 1)), ate: iso(new Date(y, m, 0)), label: "mês anterior" };
  if (key === "30d") return { de: iso(new Date(y, m, hoje.getDate() - 29)), ate: iso(hoje), label: "últimos 30 dias" };
  return { de: iso(new Date(y, 0, 1)), ate: iso(hoje), label: "ano até hoje" };
}

/** Quebra de um indicador do ERP por filial (CD × lojas): valor, meta do ERP e participação. */
export function QuebraFilial({ indicatorId, unit, decimals }: { indicatorId: number | string; unit: string; decimals: number }) {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [key, setKey] = useState<Faixa>("mes");
  const [data, setData] = useState<Quebra | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const f = faixa(key);
    setLoading(true);
    api
      .get<Quebra>(`/api/indicators/${indicatorId}/por-filial/?de=${f.de}&ate=${f.ate}`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [indicatorId, key]);

  const option = useMemo(() => {
    const fs = [...(data?.filiais ?? [])].reverse();
    return {
      grid: { left: 4, right: 56, top: 8, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis" as const,
        axisPointer: { type: "shadow" as const },
        formatter: (params: any[]) => {
          const f = fs[params[0].dataIndex];
          if (!f) return "";
          return `<div style="font-weight:600;margin-bottom:2px">${f.code} · ${f.name}</div>
            <div>Realizado <strong>${fmtNumber(f.value, decimals)}</strong> ${unit}</div>
            ${f.target !== null ? `<div>Meta <strong>${fmtNumber(f.target, decimals)}</strong> ${unit}</div>` : ""}
            <div style="color:${t.inkMuted}">${f.achievement_pct ? fmtPct(f.achievement_pct) + " da meta" : f.share_pct !== null ? fmtPct(f.share_pct) + " do total" : ""}</div>`;
        },
      },
      xAxis: { type: "value" as const, axisLabel: { fontSize: 11 } },
      yAxis: { type: "category" as const, data: fs.map((f) => `${f.code} · ${f.name.slice(0, 22)}`), axisLabel: { fontSize: 11 } },
      series: [
        {
          name: "Realizado",
          type: "bar" as const,
          barMaxWidth: BAR_MAX_WIDTH,
          label: { show: true, position: "right" as const, fontSize: 11, color: t.ink, formatter: (p: any) => fmtNumber(p.value, decimals) },
          data: fs.map((f) => ({
            value: Number(f.value),
            itemStyle: { color: f.status ? t.status[statusKey(f.status)] : t.series[0], borderRadius: BAR_RADIUS_H },
          })),
        },
        ...(fs.some((f) => f.target !== null)
          ? [{
              name: "Meta",
              type: "scatter" as const,
              symbol: "rect",
              symbolSize: [3, 18],
              itemStyle: { color: t.ink },
              data: fs.map((f) => (f.target === null ? null : Number(f.target))),
            }]
          : []),
      ],
    };
  }, [data, t, unit, decimals]);

  const f = faixa(key);
  const altura = Math.max(120, 28 * (data?.filiais.length ?? 4) + 24);

  return (
    <Panel
      title="Por filial"
      subtitle="Recalculado do ERP para cada filial no intervalo. A meta aparece quando vem do WinThor (por filial × RCA)."
      actions={
        <div className="btn-group btn-group-sm">
          {([["mes", "Mês"], ["mes_anterior", "Mês anterior"], ["30d", "30 dias"], ["ano", "Ano"]] as [Faixa, string][]).map(([k, l]) => (
            <button key={k} type="button" className={`btn ${key === k ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setKey(k)}>{l}</button>
          ))}
        </div>
      }
    >
      {loading && !data ? (
        <Skeleton height={200} />
      ) : !data ? (
        <EmptyState icon="bi-exclamation-triangle" title="Não foi possível carregar a quebra por filial" />
      ) : !data.disponivel ? (
        <EmptyState icon="bi-building" title="Quebra por filial só existe para indicadores calculados do ERP" />
      ) : data.filiais.length === 0 ? (
        <EmptyState icon="bi-building" title="Nenhuma filial com valor neste intervalo" />
      ) : (
        <>
          <div className="small text-muted-2 mb-2">
            {f.label} · {data.ini.split("-").reverse().join("/")} → {data.fim.split("-").reverse().join("/")}
            {data.parcial && <span className="badge text-bg-light border ms-2">parcial</span>}
            {data.total !== null && <> · total <strong>{fmtNumber(data.total, decimals)} {unit}</strong></>}
          </div>
          <ChartLegend items={[{ color: t.status.verde, label: "Realizado (cor = farol quando há meta)" }, { color: t.ink, label: "Meta do ERP", shape: "line" }]} />
          <EChart option={option} height={altura} />
          <div className="table-responsive mt-3">
            <table className="table table-sm mb-0">
              <thead>
                <tr><th>Filial</th><th className="num">Realizado</th>{data.soma && <th className="num">Participação</th>}<th className="num">Meta</th><th className="num">Atingimento</th><th>Farol</th></tr>
              </thead>
              <tbody>
                {data.filiais.map((fl) => (
                  <tr key={fl.code}>
                    <td><span className="fw-semibold">{fl.code}</span> · {fl.name}</td>
                    <td className="num fw-semibold">{fmtNumber(fl.value, decimals)} {unit}</td>
                    {data.soma && <td className="num text-muted-2">{fl.share_pct === null ? "—" : fmtPct(fl.share_pct)}</td>}
                    <td className="num text-muted-2">{fl.target === null ? "—" : `${fmtNumber(fl.target, decimals)} ${unit}`}</td>
                    <td className="num">{fmtPct(fl.achievement_pct)}</td>
                    <td>{fl.status ? <StatusPill status={fl.status} compact /> : <span className="text-muted-2">—</span>}</td>
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
