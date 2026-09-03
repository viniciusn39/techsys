import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form } from "react-bootstrap";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, BAR_RADIUS_V, areaWash, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { ChartLegend, EmptyState, Panel, Skeleton, StatCard, StatusPill } from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import { MONTHS_SHORT, fmtNumber, fmtPeriod } from "../utils/format";

interface Serie {
  periodo: string;
  faturamento: number | null;
  cmv: number | null;
  margem_bruta_pct: number | null;
  qtd_notas: number | null;
  ticket_medio: number | null;
  positivacao: number | null;
  recebido: number | null;
  despesas_pagas: number | null;
  compras_valor: number | null;
}

interface Conferencia {
  id: number;
  code: string;
  name: string;
  unit: string;
  decimals: number;
  erp_metric: string;
  erp_metric_label: string;
  erp_filters: { branch?: string | string[] };
  entities: string[];
  periodo: string;
  valor_gravado: number | null;
  calculado_em: string | null;
  valor_erp: number | null;
  meta: number | null;
  achievement_pct: number | null;
  status: string | null;
  situacao: "confere" | "divergente" | "aguardando" | "sem_dados" | "sem_valor" | "metrica_invalida";
}

interface Painel {
  gerado_em: string;
  meses: number;
  filial: string | null;
  filiais: { code: string; name: string }[];
  cobertura: { entity: string; label: string; total: number; de: string | null; ate: string | null; incremental: boolean }[];
  serie: Serie[];
  foto: { periodo: string; atual: Record<string, number | null>; mes_anterior: Record<string, number | null> };
  por_filial: { code: string; name: string; faturamento_mes: number | null; notas_mes: number; faturamento_ano: number | null }[];
  rankings: {
    periodo: string;
    vendedores: { name: string; valor: number | null; notas: number }[];
    clientes: { name: string; valor: number | null; notas: number }[];
    departamentos: { name: string; valor: number | null; custo: number | null; margem_pct: number | null }[];
    produtos: { name: string; valor: number | null; quantidade: number | null }[];
  };
  indicadores: Conferencia[];
  resumo_conferencia: { total: number; confere: number; divergente: number; aguardando: number; sem_dados: number };
}

const SITUACAO: Record<Conferencia["situacao"], { label: string; cls: string; icon: string }> = {
  confere: { label: "Confere", cls: "text-bg-success", icon: "bi-check-circle-fill" },
  divergente: { label: "Divergente", cls: "text-bg-warning", icon: "bi-exclamation-triangle-fill" },
  aguardando: { label: "Aguardando cálculo", cls: "text-bg-secondary", icon: "bi-hourglass-split" },
  sem_dados: { label: "Sem dados no ERP", cls: "text-bg-light border", icon: "bi-database-x" },
  sem_valor: { label: "ERP não retornou valor", cls: "text-bg-light border", icon: "bi-question-circle" },
  metrica_invalida: { label: "Métrica inválida", cls: "text-bg-danger", icon: "bi-x-circle-fill" },
};

const money = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: digits, minimumFractionDigits: digits });

/** R$ compactado para os cartões: 1,2 mi / 830 mil. */
function moneyCompact(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `R$ ${(v / 1e9).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} bi`;
  if (a >= 1e6) return `R$ ${(v / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} mi`;
  if (a >= 1e4) return `R$ ${(v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} mil`;
  return money(v);
}

