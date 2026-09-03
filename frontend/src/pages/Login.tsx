import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      navigate("/");
    } catch {
      setError("E-mail ou senha inválidos.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="d-flex min-vh-100">
      {/* Painel de marca */}
      <div
        className="d-none d-lg-flex flex-column justify-content-between p-5 text-white"
        style={{ width: "46%", background: "linear-gradient(150deg, #10233b 0%, #16324f 55%, #0d1b2e 100%)" }}
      >
        <div className="d-flex align-items-center gap-2">
          <span
            style={{
              width: 34, height: 34, borderRadius: 10, display: "grid", placeItems: "center",
              background: "linear-gradient(135deg,#2a78d6,#1baf7a)",
            }}
          >
            <i className="bi bi-compass" />
          </span>
          <span className="fw-semibold">TechSys Gestão</span>
        </div>

        <div style={{ maxWidth: 460 }}>
          <h2 className="fw-semibold" style={{ letterSpacing: "-0.02em", lineHeight: 1.25 }}>
            Da estratégia ao resultado, com inteligência artificial no meio do caminho.
          </h2>
          <p className="opacity-75 mt-3 mb-4" style={{ fontSize: "0.95rem" }}>
            Mapa estratégico, desdobramento de metas, indicadores com farol, planos de ação
            5W2H e análises automáticas de desvio — em um só lugar.
          </p>
          <div className="d-flex flex-column gap-2" style={{ fontSize: "0.88rem" }}>
            {[
              ["bi-diagram-3", "Mapa estratégico BSC com metas em cascata"],
              ["bi-graph-up-arrow", "Indicadores com farol e acumulado automático"],
              ["bi-stars", "Insights e chat de IA sobre os seus números"],
            ].map(([icon, text]) => (
              <div key={text} className="d-flex align-items-center gap-2 opacity-90">
                <i className={`bi ${icon}`} style={{ color: "#6aa9f0" }} />
                {text}
              </div>
            ))}
          </div>
        </div>

        <div className="opacity-50 small">© {new Date().getFullYear()} TechSys</div>
      </div>

      {/* Formulário */}
      <div className="flex-grow-1 d-flex align-items-center justify-content-center p-4" style={{ background: "var(--page)" }}>
        <div style={{ width: "100%", maxWidth: 380 }}>
          <div className="d-lg-none text-center mb-4">
            <i className="bi bi-compass" style={{ fontSize: "2rem", color: "var(--brand)" }} />
            <h5 className="mt-2 mb-0">TechSys Gestão</h5>
          </div>

          <h4 className="fw-semibold mb-1" style={{ letterSpacing: "-0.02em" }}>Entrar</h4>
          <p className="text-muted-2 small mb-4">Acesse o painel de desempenho da sua empresa.</p>

          <form onSubmit={submit}>
            <div className="mb-3">
              <label className="form-label">E-mail</label>
              <input
                type="email"
                className="form-control"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                autoComplete="username"
              />
            </div>
            <div className="mb-3">
              <label className="form-label">Senha</label>
              <input
                type="password"
                className="form-control"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>
            {error && (
              <div className="alert alert-danger py-2 small d-flex align-items-center gap-2">
                <i className="bi bi-exclamation-circle-fill" />{error}
              </div>
            )}
            <button className="btn btn-primary w-100" disabled={busy}>
              {busy ? (
                <><span className="spinner-border spinner-border-sm me-2" />Entrando...</>
              ) : (
                <>Entrar <i className="bi bi-arrow-right ms-1" /></>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
