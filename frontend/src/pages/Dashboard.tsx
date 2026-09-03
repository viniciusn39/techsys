import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import {
  BAR_MAX_WIDTH,
  BAR_RADIUS_H,
  BAR_RADIUS_V,
  STATUS_LABEL,
  areaWash,
  statusKey,
  vizTokens,
} from "../charts/theme";
import { EChart } from "../components/EChart";
import {
  ChartLegend,
  ChartSkeleton,
  EmptyState,
  Meter,
  Panel,
  Skeleton,
  StatCard,
  StatusDot,
  StatusPill,
} from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import type { DashboardSummary, Deviation, OrgUnit } from "../types";
import { MONTHS_SHORT, fmtNumber, fmtPct, fmtPeriod } from "../utils/format";

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

const FAROL_ORDER = ["verde", "amarelo", "vermelho", "sem_meta", "sem_lancamento"] as const;

export function Dashboard() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [deviations, setDeviations] = useState<Deviation[]>([]);
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [orgUnit, setOrgUnit] = useState("");
  const [period, setPeriod] = useState(currentPeriod());
  const [loading, setLoading] = useState(true);
  const [showTable, setShowTable] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/org-units/").then(setUnits).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ period });
    if (orgUnit) params.set("org_unit", orgUnit);
    api
      .get<DashboardSummary>(`/api/dashboard/summary/?${params}`)
      .then((d) => {
        setSummary(d);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    api.get<Deviation[]>("/api/deviations/?status=aberto").then(setDeviations).catch(() => {});
  }, [orgUnit, period]);

  const monthIdx = Number(period.slice(5, 7)) - 1;

  // --- Ranking: barra horizontal com linha de referência na meta (100%) ----
  const rankingOption = useMemo(() => {
    const rows = summary?.ranking ?? [];
    return {
      grid: { left: 4, right: 56, top: 22, bottom: 24, containLabel: true },
      xAxis: {
        type: "value" as const,
        axisLabel: { formatter: "{value}%" },
        max: (v: { max: number }) => Math.max(120, Math.ceil(v.max / 10) * 10),
      },
      yAxis: {
        type: "category" as const,
        data: rows.map((r) => r.code),
        axisLabel: { fontWeight: 500, color: t.inkSecondary },
      },
      tooltip: {
        trigger: "item" as const,
        formatter: (p: any) => {
          const r = rows[p.dataIndex];
          const label = STATUS_LABEL[statusKey(r.status)];
          return `<strong>${fmtNumber(r.achievement_pct, 1)}%</strong> da meta<br/>
            <span style="color:${t.inkSecondary}">${r.code} — ${r.name}</span><br/>
            <span style="color:${t.inkMuted}">Realizado ${fmtNumber(r.value, r.decimals ?? 2)} ${r.unit || ""} · ${label}</span>`;
        },
      },
      series: [
        {
          type: "bar" as const,
          data: rows.map((r) => ({
            value: Number(r.achievement_pct),
            itemStyle: {
              color: t.status[statusKey(r.status)],
              borderRadius: BAR_RADIUS_H,
            },
          })),
          barMaxWidth: BAR_MAX_WIDTH,
          label: {
            show: true,
            position: "right" as const,
            formatter: (p: any) => `${fmtNumber(p.value, 0)}%`,
            color: t.inkSecondary,
            fontSize: 11,
          },
          markLine: {
            silent: true,
            symbol: "none",
            label: {
              formatter: "meta",
              position: "end" as const,
              color: t.inkMuted,
              fontSize: 10,
            },
            lineStyle: { color: t.axis, width: 1, type: "solid" as const },
            data: [{ xAxis: 100 }],
          },
        },
      ],
    };
  }, [summary, t]);

  // --- Composição de faróis: donut com número-herói no centro -------------
  const farolOption = useMemo(() => {
    const f = summary?.farois ?? {};
    const data = FAROL_ORDER.filter((k) => (f[k] ?? 0) > 0).map((k) => ({
      name: STATUS_LABEL[k],
      value: f[k],
      itemStyle: { color: t.status[k], borderColor: t.surface, borderWidth: 2 },
    }));
    return {
      tooltip: {
        trigger: "item" as const,
        formatter: (p: any) => `<strong>${p.value} indicador(es)</strong><br/>${p.name} · ${p.percent}%`,
      },
      series: [
        {
          type: "pie" as const,
          radius: ["62%", "86%"],
          center: ["50%", "50%"],
          avoidLabelOverlap: true,
          label: { show: false },
          labelLine: { show: false },
          data,
        },
      ],
    };
  }, [summary, t]);

  // --- Evolução: colunas empilhadas de faróis por mês ---------------------
  const evolutionOption = useMemo(() => {
    const ev = summary?.evolution ?? [];
    const stack = (key: "verde" | "amarelo" | "vermelho", last: boolean) => ({
      name: STATUS_LABEL[key],
      type: "bar" as const,
      stack: "farol",
      barMaxWidth: BAR_MAX_WIDTH,
      // Gap de 2px na cor da superfície separa os segmentos — nunca um contorno.
      itemStyle: {
        color: t.status[key],
        borderColor: t.surface,
        borderWidth: 2,
        borderRadius: last ? BAR_RADIUS_V : 0,
      },
      data: ev.map((e) => e[key]),
    });
    return {
      grid: { left: 4, right: 8, top: 30, bottom: 4, containLabel: true },
      legend: { top: 0, left: 0 },
      tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
      xAxis: { type: "category" as const, data: MONTHS_SHORT },
      yAxis: { type: "value" as const, minInterval: 1 },
      series: [stack("vermelho", false), stack("amarelo", false), stack("verde", true)],
    };
  }, [summary, t]);

  // --- Heatmap indicador × mês -------------------------------------------
  const heatmapOption = useMemo(() => {
    const cells = summary?.heatmap ?? [];
    const codes = Array.from(new Set(cells.map((c) => c.indicator)));
    const statusIdx: Record<string, number> = { vermelho: 0, amarelo: 1, verde: 2, sem_meta: 3 };
    const data = cells.map((c) => [
      Number(c.period.slice(5, 7)) - 1,
      codes.indexOf(c.indicator),
      statusIdx[statusKey(c.status)] ?? 3,
      c.achievement_pct,
    ]);
    return {
      grid: { left: 4, right: 8, top: 8, bottom: 4, containLabel: true },
      tooltip: {
        formatter: (p: any) => {
          const [x, y, s, pct] = p.data as [number, number, number, string | null];
          const key = statusKey(Object.keys(statusIdx).find((k) => statusIdx[k] === s));
          return `<strong>${pct !== null ? `${fmtNumber(pct, 1)}%` : "sem meta"}</strong><br/>
            <span style="color:${t.inkSecondary}">${codes[y]} · ${MONTHS_SHORT[x]}</span><br/>
            <span style="color:${t.inkMuted}">${STATUS_LABEL[key]}</span>`;
        },
      },
      xAxis: { type: "category" as const, data: MONTHS_SHORT, splitArea: { show: false } },
      yAxis: {
        type: "category" as const,
        data: codes,
        axisLabel: { fontSize: 11, color: t.inkSecondary },
      },
      visualMap: {
        show: false,
        type: "piecewise" as const,
        dimension: 2,
        pieces: [
          { value: 0, color: t.status.vermelho },
          { value: 1, color: t.status.amarelo },
          { value: 2, color: t.status.verde },
          { value: 3, color: t.status.sem_meta },
        ],
      },
      series: [
        {
          type: "heatmap" as const,
          data,
          itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 3 },
          emphasis: { itemStyle: { borderColor: t.ink, borderWidth: 2 } },
          progressive: 0,
        },
      ],
    };
  }, [summary, t]);

  if (error) {
    return (
      <Panel>
        <EmptyState
          icon="bi-building"
          title="Nenhuma empresa selecionada"
          hint="Escolha uma empresa no seletor da barra lateral para ver os resultados."
        />
      </Panel>
    );
  }

  const farolTotal = FAROL_ORDER.reduce((acc, k) => acc + (summary?.farois?.[k] ?? 0), 0);
  const comLancamento = farolTotal - (summary?.farois?.sem_lancamento ?? 0);
  const evAtual = summary?.evolution?.[monthIdx]?.atingimento_pct ?? null;
  const evAnterior = monthIdx > 0 ? summary?.evolution?.[monthIdx - 1]?.atingimento_pct ?? null : null;

  return (
    <div>
      {/* Filtros: uma linha, acima de tudo que eles escopam. */}
      <div className="filter-bar">
        <div className="d-flex align-items-center gap-2">
          <i className="bi bi-calendar3 text-muted-2" />
          <input
            type="month"
            className="form-control form-control-sm"
            style={{ width: 170 }}
            value={period.slice(0, 7)}
            onChange={(e) => e.target.value && setPeriod(`${e.target.value}-01`)}
          />
        </div>
        <select
          className="form-select form-select-sm"
          style={{ width: 190 }}
          value={orgUnit}
          onChange={(e) => setOrgUnit(e.target.value)}
        >
          <option value="">Todas as áreas</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
        <span className="text-muted-2 small ms-auto">
          Competência {fmtPeriod(period)}
        </span>
      </div>

      {/* KPI row — stat tiles, não gráficos de uma barra. */}
      <div className="row g-3">
        <div className="col-6 col-xl-3">
          {loading ? <Skeleton height={104} /> : (
            <StatCard
              icon="bi-graph-up-arrow"
              label="Indicadores ativos"
              value={summary?.total_indicadores ?? 0}
              foot={`${comLancamento} com lançamento no mês`}
            />
          )}
        </div>
        <div className="col-6 col-xl-3">
          {loading ? <Skeleton height={104} /> : (
            <StatCard
              icon="bi-bullseye"
              label="Metas atingidas"
              value={summary?.metas_atingidas_pct !== null && summary?.metas_atingidas_pct !== undefined
                ? fmtPct(summary.metas_atingidas_pct) : "—"}
              delta={evAtual !== null && evAnterior !== null
                ? { value: evAtual - evAnterior, goodWhenUp: true, since: MONTHS_SHORT[monthIdx - 1] }
                : null}
              spark={summary?.evolution?.map((e) => e.atingimento_pct) ?? []}
              sparkColor={t.status.verde}
            />
          )}
        </div>
        <div className="col-6 col-xl-3">
          {loading ? <Skeleton height={104} /> : (
            <StatCard
              icon="bi-exclamation-triangle"
              label="Desvios abertos"
              value={summary?.desvios_abertos ?? 0}
              foot={
                <Link to="/desvios" className="text-decoration-none">
                  Tratar desvios <i className="bi bi-arrow-right" />
                </Link>
              }
            />
          )}
        </div>
        <div className="col-6 col-xl-3">
          {loading ? <Skeleton height={104} /> : (
            <StatCard
              icon="bi-kanban"
              label="Planos de ação"
              value={summary?.planos_andamento ?? 0}
              foot={
                <>
                  em andamento ·{" "}
                  <span style={{ color: (summary?.planos_atrasados ?? 0) > 0 ? "var(--st-vermelho)" : undefined }}>
                    {summary?.planos_atrasados ?? 0} atrasado(s)
                  </span>
                </>
              }
            />
          )}
        </div>
      </div>

      <div className="row g-3 mt-0">
        {/* Ranking de atingimento */}
        <div className="col-xl-7">
          <Panel
            title="Atingimento por indicador"
            subtitle={`Percentual da meta em ${fmtPeriod(period)} — a linha marca 100%`}
            actions={
              <button
                className="btn btn-sm btn-outline-secondary"
                onClick={() => setShowTable((v) => !v)}
              >
                <i className={`bi ${showTable ? "bi-bar-chart" : "bi-table"} me-1`} />
                {showTable ? "Gráfico" : "Tabela"}
              </button>
            }
          >
            {loading ? (
              <ChartSkeleton height={340} />
            ) : (summary?.ranking?.length ?? 0) === 0 ? (
              <EmptyState
                icon="bi-clipboard-data"
                title="Sem lançamentos neste mês"
                hint="Lance os resultados dos indicadores para ver o atingimento."
              />
            ) : showTable ? (
              /* Vista de tabela: alternativa acessível ao gráfico. */
              <div className="table-responsive">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th>Indicador</th><th>Área</th>
                      <th className="num">Realizado</th><th className="num">Meta</th>
                      <th className="num">Atingimento</th><th>Farol</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...(summary?.ranking ?? [])].reverse().map((r) => (
                      <tr key={r.id}>
                        <td>
                          <Link to={`/indicadores/${r.id}`} className="text-decoration-none fw-semibold">
                            {r.code}
                          </Link>
                          <div className="text-muted-2" style={{ fontSize: "0.75rem" }}>{r.name}</div>
                        </td>
                        <td className="text-secondary-2">{r.org_unit_name || "—"}</td>
                        <td className="num">{fmtNumber(r.value, r.decimals ?? 2)}</td>
                        <td className="num text-muted-2">{fmtNumber(r.target, r.decimals ?? 2)}</td>
                        <td className="num fw-semibold">{fmtPct(r.achievement_pct)}</td>
                        <td><StatusPill status={r.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <>
                <EChart option={rankingOption} height={Math.max(220, (summary?.ranking?.length ?? 0) * 30 + 40)} />
                <ChartLegend
                  items={[
                    { color: t.status.verde, label: "Meta atingida" },
                    { color: t.status.amarelo, label: "Atenção" },
                    { color: t.status.vermelho, label: "Crítico" },
                  ]}
                />
              </>
            )}
          </Panel>
        </div>

        {/* Composição de faróis */}
        <div className="col-xl-5">
          <Panel title="Composição dos faróis" subtitle={`${comLancamento} indicadores avaliados`}>
            {loading ? (
              <ChartSkeleton height={230} />
            ) : comLancamento === 0 ? (
              <EmptyState icon="bi-pie-chart" title="Nada lançado no período" />
            ) : (
              <div className="position-relative">
                <EChart option={farolOption} height={230} />
                <div
                  className="position-absolute top-50 start-50 translate-middle text-center"
                  style={{ pointerEvents: "none" }}
                >
                  <div className="hero-figure" style={{ fontSize: "2.4rem" }}>
                    {summary?.farois?.verde ?? 0}
                  </div>
                  <div className="text-muted-2" style={{ fontSize: "0.74rem" }}>
                    no verde
                  </div>
                </div>
              </div>
            )}
            {!loading && comLancamento > 0 && (
              <div className="d-flex flex-column gap-2 mt-2">
                {FAROL_ORDER.filter((k) => (summary?.farois?.[k] ?? 0) > 0).map((k) => (
                  <div key={k} className="d-flex align-items-center gap-2">
                    <StatusPill status={k} />
                    <div className="flex-grow-1">
                      <Meter pct={((summary?.farois?.[k] ?? 0) / farolTotal) * 100} status={k} />
                    </div>
                    <span className="num small fw-semibold" style={{ minWidth: 28 }}>
                      {summary?.farois?.[k]}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </div>

      <div className="row g-3 mt-0">
        <div className="col-xl-5">
          <Panel title="Evolução dos faróis" subtitle={`Indicadores por status a cada mês de ${summary?.year ?? ""}`}>
            {loading ? <ChartSkeleton height={260} /> : <EChart option={evolutionOption} height={260} />}
          </Panel>
        </div>
        <div className="col-xl-7">
          <Panel title="Painel de bordo do ano" subtitle="Farol de cada indicador mês a mês">
            {loading ? (
              <ChartSkeleton height={260} />
            ) : (summary?.heatmap?.length ?? 0) === 0 ? (
              <EmptyState icon="bi-grid-3x3" title="Sem histórico no ano" />
            ) : (
              <>
                <EChart
                  option={heatmapOption}
                  height={Math.max(200, new Set((summary?.heatmap ?? []).map((c) => c.indicator)).size * 26 + 50)}
                />
                <ChartLegend
                  items={[
                    { color: t.status.verde, label: "Meta atingida" },
                    { color: t.status.amarelo, label: "Atenção" },
                    { color: t.status.vermelho, label: "Crítico" },
                    { color: t.status.sem_meta, label: "Sem meta" },
                  ]}
                />
              </>
            )}
          </Panel>
        </div>
      </div>

      <div className="mt-3">
        <Panel
          title="Desvios abertos"
          subtitle="Faróis vermelhos que ainda não têm tratamento concluído"
          actions={
            <Link to="/desvios" className="btn btn-sm btn-outline-secondary">
              Ver todos
            </Link>
          }
        >
          {deviations.length === 0 ? (
            <EmptyState icon="bi-check2-circle" title="Nenhum desvio aberto" hint="Todos os indicadores críticos estão tratados." />
          ) : (
            <div className="table-responsive">
              <table className="table table-hover table-sm">
                <thead>
                  <tr>
                    <th style={{ width: 24 }}></th>
                    <th>Indicador</th><th>Período</th>
                    <th className="num">Atingimento</th><th>Status</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {deviations.slice(0, 6).map((d) => (
                    <tr key={d.id}>
                      <td><StatusDot status="vermelho" /></td>
                      <td>
                        <span className="fw-semibold">{d.indicator_code}</span>
                        <span className="text-muted-2"> — {d.indicator_name}</span>
                      </td>
                      <td className="text-secondary-2">{fmtPeriod(d.period)}</td>
                      <td className="num fw-semibold">{fmtPct(d.achievement_pct)}</td>
                      <td><StatusPill status="vermelho" /></td>
                      <td className="text-end">
                        <Link className="btn btn-sm btn-outline-secondary" to="/desvios">Tratar</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
