import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { statusKey, vizTokens } from "../charts/theme";
import type { Objective, Perspective } from "../types";

/**
 * Diagrama do mapa estratégico.
 *
 * Faixas horizontais (uma por perspectiva) com os objetivos como caixões
 * arrastáveis e as setas de causa-e-efeito ligando um ao outro. As setas saem do
 * campo `contributes_to`; a posição vem de `pos_x`/`pos_y` (em % da faixa) e,
 * quando é nula, os objetivos são distribuídos igualmente na faixa.
 *
 * SVG cru em vez de biblioteca de grafo porque aqui as raias mandam no layout:
 * o objetivo pertence à faixa em que é solto, e isso muda a perspectiva dele.
 */

const NODE_W = 190;
const NODE_H = 68;
const BAND_MIN_H = 130;
const BAND_GAP = 14;
const LABEL_W = 132;
const PAD_X = 18;

/** Quebra o nome da perspectiva em até 2 linhas que cabem na coluna do rótulo. */
function wrapLabel(name: string, maxChars = 15): string[] {
  if (name.length <= maxChars) return [name];
  const words = name.split(" ");
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    if (!current) current = word;
    else if (`${current} ${word}`.length <= maxChars) current += ` ${word}`;
    else {
      lines.push(current);
      current = word;
    }
    if (lines.length === 2) break;
  }
  if (lines.length < 2 && current) lines.push(current);
  return lines.map((l) => (l.length > maxChars ? `${l.slice(0, maxChars - 1)}…` : l));
}

export interface MapNode {
  objective: Objective;
  perspective: Perspective;
  x: number;
  y: number;
}

interface Props {
  perspectives: Perspective[];
  /** Modo "ligar": clicar em dois objetivos cria/remove a seta entre eles. */
  linking: boolean;
  linkSource: number | null;
  onNodeClick: (objective: Objective) => void;
  onLayoutChange: (
    positions: { id: number; pos_x: number; pos_y: number; perspective: number }[]
  ) => void;
  readOnly?: boolean;
}

