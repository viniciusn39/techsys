import { useEffect, useMemo, useState } from "react";
import { Form } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton } from "../components/ui";

interface Consulta {
  entity: string;
  label: string;
  sql: string;
  incremental: boolean;
  since_column: string | null;
  backfill_meses: number | null;
  every_minutes: number | null;
  fields: Record<string, string>;
}

interface Item {
  code: string;
  name: string;
  sector: string;
  sector_label: string;
  perspective: string;
  unit: string;
  decimals: number;
  polarity: string;
  aggregation: string;
  description: string;
  explanation: string;
  importance: string;
  rule: string;
  origin: string;
  origin_label: string;
  requires_system: string;
  status: "pronto" | "planejado";
  requer: string[];
  tags: string[];
  default_filters: Record<string, any>;
  erp_metric: string;
  metric_label: string;
  entities: string[];
  formula: string;
  erp_target: string;
  target_label: string;
  target_formula: string;
  target_entities: string[];
}

interface Tecnico {
  erp: string;
  setores: { key: string; label: string }[];
  consultas: Record<string, Consulta>;
  bases: Record<string, string>;
  itens: Item[];
}

const pre: React.CSSProperties = {
  background: "var(--surface-sunken)", border: "1px solid var(--border)", borderRadius: 8,
  padding: "10px 12px", fontSize: "0.76rem", whiteSpace: "pre-wrap", wordBreak: "break-word",
  maxHeight: 360, overflow: "auto", marginBottom: 0,
};

