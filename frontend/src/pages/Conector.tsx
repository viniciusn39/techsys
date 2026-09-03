import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_V, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { EmptyState, Meter, Panel, Skeleton, StatCard } from "../components/ui";
import { useTheme } from "../hooks/useTheme";

interface Connector {
  id: number;
  name: string;
  erp: string;
  perfil: string;
  ingest_token: string;
  config: Record<string, any>;
  health: Record<string, any>;
  last_seen_at: string | null;
  is_active: boolean;
  online: boolean;
  agent_version: string;
}

interface EntityRow {
  entity: string;
  last_ingest_at: string | null;
  rows_received: number;
  rows_imported: number;
  total_imported: number;
  last_error: string;
  ultimos_min: number;
  marca: string | null;
  janela: number | null;
  janela_alvo: number | null;
  incremental: boolean;
  cadencia_min: number | null;
  esperado: number | null;
  lidos: number;
  importados_passe: number;
  em_andamento: boolean;
  passe_ok: boolean | null;
  pct: number | null;
}

interface Progress {
  connector: Connector;
  coletando: boolean;
  minutos: number;
  serie: Record<string, any>[];
  entidades_serie: string[];
  entities: EntityRow[];
  total_geral: number;
  total_periodo: number;
}

interface Status {
  logs: { id: number; kind: string; summary: string; data: any; created_at: string }[];
  commands: { id: number; command: string; status: string; result: any; error: string; created_at: string }[];
}


const ENTITY_LABEL: Record<string, string> = {
  branch: "Filiais", salesrep: "Vendedores (RCA)", supplier: "Fornecedores", employee: "Funcionários",
  customer: "Clientes", product: "Produtos", sales_invoice: "Notas de venda",
  sales_invoice_item: "Itens de nota (custo/margem)", title_receivable: "Contas a receber",
  title_payable: "Contas a pagar", financial_snapshot: "Fotografia financeira diária",
  bank_account: "Contas bancárias", cash_movement: "Extrato bancário", stock: "Estoque por filial",
  order: "Pedidos de venda", purchase: "Notas de entrada (compras)", load: "Carregamentos",
  target: "Metas do ERP (PCMETA)", target_daily: "Metas diárias do ERP (PCMETARCA)",
};

const KIND_ICON: Record<string, string> = {
  ingest: "bi-cloud-arrow-down", heartbeat: "bi-heart-pulse", error: "bi-exclamation-triangle-fill",
  update: "bi-arrow-repeat", plan: "bi-list-check", command: "bi-terminal", result: "bi-reply",
};

const REFRESH_MS = 10000;


const fmtInt = (n: number) => (n ?? 0).toLocaleString("pt-BR");
const fmtHora = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—");
const fmtDataHora = (iso: string | null) => (iso ? new Date(iso).toLocaleString("pt-BR") : "—");

function relativo(iso: string | null) {
  if (!iso) return "nunca";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `há ${s}s`;
  if (s < 3600) return `há ${Math.round(s / 60)} min`;
  if (s < 86400) return `há ${Math.round(s / 3600)} h`;
  return `há ${Math.round(s / 86400)} d`;
}

