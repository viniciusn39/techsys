import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Panel, Skeleton, StatusPill } from "./ui";
import { fmtNumber, fmtPct, fmtPeriod } from "../utils/format";

interface Entidade { entity: string; label: string; ultima_carga: string | null; linhas: number; cobertura_desde: string | null }
interface Contexto {
  sobre: { descricao: string; como_calcula: string; por_que_importa: string; regra_tecnica: string; origem_inteligencia: string; exige_sistema: string };
  fonte: { tipo: "erp" | "manual"; metrica: string; descricao_metrica: string; fotografia: boolean; entidades: Entidade[]; filtros: Record<string, any>; agente_online: boolean | null };
  meta: { origem: "erp" | "manual" | "sem_meta"; fonte_erp: string; meses_com_meta: number; limiar_amarelo_pct: string; polaridade: string; agregacao: string; frequencia: string; unidade: string; decimais: number; meta_proporcional: boolean };
  estrategia: { objetivo: { id: number; name: string; perspectiva: string; mapa: string } | null; metas_desdobradas: { id: number; name: string; level: string; org_unit: string }[]; org_unit: string; owner: string; desvios_abertos: number; planos: number };
  historico: {
    meses_fechados: number; media: string | null;
    melhor: { period: string; value: string } | null; pior: { period: string; value: string } | null;
    tendencia_3m_pct: string | null; ano_anterior: { period: string; value: string; variacao_pct: string } | null;
    meses_meta_atingida: number; meses_com_meta: number;
    ultimo_fechado: { period: string; value: string; status: string } | null; dias_medidos_mes: number | null;
  };
}

const AGG: Record<string, string> = { soma: "soma dos meses", media: "média dos meses", ultimo: "último valor" };
const rel = (iso: string | null) => {
  if (!iso) return "nunca";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 60) return `há ${min} min`;
  if (min < 48 * 60) return `há ${Math.round(min / 60)} h`;
  return `há ${Math.round(min / 1440)} d`;
};
const mes = (iso: string | null | undefined) => (iso ? fmtPeriod(iso) : "—");

