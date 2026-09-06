import { useEffect, useMemo, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Skeleton } from "./ui";

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
  meta_do_erp: boolean;
  status: "pronto" | "planejado";
  tags: string[];
  plugado: boolean;
  dados_ok: boolean;
}

interface Catalogo {
  erp: string;
  setores: { key: string; label: string }[];
  itens: Item[];
}

const ERP_LABEL: Record<string, string> = { winthor: "WinThor" };
const PERSP: Record<string, string> = { financeira: "Financeira", clientes: "Clientes", processos: "Processos", aprendizado: "Aprendizado" };

/** Catálogo de KPIs do ERP: escolhe por setor e pluga com um clique. */
export function CatalogoKpi({ show, onHide, onPlugged }: { show: boolean; onHide: () => void; onPlugged: (n: number) => void }) {
  const [data, setData] = useState<Catalogo | null>(null);
  const [setor, setSetor] = useState<string>("diretoria");
  const [busca, setBusca] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [aberto, setAberto] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!show) return;
    setData(null);
    setSel(new Set());
    setErro("");
    api.get<Catalogo>("/api/erp/kpi-catalogo/").then(setData).catch((e) => setErro(e.message));
  }, [show]);

  const contagem = useMemo(() => {
    const c: Record<string, { total: number; plugados: number }> = {};
    for (const i of data?.itens ?? []) {
      const chaves = [i.sector, ...(i.tags.includes("diretoria") ? ["diretoria"] : [])];
      for (const k of chaves) {
        c[k] = c[k] ?? { total: 0, plugados: 0 };
        c[k].total += 1;
        c[k].plugados += i.plugado ? 1 : 0;
      }
    }
    return c;
  }, [data]);

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (data?.itens ?? []).filter((i) => {
      if (setor === "diretoria" ? !i.tags.includes("diretoria") : i.sector !== setor) return false;
      if (q && !`${i.code} ${i.name} ${i.description} ${i.explanation} ${i.importance}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [data, setor, busca]);

  const plugaveis = visiveis.filter((i) => !i.plugado && i.status === "pronto");
  const toggle = (code: string) => {
    const s = new Set(sel);
    if (s.has(code)) s.delete(code); else s.add(code);
    setSel(s);
  };
  const marcarTodos = () => setSel(new Set([...sel, ...plugaveis.map((i) => i.code)]));

  const plugar = async (codes: string[]) => {
    if (codes.length === 0) return;
    setBusy(true);
    setErro("");
    try {
      const r = await api.post<{ created: any[]; skipped: string[] }>("/api/erp/kpi-catalogo/", { codes });
      onPlugged(r.created.length);
      const atualizado = await api.get<Catalogo>("/api/erp/kpi-catalogo/");
      setData(atualizado);
      setSel(new Set());
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setBusy(false);
    }
  };

  const setores = [{ key: "diretoria", label: "Resumo executivo" }, ...(data?.setores ?? []).filter((s) => s.key !== "diretoria")];

  return (
    <Modal show={show} onHide={onHide} size="xl" centered scrollable>
      <Modal.Header closeButton>
        <Modal.Title className="fs-6">
          <i className="bi bi-plug me-2" />Catálogo de KPIs do {ERP_LABEL[data?.erp ?? "winthor"] ?? data?.erp}
          {data && <span className="text-muted-2 fw-normal ms-2 small">{data.itens.length} indicadores · {data.itens.filter((i) => i.plugado).length} já plugados</span>}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {erro && <div className="alert alert-danger py-2 small">{erro}</div>}
        {!data ? (
          <Skeleton height={320} />
        ) : (
          <div className="row g-3">
            <div className="col-md-3">
              <div className="list-group list-group-flush">
                {setores.map((s) => {
                  const c = contagem[s.key] ?? { total: 0, plugados: 0 };
                  return (
                    <button key={s.key} className={`list-group-item list-group-item-action d-flex justify-content-between align-items-center px-2 ${setor === s.key ? "active" : ""}`} onClick={() => setSetor(s.key)}>
                      <span>{s.label}</span>
                      <span className={`badge ${setor === s.key ? "text-bg-light" : "text-bg-secondary"}`}>{c.plugados}/{c.total}</span>
                    </button>
                  );
                })}
              </div>
              <div className="small text-muted-2 mt-3">
                <div><span className="badge text-bg-success me-1">pronto</span>calculado do espelho do ERP, hoje.</div>
                <div className="mt-1"><span className="badge text-bg-light border me-1">planejado</span>em breve: depende de dados que o agente ainda não coleta.</div>
                <div className="mt-1"><span className="badge text-bg-warning me-1">sem dados</span>os dados deste indicador ainda não chegaram do ERP.</div>
              </div>
            </div>
            <div className="col-md-9">
              <div className="d-flex flex-wrap gap-2 align-items-center mb-2">
                <Form.Control size="sm" style={{ maxWidth: 280 }} placeholder="Buscar por nome ou assunto" value={busca} onChange={(e) => setBusca(e.target.value)} />
                <Button size="sm" variant="outline-secondary" onClick={marcarTodos} disabled={plugaveis.length === 0}>
                  Marcar todos os prontos ({plugaveis.length})
                </Button>
                <Button size="sm" className="ms-auto" onClick={() => plugar([...sel])} disabled={busy || sel.size === 0}>
                  <i className="bi bi-plug-fill me-1" />Plugar selecionados ({sel.size})
                </Button>
              </div>
              {visiveis.length === 0 ? (
                <EmptyState icon="bi-search" title="Nada aqui" hint="Ajuste a busca ou escolha outro setor." />
              ) : (
                <div className="table-responsive" style={{ maxHeight: "60vh" }}>
                  <table className="table table-sm align-middle mb-0">
                    <thead className="sticky-top" style={{ background: "var(--surface)" }}>
                      <tr><th style={{ width: 28 }}></th><th>Indicador</th><th>Perspectiva</th><th>Unid.</th><th>Situação</th><th style={{ width: 90 }}></th></tr>
                    </thead>
                    <tbody>
                      {visiveis.map((i) => {
                        const podePlugar = !i.plugado && i.status === "pronto";
                        return (
                          <>
                            <tr key={i.code} className={i.plugado ? "text-muted-2" : ""}>
                              <td>
                                <Form.Check type="checkbox" checked={sel.has(i.code)} disabled={!podePlugar} onChange={() => toggle(i.code)} />
                              </td>
                              <td>
                                <button className="btn btn-link p-0 text-decoration-none text-start" onClick={() => setAberto(aberto === i.code ? null : i.code)}>
                                  <span className="fw-semibold">{i.code}</span> <span className={i.plugado ? "" : "text-body"}>· {i.name}</span>
                                  <i className={`bi ms-1 small ${aberto === i.code ? "bi-chevron-up" : "bi-chevron-down"}`} />
                                </button>
                                <div className="small text-muted-2">{i.description}</div>
                              </td>
                              <td className="small">{PERSP[i.perspective] ?? i.perspective}</td>
                              <td className="small">{i.unit} · {i.polarity === "menor_melhor" ? "↓" : "↑"}</td>
                              <td>
                                {i.plugado ? (
                                  <span className="badge text-bg-primary"><i className="bi bi-check2 me-1" />plugado</span>
                                ) : i.status === "planejado" ? (
                                  <span className="badge text-bg-light border" title="Em breve: depende de dados que o agente ainda não coleta">planejado</span>
                                ) : i.dados_ok ? (
                                  <span className="badge text-bg-success">pronto</span>
                                ) : (
                                  <span className="badge text-bg-warning" title="Os dados deste indicador ainda não chegaram do ERP">sem dados</span>
                                )}
                              </td>
                              <td className="text-end">
                                {podePlugar && (
                                  <Button size="sm" variant="outline-primary" disabled={busy} onClick={() => plugar([i.code])}>
                                    <i className="bi bi-plug me-1" />Plugar
                                  </Button>
                                )}
                              </td>
                            </tr>
                            {aberto === i.code && (
                              <tr key={`${i.code}-det`}>
                                <td></td>
                                <td colSpan={5} className="small">
                                  <div className="p-2 rounded" style={{ background: "var(--surface-sunken)", border: "1px solid var(--border)" }}>
                                    {i.explanation && <div><i className="bi bi-calculator me-1 text-muted-2" /><strong>Como é calculado:</strong> {i.explanation}</div>}
                                    {i.importance && <div className="mt-1"><i className="bi bi-lightbulb me-1 text-muted-2" /><strong>Por que importa:</strong> {i.importance}</div>}
                                    <div className="mt-1 text-muted-2">
                                      <i className="bi bi-arrow-repeat me-1" />
                                      {i.status === "pronto" ? "Atualizado automaticamente a partir do ERP a cada 30 minutos." : "Disponível em breve, quando o agente passar a coletar os dados necessários."}
                                      {i.meta_do_erp && " A meta vem do próprio ERP quando estiver cadastrada lá."}
                                      {" "}{i.polarity === "menor_melhor" ? "Quanto menor, melhor." : "Quanto maior, melhor."}
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </Modal.Body>
      <Modal.Footer>
        <span className="small text-muted-2 me-auto">Ao plugar, o indicador nasce ligado ao espelho do ERP: valor calculado a cada 30 min e, quando houver, meta puxada do WinThor. Você ajusta filial, área e objetivo depois, em Indicadores.</span>
        <Button variant="outline-secondary" onClick={onHide}>Fechar</Button>
      </Modal.Footer>
    </Modal>
  );
}
