import { useEffect, useMemo, useState } from "react";
import { Button, Modal } from "react-bootstrap";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_V, statusKey, vizTokens } from "../charts/theme";
import { useTheme } from "../hooks/useTheme";
import type { Indicator } from "../types";
import { fmtNumber, fmtPct } from "../utils/format";
import { EChart } from "./EChart";
import { EmptyState, Skeleton, StatusPill } from "./ui";

interface Periodo { label: string; ini: string; fim: string; value: number | null; target: number | null; achievement_pct: number | null; status: string | null; parcial: boolean }
interface Quebra { periodos: Periodo[]; disponivel: boolean }

/** Segundo modal: os últimos meses de um indicador (meta × realizado), sem sair da tela. */
export function IndicadorResumoModal({ indicator, onClose }: { indicator: Indicator; onClose: () => void }) {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [q, setQ] = useState<Quebra | null>(null);
  const [n, setN] = useState(12);
  const dec = indicator.decimals ?? 2;

  useEffect(() => {
    setQ(null);
    api.get<Quebra>(`/api/indicators/${indicator.id}/breakdown/?gran=mes&n=${n}`).then(setQ).catch(() => setQ({ periodos: [], disponivel: false }));
  }, [indicator.id, n]);

  const option = useMemo(() => {
    const ps = q?.periodos ?? [];
    return {
      grid: { left: 4, right: 16, top: 16, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis" as const, axisPointer: { type: "shadow" as const },
        formatter: (params: any[]) => {
          const p = ps[params[0].dataIndex];
          if (!p) return "";
          return `<div style="font-weight:600">${p.label}${p.parcial ? " (parcial)" : ""}</div><div>Realizado <strong>${fmtNumber(p.value, dec)}</strong> ${indicator.unit}</div><div>Meta <strong>${fmtNumber(p.target, dec)}</strong> ${indicator.unit}</div><div style="color:${t.inkMuted}">${p.achievement_pct ? fmtPct(p.achievement_pct) + " da meta" : "sem meta"}</div>`;
        },
      },
      xAxis: { type: "category" as const, data: ps.map((p) => p.label), axisLabel: { fontSize: 11 } },
      yAxis: { type: "value" as const },
      series: [
        { name: "Realizado", type: "bar" as const, barMaxWidth: BAR_MAX_WIDTH, data: ps.map((p) => ({ value: p.value === null ? null : Number(p.value), itemStyle: { color: p.status ? t.status[statusKey(p.status)] : t.series[0], borderRadius: BAR_RADIUS_V, opacity: p.parcial ? 0.55 : 1 } })) },
        { name: "Meta", type: "line" as const, step: "middle" as const, symbol: "none", lineStyle: { width: 2, color: t.series[0], type: "dashed" as const }, data: ps.map((p) => (p.target === null ? null : Number(p.target))) },
      ],
    };
  }, [q, t, dec, indicator.unit]);

  const fechados = (q?.periodos ?? []).filter((p) => p.value !== null && !p.parcial);
  const media = fechados.length ? fechados.reduce((s, p) => s + Number(p.value), 0) / fechados.length : null;
  const atingidos = fechados.filter((p) => p.status === "verde").length;

  return (
    <Modal show onHide={onClose} size="lg" centered backdropClassName="modal-backdrop-2">
      <Modal.Header closeButton>
        <div className="flex-grow-1">
          <div className="d-flex align-items-center gap-2">
            <span className="badge rounded-pill" style={{ background: "var(--brand-soft)", color: "var(--brand)" }}>{indicator.code}</span>
            <StatusPill status={indicator.last_value?.status ?? null} compact />
          </div>
          <Modal.Title className="fs-6 fw-bold mt-1">{indicator.name}</Modal.Title>
          <div className="small text-muted-2">{indicator.polarity === "menor_melhor" ? "menor é melhor" : "maior é melhor"} · {indicator.unit}{indicator.erp_metric ? " · calculado do ERP" : " · lançamento manual"}</div>
        </div>
        <div className="btn-group btn-group-sm me-2">
          {[6, 12, 24].map((k) => <button key={k} className={`btn ${n === k ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setN(k)}>{k} m</button>)}
        </div>
      </Modal.Header>
      <Modal.Body>
        {!q ? <Skeleton height={240} /> : !q.disponivel || q.periodos.length === 0 ? <EmptyState icon="bi-graph-up" title="Sem histórico ainda" /> : (
          <>
            <div className="row g-2 mb-2 small">
              <div className="col-4"><div className="p-2 rounded" style={{ background: "var(--surface-sunken)" }}><div className="text-muted-2">Último resultado</div><div className="fw-semibold">{indicator.last_value ? `${fmtNumber(indicator.last_value.value, dec)} ${indicator.unit}` : "—"}</div></div></div>
              <div className="col-4"><div className="p-2 rounded" style={{ background: "var(--surface-sunken)" }}><div className="text-muted-2">Média dos meses fechados</div><div className="fw-semibold">{media === null ? "—" : `${fmtNumber(media, dec)} ${indicator.unit}`}</div></div></div>
              <div className="col-4"><div className="p-2 rounded" style={{ background: "var(--surface-sunken)" }}><div className="text-muted-2">Meses com meta atingida</div><div className="fw-semibold">{fechados.length ? `${atingidos} de ${fechados.length}` : "—"}</div></div></div>
            </div>
            <EChart option={option} height={240} />
            <div className="table-responsive mt-2" style={{ maxHeight: 220, overflow: "auto" }}>
              <table className="table table-sm mb-0" style={{ fontSize: "0.8rem" }}>
                <thead><tr><th>Mês</th><th className="num">Meta</th><th className="num">Realizado</th><th className="num">Atingimento</th><th>Farol</th></tr></thead>
                <tbody>
                  {[...q.periodos].reverse().map((p) => (
                    <tr key={p.ini} className={p.value === null ? "text-muted-2" : ""}>
                      <td>{p.label}{p.parcial && <span className="badge text-bg-light border ms-1">parcial</span>}</td>
                      <td className="num text-muted-2">{p.target === null ? "—" : fmtNumber(p.target, dec)}</td>
                      <td className="num fw-semibold">{p.value === null ? "—" : fmtNumber(p.value, dec)}</td>
                      <td className="num">{fmtPct(p.achievement_pct)}</td>
                      <td>{p.status ? <StatusPill status={p.status} compact /> : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Modal.Body>
      <Modal.Footer>
        <Link to={`/indicadores/${indicator.id}`} className="btn btn-sm btn-outline-secondary me-auto"><i className="bi bi-box-arrow-up-right me-1" />Abrir página completa</Link>
        <Button size="sm" variant="outline-secondary" onClick={onClose}>Fechar</Button>
      </Modal.Footer>
    </Modal>
  );
}
