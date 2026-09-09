import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ChatSession } from "../types";
import { Markdown } from "./Markdown";

export const SUGESTOES_IA = [
  "Quais indicadores estão vermelhos e o que está sendo feito?",
  "Resuma o desempenho do mês por área.",
  "Quais planos de ação estão parados ou sem acompanhamento?",
  "Sugira contramedidas para o indicador com pior atingimento.",
  "Como está o objetivo financeiro do mapa estratégico?",
  "Quais riscos você vê para as metas do ano?",
];

const hora = (iso: string) => (iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "");

/** Conversa com o assistente: lista de mensagens, sugestões e caixa de envio.
 *  Usada na página do assistente e no painel flutuante. */
export function ConversaIA({ session, onSessionChange, compact = false, sugestoes = SUGESTOES_IA, autoFocus = false }: {
  session: ChatSession | null;
  onSessionChange: (s: ChatSession) => void;
  compact?: boolean;
  sugestoes?: string[];
  autoFocus?: boolean;
}) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [session?.messages.length, sending]);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus, session?.id]);

  const send = async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    let s = session;
    if (!s) {
      s = await api.post<ChatSession>("/api/ai/chat/sessions/", {});
    }
    setInput("");
    setSending(true);
    setError("");
    onSessionChange({ ...s, messages: [...s.messages, { id: -1, role: "user", content, created_at: new Date().toISOString() }] });
    try {
      await api.post(`/api/ai/chat/sessions/${s.id}/messages/`, { content });
      onSessionChange(await api.get<ChatSession>(`/api/ai/chat/sessions/${s.id}/`));
    } catch (e: any) {
      setError(e.message || "Não foi possível obter resposta agora.");
      onSessionChange(await api.get<ChatSession>(`/api/ai/chat/sessions/${s.id}/`).catch(() => s!));
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const vazio = !session || session.messages.length === 0;

  return (
    <div className="conversa-ia d-flex flex-column h-100 min-h-0">
      <div className={`flex-grow-1 overflow-auto chat-list ${compact ? "p-2" : "p-3"}`}>
        {vazio ? (
          <div className={`text-center ${compact ? "py-3" : "py-5"}`}>
            <span className="chat-avatar chat-avatar-lg mx-auto"><i className="bi bi-stars" /></span>
            <div className="fw-semibold mt-2">Como posso ajudar?</div>
            <div className="text-muted-2 small mb-3">Pergunte sobre resultados, desvios, planos ou como usar o sistema.</div>
            <div className="d-flex flex-column align-items-center gap-2">
              {sugestoes.map((s) => (
                <button key={s} className="chat-sugestao" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        ) : (
          session!.messages.map((m, idx) => (
            m.role === "user" ? (
              <div key={idx} className="chat-msg chat-msg-user">
                <div className="chat-bubble chat-bubble-user">{m.content}</div>
                <div className="chat-meta">Você · {hora(m.created_at)}</div>
              </div>
            ) : (
              <div key={idx} className="chat-msg chat-msg-assistant">
                <span className="chat-avatar"><i className="bi bi-stars" /></span>
                <div className="min-w-0 flex-grow-1">
                  <div className="chat-bubble chat-bubble-assistant"><Markdown text={m.content} /></div>
                  <div className="chat-meta">Assistente · {hora(m.created_at)}</div>
                </div>
              </div>
            )
          ))
        )}
        {sending && (
          <div className="chat-msg chat-msg-assistant">
            <span className="chat-avatar"><i className="bi bi-stars" /></span>
            <div className="chat-bubble chat-bubble-assistant chat-typing" aria-label="Analisando">
              <span /><span /><span />
              <span className="text-muted-2 small ms-2">Analisando os seus dados…</span>
            </div>
          </div>
        )}
        {error && <div className="alert alert-warning py-2 small mt-2 mb-0">{error}</div>}
        <div ref={bottomRef} />
      </div>

      <div className={`chat-composer ${compact ? "p-2" : "p-3"}`}>
        <textarea
          ref={inputRef}
          className="form-control"
          rows={compact ? 2 : 1}
          placeholder="Pergunte sobre um indicador, um plano, um desvio ou como fazer algo no sistema…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          disabled={sending}
        />
        <button className="btn btn-primary chat-send" onClick={() => send()} disabled={sending || !input.trim()} title="Enviar (Enter)">
          <i className="bi bi-send-fill" />
        </button>
      </div>
      {!compact && <div className="text-muted-2 px-3 pb-2" style={{ fontSize: "0.72rem" }}>Enter envia · Shift+Enter quebra linha. As respostas usam os dados da sua empresa no sistema.</div>}
    </div>
  );
}
