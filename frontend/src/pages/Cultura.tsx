import { useEffect, useState } from "react";
import { Button, Form } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel, Skeleton } from "../components/ui";

interface Mapa { id: number; name: string; year_start: number; year_end: number; purpose: string; mission: string; vision: string; values_text: string }

const CAMPOS: { key: keyof Mapa; label: string; hint: string; icon: string; color: string }[] = [
  { key: "purpose", label: "Propósito", hint: "Por que a empresa existe, além de ganhar dinheiro. Uma frase que inspira.", icon: "bi-rocket-takeoff", color: "#e64980" },
  { key: "mission", label: "Missão", hint: "O que fazemos, para quem e como. O negócio hoje.", icon: "bi-bullseye", color: "#f59f00" },
  { key: "vision", label: "Visão", hint: "Onde queremos chegar no horizonte do planejamento. Mensurável e com prazo.", icon: "bi-eye", color: "#15aabf" },
  { key: "values_text", label: "Valores", hint: "Os comportamentos inegociáveis. Um por linha.", icon: "bi-gem", color: "#12b886" },
];

/** Identidade organizacional: propósito, missão, visão e valores do mapa ativo. */
export function Cultura() {
  const [mapa, setMapa] = useState<Mapa | null | undefined>(undefined);
  const [form, setForm] = useState<Partial<Mapa>>({});
  const [editando, setEditando] = useState<keyof Mapa | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.get<Mapa | null>("/api/strategic-maps/active/").then((m) => { setMapa(m); setForm(m ?? {}); }).catch(() => setMapa(null));
  }, []);

  const salvar = async (key: keyof Mapa) => {
    if (!mapa) return;
    const atualizado = await api.patch<Mapa>(`/api/strategic-maps/${mapa.id}/`, { [key]: form[key] ?? "" });
    setMapa({ ...mapa, ...atualizado });
    setEditando(null);
    setMsg("Salvo");
    window.setTimeout(() => setMsg(""), 1800);
  };

  if (mapa === undefined) return <Panel><Skeleton height={300} /></Panel>;
  if (mapa === null) return <Panel><EmptyState icon="bi-diagram-3" title="Nenhum mapa estratégico ativo" hint="Crie o mapa em Mapa Estratégico para definir a identidade da empresa." /></Panel>;

  const valores = (mapa.values_text || "").split(/\n|;/).map((v) => v.trim()).filter(Boolean);

  return (
    <div className="d-grid gap-3">
      <Panel
        title="Cultura e identidade"
        subtitle={`${mapa.name} · ${mapa.year_start}–${mapa.year_end}. Propósito, missão, visão e valores são a base de todo o mapa: cada objetivo deveria responder a eles.`}
        actions={<div className="d-flex gap-2 align-items-center">{msg && <span className="small text-success"><i className="bi bi-check-circle me-1" />{msg}</span>}<button className="btn btn-sm btn-outline-secondary no-print" onClick={() => window.print()}><i className="bi bi-printer me-1" />Imprimir</button></div>}
      >
        <div className="row g-3">
          {CAMPOS.map((c) => {
            const valor = (mapa[c.key] as string) || "";
            return (
              <div className="col-md-6" key={c.key}>
                <div className="h-100 rounded" style={{ border: "1px solid var(--border)", overflow: "hidden" }}>
                  <div className="d-flex align-items-center gap-2 px-3 py-2 text-white" style={{ background: c.color }}>
                    <i className={`bi ${c.icon}`} /><span className="fw-semibold">{c.label}</span>
                    {editando !== c.key && <button className="btn btn-sm btn-link text-white p-0 ms-auto no-print" onClick={() => setEditando(c.key)} title="Editar"><i className="bi bi-pencil" /></button>}
                  </div>
                  <div className="p-3">
                    {editando === c.key ? (
                      <div className="d-grid gap-2">
                        <Form.Control as="textarea" rows={c.key === "values_text" ? 6 : 4} autoFocus value={(form[c.key] as string) ?? ""} onChange={(e) => setForm({ ...form, [c.key]: e.target.value })} placeholder={c.hint} />
                        <div className="d-flex gap-2 justify-content-end">
                          <Button size="sm" variant="outline-secondary" onClick={() => { setEditando(null); setForm(mapa); }}>Cancelar</Button>
                          <Button size="sm" onClick={() => salvar(c.key)}>Salvar</Button>
                        </div>
                      </div>
                    ) : c.key === "values_text" && valores.length > 0 ? (
                      <ul className="mb-0 ps-3">{valores.map((v, i) => <li key={i}>{v}</li>)}</ul>
                    ) : valor ? (
                      <div style={{ whiteSpace: "pre-wrap", fontSize: "1.02rem" }}>{valor}</div>
                    ) : (
                      <div className="text-muted-2 fst-italic" role="button" onClick={() => setEditando(c.key)}>{c.hint}</div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
