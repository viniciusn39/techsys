import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "react-bootstrap";
import { ApiError, api } from "../api/client";

interface Anexo { id: number; name: string; size: number; uploaded_by_name: string; created_at: string }

const tamanho = (b: number) => (b >= 1048576 ? `${(b / 1048576).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

/** Arquivos anexados a um registro. `kind` é o tipo do alvo na API (project_activity, kanban_task). */
export function Anexos({ kind, objectId, podeEnviar = true }: { kind: string; objectId: number | undefined; podeEnviar?: boolean }) {
  const [lista, setLista] = useState<Anexo[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    if (!objectId) { setLista([]); return; }
    api.get<Anexo[]>(`/api/anexos/?kind=${kind}&object_id=${objectId}`).then(setLista).catch(() => setLista([]));
  }, [kind, objectId]);
  useEffect(() => { load(); }, [load]);

  const mensagem = (e: unknown) => {
    const d = (e as ApiError).data;
    return d && typeof d === "object" ? Object.values(d).flat().join(" ") : (e as Error).message;
  };

  const enviar = async (arquivos: FileList | null) => {
    if (!arquivos?.length || !objectId) return;
    setEnviando(true); setErro("");
    try {
      for (const arquivo of Array.from(arquivos)) {
        const form = new FormData();
        form.append("kind", kind); form.append("object_id", String(objectId)); form.append("file", arquivo);
        await api.upload("/api/anexos/", form);
      }
    } catch (e) { setErro(mensagem(e)); }
    setEnviando(false);
    if (input.current) input.current.value = "";
    load();
  };

  const excluir = async (a: Anexo) => {
    try { await api.del(`/api/anexos/${a.id}/`); load(); } catch (e) { setErro(mensagem(e)); }
  };

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-1">
        <span className="form-label mb-0"><i className="bi bi-paperclip me-1" />Anexos{lista.length > 0 && ` (${lista.length})`}</span>
        {objectId && podeEnviar && (
          <>
            <input ref={input} type="file" multiple hidden onChange={(e) => enviar(e.target.files)} />
            <Button size="sm" variant="outline-secondary" disabled={enviando} onClick={() => input.current?.click()}>
              <i className="bi bi-upload me-1" />{enviando ? "Enviando…" : "Anexar"}
            </Button>
          </>
        )}
      </div>
      {erro && <div className="small mb-1" style={{ color: "var(--st-vermelho)" }}>{erro}</div>}
      {!objectId ? <div className="small text-muted-2 fst-italic">Salve primeiro para poder anexar arquivos.</div>
        : lista.length === 0 ? <div className="small text-muted-2">Nenhum arquivo anexado.</div>
        : lista.map((a) => (
          <div key={a.id} className="d-flex align-items-center gap-2 small py-1" style={{ borderTop: "1px solid var(--border)" }}>
            <i className="bi bi-file-earmark text-muted-2" />
            <button type="button" className="btn btn-link btn-sm p-0 text-truncate text-start flex-grow-1" onClick={() => api.download(`/api/anexos/${a.id}/download/`, a.name).catch((e) => setErro(mensagem(e)))}>{a.name}</button>
            <span className="text-muted-2 text-nowrap">{tamanho(a.size)} · {a.uploaded_by_name || "—"}</span>
            {podeEnviar && <Button size="sm" variant="link" className="p-0 text-muted-2" aria-label={`Excluir ${a.name}`} onClick={() => excluir(a)}><i className="bi bi-x-lg" /></Button>}
          </div>
        ))}
      <div className="small text-muted-2 mt-1">Até 20 MB por arquivo.</div>
    </div>
  );
}
