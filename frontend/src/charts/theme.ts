// ---------------------------------------------------------------------------
// Camada de visualização: paleta validada + tema ECharts + helpers de opção.
//
// Regras aplicadas (ver referências de dataviz):
//  · Categórica em ordem fixa, nunca ciclada (máx. 4 séries adjacentes).
//  · Status (farol) é paleta reservada e SEMPRE vem com ícone + rótulo.
//  · Um único eixo Y por gráfico — nunca dual-axis.
//  · Marcas finas, grid hairline sólido, rótulos diretos seletivos.
// ---------------------------------------------------------------------------
import * as echarts from "echarts";

export interface VizTokens {
  surface: string;
  ink: string;
  inkSecondary: string;
  inkMuted: string;
  grid: string;
  axis: string;
  series: string[];
  status: Record<StatusKey, string>;
  /** Ramp sequencial (uma matiz, claro→escuro) para magnitude contínua. */
  sequential: string[];
}

export type StatusKey = "verde" | "amarelo" | "vermelho" | "sem_meta" | "sem_lancamento";

const LIGHT: VizTokens = {
  surface: "#ffffff",
  ink: "#101318",
  inkSecondary: "#52565e",
  inkMuted: "#858a93",
  grid: "#ecedf1",
  axis: "#cfd3da",
  series: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"],
  status: {
    verde: "#0ca30c",
    amarelo: "#fab219",
    vermelho: "#d03b3b",
    sem_meta: "#a8adb6",
    sem_lancamento: "#e3e5ea",
  },
  sequential: ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"],
};

const DARK: VizTokens = {
  surface: "#1c1f26",
  ink: "#f2f3f5",
  inkSecondary: "#b6bac2",
  inkMuted: "#868b95",
  grid: "#282c34",
  axis: "#3d424c",
  series: ["#3987e5", "#d95926", "#199e70", "#c98500"],
  status: {
    verde: "#0ca30c",
    amarelo: "#fab219",
    vermelho: "#d03b3b",
    sem_meta: "#6b717b",
    sem_lancamento: "#2e323b",
  },
  sequential: ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
};

export function vizTokens(dark: boolean): VizTokens {
  return dark ? DARK : LIGHT;
}

export const STATUS_LABEL: Record<StatusKey, string> = {
  verde: "Meta atingida",
  amarelo: "Atenção",
  vermelho: "Crítico",
  sem_meta: "Sem meta",
  sem_lancamento: "Sem lançamento",
};

/** Ícone que acompanha cada status — o farol nunca comunica só pela cor. */
export const STATUS_ICON: Record<StatusKey, string> = {
  verde: "bi-check-circle-fill",
  amarelo: "bi-exclamation-circle-fill",
  vermelho: "bi-x-circle-fill",
  sem_meta: "bi-dash-circle",
  sem_lancamento: "bi-circle",
};

export function statusKey(s: string | null | undefined): StatusKey {
  const k = (s || "sem_lancamento") as StatusKey;
  return k in STATUS_LABEL ? k : "sem_lancamento";
}

// --- tema ECharts ----------------------------------------------------------

function buildTheme(t: VizTokens) {
  return {
    color: t.series,
    backgroundColor: "transparent",
    textStyle: {
      fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      color: t.ink,
    },
    title: { textStyle: { color: t.ink, fontWeight: 600, fontSize: 13 } },
    legend: {
      textStyle: { color: t.inkSecondary, fontSize: 11 },
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 14,
    },
    grid: { containLabel: true, left: 8, right: 16, top: 28, bottom: 4 },
    categoryAxis: {
      axisLine: { show: true, lineStyle: { color: t.axis, width: 1 } },
      axisTick: { show: false },
      axisLabel: { color: t.inkMuted, fontSize: 11 },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: t.inkMuted, fontSize: 11 },
      // Hairline sólida — nunca tracejada.
      splitLine: { show: true, lineStyle: { color: t.grid, width: 1, type: "solid" } },
    },
    tooltip: {
      backgroundColor: t.surface,
      borderColor: t.axis,
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { color: t.ink, fontSize: 12 },
      extraCssText: "box-shadow: 0 6px 20px rgba(0,0,0,.14); border-radius: 8px;",
    },
  };
}

let registered = false;
export function ensureThemes() {
  if (registered) return;
  echarts.registerTheme("techsys-light", buildTheme(LIGHT));
  echarts.registerTheme("techsys-dark", buildTheme(DARK));
  registered = true;
}

// --- helpers de opção ------------------------------------------------------

/** Fill de área: matiz da série a ~10% — uma lavagem, nunca um bloco saturado. */
export function areaWash(color: string, top = 0.16, bottom = 0.01) {
  return new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: withAlpha(color, top) },
    { offset: 1, color: withAlpha(color, bottom) },
  ]);
}

export function withAlpha(hex: string, alpha: number) {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/** Cantos arredondados só na ponta do dado — base quadrada na linha de base. */
export const BAR_RADIUS_V: [number, number, number, number] = [4, 4, 0, 0];
export const BAR_RADIUS_H: [number, number, number, number] = [0, 4, 4, 0];
export const BAR_MAX_WIDTH = 24;

export const nf = (decimals = 2) =>
  new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

export function fmtPctAxis(v: number) {
  return `${nf(0).format(v)}%`;
}
