import { useEffect, useState } from "react";
import { Button, Form } from "react-bootstrap";
import { api } from "../api/client";
import { EmptyState, Panel } from "../components/ui";

interface Integration {
  id?: number;
  provider: string;
  base_url: string;
  model: string;
  temperature: string;
  max_tokens: number;
  is_active: boolean;
  api_key?: string;
  api_key_set?: boolean;
  last_test_at?: string | null;
  last_test_ok?: boolean | null;
}

const PROVIDERS = [
  { id: "deepseek", label: "DeepSeek", base_url: "https://api.deepseek.com/v1", model: "deepseek-chat", ready: true },
  { id: "openai", label: "OpenAI", base_url: "https://api.openai.com/v1", model: "gpt-4o-mini", ready: true },
  { id: "anthropic", label: "Anthropic", base_url: "https://api.anthropic.com/v1", model: "claude-sonnet-5", ready: false },
];

const FONTES = [
  { icon: "bi-pencil", label: "Lançamento manual", hint: "Grade mensal na tela de indicadores", ready: true },
  { icon: "bi-robot", label: "Agente conector de ERP", hint: "Extrai indicadores direto do ERP", ready: false },
  { icon: "bi-cloud-arrow-down", label: "API REST", hint: "Coleta agendada via endpoint externo", ready: false },
  { icon: "bi-filetype-sql", label: "Consulta SQL", hint: "Query direta em banco de dados", ready: false },
];

const EMPTY: Integration = {
  provider: "deepseek",
  base_url: "https://api.deepseek.com/v1",
  model: "deepseek-chat",
  temperature: "0.3",
  max_tokens: 2000,
  is_active: true,
};

