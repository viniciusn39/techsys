import { STATUS_ICON, STATUS_LABEL, statusKey, vizTokens } from "../charts/theme";
import { useTheme } from "../hooks/useTheme";
import { fmtNumber } from "../utils/format";

// --- Farol -----------------------------------------------------------------
// Regra: cor de status nunca comunica sozinha — sempre ícone + rótulo.

export function StatusPill({ status, compact = false }: { status: string | null; compact?: boolean }) {
  const k = statusKey(status);
  return (
    <span className={`status-pill st-${k === "sem_meta" || k === "sem_lancamento" ? "neutro" : k}`}>
      <i className={`bi ${STATUS_ICON[k]}`} aria-hidden="true" />
      {!compact && STATUS_LABEL[k]}
    </span>
  );
}

/** Ponto de farol para densidade alta (tabelas). Traz o rótulo no title + aria. */
export function StatusDot({ status }: { status: string | null }) {
  const k = statusKey(status);
  const cls = k === "sem_meta" || k === "sem_lancamento" ? "neutro" : k;
  return (
    <span
      className={`status-dot st-${cls}`}
      title={STATUS_LABEL[k]}
      role="img"
      aria-label={STATUS_LABEL[k]}
    />
  );
}

// --- Stat tile -------------------------------------------------------------

interface StatProps {
  label: string;
  value: React.ReactNode;
  icon?: string;
  foot?: React.ReactNode;
  delta?: { value: number; goodWhenUp?: boolean; since?: string } | null;
  spark?: (number | string | null)[];
  sparkColor?: string;
}

export function StatCard({ label, value, icon, foot, delta, spark, sparkColor }: StatProps) {
  return (
    <div className="stat">
      <div className="stat-label">
        {icon && <i className={`bi ${icon}`} aria-hidden="true" />}
        {label}
      </div>
      <div className="stat-value">{value}</div>
      {delta && <DeltaBadge {...delta} />}
      {spark && spark.length > 1 && (
        <div className="stat-spark">
          <Sparkline data={spark} color={sparkColor} />
        </div>
      )}
      {foot && <div className="stat-foot">{foot}</div>}
    </div>
  );
}

export function DeltaBadge({
  value,
  goodWhenUp = true,
  since,
}: {
  value: number;
  goodWhenUp?: boolean;
  since?: string;
}) {
  const up = value >= 0;
  const good = up === goodWhenUp;
  return (
    <div className="stat-foot d-flex align-items-center gap-1">
      <span style={{ color: good ? "var(--st-verde)" : "var(--st-vermelho)", fontWeight: 600 }}>
        <i className={`bi ${up ? "bi-arrow-up-right" : "bi-arrow-down-right"}`} aria-hidden="true" />{" "}
        {up ? "+" : ""}
        {fmtNumber(value, 1)} p.p.
      </span>
      {since && <span className="text-muted-2">vs {since}</span>}
    </div>
  );
}

// --- Sparkline (SVG leve, sem instanciar um chart por linha) ---------------

export function Sparkline({
  data,
  color,
  width = 96,
  height = 26,
}: {
  data: (number | string | null)[];
  color?: string;
  width?: number;
  height?: number;
}) {
  const { isDark } = useTheme();
  const tokens = vizTokens(isDark);
  const stroke = color || tokens.series[0];

  const nums = data.map((d) => (d === null || d === "" ? null : Number(d)));
  const valid = nums.filter((n): n is number => n !== null && !Number.isNaN(n));
  if (valid.length < 2) return null;

  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const span = max - min || 1;
  // Margem interna: o anel de 2px do marcador final não pode ser cortado pela borda.
  const pad = 5;
  const innerW = width - pad * 2;
  const stepX = innerW / (nums.length - 1);
  const y = (v: number) => height - pad - ((v - min) / span) * (height - pad * 2);
  const x = (i: number) => pad + i * stepX;

  let d = "";
  nums.forEach((n, i) => {
    if (n === null) return;
    d += `${d ? "L" : "M"}${x(i).toFixed(1)},${y(n).toFixed(1)}`;
  });

  let lastIdx = -1;
  nums.forEach((n, i) => {
    if (n !== null && !Number.isNaN(n)) lastIdx = i;
  });
  const last = lastIdx >= 0 ? nums[lastIdx] : null;

  return (
    <svg width={width} height={height} role="img" aria-label="Tendência do período">
      <path d={d} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {last !== null && (
        <circle
          cx={x(lastIdx)}
          cy={y(last)}
          r={3}
          fill={stroke}
          stroke={tokens.surface}
          strokeWidth={2}
        />
      )}
    </svg>
  );
}

// --- Meter (razão contra um limite) ---------------------------------------

export function Meter({ pct, status }: { pct: number | null; status?: string | null }) {
  const { isDark } = useTheme();
  const tokens = vizTokens(isDark);
  const k = statusKey(status);
  const color = status ? tokens.status[k] : tokens.series[0];
  const width = Math.max(0, Math.min(100, pct ?? 0));
  return (
    <div className="meter" title={pct !== null ? `${fmtNumber(pct, 1)}%` : "—"}>
      <span style={{ width: `${width}%`, background: color }} />
    </div>
  );
}

// --- Cabeçalhos, vazios e esqueletos --------------------------------------

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-head">
          <div>
            {title && <h6>{title}</h6>}
            {subtitle && <div className="sub">{subtitle}</div>}
          </div>
          {actions}
        </div>
      )}
      <div className="panel-body">{children}</div>
    </div>
  );
}

export function EmptyState({
  icon = "bi-inbox",
  title,
  hint,
  action,
}: {
  icon?: string;
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <i className={`bi ${icon}`} aria-hidden="true" />
      <div className="title">{title}</div>
      {hint && <div className="small">{hint}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Skeleton({ height = 16, width = "100%", className = "" }: {
  height?: number | string;
  width?: number | string;
  className?: string;
}) {
  return <div className={`skeleton ${className}`} style={{ height, width }} />;
}

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return <Skeleton height={height} />;
}

/** Legenda estática — identidade nunca depende só da cor da marca. */
export function ChartLegend({
  items,
}: {
  items: { color: string; label: string; shape?: "rect" | "line" }[];
}) {
  return (
    <div className="chart-legend">
      {items.map((i) => (
        <span className="item" key={i.label}>
          <span
            className={`key ${i.shape === "line" ? "line" : ""}`}
            style={{ background: i.color }}
          />
          {i.label}
        </span>
      ))}
    </div>
  );
}