export function MapaCanvas({
  perspectives,
  linking,
  linkSource,
  onNodeClick,
  onLayoutChange,
  readOnly = false,
}: Props) {
  const t = vizTokens(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(900);
  const [drag, setDrag] = useState<{ id: number; dx: number; dy: number } | null>(null);
  /** Sobrepõe as posições vindas da API enquanto o usuário arrasta. */
  const [local, setLocal] = useState<Record<number, { x: number; y: number; persp: number }>>({});

  useLayoutEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  // Financeira no topo: a leitura do BSC é de baixo para cima.
  const bands = useMemo(() => {
    let y = 0;
    return perspectives.map((p) => {
      const count = p.objectives?.length ?? 0;
      const perRow = Math.max(1, Math.floor((width - LABEL_W - PAD_X * 2) / (NODE_W + 20)));
      const rows = Math.max(1, Math.ceil(count / perRow));
      const height = Math.max(BAND_MIN_H, rows * (NODE_H + 18) + 30);
      const band = { perspective: p, y, height };
      y += height + BAND_GAP;
      return band;
    });
  }, [perspectives, width]);

  const totalHeight = bands.reduce((acc, b) => acc + b.height + BAND_GAP, 0);
  const laneX = LABEL_W + PAD_X;
  const laneW = Math.max(NODE_W + 40, width - laneX - PAD_X);

  const nodes = useMemo<MapNode[]>(() => {
    const out: MapNode[] = [];
    bands.forEach((band) => {
      const objectives = band.perspective.objectives ?? [];
      const perRow = Math.max(1, Math.floor(laneW / (NODE_W + 20)));
      objectives.forEach((o, i) => {
        const override = local[o.id];
        const persistedX = o.pos_x;
        const persistedY = o.pos_y;

        let x: number;
        let y: number;
        if (override) {
          x = override.x;
          y = override.y;
        } else if (persistedX !== null && persistedX !== undefined && persistedY !== null && persistedY !== undefined) {
          x = laneX + (persistedX / 100) * (laneW - NODE_W);
          y = band.y + (persistedY / 100) * (band.height - NODE_H);
        } else {
          // Auto-layout: espalha pela largura útil da faixa, quebrando linha
          // só quando não couber — poucos objetivos ocupam a faixa inteira.
          const cols = Math.min(perRow, objectives.length);
          const col = i % cols;
          const row = Math.floor(i / cols);
          const step = laneW / cols;
          x = laneX + col * step + (step - NODE_W) / 2;
          y = band.y + 22 + row * (NODE_H + 14);
        }
        out.push({ objective: o, perspective: band.perspective, x, y });
      });
    });
    return out;
  }, [bands, laneX, laneW, local]);

  const nodeById = useMemo(() => {
    const m = new Map<number, MapNode>();
    nodes.forEach((n) => m.set(n.objective.id, n));
    return m;
  }, [nodes]);

  const edges = useMemo(() => {
    const out: { from: MapNode; to: MapNode }[] = [];
    nodes.forEach((n) => {
      (n.objective.contributes_to ?? []).forEach((targetId) => {
        const target = nodeById.get(targetId);
        if (target) out.push({ from: n, to: target });
      });
    });
    return out;
  }, [nodes, nodeById]);

  // --- arrastar -----------------------------------------------------------

  const onPointerDown = (e: React.PointerEvent, node: MapNode) => {
    if (readOnly || linking) return;
    e.preventDefault();
    (e.target as Element).setPointerCapture?.(e.pointerId);
    const rect = wrapRef.current!.getBoundingClientRect();
    setDrag({
      id: node.objective.id,
      dx: e.clientX - rect.left - node.x,
      dy: e.clientY - rect.top - node.y,
    });
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag) return;
    const rect = wrapRef.current!.getBoundingClientRect();
    const x = Math.min(Math.max(laneX, e.clientX - rect.left - drag.dx), laneX + laneW - NODE_W);
    const y = Math.min(Math.max(0, e.clientY - rect.top - drag.dy), totalHeight - NODE_H);

    // A faixa em que o centro do caixão está define a perspectiva.
    const center = y + NODE_H / 2;
    const band = bands.find((b) => center >= b.y && center <= b.y + b.height) ?? bands[bands.length - 1];
    setLocal((prev) => ({ ...prev, [drag.id]: { x, y, persp: band.perspective.id } }));
  };

  const onPointerUp = () => {
    if (!drag) return;
    const moved = local[drag.id];
    setDrag(null);
    if (!moved) return;

    const band = bands.find((b) => b.perspective.id === moved.persp);
    if (!band) return;
    onLayoutChange([
      {
        id: drag.id,
        pos_x: ((moved.x - laneX) / Math.max(1, laneW - NODE_W)) * 100,
        pos_y: ((moved.y - band.y) / Math.max(1, band.height - NODE_H)) * 100,
        perspective: moved.persp,
      },
    ]);
    setLocal((prev) => {
      const next = { ...prev };
      delete next[drag.id];
      return next;
    });
  };

  return (
    <div
      ref={wrapRef}
      className="mapa-canvas"
      style={{ position: "relative", width: "100%", height: totalHeight, touchAction: "none" }}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
    >
      <svg width="100%" height={totalHeight} style={{ position: "absolute", inset: 0 }}>
        <defs>
          <marker id="seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={t.inkMuted} />
          </marker>
        </defs>

        {/* Faixas das perspectivas */}
        {bands.map((b) => (
          <g key={b.perspective.id}>
            <rect
              x={0} y={b.y} width="100%" height={b.height} rx={10}
              fill={`${b.perspective.color}0f`}
              stroke={`${b.perspective.color}33`}
            />
            <rect x={0} y={b.y} width={4} height={b.height} rx={2} fill={b.perspective.color} />
            {/* Nome da perspectiva quebrado em até 2 linhas, sem cortar palavra. */}
            {wrapLabel(b.perspective.name).map((line, i) => (
              <text
                key={i}
                x={16}
                y={b.y + 22 + i * 13}
                fill={b.perspective.color}
                fontSize={10.5}
                fontWeight={700}
                style={{ textTransform: "uppercase", letterSpacing: "0.05em" }}
              >
                {line}
              </text>
            ))}
          </g>
        ))}

        {/* Setas de causa e efeito */}
        {edges.map(({ from, to }, i) => {
          const x1 = from.x + NODE_W / 2;
          const y1 = from.y;
          const x2 = to.x + NODE_W / 2;
          const y2 = to.y + NODE_H;
          const mid = (y1 + y2) / 2;
          return (
            <path
              key={i}
              d={`M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`}
              fill="none"
              stroke={t.inkMuted}
              strokeWidth={1.5}
              markerEnd="url(#seta)"
              opacity={0.75}
            />
          );
        })}
      </svg>

      {/* Objetivos */}
      {nodes.map((n) => {
        const kpis = n.objective.indicators ?? [];
        const isSource = linkSource === n.objective.id;
        return (
          <div
            key={n.objective.id}
            className={`mapa-node ${isSource ? "is-source" : ""} ${linking ? "is-linking" : ""}`}
            style={{
              position: "absolute",
              left: n.x,
              top: n.y,
              width: NODE_W,
              minHeight: NODE_H,
              borderTopColor: n.perspective.color,
              cursor: readOnly ? "default" : linking ? "crosshair" : "grab",
              zIndex: drag?.id === n.objective.id ? 5 : 2,
            }}
            onPointerDown={(e) => onPointerDown(e, n)}
            onClick={() => onNodeClick(n.objective)}
            title={n.objective.description || n.objective.name}
          >
            <div className="mapa-node-title">{n.objective.name}</div>
            <div className="mapa-node-meta">
              {kpis.length > 0 ? (
                <span className="d-inline-flex align-items-center gap-1">
                  {kpis.slice(0, 4).map((k) => (
                    <span
                      key={k.id}
                      className="mapa-node-dot"
                      style={{ background: t.status[statusKey(k.last_status)] }}
                      title={`${k.code} — ${k.name}`}
                    />
                  ))}
                  {kpis.length} KPI{kpis.length > 1 ? "s" : ""}
                </span>
              ) : (
                <span className="text-muted-2">sem indicador</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