const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${fmtNumber(v, d)}%`);
const mesCurto = (iso: string) => `${MONTHS_SHORT[Number(iso.slice(5, 7)) - 1]}/${iso.slice(2, 4)}`;
const fmtData = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");

function valorFmt(v: number | null, unit: string, decimals: number) {
  if (v === null || v === undefined) return "—";
  if (unit === "R$") return money(v, Math.min(decimals, 2));
  if (unit === "%") return `${fmtNumber(v, decimals)}%`;
  return `${fmtNumber(v, decimals)} ${unit}`.trim();
}

function variacao(atual: number | null | undefined, anterior: number | null | undefined) {
  if (atual === null || atual === undefined || !anterior) return null;
  return ((atual - anterior) / Math.abs(anterior)) * 100;
}

export function PainelErp() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const { me } = useAuth();
  const isAdmin = me?.role === "root" || me?.role === "admin";

  const [data, setData] = useState<Painel | null>(null);
  const [meses, setMeses] = useState(12);
  const [branch, setBranch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [aba, setAba] = useState<"vendedores" | "clientes" | "departamentos" | "produtos">("vendedores");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ meses: String(meses) });
      if (branch) params.set("branch", branch);
      setData(await api.get<Painel>(`/api/erp/painel/?${params}`));
      setError("");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [meses, branch]);

  useEffect(() => {
    load();
  }, [load]);

  const recalcular = async () => {
    setBusy(true);
    try {
      const conns = await api.get<{ id: number }[]>("/api/erp/connectors/");
      if (conns.length === 0) {
        setNotice("Nenhum conector configurado.");
        return;
      }
      await api.post(`/api/erp/connectors/${conns[0].id}/recalcular/`, { meses });
      setNotice("Recálculo enfileirado — os indicadores são refeitos em segundo plano; atualize em instantes.");
    } catch (e: any) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  };

  const serie = data?.serie ?? [];
  const meseslabels = serie.map((s) => mesCurto(s.periodo));

  const axisMoney = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi` : Math.abs(v) >= 1e3 ? `${(v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} mil` : String(v));

  const barPair = (a: { name: string; key: keyof Serie; color: string }, b: { name: string; key: keyof Serie; color: string }) => ({
    grid: { left: 8, right: 12, top: 12, bottom: 4, containLabel: true },
    tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const }, valueFormatter: (v: any) => money(Number(v)) },
    xAxis: { type: "category" as const, data: meseslabels },
    yAxis: { type: "value" as const, axisLabel: { formatter: axisMoney } },
    series: [a, b].map((s) => ({
      name: s.name,
      type: "bar" as const,
      barMaxWidth: BAR_MAX_WIDTH,
      itemStyle: { color: s.color, borderRadius: BAR_RADIUS_V },
      data: serie.map((x) => x[s.key] ?? 0),
    })),
  });

  const fatOption = useMemo(
    () => barPair({ name: "Faturamento", key: "faturamento", color: t.series[0] }, { name: "CMV", key: "cmv", color: t.series[1] }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [serie, t],
  );
  const caixaOption = useMemo(
    () => barPair({ name: "Recebido", key: "recebido", color: t.series[2] }, { name: "Pago", key: "despesas_pagas", color: t.series[3] }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [serie, t],
  );

  const margemOption = useMemo(() => ({
    grid: { left: 8, right: 12, top: 12, bottom: 4, containLabel: true },
    tooltip: { trigger: "axis" as const, valueFormatter: (v: any) => pct(Number(v)) },
    xAxis: { type: "category" as const, data: meseslabels, boundaryGap: false },
    yAxis: { type: "value" as const, axisLabel: { formatter: "{value}%" } },
    series: [{
      name: "Margem bruta",
      type: "line" as const,
      smooth: 0.25,
      symbol: "circle",
      symbolSize: 8,
      lineStyle: { width: 2, color: t.series[0] },
      itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 2 },
      areaStyle: { color: areaWash(t.series[0]) },
      data: serie.map((x) => x.margem_bruta_pct),
    }],
  }), [serie, meseslabels, t]);

  const notasOption = useMemo(() => ({
    grid: { left: 8, right: 12, top: 12, bottom: 4, containLabel: true },
    tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const }, valueFormatter: (v: any) => fmtNumber(Number(v), 0) },
    xAxis: { type: "category" as const, data: meseslabels },
    yAxis: { type: "value" as const, minInterval: 1 },
    series: [
      { name: "Notas", type: "bar" as const, barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[4], borderRadius: BAR_RADIUS_V }, data: serie.map((x) => x.qtd_notas ?? 0) },
      { name: "Clientes positivados", type: "bar" as const, barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[5], borderRadius: BAR_RADIUS_V }, data: serie.map((x) => x.positivacao ?? 0) },
    ],
  }), [serie, meseslabels, t]);

  const hbar = (rows: { name: string; valor: number | null }[], color: string, extra?: (i: number) => string) => ({
    grid: { left: 4, right: 70, top: 4, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "item" as const,
      formatter: (p: any) => `<strong>${money(rows[p.dataIndex].valor)}</strong><br/><span style="color:${t.inkSecondary}">${rows[p.dataIndex].name}</span>${extra ? `<br/><span style="color:${t.inkMuted}">${extra(p.dataIndex)}</span>` : ""}`,
    },
    xAxis: { type: "value" as const, axisLabel: { formatter: axisMoney } },
    yAxis: { type: "category" as const, inverse: true, data: rows.map((r) => (r.name.length > 26 ? r.name.slice(0, 25) + "…" : r.name)), axisLabel: { color: t.inkSecondary, fontSize: 11 } },
    series: [{
      type: "bar" as const,
      barMaxWidth: BAR_MAX_WIDTH,
      itemStyle: { color, borderRadius: BAR_RADIUS_H },
      label: { show: true, position: "right" as const, formatter: (p: any) => moneyCompact(p.value), color: t.inkSecondary, fontSize: 11 },
      data: rows.map((r) => r.valor ?? 0),
    }],
  });

  const filialOption = useMemo(() => {
    const rows = (data?.por_filial ?? []).filter((f) => f.faturamento_mes).map((f) => ({ name: `${f.code} · ${f.name}`, valor: f.faturamento_mes }));
    return hbar(rows, t.series[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, t]);

  const rankingOption = useMemo(() => {
    const r = data?.rankings;
    if (!r) return hbar([], t.series[1]);
    if (aba === "departamentos") return hbar(r.departamentos, t.series[1], (i) => `Margem ${pct(r.departamentos[i].margem_pct)}`);
    if (aba === "produtos") return hbar(r.produtos, t.series[1], (i) => `${fmtNumber(r.produtos[i].quantidade, 0)} un`);
    if (aba === "clientes") return hbar(r.clientes, t.series[1], (i) => `${r.clientes[i].notas} notas`);
    return hbar(r.vendedores, t.series[1], (i) => `${r.vendedores[i].notas} notas`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, aba, t]);

  if (loading && !data) {
    return (
      <div className="d-grid gap-3">
        <div className="row g-3">{[0, 1, 2, 3, 4, 5].map((i) => <div className="col-6 col-lg-2" key={i}><Skeleton height={96} /></div>)}</div>
        <Panel><Skeleton height={280} /></Panel>
      </div>
    );
  }

  if (error && !data) return <Panel><EmptyState icon="bi-exclamation-triangle" title="Não foi possível montar o painel" hint={error} /></Panel>;
  if (!data) return null;

  const semDados = data.cobertura.every((c) => c.total === 0);
  if (semDados) {
    return (
      <Panel>
        <EmptyState
          icon="bi-database"
          title="O espelho do ERP ainda está vazio"
          hint="Assim que o agente começar a enviar dados, este painel monta os números e a conferência dos indicadores."
          action={isAdmin ? <Link className="btn btn-primary" to="/admin/conector"><i className="bi bi-robot me-1" />Ver o conector</Link> : undefined}
        />
      </Panel>
    );
  }

  const a = data.foto.atual;
  const ant = data.foto.mes_anterior;
  const res = data.resumo_conferencia;
  const mesRef = fmtPeriod(data.foto.periodo);

  const delta = (k: string) => {
    const v = variacao(a[k], ant[k]);
    return v === null ? undefined : { value: v, since: "vs mês anterior" };
  };

  return (
    <div className="d-grid gap-3">
      {/* Filtros: uma linha, acima de tudo. */}
      <div className="d-flex flex-wrap align-items-center gap-2">
        <Form.Select size="sm" style={{ width: 240 }} value={branch} onChange={(e) => setBranch(e.target.value)}>
          <option value="">Todas as filiais</option>
          {data.filiais.map((f) => <option key={f.code} value={f.code}>{f.code} · {f.name}</option>)}
        </Form.Select>
        <Form.Select size="sm" style={{ width: 150 }} value={meses} onChange={(e) => setMeses(Number(e.target.value))}>
          <option value={6}>6 meses</option>
          <option value={12}>12 meses</option>
          <option value={24}>24 meses</option>
        </Form.Select>
        <Button size="sm" variant="outline-secondary" onClick={load} disabled={loading}>
          <i className={`bi bi-arrow-clockwise me-1 ${loading ? "spin" : ""}`} />Atualizar
        </Button>
        <span className="text-muted-2 small ms-auto">
          Mês de referência: <strong>{mesRef}</strong> · gerado {new Date(data.gerado_em).toLocaleTimeString("pt-BR")}
        </span>
      </div>

      {notice && (
        <div className="alert alert-info py-2 small mb-0 d-flex align-items-center">
          <i className="bi bi-info-circle me-2" />{notice}
          <button className="btn-close ms-auto" onClick={() => setNotice("")} />
        </div>
      )}

      {/* Cartões do mês */}
      <div className="row g-3">
        <div className="col-6 col-lg-2"><StatCard label="Faturamento no mês" icon="bi-cash-stack" value={moneyCompact(a.faturamento)} delta={delta("faturamento")} foot={`${fmtNumber(a.qtd_notas, 0)} notas · ticket ${money(a.ticket_medio)}`} /></div>
        <div className="col-6 col-lg-2"><StatCard label="Margem bruta" icon="bi-percent" value={pct(a.margem_bruta_pct)} delta={delta("margem_bruta_pct")} foot={`${fmtNumber(a.positivacao, 0)} clientes positivados`} /></div>
        <div className="col-6 col-lg-2"><StatCard label="A receber vencido" icon="bi-receipt" value={moneyCompact(a.a_receber_vencido)} foot={`${moneyCompact(a.a_receber_aberto)} em aberto · inadimplência ${pct(a.inadimplencia_pct)}`} /></div>
        <div className="col-6 col-lg-2"><StatCard label="A pagar vencido" icon="bi-wallet2" value={moneyCompact(a.a_pagar_vencido)} foot={`${moneyCompact(a.a_pagar_aberto)} em aberto`} /></div>
        <div className="col-6 col-lg-2"><StatCard label="Caixa e bancos" icon="bi-bank" value={moneyCompact(a.saldo_caixa)} foot={`carteira de pedidos ${moneyCompact(a.carteira_pedidos)}`} /></div>
        <div className="col-6 col-lg-2"><StatCard label="Estoque a custo" icon="bi-box-seam" value={moneyCompact(a.estoque_valor)} foot={`ruptura ${pct(a.ruptura_pct)} · ${fmtNumber(a.cobertura_estoque_dias, 0)} dias · ${fmtNumber(a.headcount, 0)} func.`} /></div>
      </div>

      {/* Conferência dos indicadores — o coração da página */}
      <Panel
        title="Conferência dos indicadores ligados ao ERP"
        subtitle={`${res.confere} de ${res.total} conferem · ${res.divergente} divergentes · ${res.aguardando} aguardando cálculo · ${res.sem_dados} sem dados`}
        actions={isAdmin && (
          <Button size="sm" variant="outline-primary" onClick={recalcular} disabled={busy}>
            <i className="bi bi-calculator me-1" />Recalcular indicadores
          </Button>
        )}
      >
        {data.indicadores.length === 0 ? (
          <EmptyState icon="bi-link-45deg" title="Nenhum indicador ligado ao ERP" hint="Em Indicadores, vincule um KPI a uma métrica do ERP para ele ser calculado do espelho." />
        ) : (
          <div className="table-responsive">
            <table className="table table-sm align-middle mb-0">
              <thead>
                <tr>
                  <th>Indicador</th>
                  <th>Métrica do ERP</th>
                  <th>Período</th>
                  <th className="text-end">Gravado no KPI</th>
                  <th className="text-end">ERP agora</th>
                  <th className="text-end">Meta</th>
                  <th>Farol</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {data.indicadores.map((c) => {
                  const s = SITUACAO[c.situacao];
                  const filiais = ([] as string[]).concat(c.erp_filters?.branch ?? []);
                  const filtro = filiais.length ? ` · ${filiais.length > 1 ? "filiais" : "filial"} ${filiais.join(", ")}` : "";
                  return (
                    <tr key={c.id}>
                      <td>
                        <Link to={`/indicadores/${c.id}`} className="fw-semibold text-decoration-none">{c.code}</Link>
                        <div className="small text-muted-2">{c.name}</div>
                      </td>
                      <td className="small">{c.erp_metric_label}<span className="text-muted-2">{filtro}</span></td>
                      <td className="small text-nowrap">{fmtPeriod(c.periodo)}</td>
                      <td className="text-end text-nowrap">
                        {valorFmt(c.valor_gravado, c.unit, c.decimals)}
                        {c.calculado_em && <div className="small text-muted-2">{new Date(c.calculado_em).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</div>}
                      </td>
                      <td className={`text-end text-nowrap ${c.situacao === "divergente" ? "fw-semibold" : ""}`}>{valorFmt(c.valor_erp, c.unit, c.decimals)}</td>
                      <td className="text-end text-nowrap">{valorFmt(c.meta, c.unit, c.decimals)}</td>
                      <td>{c.status ? <StatusPill status={c.status} compact /> : <span className="text-muted-2">—</span>}</td>
                      <td><span className={`badge ${s.cls}`}><i className={`bi ${s.icon} me-1`} />{s.label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="small text-muted-2 mt-2">
          <strong>Confere</strong>: o valor do KPI é exatamente o que o espelho do ERP dá hoje. <strong>Divergente</strong>: a carga avançou desde o último cálculo (ou a regra mudou) — recalcule. <strong>Aguardando</strong>: o ERP já tem dados, mas o cálculo automático ainda não rodou (roda a cada 30 min).
        </div>
      </Panel>

      {/* Séries mensais */}
      <div className="row g-3">
        <div className="col-lg-6">
          <Panel title="Faturamento × CMV" subtitle="Notas de saída faturadas e custo dos itens, por mês">
            <ChartLegend items={[{ color: t.series[0], label: "Faturamento" }, { color: t.series[1], label: "CMV" }]} />
            <EChart option={fatOption} height={260} />
          </Panel>
        </div>
        <div className="col-lg-6">
          <Panel title="Margem bruta" subtitle="(venda − custo) / venda, nos itens faturados">
            <EChart option={margemOption} height={260} />
          </Panel>
        </div>
        <div className="col-lg-6">
          <Panel title="Recebimentos × Pagamentos" subtitle="Títulos baixados no mês">
            <ChartLegend items={[{ color: t.series[2], label: "Recebido" }, { color: t.series[3], label: "Pago" }]} />
            <EChart option={caixaOption} height={260} />
          </Panel>
        </div>
        <div className="col-lg-6">
          <Panel title="Notas e clientes positivados" subtitle="Volume de vendas por mês">
            <ChartLegend items={[{ color: t.series[4], label: "Notas" }, { color: t.series[5], label: "Clientes positivados" }]} />
            <EChart option={notasOption} height={260} />
          </Panel>
        </div>
      </div>

      {/* Filiais e rankings do mês */}
      <div className="row g-3">
        <div className="col-lg-5">
          <Panel title={`Faturamento por filial · ${mesRef}`} subtitle="Todas as filiais, independente do filtro">
            {data.por_filial.some((f) => f.faturamento_mes) ? (
              <>
                <EChart option={filialOption} height={Math.max(160, 34 * data.por_filial.filter((f) => f.faturamento_mes).length + 20)} />
                <div className="table-responsive mt-2">
                  <table className="table table-sm mb-0 small">
                    <thead><tr><th>Filial</th><th className="text-end">Mês</th><th className="text-end">Notas</th><th className="text-end">Ano</th></tr></thead>
                    <tbody>
                      {data.por_filial.map((f) => (
                        <tr key={f.code}>
                          <td>{f.code} · {f.name}</td>
                          <td className="text-end">{money(f.faturamento_mes)}</td>
                          <td className="text-end">{fmtNumber(f.notas_mes, 0)}</td>
                          <td className="text-end">{money(f.faturamento_ano)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : <EmptyState icon="bi-shop" title="Sem faturamento no mês" hint="As notas do mês ainda não chegaram ou não há vendas no período." />}
          </Panel>
        </div>
        <div className="col-lg-7">
          <Panel
            title={`Top 10 do mês · ${mesRef}`}
            actions={
              <div className="btn-group btn-group-sm">
                {(["vendedores", "clientes", "departamentos", "produtos"] as const).map((k) => (
                  <button key={k} className={`btn ${aba === k ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setAba(k)}>
                    {k[0].toUpperCase() + k.slice(1)}
                  </button>
                ))}
              </div>
            }
          >
            {(data.rankings[aba] as { valor: number | null }[]).some((r) => r.valor) ? (
              <EChart option={rankingOption} height={Math.max(200, 34 * data.rankings[aba].length + 20)} />
            ) : <EmptyState icon="bi-bar-chart" title="Sem vendas no mês" hint={aba === "departamentos" || aba === "produtos" ? "Os itens de nota (PCMOV) ainda não chegaram para este mês." : "As notas do mês ainda não chegaram."} />}
          </Panel>
        </div>
      </div>

      {/* Cobertura */}
      <Panel title="O que já veio do ERP" subtitle="Registros no espelho e período coberto por entidade">
        <div className="table-responsive">
          <table className="table table-sm mb-0 small">
            <thead><tr><th>Entidade</th><th className="text-end">Registros</th><th>Período coberto</th><th>Tipo</th></tr></thead>
            <tbody>
              {data.cobertura.map((c) => (
                <tr key={c.entity} className={c.total === 0 ? "text-muted-2" : ""}>
                  <td>{c.label}</td>
                  <td className="text-end">{fmtNumber(c.total, 0)}</td>
                  <td>{c.de ? `${fmtData(c.de)} → ${fmtData(c.ate)}` : "—"}</td>
                  <td>{c.incremental ? "movimento (incremental)" : "cadastro (carga completa)"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
