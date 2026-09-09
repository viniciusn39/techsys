import { Fragment, type ReactNode } from "react";

/** Renderizador leve de markdown para as respostas da IA: títulos, negrito, itálico,
 *  código, listas, tabelas, linha horizontal e parágrafos. Sem HTML bruto. */
export function Markdown({ text }: { text: string }) {
  return <div className="markdown-body">{render(text || "")}</div>;
}

function inline(s: string, key = 0): ReactNode {
  // **negrito**, *itálico*, `código`
  const parts: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\n]+\*)/g;
  let last = 0; let m: RegExpExecArray | null; let i = 0;
  while ((m = re.exec(s))) {
    if (m.index > last) parts.push(s.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) parts.push(<strong key={`${key}-${i++}`}>{t.slice(2, -2)}</strong>);
    else if (t.startsWith("`")) parts.push(<code key={`${key}-${i++}`}>{t.slice(1, -1)}</code>);
    else parts.push(<em key={`${key}-${i++}`}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < s.length) parts.push(s.slice(last));
  return parts.length === 1 ? parts[0] : <Fragment key={key}>{parts}</Fragment>;
}

function render(text: string): ReactNode[] {
  const lines = text.replace(/\r/g, "").split("\n");
  const out: ReactNode[] = [];
  let i = 0; let k = 0;
  const isTable = (l: string) => /^\s*\|.*\|\s*$/.test(l);
  const isSep = (l: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);

  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    const h = /^(#{1,6})\s+(.*)$/.exec(l);
    if (h) {
      const lvl = Math.min(h[1].length + 3, 6);
      out.push(lvl === 4 ? <h4 key={k++}>{inline(h[2])}</h4> : lvl === 5 ? <h5 key={k++}>{inline(h[2])}</h5> : <h6 key={k++}>{inline(h[2])}</h6>);
      i++; continue;
    }
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(l)) { out.push(<hr key={k++} />); i++; continue; }
    if (isTable(l)) {
      const rows: string[][] = [];
      while (i < lines.length && isTable(lines[i])) {
        if (!isSep(lines[i])) rows.push(lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
        i++;
      }
      const [head, ...body] = rows;
      out.push(
        <div className="table-responsive" key={k++}>
          <table className="table table-sm mb-2">
            {head && <thead><tr>{head.map((c, j) => <th key={j}>{inline(c, j)}</th>)}</tr></thead>}
            <tbody>{body.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j}>{inline(c, j)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }
    const ul = /^\s*[-*•]\s+(.*)$/; const ol = /^\s*\d+[.)]\s+(.*)$/;
    if (ul.test(l) || ol.test(l)) {
      const ordered = ol.test(l); const items: ReactNode[] = [];
      while (i < lines.length && (ordered ? ol.test(lines[i]) : ul.test(lines[i]))) {
        const m = (ordered ? ol : ul).exec(lines[i])!; let txt = m[1]; i++;
        // continuação indentada do item
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !ul.test(lines[i]) && !ol.test(lines[i])) { txt += " " + lines[i].trim(); i++; }
        items.push(<li key={items.length}>{inline(txt)}</li>);
      }
      out.push(ordered ? <ol key={k++}>{items}</ol> : <ul key={k++}>{items}</ul>);
      continue;
    }
    if (/^\s*```/.test(l)) {
      const buf: string[] = []; i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++; out.push(<pre key={k++}><code>{buf.join("\n")}</code></pre>); continue;
    }
    // parágrafo: junta linhas até a próxima em branco ou bloco
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6})\s/.test(lines[i]) && !isTable(lines[i]) && !ul.test(lines[i]) && !ol.test(lines[i]) && !/^\s*```/.test(lines[i]) && !/^\s*(-{3,}|\*{3,})\s*$/.test(lines[i])) {
      buf.push(lines[i]); i++;
    }
    out.push(<p key={k++}>{buf.map((b, j) => <Fragment key={j}>{j > 0 && <br />}{inline(b, j)}</Fragment>)}</p>);
  }
  return out;
}
