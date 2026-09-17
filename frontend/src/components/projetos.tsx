// Tipos e peças comuns às telas de Projetos (lista, detalhe e painel).
import { vizTokens } from "../charts/theme";
import { useTheme } from "../hooks/useTheme";

export interface Projeto {
  id: number; code: number; map: number | null; map_name: string; title: string; description: string;
  owner: number | null; owner_name: string; org_unit: number | null; org_unit_name: string;
  start_date: string; end_date: string; status: string;
  partners: number[]; swot_items: number[]; objectives: number[];
  activities_count: number; subactivities_count: number; done_count: number; late_count: number; progress: number;
}

export interface Atividade {
  id: number; project: number; parent: number | null; title: string; description: string;
  responsible: number | null; responsible_name: string; phase: string; phase_label: string;
  start_date: string | null; end_date: string | null; status: string; progress_pct: number; notes: string; order: number;
  wbs: string; depth: number; has_children: boolean; progress: number; late: boolean; fcas_count: number;
}

export interface Fca {
  id: number; activity: number; activity_title: string; fact: string; cause: string; action: string;
  due_date: string | null; responsible: number | null; responsible_name: string; status: string; alert: "" | "atrasado" | "vence_logo";
}

export interface Usuario { id: number; first_name: string; last_name?: string; email: string }

export const nomeUsuario = (u: Usuario) => [u.first_name, u.last_name].filter(Boolean).join(" ") || u.email;

export const ANDAMENTO: Record<string, { label: string; cls: string; icon: string }> = {
  nao_iniciado: { label: "Não iniciado", cls: "st-neutro", icon: "bi-circle" },
  em_andamento: { label: "Em andamento", cls: "st-amarelo", icon: "bi-play-circle" },
  finalizado: { label: "Finalizado", cls: "st-verde", icon: "bi-check-circle" },
  pausado: { label: "Pausado", cls: "st-neutro", icon: "bi-pause-circle" },
  cancelado: { label: "Cancelado", cls: "st-neutro", icon: "bi-x-circle" },
};

export const FASES: [string, string][] = [
  ["iniciacao", "Iniciação"], ["planejamento", "Planejamento"], ["execucao", "Execução"],
  ["monitoramento", "Monitoramento"], ["encerramento", "Encerramento"],
];

export const FCA_STATUS: Record<string, { label: string; cls: string }> = {
  em_andamento: { label: "Em andamento", cls: "st-amarelo" },
  concluido: { label: "Concluído", cls: "st-verde" },
  cancelado: { label: "Cancelado", cls: "st-neutro" },
};

export function AndamentoPill({ status }: { status: string }) {
  const m = ANDAMENTO[status] ?? ANDAMENTO.nao_iniciado;
  return <span className={`status-pill ${m.cls}`}><i className={`bi ${m.icon}`} aria-hidden="true" />{m.label}</span>;
}

/** Cor do avanço pelo que ele significa: concluído, atrasado ou em dia — nunca só pelo número. */
export function corAvanco(t: ReturnType<typeof vizTokens>, progress: number, late: boolean) {
  if (progress >= 100) return t.status.verde;
  if (late) return t.status.vermelho;
  return t.series[0];
}

export function Avanco({ progress, late = false, width = 120 }: { progress: number; late?: boolean; width?: number }) {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  return (
    <div className="d-flex align-items-center gap-2" title={late ? "Atrasada" : progress >= 100 ? "Concluída" : "Em dia"}>
      <div className="meter" style={{ width }}><span style={{ width: `${Math.max(0, Math.min(100, progress))}%`, background: corAvanco(t, progress, late) }} /></div>
      <span className="small num" style={{ minWidth: 38 }}>{progress}%</span>
      {late && <i className="bi bi-exclamation-triangle" style={{ color: t.status.vermelho }} aria-label="Atrasada" />}
    </div>
  );
}

export function LegendaAvanco() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const itens = [
    { cor: t.series[0], icon: "bi-arrow-right-circle", label: "Em dia" },
    { cor: t.status.vermelho, icon: "bi-exclamation-triangle", label: "Atrasada (prazo vencido e abaixo de 100%)" },
    { cor: t.status.verde, icon: "bi-check-circle", label: "Concluída" },
  ];
  return (
    <div className="d-flex flex-wrap gap-3 small text-muted-2">
      {itens.map((i) => <span key={i.label}><i className={`bi ${i.icon} me-1`} style={{ color: i.cor }} aria-hidden="true" />{i.label}</span>)}
    </div>
  );
}
