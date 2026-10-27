import { useState } from "react";
import { post } from "../api";
import { ErrorBox, Loading } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useData } from "../components/useData";
import { fmtDateTime } from "../format";
import type { Dashboard as D, Run } from "../types";

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
      {hint && <span className="muted small">{hint}</span>}
    </div>
  );
}

export default function Dashboard() {
  const { data, error, loading, reload } = useData<D>("/dashboard");
  const [msg, setMsg] = useState<string | null>(null);

  async function trigger(kind: "collect" | "edition") {
    try {
      const r = await post<Run & { message: string }>(`/runs/${kind}`);
      setMsg(r.message);
      setTimeout(reload, 1500);
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  return (
    <section>
      <div className="page-head">
        <h2>Painel</h2>
        <div className="actions">
          <button className="secondary" onClick={() => trigger("collect")}>Coletar agora</button>
          <button onClick={() => trigger("edition")}>Gerar edição agora</button>
        </div>
      </div>
      {msg && <div className="alert">{msg}</div>}
      <ErrorBox message={error} />
      <Loading show={loading && !data} />
      {data && (
        <>
          <div className="stats">
            <Stat label="Notícias coletadas hoje" value={data.collected_today} />
            <Stat label="Agrupamentos analisados" value={data.analyzed_today} />
            <Stat label="Roteiros gerados" value={`${data.scripts_today}/${data.daily_limit}`} hint="limite diário compartilhado" />
            <Stat label="Notificações aceitas" value={data.notifications_sent_today} />
            <Stat label="Erros hoje" value={data.errors_today.sources + data.errors_today.deliveries + data.errors_today.runs}
              hint={`fontes ${data.errors_today.sources} · entregas ${data.errors_today.deliveries} · execuções ${data.errors_today.runs}`} />
            <Stat label="Tarefas pendentes" value={data.pending.runs + data.pending.deliveries}
              hint={`execuções ${data.pending.runs} · entregas ${data.pending.deliveries}`} />
          </div>
          <div className="grid2">
            <div className="card">
              <h3>Última edição</h3>
              {data.last_edition_run ? (
                <p>{fmtDateTime(data.last_edition_run.created_at)} — <StatusBadge status={data.last_edition_run.status} /> {data.last_edition_run.error && <span className="muted small">{data.last_edition_run.error}</span>}</p>
              ) : <p className="muted">Nenhuma edição executada ainda.</p>}
              <h3>Próximas execuções</h3>
              <ul>{data.next_runs.map((r) => <li key={r.slot}>{r.slot === "main" ? "Edição principal" : "Edição complementar"}: {fmtDateTime(r.at)}</li>)}</ul>
            </div>
            <div className="card">
              <h3>IA hoje</h3>
              <p>{data.llm_today.calls} de {data.llm_today.limit_calls} chamadas · custo estimado US$ {data.llm_today.estimated_cost_usd.toFixed(4)}</p>
              <p className="muted small">O limite de chamadas é aplicado pelo DevPulse; o custo é estimativa pelos preços configurados.</p>
            </div>
          </div>
          <div className="card">
            <h3>Execuções recentes</h3>
            <table>
              <thead><tr><th>Quando</th><th>Tipo</th><th>Origem</th><th>Status</th><th>Etapa/erro</th></tr></thead>
              <tbody>
                {data.recent_runs.map((r) => (
                  <tr key={r.id}>
                    <td>{fmtDateTime(r.created_at)}</td>
                    <td>{r.kind === "edition" ? `Edição (${r.slot})` : "Coleta"}</td>
                    <td>{r.trigger}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="small">{r.error ?? r.step ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
