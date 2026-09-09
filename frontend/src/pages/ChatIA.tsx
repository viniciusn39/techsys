import { useCallback, useEffect, useState } from "react";
import { Button } from "react-bootstrap";
import { api } from "../api/client";
import { ConversaIA } from "../components/ConversaIA";
import type { ChatSession } from "../types";

const rel = (iso: string) => {
  const d = new Date(iso); const hoje = new Date();
  if (d.toDateString() === hoje.toDateString()) return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
};

export function ChatIA() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [current, setCurrent] = useState<ChatSession | null>(null);

  const loadSessions = useCallback(async () => {
    const data = await api.get<ChatSession[]>("/api/ai/chat/sessions/");
    setSessions(data);
    return data;
  }, []);

  useEffect(() => {
    loadSessions().catch(() => {});
  }, [loadSessions]);

  const openSession = async (id: number) => {
    setCurrent(await api.get<ChatSession>(`/api/ai/chat/sessions/${id}/`));
  };

  const removeSession = async (id: number) => {
    await api.del(`/api/ai/chat/sessions/${id}/`);
    if (current?.id === id) setCurrent(null);
    loadSessions();
  };

  const onSessionChange = (s: ChatSession) => {
    setCurrent(s);
    if (!sessions.some((x) => x.id === s.id) || s.messages.length <= 2) loadSessions();
  };

  return (
    <div className="d-flex gap-3" style={{ height: "calc(100vh - 9rem)" }}>
      <div className="d-flex flex-column" style={{ width: 260, minWidth: 260 }}>
        <Button size="sm" className="mb-2" onClick={() => setCurrent(null)}>
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
              <span className="text-truncate flex-grow-1">{s.title || "Conversa"}</span>
              <span className="text-muted-2" style={{ fontSize: "0.7rem" }}>{rel(s.updated_at || s.created_at)}</span>
              <i
                className="bi bi-trash3 opacity-50"
                role="button"
                title="Apagar conversa"
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
        <div className="text-muted-2 mt-2" style={{ fontSize: "0.72rem" }}>
          <i className="bi bi-shield-check me-1" />O assistente vê só os dados da sua empresa e respeita o seu perfil de acesso.
        </div>
      </div>

      <div className="flex-grow-1 d-flex flex-column panel overflow-hidden">
        <div className="p-3 border-bottom d-flex align-items-center gap-2" style={{ borderColor: "var(--border)" }}>
          <span className="chat-avatar"><i className="bi bi-stars" /></span>
          <div className="flex-grow-1 min-w-0">
            <strong>{current?.title || "Assistente de Resultados"}</strong>
            <div className="text-muted-2 small">
              Responde sobre mapa estratégico, metas, indicadores, desvios, planos de ação, SWOT, agenda e chamados, e explica como usar cada tela.
            </div>
          </div>
        </div>
        <ConversaIA session={current} onSessionChange={onSessionChange} autoFocus />
      </div>
    </div>
  );
}