export function Integracoes() {
  const [form, setForm] = useState<Integration>(EMPTY);
  const [saved, setSaved] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<Integration | null>("/api/ai/integration/")
      .then((d) => d && setForm({ ...d, api_key: "" }))
      .catch(() => {});
  }, []);

  const pickProvider = (id: string) => {
    const p = PROVIDERS.find((x) => x.id === id)!;
    setForm({ ...form, provider: id, base_url: p.base_url, model: p.model });
  };

  const save = async () => {
    setBusy(true);
    setSaved(false);
    try {
      const body: any = { ...form };
      if (!body.api_key) delete body.api_key;
      const updated = await api.put<Integration>("/api/ai/integration/", body);
      setForm({ ...updated, api_key: "" });
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    setTestResult(null);
    try {
      setTestResult(await api.post("/api/ai/integration/test/"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="row g-3">
      <div className="col-xl-7">
        <Panel
          title="Provedor de inteligência artificial"
          subtitle="Alimenta os insights de indicador, a análise de desvios e o chat de resultados."
        >
          <div className="row g-2 mb-3">
            {PROVIDERS.map((p) => (
              <div className="col-4" key={p.id}>
                <button
                  className="objective-card w-100 text-start"
                  style={{
                    borderColor: form.provider === p.id ? "var(--brand)" : undefined,
                    background: form.provider === p.id ? "var(--brand-soft)" : undefined,
                    opacity: p.ready ? 1 : 0.6,
                  }}
                  onClick={() => p.ready && pickProvider(p.id)}
                  disabled={!p.ready}
                >
                  <div className="d-flex align-items-center justify-content-between">
                    <span className="title">{p.label}</span>
                    {form.provider === p.id && <i className="bi bi-check-circle-fill" style={{ color: "var(--brand)" }} />}
                  </div>
                  <div className="meta">{p.ready ? p.model : "em breve"}</div>
                </button>
              </div>
            ))}
          </div>

          <div className="row g-3">
            <div className="col-md-8">
              <Form.Label>Base URL</Form.Label>
              <Form.Control value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
            </div>
            <div className="col-md-4">
              <Form.Label>Modelo</Form.Label>
              <Form.Control value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
            </div>
            <div className="col-12">
              <Form.Label>
                API Key
                {form.api_key_set && (
                  <span className="status-pill st-verde ms-2">
                    <i className="bi bi-check-circle-fill" />configurada
                  </span>
                )}
              </Form.Label>
              <Form.Control
                type="password"
                placeholder={form.api_key_set ? "•••••••••• (deixe vazio para manter a atual)" : "sk-..."}
                value={form.api_key || ""}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              />
              <div className="text-muted-2 mt-1" style={{ fontSize: "0.74rem" }}>
                <i className="bi bi-shield-lock me-1" />
                Armazenada criptografada; nunca é devolvida pela API.
              </div>
            </div>
            <div className="col-md-6">
              <Form.Label>Temperatura</Form.Label>
              <Form.Control
                type="number" step="0.1" min="0" max="2"
                value={form.temperature}
                onChange={(e) => setForm({ ...form, temperature: e.target.value })}
              />
            </div>
            <div className="col-md-6">
              <Form.Label>Máximo de tokens</Form.Label>
              <Form.Control
                type="number"
                value={form.max_tokens}
                onChange={(e) => setForm({ ...form, max_tokens: Number(e.target.value) })}
              />
            </div>
          </div>

          <div className="d-flex gap-2 mt-3 align-items-center flex-wrap">
            <Button onClick={save} disabled={busy}>
              {busy ? <span className="spinner-border spinner-border-sm me-2" /> : <i className="bi bi-check-lg me-1" />}
              Salvar
            </Button>
            <Button variant="outline-secondary" onClick={test} disabled={busy}>
              <i className="bi bi-plug me-1" />Testar conexão
            </Button>
            {saved && (
              <span className="status-pill st-verde">
                <i className="bi bi-check-circle-fill" />Salvo
              </span>
            )}
          </div>

          {testResult && (
            <div className={`alert py-2 mt-3 mb-0 small ${testResult.ok ? "alert-success" : "alert-danger"}`}>
              <i className={`bi ${testResult.ok ? "bi-check-circle-fill" : "bi-x-circle-fill"} me-1`} />
              {testResult.message}
            </div>
          )}
          {form.last_test_at && !testResult && (
            <div className="text-muted-2 small mt-3">
              Último teste: {new Date(form.last_test_at).toLocaleString("pt-BR")} —{" "}
              {form.last_test_ok ? "sucesso" : "falha"}
            </div>
          )}
        </Panel>
      </div>

      <div className="col-xl-5">
        <Panel title="Fontes de dados dos indicadores" subtitle="Como os valores chegam ao sistema.">
          <div className="d-flex flex-column gap-2">
            {FONTES.map((f) => (
              <div
                key={f.label}
                className="d-flex align-items-center gap-3 p-2 rounded"
                style={{ background: "var(--surface-sunken)" }}
              >
                <span
                  style={{
                    width: 32, height: 32, borderRadius: 8, display: "grid", placeItems: "center",
                    background: "var(--surface)", color: f.ready ? "var(--brand)" : "var(--ink-muted)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <i className={`bi ${f.icon}`} />
                </span>
                <div className="flex-grow-1">
                  <div className="fw-semibold small">{f.label}</div>
                  <div className="text-muted-2" style={{ fontSize: "0.74rem" }}>{f.hint}</div>
                </div>
                <span className={`status-pill ${f.ready ? "st-verde" : "st-neutro"}`}>
                  <i className={`bi ${f.ready ? "bi-check-circle-fill" : "bi-hourglass-split"}`} />
                  {f.ready ? "Ativo" : "Em breve"}
                </span>
              </div>
            ))}
          </div>
          <div className="text-muted-2 small mt-3">
            <i className="bi bi-info-circle me-1" />
            O agente conector de ERP se acopla em <code>indicators/sources/</code> sem alterar o restante do sistema.
          </div>
        </Panel>
      </div>
    </div>
  );
}
