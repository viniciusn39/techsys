import { FAROL_COLORS, FAROL_LABELS } from "../utils/format";
import type { Farol as FarolType } from "../types";

export function Farol({ status, size = 12 }: { status: FarolType | string | null; size?: number }) {
  const s = status || "sem_lancamento";
  return (
    <span
      title={FAROL_LABELS[s] || s}
      style={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: "50%",
        backgroundColor: FAROL_COLORS[s] || FAROL_COLORS.sem_lancamento,
        verticalAlign: "middle",
      }}
    />
  );
}
