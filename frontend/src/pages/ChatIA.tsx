import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Form } from "react-bootstrap";
import { api } from "../api/client";
import type { ChatSession } from "../types";

const SUGESTOES = [
  "Quais indicadores estão vermelhos e o que está sendo feito?",
  "Resuma o desempenho do trimestre por área.",
  "Quais riscos você vê para as metas do ano?",
  "Sugira contramedidas para o indicador com pior atingimento.",
];

export function ChatIA() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [current, setCurrent] = useState<ChatSession | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadSessions = useCallback(async () => {
    const data = await api.get<ChatSession[]>("/api/ai/chat/sessions/");
    setSessions(data);
    return data;
  }, []);

  useEffect(() => {
    loadSessions().catch(() => {});
  }, [loadSessions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [current?.messages.length, sending]);

  const openSession = async (id: number) => {
    setCurrent(await api.get<ChatSession>(`/api/ai/chat/sessions/${id}/`));
    setError("");
  };

  const newSession = async () => {
    const s = await api.post<ChatSession>("/api/ai/chat/sessions/", {});
    await loadSessions();
    setCurrent(s);
    setError("");
  };

  const send = async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    let session = current;
    if (!session) {
      session = await api.post<ChatSession>("/api/ai/chat/sessions/", {});
      setCurrent(session);
    }
    setInput("");
    setSending(true);
    setError("");
    setCurrent({
      ...session,
      messages: [...session.messages, { id: -1, role: "user", content, created_at: "" }],
    });
    try {
      await api.post(`/api/ai/chat/sessions/${session.id}/messages/`, { content });
      await openSession(session.id);
      loadSessions();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  };

  const removeSession = async (id: number) => {
    await api.del(`/api/ai/chat/sessions/${id}/`);
    if (current?.id === id) setCurrent(null);
    loadSessions();
  };

  return (
    <div className="d-flex gap-3" style={{ height: "calc(100vh - 9rem)" }}>
      <div className="d-flex flex-column" style={{ width: 250, minWidth: 250 }}>
        <Button size="sm" className="mb-2" onClick={newSession}>
          <i className="bi bi-plus-lg me-1" />Nova conversa
        </Button>
        <div className="overflow-auto flex-grow-1 d-flex flex-column gap-1">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`chat-session d-flex align-items-center gap-2 ${current?.id === s.id ? "active" : ""}`}
              onClick={() => openSession(s.id)}
            >
              <i className="bi bi-chat-left-text flex-none" />
              <span className="text-truncate flex-grow-1">{s.title}</span>
              <i
                className="bi bi-trash3 opacity-50"
                role="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeSession(s.id);
                }}
              />
            </div>
          ))}
          {sessions.length === 0 && (
            <div className="text-muted-2 small text-center py-3">Nenhuma conversa ainda.</div>
          )}
        </div>
      </div>

      <div className="flex-grow-1 d-flex flex-column panel overflow-hidden">
        <div className="p-3 border-bottom" style={{ borderColor: "var(--border)" }}>
          <strong className="d-flex align-items-center gap-2">
            <span
              style={{
                width: 26, height: 26, borderRadius: 8, display: "grid", placeItems: "center",
                background: "var(--brand-soft)", color: "var(--brand)",
              }}
            >
              <i className="bi bi-stars" />
            </span>
            Assistente de Resultados
          </strong>
          <div className="text-muted-2 small mt-1">
            Responde com base nos indicadores, metas, desvios e planos da sua empresa.
          </div>
        </div>

        <div className="flex-grow-1 overflow-auto p-3 chat-list">
          {!current || current.messages.length === 0 ? (
            <div className="text-center py-5">
              <i className="bi bi-stars" style={{ fontSize: "2rem", color: "var(--brand)", opacity: 0.7 }} />
              <div className="fw-semibold mt-2">Comece por uma pergunta</div>
              <div className="d-flex flex-column align-items-center gap-2 mt-3">
                {SUGESTOES.map((s) => (
                  <button
                    key={s}
                    className="btn btn-sm btn-outline-secondary"
                    style={{ maxWidth: 460 }}
                    onClick={() => send(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            current.messages.map((m, idx) => (
              <div
                key={idx}
                className={`mb-2 ${m.role === "user" ? "chat-bubble-user" : "chat-bubble-assistant"}`}
              >
                <div className="markdown-body" style={m.role === "user" ? { color: "#fff" } : undefined}>
                  {m.content}
                </div>
              </div>
            ))
          )}
          {sending && (
            <div className="chat-bubble-assistant mb-2 d-flex align-items-center gap-2 text-muted-2">
              <span className="spinner-grow spinner-grow-sm" />
              Analisando os seus resultados…
            </div>
          )}
          {error && <div className="alert alert-warning py-2 small mt-2">{error}</div>}
          <div ref={bottomRef} />
        </div>

        <div className="p-3 border-top d-flex gap-2" style={{ borderColor: "var(--border)" }}>
          <Form.Control
            placeholder="Escreva sua pergunta..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
            disabled={sending}
          />
          <Button onClick={() => send()} disabled={sending || !input.trim()}>
            <i className="bi bi-send" />
          </Button>
        </div>
      </div>
    </div>
  );
}
