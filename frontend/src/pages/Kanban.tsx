import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Dropdown, Form, Modal, Nav } from "react-bootstrap";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { BAR_MAX_WIDTH, BAR_RADIUS_H, BAR_RADIUS_V, vizTokens } from "../charts/theme";
import { EChart } from "../components/EChart";
import { EmptyState, Meter, Panel, Skeleton, StatCard } from "../components/ui";
import { useTheme } from "../hooks/useTheme";
import { fmtDate } from "../utils/format";

interface Board { id: number; name: string; description: string; map: number | null; map_name: string; start_date: string | null; end_date: string | null; is_active: boolean; tasks_count: number }
interface Item { text: string; done: boolean }
interface Task {
  id: number; board: number; board_name: string; title: string; description: string; status: string; priority: string;
  responsible: number | null; responsible_name: string; watchers: number[]; watcher_names: string[]; due_date: string | null;
  checklist: Item[]; checklist_done: number; order: number; late: boolean; days_late: number; open_messages: number;
}
interface Evento { id: number; author_name: string; text: string; created_at: string }
interface Resposta { id: number; author: number | null; author_name: string; text: string; created_at: string }
interface Mensagem {
  id: number; task: number; task_title: string; task_status: string; board: number; sender: number | null; sender_name: string;
  recipient: number | null; recipient_name: string; text: string; status: string; status_label: string; replies: Resposta[]; created_at: string; updated_at: string;
}
interface Resumo { todos: number; pendente: number; aguardando: number; concluida: number; comigo: number }
interface Analise {
  total: number; por_status: Record<string, number>; atrasadas: number; conclusao_pct: number;
  por_board: { board: string; total: number }[];
  por_responsavel: { nome: string; total: number; concluidas: number; atrasadas: number; pct: number }[];
  lista_atrasadas: { id: number; title: string; board: string; responsible_name: string; priority: string; due_date: string; days_late: number }[];
}
interface Usuario { id: number; first_name: string; last_name?: string; email: string }
interface Mapa { id: number; name: string }

const COLUNAS: { key: string; label: string; icon: string; cls: string }[] = [
  { key: "a_fazer", label: "A fazer", icon: "bi-circle", cls: "st-neutro" },
  { key: "em_progresso", label: "Em progresso", icon: "bi-play-circle", cls: "st-amarelo" },
  { key: "bloqueado", label: "Bloqueado", icon: "bi-slash-circle", cls: "st-vermelho" },
  { key: "concluido", label: "Concluído", icon: "bi-check-circle", cls: "st-verde" },
];
const PRIORIDADE: Record<string, { label: string; cls: string }> = {
  baixa: { label: "Baixa", cls: "st-neutro" }, media: { label: "Média", cls: "st-amarelo" }, alta: { label: "Alta", cls: "st-vermelho" },
};
const MSG_STATUS: Record<string, string> = { pendente: "st-amarelo", aguardando: "st-neutro", concluida: "st-verde" };

const nomeDe = (u: Usuario) => [u.first_name, u.last_name].filter(Boolean).join(" ") || u.email;
const quando = (s: string) => new Date(s).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const erroDaApi = (e: unknown) => {
  const d = (e as ApiError).data;
  return Array.isArray(d) ? d.join(" ") : d && typeof d === "object" ? Object.values(d).flat().join(" ") : (e as Error).message;
};

// --- Conversa de uma mensagem -------------------------------------------------

function Conversa({ m, meuId, onChange }: { m: Mensagem; meuId: number | undefined; onChange: () => void }) {
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState("");
  const chamar = async (acao: string, body?: unknown) => {
    try { await api.post(`/api/kanban-mensagens/${m.id}/${acao}/`, body); setTexto(""); setErro(""); onChange(); }
    catch (e) { setErro(erroDaApi(e)); }
  };
  return (
    <div className="p-2 rounded mb-2" style={{ border: "1px solid var(--border)" }}>
      <div className="d-flex justify-content-between align-items-start gap-2">
        <div className="small text-muted-2">De <strong>{m.sender_name || "—"}</strong> para <strong>{m.recipient_name || "—"}</strong> · {quando(m.created_at)}</div>
        <span className={`status-pill ${MSG_STATUS[m.status]}`}>{m.status_label}</span>
      </div>
      <div className="small mt-1" style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
      {m.replies.map((r) => (
        <div key={r.id} className="small mt-2 p-2 rounded" style={{ background: "var(--surface-sunken)", whiteSpace: "pre-wrap" }}>
          <span className="fw-semibold">{r.author_name}</span> <span className="text-muted-2">· {quando(r.created_at)}</span><br />{r.text}
        </div>
      ))}
      {erro && <div className="small mt-2" style={{ color: "var(--st-vermelho)" }}>{erro}</div>}
      {m.status !== "concluida" ? (
        <div className="d-flex gap-2 mt-2">
          <Form.Control size="sm" as="textarea" rows={1} placeholder="Responder…" value={texto} onChange={(e) => setTexto(e.target.value)} />
          <Button size="sm" variant="outline-secondary" disabled={!texto.trim()} onClick={() => chamar("responder", { text: texto })}>Responder</Button>
          {m.sender === meuId && <Button size="sm" onClick={() => chamar("confirmar")} title="Quem pediu confirma que está resolvido"><i className="bi bi-check2 me-1" />Concluir</Button>}
        </div>
      ) : <Button size="sm" variant="link" className="p-0 mt-1" onClick={() => chamar("reabrir")}>Reabrir</Button>}
    </div>
  );
}