/** Root: o catálogo com o SQL executado no WinThor e a fórmula sobre o espelho. */
export function CatalogoTecnico() {
  const [data, setData] = useState<Tecnico | null>(null);
  const [erro, setErro] = useState("");
  const [setor, setSetor] = useState("");
  const [busca, setBusca] = useState("");
  const [aberto, setAberto] = useState<string | null>(null);
  const [verBases, setVerBases] = useState(false);
  const [verPlano, setVerPlano] = useState<string | null>(null);

  useEffect(() => {
    api.get<Tecnico>("/api/erp/kpi-catalogo/tecnico/").then(setData).catch((e) => setErro(e.message));
  }, []);

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (data?.itens ?? []).filter((i) => {
      if (setor && i.sector !== setor) return false;
      if (q && !`${i.code} ${i.name} ${i.rule} ${i.erp_metric} ${i.entities.join(" ")} ${i.origin_label} ${i.requires_system}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [data, setor, busca]);

  if (erro) return <Panel><EmptyState icon="bi-exclamation-triangle" title="Não foi possível carregar" hint={erro} /></Panel>;
  if (!data) return <Panel><Skeleton height={320} /></Panel>;

  return (
    <div className="d-grid gap-3">
      <Panel
        title={`Catálogo técnico · ${data.erp === "winthor" ? "WinThor" : data.erp}`}
        subtitle={`${data.itens.length} KPIs · ${Object.keys(data.consultas).length} consultas no plano de coleta. Cada KPI mostra a regra, o SQL que o agente roda no Oracle do cliente e a fórmula aplicada ao espelho.`}
        actions={
          <div className="d-flex gap-2">
            <button className="btn btn-sm btn-outline-secondary" onClick={() => setVerBases(!verBases)}>
              <i className="bi bi-braces me-1" />Bases comuns das fórmulas
            </button>
          </div>
        }
      >
        <div className="d-flex flex-wrap gap-2 align-items-center">
          <Form.Select size="sm" style={{ width: 200 }} value={setor} onChange={(e) => setSetor(e.target.value)}>
            <option value="">Todos os setores</option>
            {data.setores.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </Form.Select>
          <Form.Control size="sm" style={{ maxWidth: 320 }} placeholder="Buscar por código, nome, tabela, métrica…" value={busca} onChange={(e) => setBusca(e.target.value)} />
          <span className="small text-muted-2 ms-auto">{visiveis.length} exibidos</span>
        </div>

        {verBases && (
          <div className="mt-3">
            <div className="small text-muted-2 mb-2">
              Funções que as fórmulas reutilizam: a régua de nota faturada (CONDVENDA), o filtro de filial, o recorte de itens de venda, títulos, estoque, cargas e compras, e o cálculo do mês corrente até hoje.
            </div>
            <div className="row g-2">
              {Object.entries(data.bases).map(([nome, src]) => (
                <div className="col-lg-6" key={nome}>
                  <div className="fw-semibold small mb-1"><code>{nome}</code></div>
                  <pre style={pre}>{src}</pre>
                </div>
              ))}
            </div>
          </div>
        )}
      </Panel>

      <Panel title="Plano de coleta (o SQL que roda no WinThor)" subtitle="Clique numa entidade para ver a consulta. :since = marca d'água da carga incremental; :janela = meses do histórico gradual.">
        <div className="d-flex flex-wrap gap-1">
          {Object.values(data.consultas).map((c) => (
            <button key={c.entity} className={`btn btn-sm ${verPlano === c.entity ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setVerPlano(verPlano === c.entity ? null : c.entity)}>
              {c.label} <span className="opacity-75">· {c.entity}</span>
            </button>
          ))}
        </div>
        {verPlano && data.consultas[verPlano] && (() => {
          const c = data.consultas[verPlano];
          return (
            <div className="mt-3">
              <div className="small text-muted-2 mb-2">
                {c.incremental ? `incremental por ${c.since_column}` : "recarga cheia"}
                {c.backfill_meses ? ` · histórico gradual até ${c.backfill_meses} meses` : ""}
                {c.every_minutes ? ` · a cada ${c.every_minutes} min` : ""}
              </div>
              <pre style={pre}>{c.sql}</pre>
              <div className="small text-muted-2 mt-2">Mapa coluna do WinThor → campo do espelho: {Object.entries(c.fields).map(([k, v]) => `${v} → ${k}`).join(" · ")}</div>
            </div>
          );
        })()}
      </Panel>

      <Panel title="KPIs">
        <div className="table-responsive">
          <table className="table table-sm align-middle mb-0">
            <thead><tr><th>KPI</th><th>Setor</th><th>Origem da inteligência</th><th>Métrica no espelho</th><th>Lê do WinThor</th><th>Meta</th><th>Situação</th></tr></thead>
            <tbody>
              {visiveis.map((i) => (
                <>
                  <tr key={i.code} style={{ cursor: "pointer" }} onClick={() => setAberto(aberto === i.code ? null : i.code)}>
                    <td>
                      <span className="fw-semibold">{i.code}</span> · {i.name}
                      <i className={`bi ms-1 small ${aberto === i.code ? "bi-chevron-up" : "bi-chevron-down"}`} />
                      <div className="small text-muted-2">{i.description}</div>
                    </td>
                    <td className="small">{i.sector_label}</td>
                    <td className="small">
                      <span className={`badge ${i.origin === "winthor" ? "text-bg-primary" : i.origin === "techsys" ? "text-bg-dark" : "text-bg-info"}`}>{i.origin_label}</span>
                      <div className="text-muted-2" style={{ fontSize: "0.72rem" }}>
                        {i.requires_system ? <><i className="bi bi-exclamation-circle me-1" />só com: {i.requires_system}</> : <><i className="bi bi-check2-circle me-1" />qualquer banco WinThor</>}
                      </div>
                    </td>
                    <td className="small">{i.erp_metric ? <code>{i.erp_metric}</code> : <span className="text-muted-2">—</span>}<div className="text-muted-2" style={{ fontSize: "0.72rem" }}>{i.unit} · {i.aggregation} · {i.polarity === "menor_melhor" ? "menor é melhor" : "maior é melhor"}</div></td>
                    <td className="small">{i.entities.length ? i.entities.map((e) => data.consultas[e]?.label ?? e).join(", ") : <span className="text-muted-2">{i.requer.join(", ") || "—"}</span>}</td>
                    <td className="small">{i.erp_target ? <code>{i.erp_target}</code> : <span className="text-muted-2">manual</span>}</td>
                    <td>{i.status === "pronto" ? <span className="badge text-bg-success">pronto</span> : <span className="badge text-bg-light border">planejado</span>}</td>
                  </tr>
                  {aberto === i.code && (
                    <tr key={`${i.code}-det`}>
                      <td colSpan={7}>
                        <div className="row g-3">
                          <div className="col-12">
                            {i.explanation && <div className="small mb-1"><strong>Como é calculado (texto do cliente):</strong> {i.explanation}</div>}
                            {i.importance && <div className="small mb-2"><strong>Por que importa (texto do cliente):</strong> {i.importance}</div>}
                            <div className="fw-semibold small mb-1"><i className="bi bi-book me-1" />Regra no WinThor</div>
                            <div className="small">{i.rule || "—"}</div>
                            {i.requer.length > 0 && <div className="small text-muted-2 mt-1">Depende de coletar: {i.requer.join(", ")}</div>}
                            {Object.keys(i.default_filters).length > 0 && <div className="small text-muted-2 mt-1">Filtro padrão: {JSON.stringify(i.default_filters)}</div>}
                          </div>
                          {i.formula && (
                            <div className="col-lg-6">
                              <div className="fw-semibold small mb-1"><i className="bi bi-calculator me-1" />Fórmula aplicada ao espelho · <code>{i.erp_metric}</code></div>
                              <pre style={pre}>{i.formula}</pre>
                            </div>
                          )}
                          {i.entities.map((e) => data.consultas[e] && (
                            <div className="col-lg-6" key={e}>
                              <div className="fw-semibold small mb-1"><i className="bi bi-database me-1" />SQL executado no WinThor · {data.consultas[e].label} <span className="text-muted-2">({e})</span></div>
                              <pre style={pre}>{data.consultas[e].sql}</pre>
                            </div>
                          ))}
                          {i.target_formula && (
                            <div className="col-lg-6">
                              <div className="fw-semibold small mb-1"><i className="bi bi-bullseye me-1" />Meta puxada do ERP · {i.target_label} <span className="text-muted-2">(lê {i.target_entities.join(", ")})</span></div>
                              <pre style={pre}>{i.target_formula}</pre>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
