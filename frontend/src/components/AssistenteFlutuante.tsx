import { useEffect, useState } from "react";
import { Dropdown } from "react-bootstrap";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { ChatSession } from "../types";
import { ConversaIA } from "./ConversaIA";

/** Botão flutuante presente em todas as páginas que abre o assistente num painel lateral. */
export function AssistenteFlutuante() {
  const location = useLocation();
  const [aberto, setAberto] = useState(false);
  const [session, setSession] = useState<ChatSession | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  useEffect(() => {
    if (!aberto) return;
    api.get<ChatSession[]>("/api/ai/chat/sessions/").then(setSessions).catch(() => {});
  }, [aberto, session?.messages.length]);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setAberto(false); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  if (location.pathname.startsWith("/ia/chat")) return null;

  const abrir = async (id: number) => {
    setSession(await api.get<ChatSession>(`/api/ai/chat/sessions/${id}/`));
  };

  return (
    <>
      <button
        className={`assistente-fab ${aberto ? "is-open" : ""}`}
        onClick={() => setAberto(!aberto)}
        title={aberto ? "Fechar assistente" : "Perguntar ao assistente"}
        aria-label="Assistente de IA"
      >
        <i className={`bi ${aberto ? "bi-x-lg" : "bi-stars"}`} />
      </button>

      {aberto && <div className="assistente-backdrop" onClick={() => setAberto(false)} />}

      <aside className={`assistente-panel ${aberto ? "is-open" : ""}`} aria-hidden={!aberto}>
        <div className="assistente-panel-head">
          <span className="chat-avatar"><i className="bi bi-stars" /></span>
          <div className="flex-grow-1 min-w-0">
            <div className="fw-semibold">Assistente</div>
            <div className="text-muted-2 text-truncate" style={{ fontSize: "0.72rem" }}>
              {session?.title ? session.title : "Pergunte sobre qualquer parte do sistema"}
            </div>
          </div>
          {sessions.length > 0 && (
            <Dropdown align="end">
              <Dropdown.Toggle size="sm" variant="outline-secondary" title="Conversas recentes" className="no-caret"><i className="bi bi-clock-history" /></Dropdown.Toggle>
              <Dropdown.Menu style={{ maxWidth: 320 }}>
                {sessions.slice(0, 8).map((s) => (
                  <Dropdown.Item key={s.id} className="small text-truncate" onClick={() => abrir(s.id)}>{s.title || "Conversa"}</Dropdown.Item>
                ))}
              </Dropdown.Menu>
            </Dropdown>
          )}
          <button className="btn btn-sm btn-outline-secondary" onClick={() => setSession(null)} title="Nova conversa"><i className="bi bi-plus-lg" /></button>
          <Link to="/ia/chat" className="btn btn-sm btn-outline-secondary" title="Abrir a página completa" onClick={() => setAberto(false)}><i className="bi bi-arrows-angle-expand" /></Link>
          <button className="btn btn-sm btn-outline-secondary" onClick={() => setAberto(false)} title="Fechar"><i className="bi bi-x-lg" /></button>
        </div>
        <div className="flex-grow-1 min-h-0">
          {aberto && <ConversaIA session={session} onSessionChange={setSession} compact autoFocus sugestoes={[
            "O que está vermelho neste mês?",
            "Quais planos precisam de atenção?",
            "Como registro o acompanhamento de um plano?",
          ]} />}
        </div>
      </aside>
    </>
  );
}