// --- Página ---------------------------------------------------------------------

export function Kanban() {
  const { me } = useAuth();
  const { isDark } = useTheme();
  const t = vizTokens(isDark);
  const gestor = me?.role !== "colaborador";

  const [aba, setAba] = useState<"board" | "analise" | "comunicacao">("board");
  const [boards, setBoards] = useState<Board[] | null>(null);
  const [boardId, setBoardId] = useState<number | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [mapas, setMapas] = useState<Mapa[]>([]);
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [fResp, setFResp] = useState("");
  const [fPrio, setFPrio] = useState("");
  const [soAtrasadas, setSoAtrasadas] = useState(false);
  const [busca, setBusca] = useState("");
  const [filtros, setFiltros] = useState(false);
  const [dragging, setDragging] = useState<Task | null>(null);
  const [sobre, setSobre] = useState<string | null>(null);
  const [editBoard, setEditBoard] = useState<Partial<Board> | null>(null);
  const [task, setTask] = useState<Partial<Task> | null>(null);
  const [painel, setPainel] = useState<"historico" | "comunicacao">("comunicacao");
  const [eventos, setEventos] = useState<Evento[]>([]);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [novaMsg, setNovaMsg] = useState<{ recipient: string; text: string }>({ recipient: "", text: "" });
  const [novoItem, setNovoItem] = useState("");
  const [erro, setErro] = useState("");
  // Análise e comunicação
  const [analise, setAnalise] = useState<Analise | null>(null);
  const [fBoardAnalise, setFBoardAnalise] = useState("");
  const [caixa, setCaixa] = useState<Mensagem[] | null>(null);
  const [fMsg, setFMsg] = useState("pendente");
  const [soMinhas, setSoMinhas] = useState(false);

  const loadBoards = useCallback(async () => {
    const lista = await api.get<Board[]>("/api/kanban-boards/").catch(() => [] as Board[]);
    setBoards(lista);
    setBoardId((atual) => (atual && lista.some((b) => b.id === atual) ? atual : lista.find((b) => b.is_active)?.id ?? lista[0]?.id ?? null));
  }, []);
  const loadTasks = useCallback(() => {
    if (!boardId) { setTasks([]); return; }
    api.get<Task[]>(`/api/kanban-tasks/?board=${boardId}`).then(setTasks).catch(() => setTasks([]));
  }, [boardId]);
  const loadResumo = useCallback(() => { api.get<Resumo>("/api/kanban-mensagens/resumo/").then(setResumo).catch(() => {}); }, []);

  useEffect(() => {
    loadBoards(); loadResumo();
    api.get<any>("/api/users/").then((d) => setUsuarios(d.results ?? d)).catch(() => {});
    api.get<any>("/api/strategic-maps/").then((d) => setMapas(d.results ?? d)).catch(() => {});
  }, [loadBoards, loadResumo]);
  useEffect(() => { loadTasks(); }, [loadTasks]);
  useEffect(() => {
    if (aba === "analise") api.get<Analise>(`/api/kanban-tasks/analise/${fBoardAnalise ? `?board=${fBoardAnalise}` : ""}`).then(setAnalise).catch(() => setAnalise(null));
  }, [aba, fBoardAnalise, tasks]);
  const loadCaixa = useCallback(() => {
    const q = new URLSearchParams();
    if (fMsg) q.set("status", fMsg);
    if (soMinhas) q.set("minhas", "1");
    api.get<Mensagem[]>(`/api/kanban-mensagens/?${q}`).then(setCaixa).catch(() => setCaixa([]));
    loadResumo();
  }, [fMsg, soMinhas, loadResumo]);
  useEffect(() => { if (aba === "comunicacao") loadCaixa(); }, [aba, loadCaixa]);

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return tasks.filter((x) => (!fResp || String(x.responsible ?? "") === fResp) && (!fPrio || x.priority === fPrio) && (!soAtrasadas || x.late) && (!q || `${x.title} ${x.description}`.toLowerCase().includes(q)));
  }, [tasks, fResp, fPrio, soAtrasadas, busca]);
  const nFiltros = [fResp, fPrio, soAtrasadas, busca.trim()].filter(Boolean).length;

  const board = boards?.find((b) => b.id === boardId) ?? null;

  // --- board
  const salvarBoard = async () => {
    if (!editBoard?.name?.trim()) { setErro("Dê um nome ao board."); return; }
    const body = { name: editBoard.name, description: editBoard.description ?? "", map: editBoard.map || null, start_date: editBoard.start_date || null, end_date: editBoard.end_date || null, is_active: editBoard.is_active ?? true };
    try {
      const salvo = editBoard.id ? await api.patch<Board>(`/api/kanban-boards/${editBoard.id}/`, body) : await api.post<Board>("/api/kanban-boards/", body);
      setEditBoard(null);
      await loadBoards();
      setBoardId(salvo.id);
    } catch (e) { setErro(erroDaApi(e)); }
  };
  const excluirBoard = async () => {
    if (!editBoard?.id) return;
    await api.del(`/api/kanban-boards/${editBoard.id}/`);
    setEditBoard(null);
    setBoardId(null);
    loadBoards();
  };

  // --- tarefa
  const abrirTask = (x: Task) => {
    setErro(""); setTask(x); setPainel(x.open_messages > 0 ? "comunicacao" : "historico"); setNovaMsg({ recipient: "", text: "" }); setNovoItem("");
    api.get<Evento[]>(`/api/kanban-tasks/${x.id}/historico/`).then(setEventos).catch(() => setEventos([]));
    api.get<Mensagem[]>(`/api/kanban-tasks/${x.id}/mensagens/`).then(setMensagens).catch(() => setMensagens([]));
  };
  const novaTask = (status: string) => { setErro(""); setEventos([]); setMensagens([]); setNovoItem(""); setTask({ board: boardId!, status, priority: "media", watchers: [], checklist: [], responsible: me?.id ?? null }); };
  const recarregarTask = async (id: number) => {
    const [x, ev, ms] = await Promise.all([api.get<Task>(`/api/kanban-tasks/${id}/`), api.get<Evento[]>(`/api/kanban-tasks/${id}/historico/`), api.get<Mensagem[]>(`/api/kanban-tasks/${id}/mensagens/`)]);
    setTask(x); setEventos(ev); setMensagens(ms); loadTasks(); loadResumo();
  };
  const salvarTask = async (fechar = true, dados: Partial<Task> | null = task) => {
    if (!dados?.title?.trim()) { setErro("Dê um título à tarefa."); return; }
    const body = { board: dados.board, title: dados.title, description: dados.description ?? "", status: dados.status, priority: dados.priority, responsible: dados.responsible || null, watchers: dados.watchers ?? [], due_date: dados.due_date || null, checklist: dados.checklist ?? [] };
    try {
      const salvo = dados.id ? await api.patch<Task>(`/api/kanban-tasks/${dados.id}/`, body) : await api.post<Task>("/api/kanban-tasks/", body);
      if (fechar) { setTask(null); loadTasks(); } else await recarregarTask(salvo.id);
    } catch (e) { setErro(erroDaApi(e)); }
  };
  const excluirTask = async () => { if (task?.id) { await api.del(`/api/kanban-tasks/${task.id}/`); setTask(null); loadTasks(); loadResumo(); } };
  const mover = async (x: Task, status: string) => {
    if (x.status === status) return;
    setTasks((l) => l.map((y) => (y.id === x.id ? { ...y, status } : y)));
    try { await api.patch(`/api/kanban-tasks/${x.id}/move/`, { status }); } finally { loadTasks(); }
  };
  // Checklist grava na hora quando a tarefa já existe: marcar um item não pode depender do botão Salvar.
  const mudarChecklist = (lista: Item[]) => { const nova = { ...task!, checklist: lista }; setTask(nova); if (nova.id) salvarTask(false, nova); };
  const enviarMsg = async () => {
    if (!task?.id || !novaMsg.recipient || !novaMsg.text.trim()) return;
    try { await api.post(`/api/kanban-tasks/${task.id}/mensagens/`, { recipient: Number(novaMsg.recipient), text: novaMsg.text }); setNovaMsg({ recipient: "", text: "" }); await recarregarTask(task.id); }
    catch (e) { setErro(erroDaApi(e)); }
  };

  if (boards === null) return <Panel><Skeleton height={360} /></Panel>;

  return (
    <div className="d-grid gap-3">
      <div className="d-flex flex-wrap align-items-center gap-2">
        <Nav variant="pills" activeKey={aba} onSelect={(k) => setAba(k as typeof aba)} className="me-auto">
          <Nav.Item><Nav.Link eventKey="board" className="py-1 px-3 small"><i className="bi bi-kanban me-1" />Board</Nav.Link></Nav.Item>
          <Nav.Item><Nav.Link eventKey="analise" className="py-1 px-3 small"><i className="bi bi-bar-chart me-1" />Análise</Nav.Link></Nav.Item>
          <Nav.Item><Nav.Link eventKey="comunicacao" className="py-1 px-3 small"><i className="bi bi-chat-left-text me-1" />Comunicação{!!resumo?.comigo && <span className="badge text-bg-danger ms-1" title="Esperando você">{resumo.comigo}</span>}</Nav.Link></Nav.Item>
        </Nav>
        {aba === "board" && (
          <>
            <Button size="sm" variant={nFiltros ? "primary" : "outline-secondary"} onClick={() => setFiltros(!filtros)}><i className="bi bi-funnel me-1" />Filtros{nFiltros > 0 && ` (${nFiltros})`}</Button>
            <Form.Select size="sm" value={boardId ?? ""} onChange={(e) => setBoardId(Number(e.target.value))} style={{ width: 220 }} aria-label="Board" disabled={boards.length === 0}>
              {boards.length === 0 && <option value="">Nenhum board</option>}
              {boards.map((b) => <option key={b.id} value={b.id}>{b.name}{b.map_name ? ` · ${b.map_name}` : ""}{b.is_active ? "" : " (inativo)"}</option>)}
            </Form.Select>
            {gestor && board && (
              <Dropdown align="end">
                <Dropdown.Toggle size="sm" variant="outline-secondary" aria-label="Opções do board"><i className="bi bi-three-dots" /></Dropdown.Toggle>
                <Dropdown.Menu>
                  <Dropdown.Item onClick={() => { setErro(""); setEditBoard(board); }}><i className="bi bi-pencil me-2" />Editar board</Dropdown.Item>
                </Dropdown.Menu>
              </Dropdown>
            )}
            {gestor && <Button size="sm" onClick={() => { setErro(""); setEditBoard({ is_active: true }); }}><i className="bi bi-plus-lg me-1" />Novo board</Button>}
          </>
        )}
      </div>

      {aba === "board" && filtros && (
        <Panel>
          <div className="d-flex flex-wrap align-items-center gap-2">
            <Form.Control size="sm" placeholder="Buscar tarefa…" value={busca} onChange={(e) => setBusca(e.target.value)} style={{ width: 200 }} />
            <Form.Select size="sm" value={fResp} onChange={(e) => setFResp(e.target.value)} style={{ width: 190 }}><option value="">Todos os responsáveis</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{nomeDe(u)}</option>)}</Form.Select>
            <Form.Select size="sm" value={fPrio} onChange={(e) => setFPrio(e.target.value)} style={{ width: 170 }}><option value="">Todas as prioridades</option>{Object.entries(PRIORIDADE).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Form.Select>
            <Form.Check type="switch" id="kb-atrasadas" className="small" label="Só atrasadas" checked={soAtrasadas} onChange={(e) => setSoAtrasadas(e.target.checked)} />
            <Button size="sm" variant="link" onClick={() => { setBusca(""); setFResp(""); setFPrio(""); setSoAtrasadas(false); }}>Limpar</Button>
          </div>
        </Panel>
      )}

      {aba === "board" && (boards.length === 0 ? (
        <Panel><EmptyState icon="bi-kanban" title="Nenhum board ainda" hint="Crie um board para cada frente de trabalho, sprint ou cliente." action={gestor ? <Button size="sm" onClick={() => setEditBoard({ is_active: true })}>Novo board</Button> : undefined} /></Panel>
      ) : (
        <div className="row g-3">
          {COLUNAS.map((c) => {
            const lista = visiveis.filter((x) => x.status === c.key);
            return (
              <div className="col-md-6 col-xl-3" key={c.key}>
                <div className="rounded h-100 p-2" style={{ background: "var(--surface-sunken)", border: `1px ${sobre === c.key ? "dashed var(--brand)" : "solid var(--border)"}`, minHeight: 420 }}
                  onDragOver={(e) => { e.preventDefault(); setSobre(c.key); }} onDragLeave={() => setSobre(null)}
                  onDrop={() => { if (dragging) mover(dragging, c.key); setDragging(null); setSobre(null); }}>
                  <div className="d-flex align-items-center mb-2 px-1">
                    <span className={`status-pill ${c.cls}`}><i className={`bi ${c.icon}`} aria-hidden="true" />{c.label}</span>
                    <span className="small text-muted-2 ms-2">{lista.length}</span>
                    <Button size="sm" variant="link" className="p-0 ms-auto" title={`Nova tarefa em ${c.label}`} onClick={() => novaTask(c.key)}><i className="bi bi-plus-lg" /></Button>
                  </div>
                  {lista.map((x) => (
                    <div key={x.id} draggable onDragStart={() => setDragging(x)} onDragEnd={() => { setDragging(null); setSobre(null); }} onClick={() => abrirTask(x)} role="button"
                      className="p-2 rounded mb-2" style={{ background: "var(--surface)", border: "1px solid var(--border)", opacity: dragging?.id === x.id ? 0.5 : 1 }}>
                      <div className="fw-semibold small">{x.title}</div>
                      {x.description && <div className="small text-muted-2 text-truncate">{x.description}</div>}
                      <div className="d-flex flex-wrap align-items-center gap-2 mt-1 small text-muted-2">
                        <span className={`status-pill ${PRIORIDADE[x.priority]?.cls}`}>{PRIORIDADE[x.priority]?.label}</span>
                        {x.responsible_name && <span><i className="bi bi-person me-1" />{x.responsible_name}</span>}
                        {x.due_date && <span style={x.late ? { color: "var(--st-vermelho)", fontWeight: 600 } : undefined}><i className={`bi ${x.late ? "bi-exclamation-triangle" : "bi-calendar3"} me-1`} />{fmtDate(x.due_date).slice(0, 5)}{x.late && ` · ${x.days_late}d`}</span>}
                        {x.checklist.length > 0 && <span><i className="bi bi-check2-square me-1" />{x.checklist_done}/{x.checklist.length}</span>}
                        {x.open_messages > 0 && <span title="Mensagens em aberto"><i className="bi bi-chat-left-text me-1" />{x.open_messages}</span>}
                      </div>
                    </div>
                  ))}
                  {lista.length === 0 && <div className="small text-muted-2 text-center py-4">Arraste uma tarefa para cá</div>}
                </div>
              </div>
            );
          })}
        </div>
      ))}

      {aba === "analise" && (!analise ? <Panel><Skeleton height={300} /></Panel> : (
        <>
          <div className="d-flex align-items-center gap-2">
            <span className="small text-muted-2"><i className="bi bi-funnel me-1" />Board:</span>
            <Form.Select size="sm" value={fBoardAnalise} onChange={(e) => setFBoardAnalise(e.target.value)} style={{ width: 240 }}><option value="">Todos os boards</option>{boards.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Form.Select>
          </div>
          <div className="row g-3">
            <div className="col-6 col-md-4 col-xl"><StatCard icon="bi-list-task" label="Total" value={analise.total} /></div>
            {COLUNAS.map((c) => <div className="col-6 col-md-4 col-xl" key={c.key}><StatCard icon={c.icon} label={c.label} value={analise.por_status[c.key] ?? 0} /></div>)}
            <div className="col-6 col-md-4 col-xl"><StatCard icon="bi-exclamation-triangle" label="Atrasadas" value={analise.atrasadas} /></div>
            <div className="col-6 col-md-4 col-xl"><StatCard icon="bi-graph-up" label="Conclusão" value={`${analise.conclusao_pct}%`} /></div>
          </div>
          <div className="row g-3">
            <div className="col-xl-6">
              <Panel title="Distribuição por status" className="h-100">
                {analise.total === 0 ? <EmptyState icon="bi-kanban" title="Sem tarefas" /> : (
                  <EChart height={190} option={{
                    grid: { left: 4, right: 36, top: 4, bottom: 4, containLabel: true },
                    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
                    xAxis: { type: "value", minInterval: 1 },
                    yAxis: { type: "category", inverse: true, data: COLUNAS.map((c) => c.label) },
                    series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, label: { show: true, position: "right" },
                      data: COLUNAS.map((c) => ({ value: analise.por_status[c.key] ?? 0, itemStyle: { borderRadius: BAR_RADIUS_H, color: { a_fazer: t.status.sem_meta, em_progresso: t.series[0], bloqueado: t.status.vermelho, concluido: t.status.verde }[c.key] } })) }],
                  }} />
                )}
              </Panel>
            </div>
            <div className="col-xl-6">
              <Panel title="Tarefas por board" className="h-100">
                {analise.por_board.length === 0 ? <EmptyState icon="bi-kanban" title="Sem tarefas" /> : (
                  <EChart height={190} option={{
                    grid: { left: 4, right: 8, top: 20, bottom: 4, containLabel: true },
                    tooltip: { trigger: "axis" },
                    xAxis: { type: "category", data: analise.por_board.map((b) => b.board), axisLabel: { interval: 0 } },
                    yAxis: { type: "value", minInterval: 1 },
                    series: [{ type: "bar", barMaxWidth: BAR_MAX_WIDTH, itemStyle: { color: t.series[0], borderRadius: BAR_RADIUS_V }, label: { show: true, position: "top" }, data: analise.por_board.map((b) => b.total) }],
                  }} />
                )}
              </Panel>
            </div>
          </div>
          <div className="row g-3">
            <div className="col-xl-6">
              <Panel title="Desempenho por responsável" subtitle="Concluídas sobre o total de cada um" className="h-100">
                {analise.por_responsavel.length === 0 ? <EmptyState icon="bi-people" title="Sem tarefas" /> : analise.por_responsavel.map((r) => (
                  <div key={r.nome} className="mb-3">
                    <div className="d-flex justify-content-between small"><span className="fw-semibold">{r.nome}{r.atrasadas > 0 && <span className="text-muted-2 fw-normal ms-2">{r.atrasadas} atrasada(s)</span>}</span><span className="num">{r.pct}% · {r.concluidas}/{r.total}</span></div>
                    <Meter pct={r.pct} />
                  </div>
                ))}
              </Panel>
            </div>
            <div className="col-xl-6">
              <Panel title={`Tarefas atrasadas (${analise.atrasadas})`} className="h-100">
                {analise.lista_atrasadas.length === 0 ? <EmptyState icon="bi-check2-circle" title="Nenhuma tarefa atrasada" /> : analise.lista_atrasadas.map((x) => (
                  <div key={x.id} className="d-flex align-items-center gap-2 p-2 rounded mb-2" style={{ background: "var(--surface-sunken)" }}>
                    <div className="flex-grow-1 min-w-0"><div className="fw-semibold small text-truncate">{x.title}</div><div className="small text-muted-2">{[x.board, x.responsible_name].filter(Boolean).join(" · ")} <span className={`status-pill ${PRIORIDADE[x.priority]?.cls} ms-1`}>{PRIORIDADE[x.priority]?.label}</span></div></div>
                    <div className="text-end small text-nowrap"><div style={{ color: "var(--st-vermelho)", fontWeight: 600 }}>{x.days_late}d atrasada</div><div className="text-muted-2">{fmtDate(x.due_date)}</div></div>
                  </div>
                ))}
              </Panel>
            </div>
          </div>
        </>
      ))}

      {aba === "comunicacao" && (
        <Panel title="Comunicação" subtitle="Pedidos feitos dentro das tarefas. Pendente: esperando a resposta de quem recebeu. Aguardando confirmação: respondido, falta quem pediu concluir."
          actions={gestor ? <Form.Check type="switch" id="kb-minhas" className="small" label="Só as minhas" checked={soMinhas} onChange={(e) => setSoMinhas(e.target.checked)} /> : undefined}>
          <div className="d-flex flex-wrap gap-2 mb-3">
            {([["", "Todos", resumo?.todos], ["pendente", "Pendente", resumo?.pendente], ["aguardando", "Aguardando confirmação", resumo?.aguardando], ["concluida", "Concluída", resumo?.concluida]] as [string, string, number | undefined][]).map(([k, l, n]) => (
              <button key={k} type="button" className={`btn btn-sm ${fMsg === k ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setFMsg(k)}>{l} <span className="badge text-bg-light border ms-1">{n ?? 0}</span></button>
            ))}
          </div>
          {caixa === null ? <Skeleton height={160} /> : caixa.length === 0 ? <EmptyState icon="bi-chat-left-text" title="Nenhuma mensagem aqui" hint="As mensagens são enviadas de dentro da tarefa, na aba Comunicação dela." /> : caixa.map((m) => (
            <div key={m.id}>
              <div className="small fw-semibold mb-1"><i className="bi bi-card-text me-1 text-muted-2" />{m.task_title} <span className="text-muted-2 fw-normal">· {COLUNAS.find((c) => c.key === m.task_status)?.label}</span></div>
              <Conversa m={m} meuId={me?.id} onChange={loadCaixa} />
            </div>
          ))}
        </Panel>
      )}

      {/* Board */}
      <Modal show={!!editBoard} onHide={() => setEditBoard(null)}>
        <Modal.Header closeButton><Modal.Title>{editBoard?.id ? "Editar board" : "Novo board"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {editBoard && (
            <div className="row g-3">
              {erro && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erro}</Alert></div>}
              <div className="col-12"><Form.Label>Nome *</Form.Label><Form.Control autoFocus value={editBoard.name ?? ""} onChange={(e) => setEditBoard({ ...editBoard, name: e.target.value })} placeholder="Ex.: Sprint de setembro, Cliente X" /></div>
              <div className="col-12"><Form.Label>Descrição</Form.Label><Form.Control as="textarea" rows={2} value={editBoard.description ?? ""} onChange={(e) => setEditBoard({ ...editBoard, description: e.target.value })} /></div>
              <div className="col-12"><Form.Label>Planejamento</Form.Label><Form.Select value={editBoard.map ?? ""} onChange={(e) => setEditBoard({ ...editBoard, map: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{mapas.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</Form.Select></div>
              <div className="col-6"><Form.Label>Início</Form.Label><Form.Control type="date" value={editBoard.start_date ?? ""} onChange={(e) => setEditBoard({ ...editBoard, start_date: e.target.value })} /></div>
              <div className="col-6"><Form.Label>Fim</Form.Label><Form.Control type="date" value={editBoard.end_date ?? ""} onChange={(e) => setEditBoard({ ...editBoard, end_date: e.target.value })} /></div>
              <div className="col-12"><Form.Check type="switch" id="kb-board-ativo" label="Ativo" checked={editBoard.is_active ?? true} onChange={(e) => setEditBoard({ ...editBoard, is_active: e.target.checked })} /></div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          {editBoard?.id && <Button variant="outline-danger" className="me-auto" onClick={excluirBoard} title="Exclui o board e todas as tarefas dele">Excluir board{editBoard.tasks_count ? ` e ${editBoard.tasks_count} tarefa(s)` : ""}</Button>}
          <Button variant="outline-secondary" onClick={() => setEditBoard(null)}>Cancelar</Button>
          <Button onClick={salvarBoard}>Salvar</Button>
        </Modal.Footer>
      </Modal>

      {/* Tarefa */}
      <Modal show={!!task} onHide={() => { setTask(null); loadTasks(); }} size="xl" scrollable>
        <Modal.Header closeButton><Modal.Title>{task?.id ? "Tarefa" : "Nova tarefa"}</Modal.Title></Modal.Header>
        <Modal.Body>
          {task && (
            <div className="row g-4">
              <div className={task.id ? "col-lg-6" : "col-12"}>
                <div className="row g-3">
                  {erro && <div className="col-12"><Alert variant="danger" className="mb-0 py-2 small">{erro}</Alert></div>}
                  <div className="col-12"><Form.Label>Título *</Form.Label><Form.Control autoFocus={!task.id} value={task.title ?? ""} onChange={(e) => setTask({ ...task, title: e.target.value })} /></div>
                  <div className="col-md-4"><Form.Label>Coluna</Form.Label><Form.Select value={task.status} onChange={(e) => setTask({ ...task, status: e.target.value })}>{COLUNAS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</Form.Select></div>
                  <div className="col-md-4"><Form.Label>Prioridade</Form.Label><Form.Select value={task.priority} onChange={(e) => setTask({ ...task, priority: e.target.value })}>{Object.entries(PRIORIDADE).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Form.Select></div>
                  <div className="col-md-4"><Form.Label>Prazo</Form.Label><Form.Control type="date" value={task.due_date ?? ""} onChange={(e) => setTask({ ...task, due_date: e.target.value })} /></div>
                  <div className="col-12"><Form.Label>Responsável</Form.Label><Form.Select value={task.responsible ?? ""} onChange={(e) => setTask({ ...task, responsible: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{usuarios.map((u) => <option key={u.id} value={u.id}>{nomeDe(u)}</option>)}</Form.Select></div>
                  <div className="col-12">
                    <div className="d-flex justify-content-between"><Form.Label>Pessoas vinculadas</Form.Label><Button variant="link" size="sm" className="p-0" onClick={() => setTask({ ...task, watchers: usuarios.map((u) => u.id) })}>Vincular todos</Button></div>
                    <div className="d-flex flex-wrap gap-1">{usuarios.map((u) => { const on = task.watchers?.includes(u.id); return <button type="button" key={u.id} className={`btn btn-sm ${on ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setTask({ ...task, watchers: on ? task.watchers!.filter((i) => i !== u.id) : [...(task.watchers ?? []), u.id] })}>{nomeDe(u)}</button>; })}</div>
                    <Form.Text>Também acompanham a tarefa e participam da comunicação.</Form.Text>
                  </div>
                  <div className="col-12"><Form.Label>Descrição</Form.Label><Form.Control as="textarea" rows={3} value={task.description ?? ""} onChange={(e) => setTask({ ...task, description: e.target.value })} /></div>
                  <div className="col-12">
                    <Form.Label><i className="bi bi-check2-square me-1" />Checklist{(task.checklist?.length ?? 0) > 0 && ` · ${task.checklist!.filter((i) => i.done).length}/${task.checklist!.length}`}</Form.Label>
                    {(task.checklist ?? []).map((item, i) => (
                      <div key={i} className="d-flex align-items-center gap-2">
                        <Form.Check id={`kb-item-${i}`} checked={item.done} label={<span style={item.done ? { textDecoration: "line-through", opacity: 0.6 } : undefined}>{item.text}</span>} className="flex-grow-1 small"
                          onChange={(e) => mudarChecklist(task.checklist!.map((x, j) => (j === i ? { ...x, done: e.target.checked } : x)))} />
                        <Button size="sm" variant="link" className="p-0 text-muted-2" aria-label="Remover item" onClick={() => mudarChecklist(task.checklist!.filter((_, j) => j !== i))}><i className="bi bi-x-lg" /></Button>
                      </div>
                    ))}
                    <div className="d-flex gap-2 mt-1">
                      <Form.Control size="sm" placeholder="Adicionar item…" value={novoItem} onChange={(e) => setNovoItem(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter" && novoItem.trim()) { e.preventDefault(); mudarChecklist([...(task.checklist ?? []), { text: novoItem.trim(), done: false }]); setNovoItem(""); } }} />
                      <Button size="sm" variant="outline-secondary" disabled={!novoItem.trim()} onClick={() => { mudarChecklist([...(task.checklist ?? []), { text: novoItem.trim(), done: false }]); setNovoItem(""); }}>Adicionar</Button>
                    </div>
                  </div>
                </div>
              </div>

              {task.id && (
                <div className="col-lg-6">
                  <Nav variant="pills" activeKey={painel} onSelect={(k) => setPainel(k as typeof painel)} className="mb-3">
                    <Nav.Item><Nav.Link eventKey="comunicacao" className="py-1 px-3 small"><i className="bi bi-chat-left-text me-1" />Comunicação ({mensagens.length})</Nav.Link></Nav.Item>
                    <Nav.Item><Nav.Link eventKey="historico" className="py-1 px-3 small"><i className="bi bi-clock-history me-1" />Histórico ({eventos.length})</Nav.Link></Nav.Item>
                  </Nav>
                  {painel === "historico" ? (
                    eventos.length === 0 ? <div className="small text-muted-2">Sem histórico.</div> : eventos.map((ev) => (
                      <div key={ev.id} className="small py-1" style={{ borderBottom: "1px solid var(--border)" }}><span className="text-muted-2">{quando(ev.created_at)}</span> · <span className="fw-semibold">{ev.author_name || "—"}</span> · {ev.text}</div>
                    ))
                  ) : (
                    <>
                      {mensagens.length === 0 && <div className="small text-muted-2 mb-3">Nenhuma mensagem nesta tarefa.</div>}
                      {mensagens.map((m) => <Conversa key={m.id} m={m} meuId={me?.id} onChange={() => recarregarTask(task.id!)} />)}
                      <div className="p-2 rounded" style={{ background: "var(--surface-sunken)" }}>
                        <div className="small fw-semibold mb-2">Nova mensagem</div>
                        <Form.Select size="sm" className="mb-2" value={novaMsg.recipient} onChange={(e) => setNovaMsg({ ...novaMsg, recipient: e.target.value })}><option value="">Para quem?</option>{usuarios.filter((u) => u.id !== me?.id).map((u) => <option key={u.id} value={u.id}>{nomeDe(u)}</option>)}</Form.Select>
                        <Form.Control size="sm" as="textarea" rows={2} placeholder="O que você precisa?" value={novaMsg.text} onChange={(e) => setNovaMsg({ ...novaMsg, text: e.target.value })} />
                        <div className="text-end mt-2"><Button size="sm" onClick={enviarMsg} disabled={!novaMsg.recipient || !novaMsg.text.trim()}><i className="bi bi-send me-1" />Enviar</Button></div>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          {task?.id && gestor && <Button variant="outline-danger" className="me-auto" onClick={excluirTask}>Excluir tarefa</Button>}
          <Button variant="outline-secondary" onClick={() => { setTask(null); loadTasks(); }}>Fechar</Button>
          <Button onClick={() => salvarTask(true)}>{task?.id ? "Salvar" : "Criar"}</Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
