import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { Panel, Skeleton } from "../components/ui";

interface Item { id: number; block: string; text: string; order: number }

const BLOCOS: { key: string; label: string; icon: string; color: string; area: string }[] = [
  { key: "parcerias", label: "Parcerias principais", icon: "bi-people", color: "#3b5bdb", area: "parcerias" },
  { key: "atividades", label: "Atividades principais", icon: "bi-activity", color: "#4c6ef5", area: "atividades" },
  { key: "recursos", label: "Recursos principais", icon: "bi-box-seam", color: "#4c6ef5", area: "recursos" },
  { key: "proposta", label: "Proposta de valor", icon: "bi-gift", color: "#e64980", area: "proposta" },
  { key: "relacionamento", label: "Relacionamento com clientes", icon: "bi-heart", color: "#12b886", area: "relacionamento" },
  { key: "canais", label: "Canais", icon: "bi-truck", color: "#12b886", area: "canais" },
  { key: "segmentos", label: "Segmentos de clientes", icon: "bi-person-badge", color: "#0b7285", area: "segmentos" },
  { key: "custos", label: "Estrutura de custos", icon: "bi-cash-stack", color: "#f59f00", area: "custos" },
  { key: "receitas", label: "Fontes de receita", icon: "bi-currency-dollar", color: "#f59f00", area: "receitas" },
];

const GRID: React.CSSProperties = {
  display: "grid",
  gap: 12,
  gridTemplateColumns: "repeat(10, 1fr)",
  gridTemplateAreas: `
    "parcerias parcerias atividades atividades proposta proposta relacionamento relacionamento segmentos segmentos"
    "parcerias parcerias recursos recursos proposta proposta canais canais segmentos segmentos"
    "custos custos custos custos custos receitas receitas receitas receitas receitas"`,
};

/** Business Model Canvas do mapa ativo: nove blocos com post-its editáveis. */
export function Canvas() {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [novo, setNovo] = useState<{ block: string; text: string } | null>(null);
  const [editando, setEditando] = useState<{ id: number; text: string } | null>(null);

  const load = useCallback(() => {
    api.get<Item[]>("/api/canvas/").then(setItens).catch(() => setItens([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const porBloco = useMemo(() => {
    const m: Record<string, Item[]> = {};
    (itens ?? []).forEach((i) => { (m[i.block] = m[i.block] ?? []).push(i); });
    return m;
  }, [itens]);

  const adicionar = async () => {
    if (!novo?.text.trim()) { setNovo(null); return; }
    await api.post("/api/canvas/", { block: novo.block, text: novo.text.trim() });
    setNovo(null);
    load();
  };
  const salvarEdicao = async () => {
    if (!editando) return;
    if (editando.text.trim()) await api.patch(`/api/canvas/${editando.id}/`, { text: editando.text.trim() });
    else await api.del(`/api/canvas/${editando.id}/`);
    setEditando(null);
    load();
  };

  if (itens === null) return <Panel><Skeleton height={400} /></Panel>;

  return (
    <Panel
      title="Business Model Canvas"
      subtitle="Como a empresa cria, entrega e captura valor. Clique em + para adicionar um post-it; clique no post-it para editar (vazio apaga)."
      actions={<button className="btn btn-sm btn-outline-secondary no-print" onClick={() => window.print()}><i className="bi bi-printer me-1" />Imprimir</button>}
    >
      <div style={GRID} className="canvas-grid">
        {BLOCOS.map((b) => (
          <div key={b.key} style={{ gridArea: b.area, border: "1px solid var(--border)", borderRadius: 10, minHeight: 170, display: "flex", flexDirection: "column" }}>
            <div className="d-flex align-items-center gap-2 px-2 py-2 text-white" style={{ background: b.color, borderRadius: "10px 10px 0 0", fontSize: "0.78rem", fontWeight: 600, letterSpacing: 0.3 }}>
              <i className={`bi ${b.icon}`} />{b.label.toUpperCase()}
              <button className="btn btn-sm btn-link text-white p-0 ms-auto no-print" title="Adicionar" onClick={() => setNovo({ block: b.key, text: "" })}><i className="bi bi-plus-lg" /></button>
            </div>
            <div className="p-2 d-grid gap-2 align-content-start flex-grow-1">
              {(porBloco[b.key] ?? []).map((i) => (
                editando?.id === i.id ? (
                  <textarea key={i.id} autoFocus className="form-control form-control-sm" rows={2} value={editando.text}
                    onChange={(e) => setEditando({ id: i.id, text: e.target.value })}
                    onBlur={salvarEdicao}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); salvarEdicao(); } if (e.key === "Escape") setEditando(null); }} />
                ) : (
                  <div key={i.id} className="small p-2 rounded" style={{ background: "var(--surface-sunken)", borderLeft: `3px solid ${b.color}`, cursor: "text" }} onClick={() => setEditando({ id: i.id, text: i.text })}>
                    {i.text}
                  </div>
                )
              ))}
              {novo?.block === b.key && (
                <textarea autoFocus className="form-control form-control-sm" rows={2} placeholder="Escreva e pressione Enter" value={novo.text}
                  onChange={(e) => setNovo({ block: b.key, text: e.target.value })}
                  onBlur={adicionar}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); adicionar(); } if (e.key === "Escape") setNovo(null); }} />
              )}
              {(porBloco[b.key] ?? []).length === 0 && novo?.block !== b.key && (
                <div className="small text-muted-2 text-center py-3 no-print" role="button" onClick={() => setNovo({ block: b.key, text: "" })}>Clique em + para adicionar</div>
              )}
            </div>
          </div>
        ))}
      </div>
      <style>{`@media (max-width: 992px) { .canvas-grid { grid-template-columns: 1fr 1fr !important; grid-template-areas:
        "parcerias atividades" "recursos proposta" "relacionamento canais" "segmentos custos" "receitas receitas" !important; } }`}</style>
    </Panel>
  );
}
