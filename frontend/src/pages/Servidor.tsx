import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, areaWash, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { EmptyState, Meter, Panel, Skeleton, StatCard } from "../components/ui";
import { useTheme } from "../hooks/useTheme";

interface Servidor {
  agora: string;
  host: {
    cpu_pct: number | null;
    memoria: { total: number; usado: number; disponivel: number; pct: number; swap_total: number; swap_usado: number } | null;
    disco: { caminho: string; total: number; usado: number; livre: number; pct: number } | null;
    load: { m1: number; m5: number; m15: number; cpus: number } | null;
    uptime: number | null;
  };
  postgres: { tamanho: number; versao: string; conexoes: number; conexoes_ativas: number; max_conexoes: number; cache_hit_pct: number; tamanho_tabelas: number; tabelas: { tabela: string; linhas: number; mortas: number; tamanho: number; autovacuum: string | null; autoanalyze: string | null }[] };
  redis: { ok: boolean; erro?: string; versao?: string; memoria?: number; memoria_pico?: number; clientes?: number; chaves?: number; uptime?: number; filas?: Record<string, number | null>; hits?: number; misses?: number };
  celery: { ok: boolean; erro?: string; workers?: string[]; em_execucao?: number; reservadas?: number; tarefas?: { worker: string; nome: string; inicio: number }[] };
  aplicacao: { empresas: number; usuarios: number; indicadores: number; valores: number; linhas_espelho: number; conectores: number; agentes_online: number; chamados_abertos: number };
  amostras: { at: string; cpu_pct: number | null; mem_pct: number | null; disco_pct: number | null; load_m1: number | null; db_bytes: number | null; db_conexoes: number | null }[];
}

const bytes = (n: number | null | undefined) => {
  if (n === null || n === undefined) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
};
const dur = (s: number | null | undefined) => {
  if (!s) return "—";
  const d = Math.floor(s / 86400); const h = Math.floor((s % 86400) / 3600); const m = Math.floor((s % 3600) / 60);
  return d ? `${d} d ${h} h` : h ? `${h} h ${m} min` : `${m} min`;
};
const statusPct = (p: number | null | undefined, amarelo = 70, vermelho = 90) => (p === null || p === undefined ? null : p >= vermelho ? "vermelho" : p >= amarelo ? "amarelo" : "verde");

