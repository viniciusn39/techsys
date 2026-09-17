import { useRef, useState } from "react";
import { Form } from "react-bootstrap";
import { Markdown } from "./Markdown";

interface Props { value: string; onChange: (v: string) => void; rows?: number; placeholder?: string }

const BOTOES: { icon: string; titulo: string; antes: string; depois?: string; linha?: boolean }[] = [
  { icon: "bi-type-h2", titulo: "Título", antes: "## ", linha: true },
  { icon: "bi-type-h3", titulo: "Subtítulo", antes: "### ", linha: true },
  { icon: "bi-type-bold", titulo: "Negrito", antes: "**", depois: "**" },
  { icon: "bi-type-italic", titulo: "Itálico", antes: "*", depois: "*" },
  { icon: "bi-code", titulo: "Código", antes: "`", depois: "`" },
  { icon: "bi-list-ul", titulo: "Lista", antes: "- ", linha: true },
  { icon: "bi-list-ol", titulo: "Lista numerada", antes: "1. ", linha: true },
  { icon: "bi-hr", titulo: "Linha divisória", antes: "\n---\n" },
];

/** Editor de texto com formatação (markdown): barra de botões, escrever e visualizar. O texto salvo é markdown puro. */
export function EditorTexto({ value, onChange, rows = 5, placeholder }: Props) {
  const area = useRef<HTMLTextAreaElement>(null);
  const [previa, setPrevia] = useState(false);

  const aplicar = (b: (typeof BOTOES)[number]) => {
    const el = area.current;
    if (!el) return;
    const { selectionStart: ini, selectionEnd: fim } = el;
    const selecionado = value.slice(ini, fim);
    let novo: string; let cursor: number;
    if (b.linha) {
      const inicioLinha = value.lastIndexOf("\n", ini - 1) + 1;
      const bloco = (value.slice(inicioLinha, fim) || "").split("\n").map((l) => b.antes + l).join("\n");
      novo = value.slice(0, inicioLinha) + bloco + value.slice(fim);
      cursor = inicioLinha + bloco.length;
    } else {
      const meio = selecionado || (b.depois ? "texto" : "");
      novo = value.slice(0, ini) + b.antes + meio + (b.depois ?? "") + value.slice(fim);
      cursor = ini + b.antes.length + meio.length + (b.depois?.length ?? 0);
    }
    onChange(novo);
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(cursor, cursor); });
  };

  return (
    <div className="rounded" style={{ border: "1px solid var(--border)" }}>
      <div className="d-flex align-items-center gap-1 px-2 py-1" style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-sunken)" }}>
        {BOTOES.map((b) => (
          <button key={b.titulo} type="button" className="btn btn-sm btn-link p-1 text-muted-2" title={b.titulo} aria-label={b.titulo} disabled={previa} onClick={() => aplicar(b)}><i className={`bi ${b.icon}`} /></button>
        ))}
        <button type="button" className={`btn btn-sm ms-auto ${previa ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setPrevia(!previa)}>{previa ? "Editar" : "Visualizar"}</button>
      </div>
      {previa
        ? <div className="p-2" style={{ minHeight: rows * 24 }}>{value.trim() ? <Markdown text={value} /> : <span className="small text-muted-2">Nada escrito ainda.</span>}</div>
        : <Form.Control ref={area} as="textarea" rows={rows} className="border-0" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />}
    </div>
  );
}
