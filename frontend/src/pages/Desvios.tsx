import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { areaWash, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { EmptyState, Panel, Skeleton, StatCard, StatusDot } from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import type { AIInsight, Deviation, IndicatorSeries } from "../types";
import { MONTHS_SHORT, fmtNumber, fmtPct, fmtPeriod } from "../utils/format";

const STATUS_META: Record<string, { label: string; cls: string; icon: string }> = {
  aberto: { label: "Aberto", cls: "st-vermelho", icon: "bi-exclamation-circle-fill" },
  em_tratamento: { label: "Em tratamento", cls: "st-amarelo", icon: "bi-arrow-repeat" },
  concluido: { label: "Concluído", cls: "st-verde", icon: "bi-check-circle-fill" },
};

export function Desvios() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const navigate = useNavigate();

  const [rows, setRows] = useState<Deviation[] | null>(null);
  const [filter, setFilter] = useState("");
  const [treating, setTreating] = useState<Deviation | null>(null);
  const [rootCause, setRootCause] = useState("");
  const [series, setSeries] = useState<IndicatorSeries | null>(null);
  const [aiInsight, setAiInsight] = useState<AIInsight | null>(null);
  const [generating, setGenerating] = useState(false);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(() => {
    const params = filter ? `?status=${filter}` : "";
    api.get<Deviation[]>(`/api/deviations/${params}`).then(setRows).catch(() => setRows([]));
  }, [filter]);

  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [load]);

  const openTreat = async (d: Deviation) => {
    setTreating(d);
    setRootCause(d.root_cause);
    setAiInsight(null);
    setSeries(null);
    const year = Number(d.period.slice(0, 4));
    api
      .get<IndicatorSeries>(`/api/indicators/${d.indicator}/series/?year=${year}`)
      .then(setSeries)
      .catch(() => {});
  };

  const saveCause = async () => {
    if (!treating) return;
    await api.patch(`/api/deviations/${treating.id}/`, {
      root_cause: rootCause,
      status: treating.status === "aberto" ? "em_tratamento" : treating.status,
    });
    load();
  };

  const createPlan = async () => {
    if (!treating) return;
    await saveCause();
    await api.post(`/api/deviations/${treating.id}/create-plan/`);
    setTreating(null);
    navigate("/planos-acao");
  };

  const analyzeAI = async () => {
    if (!treating) return;
    setGenerating(true);
    const insight = await api.post<AIInsight>("/api/ai/insights/generate/", {
      kind: "analise_desvio",
      deviation: treating.id,
    });
    pollRef.current = window.setInterval(async () => {
      const updated = await api.get<AIInsight>(`/api/ai/insights/${insight.id}/`);
      if (updated.status === "concluido" || updated.status === "erro") {
        if (pollRef.current) window.clearInterval(pollRef.current);
        setGenerating(false);
        setAiInsight(updated);
      }
    }, 2500);
  };

  // Contexto do desvio: linha do realizado vs meta no ano do indicador.
  const contextOption = useMemo(() => {
    const s = series?.series ?? [];
    const dec = series?.indicator.decimals ?? 2;
    const markIdx = treating ? Number(treating.period.slice(5, 7)) - 1 : -1;
    return {
      grid: { left: 4, right: 12, top: 26, bottom: 4, containLabel: true },
      legend: { top: 0, left: 0 },
      tooltip: { trigger: "axis" as const, valueFormatter: (v: any) => fmtNumber(v, dec) },
      xAxis: { type: "category" as const, data: MONTHS_SHORT, boundaryGap: false },
      yAxis: { type: "value" as const },
      series: [
        {
          name: "Realizado",
          type: "line" as const,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2, color: t.series[0] },
          itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 2 },
          areaStyle: { color: areaWash(t.series[0]) },
          data: s.map((p) => (p.value !== null ? Number(p.value) : null)),
          markPoint:
            markIdx >= 0 && s[markIdx]?.value !== null
              ? {
                  symbol: "pin",
                  symbolSize: 34,
                  itemStyle: { color: t.status.vermelho },
                  label: { color: "#fff", fontSize: 10, formatter: "!" },
                  data: [{ coord: [markIdx, Number(s[markIdx].value)] }],
                }
              : undefined,
        },
        {
          name: "Meta",
          type: "line" as const,
          symbol: "none",
          lineStyle: { width: 2, color: t.series[1] },
          itemStyle: { color: t.series[1] },
          data: s.map((p) => (p.target !== null ? Number(p.target) : null)),
        },
      ],
    };
  }, [series, treating, t]);

  const list = rows ?? [];
  const abertos = list.filter((d) => d.status === "aberto").length;
  const emTratamento = list.filter((d) => d.status === "em_tratamento").length;
  const concluidos = list.filter((d) => d.status === "concluido").length;

  return (
    <div>
      <div className="row g-3 mb-3">
        <div className="col-4">
          <StatCard icon="bi-exclamation-circle" label="Abertos" value={abertos} foot="aguardando tratamento" />
        </div>
        <div className="col-4">
          <StatCard icon="bi-arrow-repeat" label="Em tratamento" value={emTratamento} foot="com causa ou plano em curso" />
        </div>
        <div className="col-4">
          <StatCard icon="bi-check2-circle" label="Concluídos" value={concluidos} foot="plano de ação finalizado" />
        </div>
      </div>

      <div className="filter-bar">
        <span className="text-muted-2 small">
          Faróis vermelhos geram desvios automaticamente e exigem plano de ação.
        </span>
        <Form.Select
          size="sm"
          className="ms-auto"
          style={{ width: 180 }}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="">Todos</option>
          <option value="aberto">Abertos</option>
          <option value="em_tratamento">Em tratamento</option>
          <option value="concluido">Concluídos</option>
        </Form.Select>
      </div>

      <Panel>
        {rows === null ? (
          <div className="d-flex flex-column gap-2 py-2">
            {[...Array(5)].map((_, i) => <Skeleton key={i} height={40} />)}
          </div>
        ) : list.length === 0 ? (
          <EmptyState
            icon="bi-check2-circle"
            title="Nenhum desvio"
            hint="Todos os indicadores estão dentro da meta ou já foram tratados."
          />
        ) : (
          <div className="table-responsive">
            <table className="table table-hover align-middle">
              <thead>
                <tr>
                  <th style={{ width: 24 }}></th>
                  <th>Indicador</th><th>Período</th>
                  <th className="num">Realizado</th><th className="num">Atingimento</th>
                  <th>Planos</th><th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {list.map((d) => (
                  <tr key={d.id}>
                    <td><StatusDot status="vermelho" /></td>
                    <td>
                      <span className="fw-semibold">{d.indicator_code}</span>
                      <span className="text-secondary-2"> — {d.indicator_name}</span>
                      {d.root_cause && (
                        <div className="text-muted-2" style={{ fontSize: "0.74rem" }}>
                          <i className="bi bi-search me-1" />{d.root_cause.slice(0, 90)}
                          {d.root_cause.length > 90 ? "…" : ""}
                        </div>
                      )}
                    </td>
                    <td className="text-secondary-2">{fmtPeriod(d.period)}</td>
                    <td className="num">{fmtNumber(d.value, 2)}</td>
                    <td className="num fw-semibold">{fmtPct(d.achievement_pct)}</td>
                    <td>
                      {d.plans_count > 0 ? (
                        <span className="badge text-bg-light border fw-normal">
                          <i className="bi bi-kanban me-1" />{d.plans_count}
                        </span>
                      ) : (
                        <span className="text-muted-2 small">—</span>
                      )}
                    </td>
                    <td>
                      <span className={`status-pill ${STATUS_META[d.status].cls}`}>
                        <i className={`bi ${STATUS_META[d.status].icon}`} />{STATUS_META[d.status].label}
                      </span>
                    </td>
                    <td className="text-end">
                      <Button size="sm" variant="outline-secondary" onClick={() => openTreat(d)}>
                        {d.status === "concluido" ? "Ver" : "Tratar"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal show={!!treating} onHide={() => setTreating(null)} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title className="fs-6">
            Desvio · {treating?.indicator_code} — {fmtPeriod(treating?.period)}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <div className="row g-3 mb-3">
            <div className="col-4">
              <StatCard label="Realizado" value={fmtNumber(treating?.value, 2)} />
            </div>
            <div className="col-4">
              <StatCard label="Atingimento" value={fmtPct(treating?.achievement_pct)} />
            </div>
            <div className="col-4">
              <StatCard label="Planos vinculados" value={treating?.plans_count ?? 0} />
            </div>
          </div>

          <Panel title="Contexto do indicador no ano" className="mb-3">
            {series ? <EChart option={contextOption} height={220} /> : <Skeleton height={220} />}
          </Panel>

          <Form.Group className="mb-3">
            <Form.Label>Análise de causa raiz</Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              placeholder="Descreva a causa raiz (5 porquês, Ishikawa...)"
              value={rootCause}
              onChange={(e) => setRootCause(e.target.value)}
              disabled={treating?.status === "concluido"}
            />
          </Form.Group>

          <div className="d-flex gap-2 mb-3 flex-wrap">
            {treating?.status !== "concluido" && (
              <>
                <Button size="sm" variant="outline-secondary" onClick={saveCause}>
                  <i className="bi bi-save me-1" />Salvar causa
                </Button>
                <Button size="sm" onClick={createPlan}>
                  <i className="bi bi-kanban me-1" />Criar plano de ação 5W2H
                </Button>
              </>
            )}
            <Button size="sm" variant="outline-secondary" onClick={analyzeAI} disabled={generating}>
              <i className="bi bi-stars me-1" />
              {generating ? "Analisando..." : "Analisar desvio com IA"}
            </Button>
          </div>

          {generating && (
            <div className="d-flex align-items-center gap-2 text-muted-2 small py-2">
              <span className="spinner-border spinner-border-sm" />
              A IA está levantando hipóteses de causa raiz e contramedidas…
            </div>
          )}

          {aiInsight && (
            <Panel title="Análise da IA">
              {aiInsight.status === "erro" ? (
                <div className="text-danger small">{aiInsight.error_message}</div>
              ) : (
                <div className="markdown-body">{aiInsight.content}</div>
              )}
            </Panel>
          )}
        </Modal.Body>
      </Modal>
    </div>
  );
}
