import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export interface MapaOpcao { id: number; name: string; is_active: boolean }

/**
 * Planejamento em uso, escolhido na própria página (mapa, SWOT, canvas, cultura, dashboard, relatório).
 * Só aparece quando a empresa tem mais de um planejamento.
 */
export function SeletorPlanejamento({ mapas }: { mapas: MapaOpcao[] }) {
  const { mapId, selectMap } = useAuth();
  const navigate = useNavigate();
  if (mapas.length < 2) return null;
  const padrao = mapas.find((m) => m.is_active) ?? mapas[0];
  const atual = mapas.find((m) => m.id === mapId) ?? padrao;

  return (
    <div className="d-flex flex-wrap align-items-center gap-2 mb-3 d-print-none">
      <span className="small text-muted-2"><i className="bi bi-journal-richtext me-1" aria-hidden="true" />Planejamento:</span>
      <div className="d-flex flex-wrap gap-1" role="group" aria-label="Planejamento em uso">
        {mapas.map((m) => (
          <button key={m.id} type="button" aria-pressed={m.id === atual.id}
            className={`btn btn-sm ${m.id === atual.id ? "btn-primary" : "btn-outline-secondary"}`}
            onClick={() => selectMap(m.id)}>
            {m.name}{!m.is_active && " (inativo)"}
          </button>
        ))}
      </div>
      <button type="button" className="btn btn-sm btn-link p-0 ms-1" onClick={() => navigate("/planejamentos")}>gerenciar</button>
    </div>
  );
}