export function Conector() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);

  const [connectors, setConnectors] = useState<Connector[] | null>(null);
  const [current, setCurrent] = useState<Connector | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [showLogs, setShowLogs] = useState(false);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [minutos, setMinutos] = useState(120);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(async (id: number) => {
    const [p, s] = await Promise.all([
      api.get<Progress>(`/api/erp/connectors/${id}/progress/?minutos=${minutos}`),
      api.get<Status>(`/api/erp/connectors/${id}/status/`),
    ]);
    setProgress(p);
    setStatus(s);
    setTick((x) => x + 1);
  }, [minutos]);

  const load = useCallback(async () => {
    const list = await api.get<Connector[]>("/api/erp/connectors/");
    setConnectors(list);
    if (list.length > 0) {
      setCurrent(list[0]);
      await refresh(list[0].id);
    }
  }, [refresh]);

  useEffect(() => {
    load().catch(() => setConnectors([]));
  }, [load]);

  // Ao vivo: enquanto a tela está aberta, atualiza a cada 10 s.
  useEffect(() => {
    if (!current) return;
    const timer = window.setInterval(() => refresh(current.id).catch(() => {}), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [current, refresh]);

  const create = async () => {
    setBusy("create");
    try {
      await api.post("/api/erp/connectors/", { name: "WinThor", erp: "winthor", perfil: "misto" });
      await load();
    } finally {
      setBusy("");
    }
  };



  const command = async (cmd: string, payload: any = {}) => {
    if (!current) return;
    setBusy(cmd);
    try {
      await api.post(`/api/erp/connectors/${current.id}/command/`, { command: cmd, payload });
      setNotice(`Comando "${cmd}" enfileirado — o agente responde em até 30 s.`);
    } finally {
      setBusy("");
    }
  };

  const recalcular = async () => {
    if (!current) return;
    setBusy("recalc");
    try {
      await api.post(`/api/erp/connectors/${current.id}/recalcular/`, { meses: 12 });
      setNotice("Recálculo dos indicadores ligados ao ERP enfileirado (últimos 12 meses).");
    } finally {
      setBusy("");
    }
  };


  // --- gráfico: registros importados por minuto, empilhado por entidade ---
  const chartOption = useMemo(() => {
    const serie = progress?.serie ?? [];
    const ents = (progress?.entidades_serie ?? []).slice(0, 8);
    const cores = [...t.series, "#0d9488", "#b45309", "#6f42c1", "#d03b3b"];
    return {
      grid: { left: 8, right: 12, top: 30, bottom: 4, containLabel: true },
      legend: { top: 0, left: 0, data: ents.map((e) => ENTITY_LABEL[e] ?? e) },
      tooltip: {
        trigger: "axis" as const,
        axisPointer: { type: "shadow" as const },
        valueFormatter: (v: any) => fmtInt(Number(v)),
      },
      xAxis: {
        type: "category" as const,
        data: serie.map((s) => String(s.minuto).slice(11)),
        axisLabel: { interval: Math.max(0, Math.floor(serie.length / 12) - 1) },
      },
      yAxis: { type: "value" as const, minInterval: 1 },
      series: ents.map((e, i) => ({
        name: ENTITY_LABEL[e] ?? e,
        type: "bar" as const,
        stack: "carga",
        barMaxWidth: BAR_MAX_WIDTH,
        itemStyle: {
          color: cores[i % cores.length],
          borderColor: t.surface,
          borderWidth: 1,
          borderRadius: i === ents.length - 1 ? BAR_RADIUS_V : 0,
        },
        data: serie.map((s) => s[e] ?? 0),
      })),
    };
  }, [progress, t]);

  if (connectors === null) return <Panel><Skeleton height={300} /></Panel>;

  if (connectors.length === 0) {
    return (
      <Panel>
        <EmptyState
          icon="bi-robot"
          title="Nenhum conector configurado"
          hint="Crie o conector; a chave e o instalador do agente são fornecidos pela TechSys. O agente roda na rede do cliente e só lê o ERP."
          action={<Button onClick={create} disabled={!!busy}><i className="bi bi-plus-lg me-1" />Criar conector WinThor</Button>}
        />
      </Panel>
    );
  }

  const c = progress?.connector ?? current!;
  const h = c.health || {};
  const rows = progress?.entities ?? [];
  const comCarga = rows.filter((e) => e.last_ingest_at).length;
  const comErro = rows.filter((e) => e.last_error).length;
  const taxa = progress ? Math.round(progress.total_periodo / Math.max(1, progress.minutos)) : 0;

  return (
    <div>
      {notice && (
        <div className="alert alert-info py-2 small d-flex align-items-center gap-2">
          <i className="bi bi-info-circle-fill" />{notice}
          <button className="btn-close ms-auto" style={{ fontSize: "0.6rem" }} onClick={() => setNotice("")} />
        </div>
      )}

      {/* --- KPI row --- */}
      <div className="row g-3 mb-3">
        <div className="col-6 col-xl-3">
          <StatCard
            icon={c.online ? "bi-wifi" : "bi-wifi-off"}
            label="Agente"
            value={
              <span className={`status-pill ${c.online ? "st-verde" : "st-vermelho"}`} style={{ fontSize: "0.95rem" }}>
                <i className={`bi ${c.online ? "bi-check-circle-fill" : "bi-x-circle-fill"}`} />
                {c.online ? (progress?.coletando ? "Coletando agora" : "Online") : "Offline"}
              </span>
            }
            foot={`v${c.agent_version || "?"} · ${h.host || "—"} · contato ${relativo(c.last_seen_at)}`}
          />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard
            icon="bi-database"
            label="Oracle do WinThor"
            value={
              <span className={`status-pill ${h.oracle_ok ? "st-verde" : h.oracle_ok === false ? "st-vermelho" : "st-neutro"}`} style={{ fontSize: "0.95rem" }}>
                <i className={`bi ${h.oracle_ok ? "bi-check-circle-fill" : "bi-dash-circle"}`} />
                {h.oracle_ok ? "Conectado" : h.oracle_ok === false ? "Sem conexão" : "Sem informação"}
              </span>
            }
            foot={h.oracle_erro ? <span className="text-danger">{String(h.oracle_erro).slice(0, 90)}</span> : h.schema ? `schema ${h.schema}` : "aguardando heartbeat"}
          />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard
            icon="bi-cloud-arrow-down"
            label="Registros no espelho"
            value={fmtInt(progress?.total_geral ?? 0)}
            foot={`${comCarga} de ${rows.length} entidades já chegaram${comErro ? ` · ${comErro} com erro` : ""}`}
          />
        </div>
        <div className="col-6 col-xl-3">
          <StatCard
            icon="bi-speedometer2"
            label={`Ritmo (últimos ${progress?.minutos ?? minutos} min)`}
            value={<>{fmtInt(taxa)} <span className="fs-6 text-muted-2">reg/min</span></>}
            foot={`${fmtInt(progress?.total_periodo ?? 0)} registros no período`}
          />
        </div>
      </div>

      {/* --- barra de ações --- */}
      <div className="filter-bar">
        <span className="fw-semibold">{c.name}</span>
        <span className="badge text-bg-light border fw-normal text-capitalize">{c.perfil}</span>
        <span className="text-muted-2 small">
          <i className="bi bi-arrow-repeat me-1" />ao vivo · atualizado {tick > 0 ? "agora" : "—"}
        </span>
        <div className="ms-auto d-flex gap-2 flex-wrap">
          <Button size="sm" variant="outline-secondary" onClick={() => command("reiniciar")} disabled={!!busy || !c.online} title="Encerra o processo do agente; o serviço sobe de novo em segundos e aplica a versão mais nova">
            <i className="bi bi-bootstrap-reboot me-1" />Reiniciar agente
          </Button>
          <Button size="sm" variant="outline-secondary" onClick={() => command("validar_schema")} disabled={!!busy || !c.online}>
            <i className="bi bi-clipboard-check me-1" />Validar schema
          </Button>
          <Button size="sm" variant="outline-secondary" onClick={() => command("coletar")} disabled={!!busy || !c.online}>
            <i className="bi bi-play-circle me-1" />Coletar agora
          </Button>
          <Button size="sm" variant="outline-secondary" onClick={recalcular} disabled={!!busy}>
            <i className="bi bi-calculator me-1" />Recalcular indicadores
          </Button>
          <Button size="sm" variant="outline-secondary" onClick={() => setShowLogs(true)}>
            <i className="bi bi-journal-text me-1" />Atividade
          </Button>
        </div>
      </div>

      {/* --- progressão --- */}
      <Panel
        className="mb-3"
        title="Progressão da carga"
        subtitle="Registros importados por minuto, por entidade"
        actions={
          <Form.Select size="sm" style={{ width: 150 }} value={minutos} onChange={(e) => setMinutos(Number(e.target.value))}>
            <option value={30}>Últimos 30 min</option>
            <option value={120}>Últimas 2 horas</option>
            <option value={360}>Últimas 6 horas</option>
            <option value={1440}>Últimas 24 horas</option>
          </Form.Select>
        }
      >
        {(progress?.serie.length ?? 0) === 0 ? (
          <EmptyState icon="bi-activity" title="Nenhuma carga no período" hint="Assim que o agente enviar dados, o gráfico aparece aqui." />
        ) : (
          <EChart option={chartOption} height={260} />
        )}
      </Panel>

      <Panel title="Sincronização por entidade" subtitle="O que já chegou do ERP, o histórico coberto e quando foi a última carga">
        <div className="table-responsive">
          <table className="table table-sm align-middle">
            <thead>
              <tr>
                <th>Entidade</th>
                <th style={{ width: 240 }}>Já chegou (0–100 %)</th>
                <th>Histórico</th>
                <th>Última carga</th>
                <th className="num">Último lote</th>
                <th className="num">Últ. {progress?.minutos ?? minutos} min</th>
                <th>Situação</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => {
                const backfill = e.janela_alvo ? Math.min(100, ((e.janela ?? 0) / e.janela_alvo) * 100) : null;
                return (
                  <tr key={e.entity}>
                    <td>
                      <div className="fw-semibold small">{ENTITY_LABEL[e.entity] ?? e.entity}</div>
                      <div className="text-muted-2" style={{ fontSize: "0.72rem" }}>
                        {e.entity}{e.cadencia_min ? ` · a cada ${e.cadencia_min >= 60 ? `${e.cadencia_min / 60} h` : `${e.cadencia_min} min`}` : ""}
                      </div>
                    </td>
                    <td>
                      {/* 0–100 %: quanto do que o ERP tem para esta entidade já chegou (passe atual/último). */}
                      <div className="d-flex align-items-center gap-2">
                        <div className="flex-grow-1">
                          <Meter pct={e.pct ?? 0} status={e.pct === null ? undefined : e.pct >= 100 ? "verde" : e.em_andamento ? "amarelo" : e.passe_ok === false ? "vermelho" : "amarelo"} />
                        </div>
                        <span className="num small fw-semibold" style={{ minWidth: 44, textAlign: "right" }}>
                          {e.pct === null ? "—" : `${Math.floor(e.pct)}%`}
                        </span>
                      </div>
                      <div className="text-muted-2" style={{ fontSize: "0.72rem" }}>
                        {e.esperado
                          ? `${fmtInt(e.lidos)} de ${fmtInt(e.esperado)}${e.em_andamento ? " · chegando" : ""}`
                          : e.em_andamento
                            ? `${fmtInt(e.lidos)} lidos · chegando`
                            : e.pct === null
                              ? (e.total_imported > 0 ? "histórico em carga" : "ainda não coletado")
                              : e.lidos
                                ? `${fmtInt(e.lidos)} no último passe`
                                : "sincronizado"}
                        {" · "}{fmtInt(e.total_imported)} no espelho
                      </div>
                    </td>
                    <td className="small">
                      {e.janela_alvo ? (
                        <div>
                          <div className="d-flex align-items-center gap-2">
                            <div style={{ width: 90 }}><Meter pct={backfill} status={backfill! >= 100 ? "verde" : "amarelo"} /></div>
                            <span className="text-secondary-2">{e.janela ?? 0}/{e.janela_alvo} meses</span>
                          </div>
                          {e.marca && <div className="text-muted-2" style={{ fontSize: "0.72rem" }}>marca d'água {String(e.marca).slice(0, 16)}</div>}
                        </div>
                      ) : e.marca ? (
                        <span className="text-muted-2" style={{ fontSize: "0.74rem" }}>incremental · marca {String(e.marca).slice(0, 16)}</span>
                      ) : e.incremental ? (
                        <span className="text-muted-2" style={{ fontSize: "0.74rem" }}>incremental</span>
                      ) : (
                        <span className="text-muted-2" style={{ fontSize: "0.74rem" }}>recarga cheia</span>
                      )}
                    </td>
                    <td className="small text-secondary-2" title={fmtDataHora(e.last_ingest_at)}>
                      {e.last_ingest_at ? `${fmtHora(e.last_ingest_at)} (${relativo(e.last_ingest_at)})` : "—"}
                    </td>
                    <td className="num small">{e.last_ingest_at ? `${fmtInt(e.rows_imported)}/${fmtInt(e.rows_received)}` : "—"}</td>
                    <td className="num small">{e.ultimos_min ? <span className="fw-semibold">+{fmtInt(e.ultimos_min)}</span> : <span className="text-muted-2">—</span>}</td>
                    <td>
                      {e.last_error ? (
                        <span className="status-pill st-vermelho" title={e.last_error}><i className="bi bi-x-circle-fill" />erro</span>
                      ) : e.ultimos_min > 0 ? (
                        <span className="status-pill st-verde"><i className="bi bi-arrow-down-circle-fill" />carregando</span>
                      ) : e.last_ingest_at ? (
                        <span className="status-pill st-verde"><i className="bi bi-check-circle-fill" />sincronizado</span>
                      ) : (
                        <span className="status-pill st-neutro"><i className="bi bi-hourglass-split" />aguardando</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* --- modais --- */}
      <Modal show={showLogs} onHide={() => setShowLogs(false)} size="lg" centered scrollable>
        <Modal.Header closeButton><Modal.Title className="fs-6">Atividade do agente</Modal.Title></Modal.Header>
        <Modal.Body>
          {(status?.commands ?? []).length > 0 && (
            <div className="mb-3">
              <div className="stat-label mb-2"><i className="bi bi-terminal" />Comandos</div>
              {status!.commands.slice(0, 5).map((cmd) => (
                <div key={cmd.id} className="suggestion-row">
                  <div className="flex-grow-1 small">
                    <div className="d-flex justify-content-between">
                      <span className="fw-semibold">{cmd.command} <span className="text-muted-2 fw-normal">{fmtDataHora(cmd.created_at)}</span></span>
                      <span className={`status-pill ${cmd.status === "done" ? "st-verde" : cmd.status === "error" ? "st-vermelho" : "st-amarelo"}`}>
                        <i className={`bi ${cmd.status === "done" ? "bi-check-circle-fill" : cmd.status === "error" ? "bi-x-circle-fill" : "bi-hourglass-split"}`} />{cmd.status}
                      </span>
                    </div>
                    {cmd.error && <div className="text-danger" style={{ fontSize: "0.74rem" }}>{cmd.error.slice(0, 300)}</div>}
                    {cmd.status === "done" && cmd.result?.resumo && (
                      <div className="text-muted-2" style={{ fontSize: "0.74rem" }}>
                        {cmd.result.resumo.ok} ok · {cmd.result.resumo.parcial} parcial · {cmd.result.resumo.falha} falha
                        {(cmd.result.entidades || []).filter((x: any) => x.estado !== "ok").map((x: any) => (
                          <div key={x.entidade}><code>{x.entidade}</code>: {x.estado} {x.colunas_ignoradas?.length ? `(colunas ignoradas: ${x.colunas_ignoradas.join(", ")})` : ""} {x.erro}</div>
                        ))}
                        {Object.entries(cmd.result.tabelas_inacessiveis || {}).map(([tb, m]) => <div key={tb}><code>{tb}</code> — {String(m)}</div>)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="stat-label mb-2"><i className="bi bi-journal-text" />Comunicação recente</div>
          {(status?.logs ?? []).length === 0 ? (
            <div className="text-muted-2 small">Nenhuma comunicação ainda.</div>
          ) : (
            status!.logs.map((l) => (
              <div key={l.id} className="d-flex gap-2 py-1 border-bottom small" style={{ borderColor: "var(--grid)" }}>
                <i className={`bi ${KIND_ICON[l.kind] ?? "bi-dot"} ${l.kind === "error" ? "text-danger" : "text-muted-2"}`} />
                <span className="text-muted-2" style={{ minWidth: 130, fontSize: "0.72rem" }}>{fmtDataHora(l.created_at)}</span>
                <span className="flex-grow-1">{l.summary}</span>
              </div>
            ))
          )}
        </Modal.Body>
      </Modal>


    </div>
  );
}