function Bloco({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return (
    <div className="col-lg-6 col-xxl-3">
      <div className="h-100 p-3 rounded" style={{ background: "var(--surface-sunken)", border: "1px solid var(--border)" }}>
        <div className="fw-semibold small mb-2"><i className={`bi ${icon} me-1`} />{title}</div>
        <div className="small d-grid gap-1">{children}</div>
      </div>
    </div>
  );
}

/** Ficha do indicador: o que é, de onde vem o dado, como a meta funciona, onde entra na estratégia e o resumo do histórico. */
export function SobreIndicador({ indicatorId, unit, decimals, polarity }: { indicatorId: number | string; unit: string; decimals: number; polarity: string }) {
  const [c, setC] = useState<Contexto | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    setC(null);
    api.get<Contexto>(`/api/indicators/${indicatorId}/contexto/`).then(setC).catch(() => setErro(true));
  }, [indicatorId]);

  if (erro) return null;
  if (!c) return <Panel><Skeleton height={140} /></Panel>;

  const h = c.historico;
  const fmt = (v: string | null | undefined) => (v === null || v === undefined ? "—" : `${fmtNumber(v, decimals)} ${unit}`);
  const tend = h.tendencia_3m_pct !== null ? Number(h.tendencia_3m_pct) : null;
  const tendBoa = tend !== null && ((polarity === "menor_melhor" && tend < 0) || (polarity !== "menor_melhor" && tend > 0));

  return (
    <Panel title="Sobre este indicador" subtitle={c.sobre.descricao || undefined}>
      <div className="row g-3">
        <Bloco icon="bi-book" title="O que mede e por que importa">
          {c.sobre.como_calcula ? <div><strong>Como é calculado:</strong> {c.sobre.como_calcula}</div> : <div className="text-muted-2">Sem descrição do cálculo.</div>}
          {c.sobre.por_que_importa && <div><strong>Por que importa:</strong> {c.sobre.por_que_importa}</div>}
          {c.sobre.exige_sistema && <div className="text-warning-emphasis"><i className="bi bi-exclamation-circle me-1" />Exige: {c.sobre.exige_sistema}</div>}
          {c.sobre.regra_tecnica && (
            <details className="mt-1">
              <summary className="text-muted-2" style={{ cursor: "pointer" }}>Regra técnica (root)</summary>
              <div className="text-muted-2 mt-1">{c.sobre.regra_tecnica}</div>
            </details>
          )}
        </Bloco>

        <Bloco icon="bi-database" title="De onde vem o dado">
          {c.fonte.tipo === "erp" ? (
            <>
              <div><strong>Calculado do ERP</strong> · métrica <em>{c.fonte.metrica}</em>{c.fonte.fotografia ? " · fotografia (saldo de hoje)" : ""}</div>
              {c.fonte.agente_online !== null && (
                <div>Agente {c.fonte.agente_online ? <span className="text-success">online</span> : <span className="text-danger">offline</span>} · recalculado a cada 30 min{h.dias_medidos_mes ? ` · mês corrente medido até o dia ${h.dias_medidos_mes}` : ""}</div>
              )}
              {c.fonte.entidades.map((e) => (
                <div key={e.entity} className="d-flex justify-content-between gap-2">
                  <span>{e.label}</span>
                  <span className="text-muted-2 text-end">{e.linhas.toLocaleString("pt-BR")} linhas · carga {rel(e.ultima_carga)}{e.cobertura_desde ? ` · desde ${mes(e.cobertura_desde)}` : ""}</span>
                </div>
              ))}
              {c.fonte.filtros.filiais?.length > 0 && (
                <div><strong>Filiais:</strong> {c.fonte.filtros.filiais.map((f: any) => `${f.code}${f.name ? ` · ${f.name}` : ""}`).join(", ")}</div>
              )}
              {c.fonte.filtros.sales_rep && <div><strong>Vendedores:</strong> {String(c.fonte.filtros.sales_rep)}</div>}
            </>
          ) : (
            <div>Lançamento <strong>manual</strong>, mensal. Quem lança é o responsável pelo indicador.</div>
          )}
        </Bloco>

        <Bloco icon="bi-bullseye" title="Meta e farol">
          <div>
            <strong>Meta:</strong>{" "}
            {c.meta.origem === "erp" ? <>puxada do ERP ({c.meta.fonte_erp}), sincronizada a cada 6 h</> : c.meta.origem === "manual" ? <>cadastrada na plataforma ({c.meta.meses_com_meta} meses no ano)</> : <span className="text-muted-2">sem meta no ano</span>}
          </div>
          <div><strong>Farol:</strong> verde ≥ 100 % da meta · amarelo ≥ {fmtNumber(c.meta.limiar_amarelo_pct, 0)} % · vermelho abaixo</div>
          <div><strong>Regra:</strong> {c.meta.polaridade === "menor_melhor" ? "menor é melhor" : "maior é melhor"} · acumulado por {AGG[c.meta.agregacao] ?? c.meta.agregacao} · {c.meta.frequencia}</div>
          {c.meta.meta_proporcional && <div className="text-muted-2">No mês em curso a meta é proporcional aos dias já medidos.</div>}
        </Bloco>

        <Bloco icon="bi-diagram-3" title="Na estratégia">
          {c.estrategia.objetivo ? (
            <div><strong>Objetivo:</strong> <Link to="/mapa-estrategico">{c.estrategia.objetivo.name}</Link> <span className="text-muted-2">· {c.estrategia.objetivo.perspectiva}</span></div>
          ) : <div className="text-muted-2">Sem objetivo no mapa estratégico.</div>}
          {c.estrategia.metas_desdobradas.length > 0 && (
            <div><strong>Metas desdobradas:</strong> {c.estrategia.metas_desdobradas.map((g) => `${g.name}${g.org_unit ? ` (${g.org_unit})` : ""}`).join("; ")}</div>
          )}
          <div>{c.estrategia.org_unit && <><strong>Área:</strong> {c.estrategia.org_unit} · </>}<strong>Responsável:</strong> {c.estrategia.owner || <span className="text-muted-2">não definido</span>}</div>
          <div>
            <Link to="/desvios">{c.estrategia.desvios_abertos} desvio(s) aberto(s)</Link> · <Link to="/planos-acao">{c.estrategia.planos} plano(s) de ação</Link>
          </div>
        </Bloco>

        <div className="col-12">
          <div className="p-3 rounded" style={{ background: "var(--surface-sunken)", border: "1px solid var(--border)" }}>
            <div className="fw-semibold small mb-2"><i className="bi bi-clock-history me-1" />Últimos 12 meses fechados ({h.meses_fechados})</div>
            {h.meses_fechados === 0 ? (
              <div className="small text-muted-2">Ainda não há mês fechado com valor.</div>
            ) : (
              <div className="row g-3 small">
                <div className="col-6 col-md-4 col-xl-2"><div className="text-muted-2">Média mensal</div><div className="fw-semibold">{fmt(h.media)}</div></div>
                <div className="col-6 col-md-4 col-xl-2"><div className="text-muted-2">Melhor mês</div><div className="fw-semibold">{fmt(h.melhor?.value)}</div><div className="text-muted-2">{mes(h.melhor?.period)}</div></div>
                <div className="col-6 col-md-4 col-xl-2"><div className="text-muted-2">Pior mês</div><div className="fw-semibold">{fmt(h.pior?.value)}</div><div className="text-muted-2">{mes(h.pior?.period)}</div></div>
                <div className="col-6 col-md-4 col-xl-2">
                  <div className="text-muted-2">Tendência (3 m × 3 m anteriores)</div>
                  <div className={`fw-semibold ${tend === null ? "" : tendBoa ? "text-success" : "text-danger"}`}>{tend === null ? "—" : `${tend > 0 ? "+" : ""}${fmtNumber(tend, 1)}%`}</div>
                </div>
                <div className="col-6 col-md-4 col-xl-2">
                  <div className="text-muted-2">Mesmo mês do ano anterior</div>
                  <div className="fw-semibold">{h.ano_anterior ? fmt(h.ano_anterior.value) : "—"}</div>
                  {h.ano_anterior && <div className="text-muted-2">{mes(h.ano_anterior.period)} · {Number(h.ano_anterior.variacao_pct) > 0 ? "+" : ""}{fmtNumber(h.ano_anterior.variacao_pct, 1)}%</div>}
                </div>
                <div className="col-6 col-md-4 col-xl-2">
                  <div className="text-muted-2">Meses com meta atingida</div>
                  <div className="fw-semibold">{h.meses_com_meta ? `${h.meses_meta_atingida} de ${h.meses_com_meta}` : "—"}</div>
                  {h.ultimo_fechado && <div className="d-flex align-items-center gap-1 text-muted-2">{mes(h.ultimo_fechado.period)} <StatusPill status={h.ultimo_fechado.status} compact /></div>}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}
