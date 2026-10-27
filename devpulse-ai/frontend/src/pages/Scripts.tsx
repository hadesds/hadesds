import { useState } from "react";
import { Link } from "react-router-dom";
import { Empty, ErrorBox, Loading } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useData } from "../components/useData";
import { CATEGORY_LABEL, fmtDate, fmtSeconds } from "../format";
import type { ScriptSummary } from "../types";

export default function Scripts() {
  const [q, setQ] = useState("");
  const [rejected, setRejected] = useState(false);
  const { data, error, loading } = useData<ScriptSummary[]>(`/scripts?include_rejected=${rejected}${q ? `&q=${encodeURIComponent(q)}` : ""}`);
  return (
    <section>
      <h2>Roteiros</h2>
      <div className="filters">
        <input placeholder="Buscar por título" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="inline"><input type="checkbox" checked={rejected} onChange={(e) => setRejected(e.target.checked)} /> Incluir reprovados na checagem</label>
      </div>
      <ErrorBox message={error} />
      <Loading show={loading && !data} />
      {data?.length === 0 && <Empty>Nenhum roteiro ainda. A edição principal roda às 8h (America/Fortaleza).</Empty>}
      <div className="cards">
        {data?.map((s) => (
          <Link key={s.id} to={`/roteiros/${s.id}`} className="card script-card">
            <div className="row-between"><span className="muted small">{fmtDate(s.edition_date)} · #{s.position}</span><StatusBadge status={s.status} /></div>
            <h3>{s.video_title}</h3>
            <p className="muted small">{s.news_title}</p>
            <div className="chips">
              {s.category && <span className="chip">{CATEGORY_LABEL[s.category]}</span>}
              <span className="chip">{fmtSeconds(s.estimated_duration_seconds)}</span>
              <span className="chip">{s.editorial_score?.toFixed(0)}/100</span>
              <span className="chip">{s.generator === "extractive" ? "roteiro-base (sem IA)" : "IA"}</span>
              {s.edited_manually && <span className="chip">editado</span>}
            </div>
            {s.rejection_reason && <p className="small error-text">{s.rejection_reason}</p>}
          </Link>
        ))}
      </div>
    </section>
  );
}
