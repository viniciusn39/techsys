import * as echarts from "echarts";
import { useEffect, useRef } from "react";
import { ensureThemes } from "../charts/theme";
import { useTheme } from "../hooks/useTheme";

interface Props {
  /** Tipo frouxo que o próprio setOption aceita — evita brigar com a tipagem por série. */
  option: echarts.EChartsCoreOption;
  height?: number | string;
  /** Handlers de eventos ECharts, ex.: { click: (p) => ... } */
  onEvents?: Record<string, (params: any) => void>;
}

export function EChart({ option, height = 300, onEvents }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const { isDark } = useTheme();

  // O tema do ECharts é fixado na init, então recriamos o gráfico ao trocar de tema.
  useEffect(() => {
    if (!ref.current) return;
    ensureThemes();
    const chart = echarts.init(ref.current, isDark ? "techsys-dark" : "techsys-light", {
      renderer: "canvas",
    });
    chartRef.current = chart;

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [isDark]);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option, isDark]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onEvents) return;
    Object.entries(onEvents).forEach(([evt, handler]) => chart.on(evt, handler));
    return () => {
      Object.keys(onEvents).forEach((evt) => chart.off(evt));
    };
  }, [onEvents, isDark, option]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
