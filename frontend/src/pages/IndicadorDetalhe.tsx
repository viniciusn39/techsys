import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Form, Tab, Tabs } from "react-bootstrap";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import {
  BAR_MAX_WIDTH,
  BAR_RADIUS_V,
  STATUS_LABEL,
  areaWash,
  statusKey,
  vizTokens,
} from "../charts/theme";
import { EChart } from "../components/EChart";
import { QuebraPeriodo } from "../components/QuebraPeriodo";
import {
  ChartLegend,
  ChartSkeleton,
  EmptyState,
  Panel,
  StatCard,
  StatusPill,
} from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import type { AIInsight, Deviation, IndicatorSeries } from "../types";
import { MONTHS_SHORT, fmtNumber, fmtPct, fmtPeriod } from "../utils/format";

export function IndicadorDetalhe() {
  const { id } = useParams();
  const { isDark } = useTheme();
  const t = vizTokens(isDark);

  const [data, setData] = useState<IndicatorSeries | null>(null);
  const [year, setYear] = useState(new Date().getFullYear());
  const [values, setValues] = useState<Record<string, string>>({});
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [deviations, setDeviations] = useState<Deviation[]>([]);
  const [insights, setInsights] = useState<AIInsight[]>([]);
  const [generating, setGenerating] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    const d = await api.get<IndicatorSeries>(`/api/indicators/${id}/series/?year=${year}`);
    setData(d);
    const v: Record<string, string> = {};
    const tg: Record<string, string> = {};
    d.series.forEach((p) => {
      v[p.period] = p.value ?? "";
      tg[p.period] = p.target ?? "";
    });
    setValues(v);
    setTargets(tg);
    api.get<Deviation[]>(`/api/deviations/?indicator=${id}`).then(setDeviations).catch(() => {});
    api.get<AIInsight[]>(`/api/ai/insights/?indicator=${id}`).then(setInsights).catch(() => {});
  }, [id, year]);

  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [load]);

  const flash = (msg: string) => {
    setSavedMsg(msg);
    window.setTimeout(() => setSavedMsg(""), 2200);
  };

  const saveValue = async (period: string) => {
    await api.post(`/api/indicators/${id}/values/`, { period, value: values[period] });
    await load();
    flash("Lançamento salvo");
  };

  const saveTargets = async () => {
    await api.post(`/api/indicators/${id}/targets/bulk/`, {
      targets: Object.entries(targets).map(([period, target_value]) => ({ period, target_value })),
    });
    await load();
    flash("Metas do ano atualizadas");
  };

  const analyze = async () => {
    setGenerating(true);
    const insight = await api.post<AIInsight>("/api/ai/insights/generate/", {
      kind: "analise_indicador",
      indicator: Number(id),
      period: `${year}-01-01`,
    });
    pollRef.current = window.setInterval(async () => {
      const updated = await api.get<AIInsight>(`/api/ai/insights/${insight.id}/`);
      if (updated.status === "concluido" || updated.status === "erro") {
        if (pollRef.current) window.clearInterval(pollRef.current);
        setGenerating(false);
        api.get<AIInsight[]>(`/api/ai/insights/?indicator=${id}`).then(setInsights);
      }
    }, 2500);
  };

  const ind = data?.indicator;
  const dec = ind?.decimals ?? 2;

  // --- Combo: colunas (realizado, cor = farol) + linha de meta -------------
  // Um único eixo Y — mesma unidade nas duas séries, nunca dual-axis.
  const mainOption = useMemo(() => {
    const series = data?.series ?? [];
    return {
      grid: { left: 4, right: 16, top: 16, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis" as const,
        axisPointer: { type: "shadow" as const },
        formatter: (params: any[]) => {
          const i = params[0].dataIndex;
          const p = series[i];
          if (!p) return "";
          const st = statusKey(p.status);
          return `<div style="font-weight:600;margin-bottom:2px">${MONTHS_SHORT[i]}/${year}</div>
            <div><span style="display:inline-block;width:14px;height:2px;background:${t.status[st]};vertical-align:middle;margin-right:6px"></span>
            Realizado <strong>${fmtNumber(p.value, dec)}</strong> ${ind?.unit || ""}</div>
            <div><span style="display:inline-block;width:14px;height:2px;background:${t.series[0]};vertical-align:middle;margin-right:6px"></span>
            Meta <strong>${fmtNumber(p.target, dec)}</strong> ${ind?.unit || ""}</div>
            <div style="color:${t.inkMuted};margin-top:2px">${fmtPct(p.achievement_pct)} da meta · ${STATUS_LABEL[st]}</div>`;
        },
      },
      xAxis: { type: "category" as const, data: MONTHS_SHORT },
      yAxis: { type: "value" as const },
      series: [
        {
          name: "Realizado",
          type: "bar" as const,
          barMaxWidth: BAR_MAX_WIDTH,
          data: series.map((p) => ({
            value: p.value !== null ? Number(p.value) : null,
            itemStyle: {
              color: t.status[statusKey(p.status)],
              borderRadius: BAR_RADIUS_V,
            },
          })),
        },
        {
          name: "Meta",
          type: "line" as const,
          smooth: false,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2, color: t.series[0] },
          itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 2 },
          z: 3,
          data: series.map((p) => (p.target !== null ? Number(p.target) : null)),
        },
      ],
    };
  }, [data, t, year, dec, ind]);

  // --- Acumulado do ano: área única (tendência) ---------------------------
  const ytdOption = useMemo(() => {
    const series = data?.series ?? [];
    const agg = ind?.aggregation ?? "soma";
    const acc: (number | null)[] = [];
    const vals: number[] = [];
    series.forEach((p) => {
      if (p.value === null) {
        acc.push(null);
        return;
      }
      vals.push(Number(p.value));
      if (agg === "soma") acc.push(vals.reduce((a, b) => a + b, 0));
      else if (agg === "media") acc.push(vals.reduce((a, b) => a + b, 0) / vals.length);
      else acc.push(vals[vals.length - 1]);
    });
    return {
      grid: { left: 4, right: 12, top: 16, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis" as const },
      xAxis: { type: "category" as const, data: MONTHS_SHORT, boundaryGap: false },
      yAxis: { type: "value" as const },
      series: [
        {
          name: "Acumulado",
          type: "line" as const,
          smooth: 0.25,
          symbol: "circle",
          symbolSize: 8,
          showSymbol: false,
          lineStyle: { width: 2, color: t.series[0] },
          itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 2 },
          areaStyle: { color: areaWash(t.series[0]) },
          connectNulls: false,
          data: acc,
        },
      ],
    };
  }, [data, t, ind]);

  // --- Medidor de atingimento YTD ----------------------------------------
  const gaugeOption = useMemo(() => {
    const pct = data?.ytd.achievement_pct !== null && data?.ytd.achievement_pct !== undefined
      ? Number(data.ytd.achievement_pct) : null;
    const st = pct === null ? "sem_meta" : pct >= 100 ? "verde" : pct >= 90 ? "amarelo" : "vermelho";
    return {
      series: [
        {
          type: "gauge" as const,
          startAngle: 200,
          endAngle: -20,
          min: 0,
          max: 130,
          splitNumber: 0,
          radius: "100%",
          center: ["50%", "68%"],
          progress: { show: true, width: 14, roundCap: true, itemStyle: { color: t.status[st] } },
          axisLine: { lineStyle: { width: 14, color: [[1, t.grid]] } },
          pointer: { show: false },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          anchor: { show: false },
          title: { show: false },
          detail: {
            valueAnimation: true,
            offsetCenter: [0, "-2%"],
            fontSize: 26,
            fontWeight: 600,
            color: t.ink,
            formatter: pct === null ? "—" : `${fmtNumber(pct, 0)}%`,
          },
          data: [{ value: pct ?? 0 }],
        },
      ],
    };
  }, [data, t]);

  if (!data || !ind) {
    return (
      <Panel>
        <ChartSkeleton height={320} />
      </Panel>
    );
  }

  const last = ind.last_value;
  const lastIdx = data.series.reduce((acc, p, i) => (p.value !== null ? i : acc), -1);
  const prev = lastIdx > 0 ? data.series[lastIdx - 1] : null;
  const deltaPct =
    last?.achievement_pct && prev?.achievement_pct
      ? Number(last.achievement_pct) - Number(prev.achievement_pct)
      : null;

  return (
    <div>
      <div className="filter-bar">
        <Link to="/indicadores" className="btn btn-sm btn-outline-secondary">
          <i className="bi bi-arrow-left me-1" />Indicadores
        </Link>
        <span className="badge rounded-pill" style={{ background: "var(--brand-soft)", color: "var(--brand)" }}>
          {ind.code}
        </span>
        <span className="fw-semibold">{ind.name}</span>
        <span className="badge rounded-pill text-bg-light border">
          <i className={`bi ${ind.polarity === "menor_melhor" ? "bi-arrow-down" : "bi-arrow-up"} me-1`} />
          {ind.polarity === "menor_melhor" ? "Menor é melhor" : "Maior é melhor"}
        </span>
        {ind.org_unit_name && <span className="text-muted-2 small"><i className="bi bi-diagram-2 me-1" />{ind.org_unit_name}</span>}
        {ind.owner_name && <span className="text-muted-2 small"><i className="bi bi-person me-1" />{ind.owner_name}</span>}
        <Form.Select
          size="sm"
          className="ms-auto"
          style={{ width: 100 }}
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
        >
          {[year - 1, year, year + 1].map((y) => <option key={y} value={y}>{y}</option>)}
        </Form.Select>
      </div>

      {savedMsg && (
        <div className="alert alert-success py-2 small d-flex align-items-center gap-2">
          <i className="bi bi-check-circle-fill" />{savedMsg}
        </div>
      )}

      <div className="row g-3">
        <div className="col-6 col-xl-3">
          <StatCard
            icon="bi-speedometer2"
            label={`Realizado · ${fmtPeriod(last?.period)}`}
            value={<>{fmtNumber(last?.value, dec)} <span className="fs-6 text-muted-2">{ind.unit}</span></>}
            delta={deltaPct !== null ? { value: deltaPct, goodWhenUp: true, since: "mês anterior" } : null}
          />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard
            icon="bi-flag"
            label="Atingimento do mês"
            value={fmtPct(last?.achievement_pct)}
            foot={<StatusPill status={last?.status ?? null} />}
            spark={data.series.map((p) => p.achievement_pct)}
            sparkColor={t.status[statusKey(last?.status)]}
          />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard
            icon="bi-calendar3-range"
            label={`Acumulado ${year} (${ind.aggregation})`}
            value={<>{fmtNumber(data.ytd.value, dec)} <span className="fs-6 text-muted-2">{ind.unit}</span></>}
            foot={`Meta acumulada ${fmtNumber(data.ytd.target, dec)} ${ind.unit}`}
          />
        </div>
        <div className="col-6 col-xl-3">
          <div className="stat">
            <div className="stat-label"><i className="bi bi-bullseye" />Atingimento acumulado</div>
            <EChart option={gaugeOption} height={104} />
          </div>
        </div>
      </div>

      <div className="row g-3 mt-0">
        <div className="col-xl-8">
          <Panel title="Meta × Realizado" subtitle={`Mês a mês em ${year} — a cor da coluna é o farol`}>
            <EChart option={mainOption} height={320} />
            <ChartLegend
              items={[
                { color: t.series[0], label: "Meta", shape: "line" },
                { color: t.status.verde, label: "Realizado · meta atingida" },
                { color: t.status.amarelo, label: "Realizado · atenção" },
                { color: t.status.vermelho, label: "Realizado · crítico" },
              ]}
            />
          </Panel>
        </div>
        <div className="col-xl-4">
          <Panel title={`Acumulado do ano`} subtitle={`Agregação: ${ind.aggregation}`}>
            <EChart option={ytdOption} height={320} />
          </Panel>
        </div>
      </div>

      <div className="mt-3">
        <QuebraPeriodo indicatorId={ind.id} unit={ind.unit} decimals={dec} erp={!!ind.erp_metric} />
      </div>

      <div className="mt-3">
        <Tabs defaultActiveKey="lancamentos" className="mb-3">
          <Tab eventKey="lancamentos" title="Lançamentos">
            <Panel subtitle={ind.erp_metric ? <><i className="bi bi-robot me-1" />Calculado do ERP ({ind.erp_metric_label}) pelo agente a cada 30 min — lançamento manual bloqueado.</> : undefined}>
              <div className="table-responsive">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th>Mês</th><th className="num">Meta</th>
                      <th style={{ width: 170 }}>Realizado</th>
                      <th className="num">Atingimento</th><th>Farol</th><th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.series.map((p, i) => (
                      <tr key={p.period}>
                        <td className="fw-semibold">{MONTHS_SHORT[i]}/{year}</td>
                        <td className="num text-muted-2">{fmtNumber(p.target, dec)}</td>
                        <td>
                          {ind.erp_metric ? (
                            <span className="num d-block">{values[p.period] ? fmtNumber(values[p.period], dec) : "—"}</span>
                          ) : (
                            <Form.Control
                              size="sm" type="number" step="any" className="num"
                              value={values[p.period] ?? ""}
                              onChange={(e) => setValues({ ...values, [p.period]: e.target.value })}
                              onKeyDown={(e) => e.key === "Enter" && saveValue(p.period)}
                            />
                          )}
                        </td>
                        <td className="num fw-semibold">{fmtPct(p.achievement_pct)}</td>
                        <td><StatusPill status={p.status} /></td>
                        <td className="text-end">
                          {ind.erp_metric ? (
                            <i className="bi bi-lock-fill text-muted-2" title="Calculado do ERP pelo agente; lançamento manual bloqueado" />
                          ) : (
                            <Button size="sm" variant="outline-secondary" onClick={() => saveValue(p.period)} title="Salvar">
                              <i className="bi bi-check-lg" />
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </Tab>

          <Tab eventKey="metas" title="Metas do ano">
            {ind.erp_target ? (
              <Panel subtitle={<><i className="bi bi-lock-fill me-1" />Metas puxadas do ERP ({ind.erp_target_label}), sincronizadas a cada 6 h — edição manual bloqueada.</>}>
                <div className="row g-2">
                  {data.series.map((p, i) => (
                    <div className="col-6 col-md-3 col-xl-2" key={p.period}>
                      <div className="text-muted-2 small">{MONTHS_SHORT[i]}</div>
                      <div className="num fw-semibold">{p.target === null || p.target === undefined ? "—" : `${fmtNumber(p.target, dec)} ${ind.unit}`}</div>
                    </div>
                  ))}
                </div>
              </Panel>
            ) : (
            <Panel subtitle="Defina as 12 metas de uma vez; o farol é recalculado ao salvar.">
              <div className="row g-2">
                {data.series.map((p, i) => (
                  <div className="col-6 col-md-3 col-xl-2" key={p.period}>
                    <Form.Label className="mb-0">{MONTHS_SHORT[i]}</Form.Label>
                    <Form.Control
                      size="sm" type="number" step="any" className="num"
                      value={targets[p.period] ?? ""}
                      onChange={(e) => setTargets({ ...targets, [p.period]: e.target.value })}
                    />
                  </div>
                ))}
              </div>
              <div className="mt-3 d-flex gap-2">
                <Button size="sm" onClick={saveTargets}>
                  <i className="bi bi-check-lg me-1" />Salvar metas
                </Button>
                <Button
                  size="sm"
                  variant="outline-secondary"
                  onClick={() => {
                    const first = targets[data.series[0].period];
                    if (!first) return;
                    const copy = { ...targets };
                    data.series.forEach((p) => (copy[p.period] = first));
                    setTargets(copy);
                  }}
                >
                  <i className="bi bi-arrow-repeat me-1" />Repetir janeiro nos 12 meses
                </Button>
              </div>
            </Panel>
            )}
          </Tab>

          <Tab eventKey="desvios" title={`Desvios (${deviations.length})`}>
            <Panel>
              {deviations.length === 0 ? (
                <EmptyState icon="bi-check2-circle" title="Nenhum desvio neste indicador" />
              ) : (
                <table className="table table-sm">
                  <thead>
                    <tr><th>Período</th><th className="num">Atingimento</th><th>Status</th><th>Causa raiz</th></tr>
                  </thead>
                  <tbody>
                    {deviations.map((d) => (
                      <tr key={d.id}>
                        <td className="fw-semibold">{fmtPeriod(d.period)}</td>
                        <td className="num">{fmtPct(d.achievement_pct)}</td>
                        <td>
                          <span className={`status-pill st-${d.status === "concluido" ? "verde" : d.status === "em_tratamento" ? "amarelo" : "vermelho"}`}>
                            <i className={`bi ${d.status === "concluido" ? "bi-check-circle-fill" : d.status === "em_tratamento" ? "bi-arrow-repeat" : "bi-exclamation-circle-fill"}`} />
                            {d.status === "concluido" ? "Concluído" : d.status === "em_tratamento" ? "Em tratamento" : "Aberto"}
                          </span>
                        </td>
                        <td className="text-secondary-2 small">{d.root_cause || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          </Tab>

          <Tab eventKey="ia" title={<><i className="bi bi-stars me-1" />Insights de IA</>}>
            <Panel
              actions={
                <Button size="sm" onClick={analyze} disabled={generating}>
                  <i className="bi bi-stars me-1" />
                  {generating ? "Analisando..." : "Analisar com IA"}
                </Button>
              }
              title="Análises geradas"
              subtitle="A IA lê a série, as metas e o acumulado do indicador."
            >
              {insights.length === 0 && !generating && (
                <EmptyState
                  icon="bi-stars"
                  title="Nenhuma análise ainda"
                  hint="Gere uma leitura de tendência, riscos e recomendações para este indicador."
                />
              )}
              {generating && (
                <div className="d-flex align-items-center gap-2 text-muted-2 small py-3">
                  <span className="spinner-border spinner-border-sm" />
                  Consultando o provedor de IA…
                </div>
              )}
              {insights.map((ins) => (
                <div key={ins.id} className="panel mb-2" style={{ boxShadow: "none" }}>
                  <div className="panel-head">
                    <div className="sub">
                      <i className="bi bi-stars me-1" />
                      {new Date(ins.created_at).toLocaleString("pt-BR")}
                      {ins.requested_by_name ? ` · ${ins.requested_by_name}` : ""}
                    </div>
                    <span className={`status-pill st-${ins.status === "concluido" ? "verde" : ins.status === "erro" ? "vermelho" : "neutro"}`}>
                      <i className={`bi ${ins.status === "concluido" ? "bi-check-circle-fill" : ins.status === "erro" ? "bi-x-circle-fill" : "bi-hourglass-split"}`} />
                      {ins.status}
                    </span>
                  </div>
                  <div className="panel-body">
                    {ins.status === "erro" ? (
                      <div className="text-danger small">{ins.error_message}</div>
                    ) : (
                      <div className="markdown-body">{ins.content}</div>
                    )}
                  </div>
                </div>
              ))}
            </Panel>
          </Tab>
        </Tabs>
      </div>
    </div>
  );
}
