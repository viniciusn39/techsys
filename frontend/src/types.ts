export type Role = "root" | "admin" | "gestor" | "colaborador";
export type Farol = "verde" | "amarelo" | "vermelho" | "sem_meta" | null;

export interface Tenant {
  id: number;
  name: string;
  slug: string;
  cnpj?: string;
  is_active: boolean;
  users_count?: number;
}

export interface Me {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  cargo: string;
  tenant: Tenant | null;
  acting_tenant: Tenant | null;
}

export interface UserRow {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  cargo: string;
  org_unit: number | null;
  org_unit_name?: string;
  is_active: boolean;
}

export interface OrgUnit {
  id: number;
  parent: number | null;
  name: string;
  kind: "empresa" | "area" | "time";
  manager: number | null;
  manager_name?: string;
  order: number;
  children?: OrgUnit[];
}

export interface Objective {
  id: number;
  perspective: number;
  perspective_name?: string;
  name: string;
  description: string;
  owner: number | null;
  owner_name?: string;
  order: number;
  /** Setas de causa e efeito: ids dos objetivos para os quais este contribui. */
  contributes_to: number[];
  /** Posição no diagrama, em % da faixa. Nulo = auto-layout. */
  pos_x: number | null;
  pos_y: number | null;
  indicators?: { id: number; code: string; name: string; last_status: Farol }[];
}

export interface MapSuggestionObjective {
  perspective: string;
  name: string;
  description: string;
  indicator_code: string | null;
}

export interface MapSuggestion {
  objectives: MapSuggestionObjective[];
  links: { from: string; to: string }[];
}

export interface Perspective {
  id: number;
  map: number;
  name: string;
  order: number;
  color: string;
  objectives_count?: number;
  objectives?: Objective[];
}

export interface StrategicMap {
  id: number;
  name: string;
  year_start: number;
  year_end: number;
  mission: string;
  vision: string;
  values_text: string;
  is_active: boolean;
  perspectives?: Perspective[];
}

export interface Goal {
  id: number;
  objective: number | null;
  objective_name?: string;
  parent: number | null;
  level: "empresa" | "area" | "time" | "pessoa";
  org_unit: number | null;
  org_unit_name?: string;
  owner: number | null;
  owner_name?: string;
  name: string;
  description: string;
  indicator: number | null;
  indicator_status?: Farol;
  weight: string;
  status: string;
  children?: Goal[];
}

export interface Indicator {
  id: number;
  code: string;
  name: string;
  description: string;
  unit: string;
  decimals: number;
  frequency: string;
  polarity: "maior_melhor" | "menor_melhor";
  aggregation: "soma" | "media" | "ultimo";
  org_unit: number | null;
  org_unit_name?: string;
  owner: number | null;
  owner_name?: string;
  objective: number | null;
  objective_name?: string;
  data_source: number | null;
  /** Métrica do ERP que calcula este KPI (vazio = lançamento manual). */
  erp_metric?: string;
  erp_metric_label?: string | null;
  erp_filters?: { branch?: string | string[] };
  yellow_threshold_pct: string;
  is_active: boolean;
  last_value?: {
    period: string;
    value: string;
    achievement_pct: string | null;
    status: Farol;
  } | null;
  spark?: (string | null)[];
}

export interface SeriesPoint {
  period: string;
  target: string | null;
  value: string | null;
  achievement_pct: string | null;
  status: Farol;
  note: string;
}

export interface IndicatorSeries {
  indicator: Indicator;
  year: number;
  series: SeriesPoint[];
  ytd: { value: string | null; target: string | null; achievement_pct: string | null };
}

export interface Deviation {
  id: number;
  indicator: number;
  indicator_code: string;
  indicator_name: string;
  period: string;
  value: string;
  achievement_pct: string | null;
  status: "aberto" | "em_tratamento" | "concluido";
  root_cause: string;
  detected_at: string;
  plans_count: number;
}

export interface ActionItem {
  id: number;
  plan: number;
  title: string;
  responsible: number | null;
  responsible_name?: string;
  due_date: string | null;
  status: "a_fazer" | "fazendo" | "feito";
  order: number;
}

export interface ActionPlan {
  id: number;
  title: string;
  what: string;
  why: string;
  where: string;
  who: number | null;
  who_name?: string;
  when_start: string | null;
  when_end: string | null;
  how: string;
  how_much: string | null;
  status: "rascunho" | "em_andamento" | "concluido" | "cancelado";
  pdca_stage: "plan" | "do" | "check" | "act";
  origin: "manual" | "desvio";
  deviation: number | null;
  objective: number | null;
  indicator: number | null;
  indicator_code?: string;
  org_unit: number | null;
  org_unit_name?: string;
  priority: "baixa" | "media" | "alta";
  items: ActionItem[];
  items_done: number;
  items_total: number;
  created_at: string;
}

export interface AIInsight {
  id: number;
  kind: string;
  indicator: number | null;
  indicator_code?: string;
  deviation: number | null;
  period: string | null;
  status: "pendente" | "processando" | "concluido" | "erro";
  content: string;
  /** Resultado estruturado (usado pela sugestão de mapa). */
  data?: MapSuggestion | Record<string, unknown>;
  error_message: string;
  requested_by_name?: string;
  created_at: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface ChatSession {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface RankingRow {
  id: number;
  code: string;
  name: string;
  org_unit_name: string | null;
  unit: string;
  decimals: number;
  polarity: string;
  value: string;
  target: string | null;
  achievement_pct: string;
  status: Farol;
  spark: (string | null)[];
}

export interface EvolutionRow {
  period: string;
  verde: number;
  amarelo: number;
  vermelho: number;
  atingimento_pct: number | null;
}

export interface HeatmapCell {
  indicator: string;
  period: string;
  status: Farol;
  achievement_pct: string | null;
}

export interface DashboardSummary {
  period: string;
  year: number;
  farois: Record<string, number>;
  total_indicadores: number;
  metas_atingidas_pct: number | null;
  desvios_abertos: number;
  planos_atrasados: number;
  planos_andamento: number;
  planos_total: number;
  planos_concluidos: number;
  ranking: RankingRow[];
  piores: RankingRow[];
  melhores: RankingRow[];
  evolution: EvolutionRow[];
  heatmap: HeatmapCell[];
}
