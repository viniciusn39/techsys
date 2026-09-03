export function fmtNumber(v: string | number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString("pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function fmtPct(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  return `${fmtNumber(v, 1)}%`;
}

export function fmtPeriod(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m] = iso.split("-");
  return `${m}/${y}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return d.toLocaleDateString("pt-BR");
}

export const MONTHS_SHORT = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez",
];

export const FAROL_COLORS: Record<string, string> = {
  verde: "#198754",
  amarelo: "#ffc107",
  vermelho: "#dc3545",
  sem_meta: "#adb5bd",
  sem_lancamento: "#dee2e6",
};

export const FAROL_LABELS: Record<string, string> = {
  verde: "Verde",
  amarelo: "Amarelo",
  vermelho: "Vermelho",
  sem_meta: "Sem meta",
  sem_lancamento: "Sem lançamento",
};
