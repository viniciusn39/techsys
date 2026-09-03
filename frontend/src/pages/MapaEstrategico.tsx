import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Dropdown, Form, Modal } from "react-bootstrap";
import { api } from "../api/client";
import { statusKey, vizTokens, withAlpha } from "../charts/theme";
import { EChart } from "../components/EChart";
import { MapaCanvas } from "../components/MapaCanvas";
import { EmptyState, Panel, Skeleton, StatusDot } from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import type {
  AIInsight,
  MapSuggestion,
  Objective,
  Perspective,
  StrategicMap,
  UserRow,
} from "../types";

const PERSPECTIVE_ICONS: Record<string, string> = {
  Financeira: "bi-cash-coin",
  Clientes: "bi-people",
  "Processos Internos": "bi-gear-wide-connected",
  "Aprendizado e Crescimento": "bi-mortarboard",
};

const PERSPECTIVE_COLORS = [
  "#198754", "#2a78d6", "#eb6834", "#6f42c1",
  "#1baf7a", "#d03b3b", "#0d9488", "#b45309",
];

type View = "diagrama" | "faixas";

export function MapaEstrategico() {
  const { isDark } = useTheme();
  const t = vizTokens(isDark);

  const [map, setMap] = useState<StrategicMap | null | undefined>(undefined);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [view, setView] = useState<View>("diagrama");
  const [editing, setEditing] = useState<Partial<Objective> | null>(null);
  const [persp, setPersp] = useState<Partial<Perspective> | null>(null);
  const [creatingMap, setCreatingMap] = useState(false);
  const [mapForm, setMapForm] = useState({
    name: `Planejamento Estratégico ${new Date().getFullYear()}`,
    year_start: new Date().getFullYear(),
    year_end: new Date().getFullYear() + 2,
    mission: "",
    vision: "",
    values_text: "",
  });

  // Modo "ligar": clicar em dois objetivos cria ou remove a seta entre eles.
  const [linking, setLinking] = useState(false);
  const [linkSource, setLinkSource] = useState<number | null>(null);

  // Sugestão de IA
  const [suggesting, setSuggesting] = useState(false);
  const [suggestion, setSuggestion] = useState<MapSuggestion | null>(null);
  const [accepted, setAccepted] = useState<Set<string>>(new Set());
  const [aiError, setAiError] = useState("");
  const pollRef = useRef<number | null>(null);

  const load = useCallback(() => {
    api.get<StrategicMap | null>("/api/strategic-maps/active/").then(setMap).catch(() => setMap(null));
  }, []);

  useEffect(() => {
    load();
    api.get("/api/users/").then((d) => setUsers(d.results ?? d)).catch(() => {});
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [load]);

  // --- objetivos ----------------------------------------------------------

  const saveObjective = async () => {
    if (!editing) return;
    const body = {
      perspective: editing.perspective,
      name: editing.name,
      description: editing.description || "",
      owner: editing.owner || null,
    };
    if (editing.id) await api.patch(`/api/objectives/${editing.id}/`, body);
    else await api.post("/api/objectives/", body);
    setEditing(null);
    load();
  };

  const deleteObjective = async () => {
    if (editing?.id && confirm("Excluir este objetivo? As setas ligadas a ele somem junto.")) {
      await api.del(`/api/objectives/${editing.id}/`);
      setEditing(null);
      load();
    }
  };

  // --- perspectivas -------------------------------------------------------

  const savePerspective = async () => {
    if (!persp?.name) return;
    const body = { name: persp.name, color: persp.color || PERSPECTIVE_COLORS[0] };
    if (persp.id) await api.patch(`/api/perspectives/${persp.id}/`, body);
    else await api.post("/api/perspectives/", body);
    setPersp(null);
    load();
  };

  const movePerspective = async (p: Perspective, direction: "up" | "down") => {
    await api.patch(`/api/perspectives/${p.id}/move/`, { direction });
    load();
  };

  const deletePerspective = async (p: Perspective) => {
    const count = p.objectives?.length ?? p.objectives_count ?? 0;
    const aviso =
      count > 0
        ? `A perspectiva "${p.name}" tem ${count} objetivo(s), que serão excluídos junto. Confirma?`
        : `Excluir a perspectiva "${p.name}"?`;
    if (!confirm(aviso)) return;
    await api.del(`/api/perspectives/${p.id}/`);
    load();
  };

  // --- diagrama: arrastar e ligar -----------------------------------------

  const handleLayout = async (
    positions: { id: number; pos_x: number; pos_y: number; perspective: number }[]
  ) => {
    await api.post("/api/objectives/layout/", { positions });
    load();
  };

  const handleNodeClick = async (objective: Objective) => {
    if (!linking) {
      setEditing(objective);
      return;
    }
    if (linkSource === null) {
      setLinkSource(objective.id);
      return;
    }
    if (linkSource === objective.id) {
      setLinkSource(null);
      return;
    }
    await api.post(`/api/objectives/${linkSource}/toggle-link/`, { target: objective.id });
    setLinkSource(null);
    load();
  };

  // --- sugestão por IA ----------------------------------------------------

  const generateSuggestion = async () => {
    setSuggesting(true);
    setAiError("");
    setSuggestion(null);
    try {
      const insight = await api.post<AIInsight>("/api/ai/insights/generate/", {
        kind: "sugestao_mapa",
      });
      pollRef.current = window.setInterval(async () => {
        const updated = await api.get<AIInsight>(`/api/ai/insights/${insight.id}/`);
        if (updated.status === "concluido") {
          window.clearInterval(pollRef.current!);
          setSuggesting(false);
          const data = updated.data as MapSuggestion;
          setSuggestion(data);
          setAccepted(new Set(data.objectives.map((o) => o.name)));
        } else if (updated.status === "erro") {
          window.clearInterval(pollRef.current!);
          setSuggesting(false);
          setAiError(updated.error_message);
        }
      }, 2500);
    } catch (e: any) {
      setSuggesting(false);
      setAiError(e.message);
    }
  };

  const applySuggestion = async () => {
    if (!suggestion || !map) return;
    const objectives = suggestion.objectives.filter((o) => accepted.has(o.name));
    const links = suggestion.links.filter(
      (l) => accepted.has(l.from) && accepted.has(l.to)
    );
    await api.post(`/api/strategic-maps/${map.id}/apply-suggestion/`, { objectives, links });
    setSuggestion(null);
    load();
  };

  // --- radar de saúde -----------------------------------------------------

  const radarOption = useMemo(() => {
    const persps = map?.perspectives ?? [];
    const scores = persps.map((p) => {
      const kpis = (p.objectives ?? []).flatMap((o) => o.indicators ?? []);
      if (kpis.length === 0) return 0;
      return Math.round((kpis.filter((k) => statusKey(k.last_status) === "verde").length / kpis.length) * 100);
    });
    return {
      tooltip: {
        trigger: "item" as const,
        formatter: () => persps.map((p, i) => `${p.name}: <strong>${scores[i]}%</strong>`).join("<br/>"),
      },
      radar: {
        indicator: persps.map((p) => ({ name: p.name, max: 100 })),
        radius: "62%",
        center: ["50%", "54%"],
        axisName: { color: t.inkSecondary, fontSize: 10 },
        splitLine: { lineStyle: { color: t.grid } },
        splitArea: { show: false },
        axisLine: { lineStyle: { color: t.grid } },
      },
      series: [
        {
          type: "radar" as const,
          symbolSize: 8,
          lineStyle: { width: 2, color: t.series[0] },
          itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 2 },
          areaStyle: { color: withAlpha(t.series[0], 0.14) },
          data: [{ value: scores, name: "KPIs no verde" }],
        },
      ],
    };
  }, [map, t]);

  if (map === undefined) return <Panel><Skeleton height={320} /></Panel>;

  if (map === null) {
    return (
      <>
        <Panel>
          <EmptyState
            icon="bi-diagram-3"
            title="Nenhum mapa estratégico ativo"
            hint="Crie o mapa e as 4 perspectivas do BSC são geradas automaticamente."
            action={<Button onClick={() => setCreatingMap(true)}><i className="bi bi-plus-lg me-1" />Criar mapa estratégico</Button>}
          />
        </Panel>
        <Modal show={creatingMap} onHide={() => setCreatingMap(false)} centered>
          <Modal.Header closeButton><Modal.Title className="fs-6">Novo mapa estratégico</Modal.Title></Modal.Header>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>Nome</Form.Label>
              <Form.Control value={mapForm.name} onChange={(e) => setMapForm({ ...mapForm, name: e.target.value })} />
            </Form.Group>
            <div className="row g-3">
              <div className="col">
                <Form.Label>Ano inicial</Form.Label>
                <Form.Control type="number" value={mapForm.year_start} onChange={(e) => setMapForm({ ...mapForm, year_start: Number(e.target.value) })} />
              </div>
              <div className="col">
                <Form.Label>Ano final</Form.Label>
                <Form.Control type="number" value={mapForm.year_end} onChange={(e) => setMapForm({ ...mapForm, year_end: Number(e.target.value) })} />
              </div>
            </div>
            <Form.Group className="mt-3">
              <Form.Label>Missão</Form.Label>
              <Form.Control as="textarea" rows={2} value={mapForm.mission} onChange={(e) => setMapForm({ ...mapForm, mission: e.target.value })} />
            </Form.Group>
            <Form.Group className="mt-3">
              <Form.Label>Visão</Form.Label>
              <Form.Control as="textarea" rows={2} value={mapForm.vision} onChange={(e) => setMapForm({ ...mapForm, vision: e.target.value })} />
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="outline-secondary" onClick={() => setCreatingMap(false)}>Cancelar</Button>
            <Button
              onClick={async () => {
                await api.post("/api/strategic-maps/", mapForm);
                setCreatingMap(false);
                load();
              }}
              disabled={!mapForm.name}
            >
              Criar
            </Button>
          </Modal.Footer>
        </Modal>
      </>
    );
  }

  const allKpis = (map.perspectives ?? []).flatMap((p) =>
    (p.objectives ?? []).flatMap((o) => o.indicators ?? [])
  );
  const totalObjectives = (map.perspectives ?? []).reduce(
    (acc, p) => acc + (p.objectives?.length ?? 0), 0
  );
  const totalLinks = (map.perspectives ?? []).reduce(
    (acc, p) => acc + (p.objectives ?? []).reduce((a, o) => a + (o.contributes_to?.length ?? 0), 0), 0
  );

  return (
    <div>
      <div className="row g-3 mb-3">
        <div className="col-lg-8">
          <div className="row g-3 h-100">
            {[
              { icon: "bi-flag", label: "Missão", text: map.mission },
              { icon: "bi-eye", label: "Visão", text: map.vision },
              { icon: "bi-gem", label: "Valores", text: map.values_text },
            ]
              .filter((c) => c.text)
              .map((c) => (
                <div className="col-md-4" key={c.label}>
                  <div className="panel h-100 p-3">
                    <div className="stat-label mb-1"><i className={`bi ${c.icon}`} />{c.label}</div>
                    <div className="small text-secondary-2">{c.text}</div>
                  </div>
                </div>
              ))}
          </div>
        </div>
        <div className="col-lg-4">
          <Panel title="Saúde por perspectiva" subtitle="% de KPIs com meta atingida">
            <EChart option={radarOption} height={200} />
          </Panel>
        </div>
      </div>

      <div className="filter-bar">
        <div className="btn-group btn-group-sm">
          {(["diagrama", "faixas"] as View[]).map((v) => (
            <button
              key={v}
              className={`btn btn-outline-secondary ${view === v ? "active" : ""}`}
              onClick={() => { setView(v); setLinking(false); setLinkSource(null); }}
            >
              <i className={`bi ${v === "diagrama" ? "bi-diagram-3" : "bi-list-nested"} me-1`} />
              {v === "diagrama" ? "Diagrama" : "Faixas"}
            </button>
          ))}
        </div>

        {view === "diagrama" && (
          <Button
            size="sm"
            variant={linking ? "primary" : "outline-secondary"}
            onClick={() => { setLinking(!linking); setLinkSource(null); }}
          >
            <i className="bi bi-arrow-up-right me-1" />
            {linking ? "Concluir ligações" : "Ligar objetivos"}
          </Button>
        )}

        <Button size="sm" variant="outline-secondary" onClick={() => setPersp({ name: "", color: PERSPECTIVE_COLORS[0] })}>
          <i className="bi bi-plus-lg me-1" />Perspectiva
        </Button>

        <Button size="sm" variant="outline-secondary" onClick={generateSuggestion} disabled={suggesting}>
          <i className="bi bi-stars me-1" />
          {suggesting ? "Gerando..." : "Gerar com IA"}
        </Button>

        <span className="text-muted-2 small ms-auto">
          {map.perspectives?.length ?? 0} perspectivas · {totalObjectives} objetivos ·{" "}
          {totalLinks} ligações · {allKpis.length} KPIs
        </span>
      </div>

      {linking && (
        <div className="alert alert-info py-2 small d-flex align-items-center gap-2">
          <i className="bi bi-info-circle-fill" />
          {linkSource === null
            ? "Clique no objetivo de origem (o que sustenta) e depois no de destino."
            : "Agora clique no objetivo de destino. Clicar no mesmo cancela."}
        </div>
      )}
      {aiError && (
        <div className="alert alert-warning py-2 small d-flex align-items-center gap-2">
          <i className="bi bi-exclamation-triangle-fill" />{aiError}
        </div>
      )}

      {/* --- Sugestão da IA --- */}
      {suggestion && (
        <Panel
          className="mb-3"
          title="Rascunho sugerido pela IA"
          subtitle="Desmarque o que não quiser. Objetivos com nome já existente são ignorados."
          actions={
            <div className="d-flex gap-2">
              <Button size="sm" variant="outline-secondary" onClick={() => setSuggestion(null)}>
                Descartar
              </Button>
              <Button size="sm" onClick={applySuggestion} disabled={accepted.size === 0}>
                <i className="bi bi-check-lg me-1" />Aplicar {accepted.size} ao mapa
              </Button>
            </div>
          }
        >
          <div className="row g-3">
            <div className="col-lg-7">
              {(map.perspectives ?? []).map((p) => {
                const items = suggestion.objectives.filter((o) => o.perspective === p.name);
                if (items.length === 0) return null;
                return (
                  <div key={p.id} className="mb-2">
                    <div className="perspective-name mb-1" style={{ ["--persp-color" as any]: p.color, color: p.color }}>
                      {p.name}
                    </div>
                    {items.map((o) => (
                      <label key={o.name} className="suggestion-row" role="button">
                        <Form.Check
                          checked={accepted.has(o.name)}
                          onChange={(e) => {
                            const next = new Set(accepted);
                            e.target.checked ? next.add(o.name) : next.delete(o.name);
                            setAccepted(next);
                          }}
                        />
                        <span>
                          <span className="fw-semibold small d-block">{o.name}</span>
                          <span className="text-muted-2" style={{ fontSize: "0.75rem" }}>
                            {o.description}
                          </span>
                          {o.indicator_code && (
                            <span className="badge text-bg-light border fw-normal mt-1">
                              KPI {o.indicator_code}
                            </span>
                          )}
                        </span>
                      </label>
                    ))}
                  </div>
                );
              })}
            </div>
            <div className="col-lg-5">
              <div className="stat-label mb-2"><i className="bi bi-arrow-up-right" />Ligações de causa e efeito</div>
              {suggestion.links.length === 0 && (
                <div className="text-muted-2 small">Nenhuma ligação sugerida.</div>
              )}
              {suggestion.links.map((l, i) => {
                const ativo = accepted.has(l.from) && accepted.has(l.to);
                return (
                  <div
                    key={i}
                    className="small mb-1"
                    style={{ opacity: ativo ? 1 : 0.4, textDecoration: ativo ? "none" : "line-through" }}
                  >
                    {l.from} <i className="bi bi-arrow-right mx-1 text-muted-2" /> {l.to}
                  </div>
                );
              })}
            </div>
          </div>
        </Panel>
      )}

      {/* --- Diagrama --- */}
      {view === "diagrama" ? (
        <Panel
          title={map.name}
          subtitle="Arraste os objetivos para posicioná-los; soltar em outra faixa muda a perspectiva."
        >
          {totalObjectives === 0 ? (
            <EmptyState
              icon="bi-diagram-3"
              title="Mapa ainda sem objetivos"
              hint="Crie objetivos nas faixas ou peça um rascunho à IA."
              action={
                <Button size="sm" onClick={generateSuggestion} disabled={suggesting}>
                  <i className="bi bi-stars me-1" />Gerar com IA
                </Button>
              }
            />
          ) : (
            <MapaCanvas
              perspectives={map.perspectives ?? []}
              linking={linking}
              linkSource={linkSource}
              onNodeClick={handleNodeClick}
              onLayoutChange={handleLayout}
            />
          )}
        </Panel>
      ) : (
        /* --- Faixas (lista) --- */
        <div className="d-flex flex-column gap-3">
          {map.perspectives?.map((p, idx) => {
            const color = p.color || t.series[0];
            const total = map.perspectives?.length ?? 0;
            return (
              <div key={p.id} className="perspective" style={{ ["--persp-color" as any]: color }}>
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <div className="perspective-name">
                    <i className={`bi ${PERSPECTIVE_ICONS[p.name] ?? "bi-bookmark"} me-1`} />
                    {p.name}
                  </div>
                  <div className="d-flex align-items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline-secondary"
                      onClick={() => setEditing({ perspective: p.id, name: "", description: "" })}
                    >
                      <i className="bi bi-plus-lg me-1" />Objetivo
                    </Button>
                    <Dropdown align="end">
                      <Dropdown.Toggle size="sm" variant="outline-secondary" className="no-caret" aria-label={`Ações da perspectiva ${p.name}`}>
                        <i className="bi bi-three-dots" />
                      </Dropdown.Toggle>
                      <Dropdown.Menu>
                        <Dropdown.Item onClick={() => setPersp(p)}>
                          <i className="bi bi-pencil me-2" />Renomear / cor
                        </Dropdown.Item>
                        <Dropdown.Item disabled={idx === 0} onClick={() => movePerspective(p, "up")}>
                          <i className="bi bi-arrow-up me-2" />Mover para cima
                        </Dropdown.Item>
                        <Dropdown.Item disabled={idx === total - 1} onClick={() => movePerspective(p, "down")}>
                          <i className="bi bi-arrow-down me-2" />Mover para baixo
                        </Dropdown.Item>
                        <Dropdown.Divider />
                        <Dropdown.Item className="text-danger" onClick={() => deletePerspective(p)}>
                          <i className="bi bi-trash3 me-2" />Excluir perspectiva
                        </Dropdown.Item>
                      </Dropdown.Menu>
                    </Dropdown>
                  </div>
                </div>
                <div className="row g-2">
                  {p.objectives?.map((o) => (
                    <div className="col-md-6 col-xl-3" key={o.id}>
                      <div className="objective-card" onClick={() => setEditing(o)} role="button">
                        <div className="title">{o.name}</div>
                        {o.owner_name && (
                          <div className="meta mt-1"><i className="bi bi-person me-1" />{o.owner_name}</div>
                        )}
                        <div className="d-flex align-items-center gap-1 mt-2 flex-wrap">
                          {(o.indicators ?? []).map((i) => (
                            <span key={i.id} title={`${i.code} — ${i.name}`}>
                              <StatusDot status={i.last_status} />
                            </span>
                          ))}
                          {(o.contributes_to?.length ?? 0) > 0 && (
                            <span className="meta ms-1">
                              <i className="bi bi-arrow-up-right" /> {o.contributes_to.length}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                  {(!p.objectives || p.objectives.length === 0) && (
                    <div className="col-12">
                      <div className="text-muted-2 small px-1 py-2">Nenhum objetivo nesta perspectiva.</div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* --- Perspectiva --- */}
      <Modal show={!!persp} onHide={() => setPersp(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title className="fs-6">{persp?.id ? "Editar perspectiva" : "Nova perspectiva"}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group className="mb-3">
            <Form.Label>Nome</Form.Label>
            <Form.Control
              autoFocus
              placeholder="Ex.: Sustentabilidade, Pessoas, ESG..."
              value={persp?.name || ""}
              onChange={(e) => setPersp({ ...persp!, name: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && savePerspective()}
            />
            <div className="text-muted-2 mt-1" style={{ fontSize: "0.74rem" }}>
              As quatro perspectivas iniciais são apenas o BSC como ponto de partida —
              você pode renomear, reordenar e criar quantas fizerem sentido.
            </div>
          </Form.Group>
          <Form.Group>
            <Form.Label>Cor da faixa</Form.Label>
            <div className="d-flex gap-2 flex-wrap">
              {PERSPECTIVE_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  aria-label={`Cor ${c}`}
                  onClick={() => setPersp({ ...persp!, color: c })}
                  style={{
                    width: 30, height: 30, borderRadius: 8, background: c,
                    border: persp?.color === c ? "3px solid var(--ink)" : "1px solid var(--border)",
                    cursor: "pointer",
                  }}
                />
              ))}
            </div>
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setPersp(null)}>Cancelar</Button>
          <Button onClick={savePerspective} disabled={!persp?.name}>Salvar</Button>
        </Modal.Footer>
      </Modal>

      {/* --- Objetivo --- */}
      <Modal show={!!editing} onHide={() => setEditing(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title className="fs-6">{editing?.id ? "Editar objetivo" : "Novo objetivo"}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group className="mb-3">
            <Form.Label>Nome</Form.Label>
            <Form.Control value={editing?.name || ""} onChange={(e) => setEditing({ ...editing!, name: e.target.value })} />
          </Form.Group>
          <Form.Group className="mb-3">
            <Form.Label>Descrição</Form.Label>
            <Form.Control as="textarea" rows={2} value={editing?.description || ""} onChange={(e) => setEditing({ ...editing!, description: e.target.value })} />
          </Form.Group>
          <Form.Group>
            <Form.Label>Dono</Form.Label>
            <Form.Select value={editing?.owner ?? ""} onChange={(e) => setEditing({ ...editing!, owner: e.target.value ? Number(e.target.value) : null })}>
              <option value="">—</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
            </Form.Select>
          </Form.Group>
          {(editing?.contributes_to?.length ?? 0) > 0 && (
            <div className="text-muted-2 small mt-3">
              <i className="bi bi-arrow-up-right me-1" />
              Contribui para {editing!.contributes_to!.length} objetivo(s). Use "Ligar objetivos"
              no diagrama para alterar.
            </div>
          )}
        </Modal.Body>
        <Modal.Footer className="justify-content-between">
          <div>{editing?.id && <Button variant="outline-danger" size="sm" onClick={deleteObjective}>Excluir</Button>}</div>
          <div className="d-flex gap-2">
            <Button variant="outline-secondary" onClick={() => setEditing(null)}>Cancelar</Button>
            <Button onClick={saveObjective} disabled={!editing?.name}>Salvar</Button>
          </div>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