/** Root: monitoramento, performance e armazenamento do servidor da plataforma. */
export function Servidor() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const [d, setD] = useState<Servidor | null>(null);
  const [erro, setErro] = useState("");
  const [horas, setHoras] = useState(24);
  const [auto, setAuto] = useState(true);

  const load = useCallback(() => {
    api.get<Servidor>(`/api/root/servidor/?horas=${horas}`).then((x) => { setD(x); setErro(""); }).catch((e) => setErro(e.message));
  }, [horas]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!auto) return;
    const id = window.setInterval(load, 30000);
    return () => window.clearInterval(id);
  }, [auto, load]);

  const serie = (campo: keyof Servidor["amostras"][number], nome: string, cor: string) => ({
    name: nome, type: "line" as const, showSymbol: false, smooth: 0.2, lineStyle: { width: 2, color: cor }, itemStyle: { color: cor },
    areaStyle: { color: areaWash(cor) }, data: (d?.amostras ?? []).map((a) => [a.at, a[campo] as number | null]),
  });
  const optPct = useMemo(() => ({
    grid: { left: 4, right: 12, top: 30, bottom: 4, containLabel: true },
    legend: { top: 0, left: 0 },
    tooltip: { trigger: "axis" as const, valueFormatter: (v: any) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(1)}%`) },
    xAxis: { type: "time" as const },
    yAxis: { type: "value" as const, min: 0, max: 100, axisLabel: { formatter: "{value}%" } },
    series: [serie("cpu_pct", "CPU", t.series[0]), serie("mem_pct", "Memória", t.series[1]), serie("disco_pct", "Disco", t.series[2])],
  }), [d, t]);
  const optLoad = useMemo(() => ({
    grid: { left: 4, right: 12, top: 30, bottom: 4, containLabel: true },
    legend: { top: 0, left: 0 },
    tooltip: { trigger: "axis" as const },
    xAxis: { type: "time" as const },
    yAxis: { type: "value" as const, min: 0 },
    series: [serie("load_m1", "Load (1 min)", t.series[3]), serie("db_conexoes", "Conexões no banco", t.series[4])],
  }), [d, t]);
  const optDb = useMemo(() => ({
    grid: { left: 4, right: 12, top: 30, bottom: 4, containLabel: true },
    legend: { top: 0, left: 0 },
    tooltip: { trigger: "axis" as const, valueFormatter: (v: any) => bytes(v) },
    xAxis: { type: "time" as const },
    yAxis: { type: "value" as const, min: 0, axisLabel: { formatter: (v: number) => bytes(v) } },
    series: [serie("db_bytes", "Tamanho do banco", t.series[0])],
  }), [d, t]);
  const optTabelas = useMemo(() => {
    const rows = [...(d?.postgres.tabelas ?? [])].slice(0, 15).reverse();
    return {
      grid: { left: 4, right: 70, top: 6, bottom: 4, containLabel: true },
      tooltip: { trigger: "item" as const, formatter: (p: any) => { const r = rows[p.dataIndex]; return `<strong>${bytes(r.tamanho)}</strong><br/>${r.tabela}<br/><span style="color:${t.inkMuted}">${r.linhas.toLocaleString("pt-BR")} linhas</span>`; } },
      xAxis: { type: "value" as const, axisLabel: { formatter: (v: number) => bytes(v) } },
      yAxis: { type: "category" as const, data: rows.map((r) => r.tabela.replace(/^(erp|indicators|strategy|plans|support|accounts|ai)_/, "")), axisLabel: { fontSize: 11, color: t.inkSecondary } },
      series: [{ type: "bar" as const, barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[0], borderRadius: BAR_RADIUS_H }, label: { show: true, position: "right" as const, fontSize: 11, color: t.inkSecondary, formatter: (p: any) => bytes(p.value) }, data: rows.map((r) => r.tamanho) }],
    };
  }, [d, t]);

  if (erro) return <Panel><EmptyState icon="bi-exclamation-triangle" title="Não foi possível ler o servidor" hint={erro} /></Panel>;
  if (!d) return <Panel><Skeleton height={320} /></Panel>;
  const h = d.host;
  const pg = d.postgres;
  const hitRedis = d.redis.ok && (d.redis.hits! + d.redis.misses!) > 0 ? Math.round(100 * d.redis.hits! / (d.redis.hits! + d.redis.misses!)) : null;

  return (
    <div className="d-grid gap-3">
      <div className="filter-bar">
        <span className="small text-muted-2">Leitura em {new Date(d.agora).toLocaleTimeString("pt-BR")} · host com {h.load?.cpus ?? "?"} CPUs · no ar há {dur(h.uptime)}</span>
        <select className="form-select form-select-sm ms-auto" style={{ width: 130 }} value={horas} onChange={(e) => setHoras(Number(e.target.value))}>
          {[6, 24, 72, 168].map((x) => <option key={x} value={x}>últimas {x} h</option>)}
        </select>
        <div className="form-check form-switch small mb-0"><input className="form-check-input" type="checkbox" id="auto" checked={auto} onChange={(e) => setAuto(e.target.checked)} /><label className="form-check-label" htmlFor="auto">atualizar a cada 30 s</label></div>
        <button className="btn btn-sm btn-outline-secondary" onClick={load}><i className="bi bi-arrow-clockwise" /></button>
      </div>

      <div className="row g-3">
        <div className="col-6 col-xl-3"><StatCard icon="bi-cpu" label="CPU agora" value={h.cpu_pct === null ? "—" : `${h.cpu_pct}%`} foot={<Meter pct={h.cpu_pct} status={statusPct(h.cpu_pct)} />} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-memory" label="Memória" value={h.memoria ? `${h.memoria.pct}%` : "—"} foot={h.memoria ? <>{bytes(h.memoria.usado)} de {bytes(h.memoria.total)}{h.memoria.swap_total ? ` · swap ${bytes(h.memoria.swap_usado)}/${bytes(h.memoria.swap_total)}` : ""}<Meter pct={h.memoria.pct} status={statusPct(h.memoria.pct, 80, 92)} /></> : undefined} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-hdd" label="Disco" value={h.disco ? `${h.disco.pct}%` : "—"} foot={h.disco ? <>{bytes(h.disco.usado)} usados · {bytes(h.disco.livre)} livres<Meter pct={h.disco.pct} status={statusPct(h.disco.pct, 75, 90)} /></> : undefined} /></div>
        <div className="col-6 col-xl-3"><StatCard icon="bi-speedometer" label="Load (1 / 5 / 15 min)" value={h.load ? `${h.load.m1} · ${h.load.m5} · ${h.load.m15}` : "—"} foot={h.load ? `${(h.load.m1 / h.load.cpus).toFixed(2)} por CPU` : undefined} /></div>
      </div>

      <div className="row g-3">
        <div className="col-xl-8">
          <Panel title="Uso do host" subtitle="CPU, memória e disco em % (amostra a cada 5 min)"><EChart option={optPct} height={240} /></Panel>
        </div>
        <div className="col-xl-4">
          <Panel title="Carga e conexões" subtitle="Load de 1 min e conexões abertas no Postgres"><EChart option={optLoad} height={240} /></Panel>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-xl-4">
          <Panel title="Banco de dados" subtitle={pg.versao}>
            <div className="d-grid gap-2 small">
              <div className="d-flex justify-content-between"><span>Tamanho do banco</span><strong>{bytes(pg.tamanho)}</strong></div>
              <div className="d-flex justify-content-between"><span>Tabelas + índices</span><strong>{bytes(pg.tamanho_tabelas)}</strong></div>
              <div className="d-flex justify-content-between"><span>Conexões</span><strong>{pg.conexoes} ({pg.conexoes_ativas} ativas) de {pg.max_conexoes}</strong></div>
              <div className="d-flex justify-content-between"><span>Acerto de cache</span><strong className={pg.cache_hit_pct < 95 ? "text-danger" : ""}>{pg.cache_hit_pct}%</strong></div>
            </div>
            <div className="mt-2"><EChart option={optDb} height={160} /></div>
          </Panel>
        </div>
        <div className="col-xl-4">
          <Panel title="Redis (cache e fila)" subtitle={d.redis.ok ? `versão ${d.redis.versao} · no ar há ${dur(d.redis.uptime)}` : "indisponível"}>
            {d.redis.ok ? (
              <div className="d-grid gap-2 small">
                <div className="d-flex justify-content-between"><span>Memória</span><strong>{bytes(d.redis.memoria)} (pico {bytes(d.redis.memoria_pico)})</strong></div>
                <div className="d-flex justify-content-between"><span>Chaves</span><strong>{d.redis.chaves}</strong></div>
                <div className="d-flex justify-content-between"><span>Clientes conectados</span><strong>{d.redis.clientes}</strong></div>
                <div className="d-flex justify-content-between"><span>Acerto do cache</span><strong>{hitRedis === null ? "—" : `${hitRedis}%`}</strong></div>
                {Object.entries(d.redis.filas ?? {}).map(([f, n]) => <div key={f} className="d-flex justify-content-between"><span>Fila {f}</span><strong className={(n ?? 0) > 50 ? "text-danger" : ""}>{n ?? "—"} tarefa(s)</strong></div>)}
              </div>
            ) : <div className="small text-danger">{d.redis.erro}</div>}
          </Panel>
        </div>
        <div className="col-xl-4">
          <Panel title="Celery (tarefas de fundo)" subtitle={d.celery.ok ? `${d.celery.workers?.length ?? 0} worker(s)` : "sem resposta"}>
            {d.celery.ok ? (
              <div className="d-grid gap-2 small">
                <div className="d-flex justify-content-between"><span>Em execução</span><strong>{d.celery.em_execucao}</strong></div>
                <div className="d-flex justify-content-between"><span>Reservadas</span><strong>{d.celery.reservadas}</strong></div>
                {(d.celery.tarefas ?? []).map((tk, i) => <div key={i} className="text-muted-2"><code>{tk.nome}</code> em {tk.worker}</div>)}
                {(d.celery.tarefas ?? []).length === 0 && <div className="text-muted-2">Nenhuma tarefa rodando agora.</div>}
              </div>
            ) : <div className="small text-danger">{d.celery.erro}</div>}
          </Panel>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-xl-7">
          <Panel title="Maiores tabelas" subtitle="Tamanho em disco (dados + índices)">
            <EChart option={optTabelas} height={Math.max(220, Math.min(15, pg.tabelas.length) * 24 + 20)} />
            <div className="table-responsive mt-2">
              <table className="table table-sm mb-0" style={{ fontSize: "0.8rem" }}>
                <thead><tr><th>Tabela</th><th className="num">Linhas</th><th className="num">Mortas</th><th className="num">Tamanho</th><th>Último autovacuum</th></tr></thead>
                <tbody>
                  {pg.tabelas.map((r) => (
                    <tr key={r.tabela}>
                      <td><code>{r.tabela}</code></td>
                      <td className="num">{r.linhas.toLocaleString("pt-BR")}</td>
                      <td className={`num ${r.linhas && r.mortas > r.linhas * 0.2 ? "text-danger" : "text-muted-2"}`}>{r.mortas.toLocaleString("pt-BR")}</td>
                      <td className="num">{bytes(r.tamanho)}</td>
                      <td className="text-muted-2">{r.autovacuum ? new Date(r.autovacuum).toLocaleString("pt-BR") : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
        <div className="col-xl-5">
          <Panel title="Aplicação" subtitle="O que a plataforma carrega hoje">
            <div className="row g-2">
              {[
                ["Empresas ativas", d.aplicacao.empresas], ["Usuários ativos", d.aplicacao.usuarios], ["Indicadores ativos", d.aplicacao.indicadores],
                ["Valores de indicador", d.aplicacao.valores.toLocaleString("pt-BR")], ["Linhas no espelho do ERP", d.aplicacao.linhas_espelho.toLocaleString("pt-BR")],
                ["Agentes online", `${d.aplicacao.agentes_online} de ${d.aplicacao.conectores}`], ["Chamados abertos", d.aplicacao.chamados_abertos],
              ].map(([l, v]) => (
                <div className="col-6" key={l as string}><div className="p-2 rounded" style={{ background: "var(--surface-sunken)" }}><div className="small text-muted-2">{l}</div><div className="fw-semibold">{v}</div></div></div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
