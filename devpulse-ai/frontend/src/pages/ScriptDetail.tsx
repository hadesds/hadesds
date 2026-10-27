import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, post, put } from "../api";
import { ErrorBox, Loading } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useData } from "../components/useData";
import { CATEGORY_LABEL, fmtDate, fmtDateTime } from "../format";
import type { Package, ScriptFull } from "../types";

const RESULT: Record<string, string> = { supported: "✅ sustentada", partially_supported: "⚠️ parcial", unsupported: "❌ não sustentada", unverifiable: "❔ não verificável" };

export default function ScriptDetail() {
  const { id } = useParams();
  const { data, error, loading, setData } = useData<ScriptFull>(`/scripts/${id}`);
  const [draft, setDraft] = useState<Package | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function saveEdit() {
    if (!draft) return;
    try {
      setData(await put<ScriptFull>(`/scripts/${id}`, { package: draft }));
      setDraft(null);
      setMsg("Roteiro salvo.");
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  async function mark(status: string) {
    try {
      await post(`/scripts/${id}/status`, { status });
      setData(await api<ScriptFull>(`/scripts/${id}`));
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  function download() {
    if (!data) return;
    const blob = new Blob([data.markdown], { type: "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `roteiro-${data.edition_date}-${data.position}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  if (!data) return <><ErrorBox message={error} /><Loading show={loading} /></>;
  const p = draft ?? data.package;
  const editing = Boolean(draft);
  const setScene = (i: number, field: string, value: string) =>
    setDraft({ ...p, scenes: p.scenes.map((s, j) => (j === i ? { ...s, [field]: value } : s)) });

  return (
    <section>
      <p><Link to="/roteiros">← Roteiros</Link></p>
      <div className="page-head">
        <div>
          <h2>{p.identification.video_title}</h2>
          <p className="muted">{data.news_title} · edição {fmtDate(data.edition_date)} · <StatusBadge status={data.status} /></p>
        </div>
        <div className="actions">
          {!editing && <button className="secondary" onClick={() => setDraft(structuredClone(data.package))}>Editar</button>}
          {editing && <><button onClick={saveEdit}>Salvar</button><button className="secondary" onClick={() => setDraft(null)}>Cancelar</button></>}
          <button className="secondary" onClick={download}>Exportar Markdown</button>
          {data.status !== "rejected" && <>
            <button className="secondary" onClick={() => mark("recorded")}>Marcar gravado</button>
            <button className="secondary" onClick={() => mark("published")}>Marcar publicado</button>
          </>}
        </div>
      </div>
      {msg && <div className="alert">{msg}</div>}
      {p.generator === "extractive" && <div className="alert">Roteiro-base extrativo (gerado sem IA): os trechos estão no idioma original da fonte; traduza e complete a análise antes de gravar.</div>}
      {data.status === "rejected" && <div className="alert alert-bad">Reprovado na checagem: {data.rejection_reason}</div>}

      <div className="grid2">
        <div className="card">
          <h3>Identificação</h3>
          <dl>
            <dt>Categoria</dt><dd>{CATEGORY_LABEL[p.identification.category] ?? p.identification.category}</dd>
            <dt>Publicação original</dt><dd>{fmtDateTime(p.identification.published_at)}</dd>
            <dt>Última verificação</dt><dd>{fmtDateTime(p.identification.last_verified_at)}</dd>
            <dt>Pontuação</dt><dd>{p.identification.editorial_score.toFixed(0)}/100</dd>
            <dt>Motivo</dt><dd>{p.identification.selection_reason}</dd>
          </dl>
          <h4>Fontes</h4>
          <ul>{[...p.identification.primary_sources, ...p.identification.complementary_sources].map((s) => <li key={s.ref}>[{s.ref}] <a href={s.url} target="_blank" rel="noreferrer noopener">{s.title}</a> — {s.publisher} ({s.evidence_type})</li>)}</ul>
        </div>
        <div className="card">
          <h3>Planejamento</h3>
          <dl>
            <dt>Objetivo</dt><dd>{p.planning.objective}</dd>
            <dt>Público / nível</dt><dd>{p.planning.audience} · {p.planning.technical_level}</dd>
            <dt>Formato / duração</dt><dd>{p.planning.format} · {p.planning.duration_seconds}s</dd>
            <dt>Gancho</dt><dd>{p.planning.hook}</dd>
            <dt>Mensagem principal</dt><dd>{p.planning.key_message}</dd>
          </dl>
        </div>
      </div>

      <div className="card">
        <h3>Roteiro cronometrado</h3>
        {p.scenes.map((s, i) => (
          <div key={i} className="scene">
            <div className="scene-time">{s.start_second}–{s.end_second}s · {s.section}</div>
            {editing ? (
              <div className="form-grid">
                <label className="wide">Fala<textarea rows={3} value={s.speech} onChange={(e) => setScene(i, "speech", e.target.value)} /></label>
                <label>Ação/cena<input value={s.action} onChange={(e) => setScene(i, "action", e.target.value)} /></label>
                <label>Na tela<input value={s.on_screen} onChange={(e) => setScene(i, "on_screen", e.target.value)} /></label>
                <label>Texto sobreposto<input value={s.overlay_text} onChange={(e) => setScene(i, "overlay_text", e.target.value)} /></label>
                <label>Edição<input value={s.editing_notes} onChange={(e) => setScene(i, "editing_notes", e.target.value)} /></label>
              </div>
            ) : (
              <>
                <p className="speech">{s.speech}</p>
                <p className="small muted">Cena: {s.action} · Tela: {s.on_screen} · Texto: {s.overlay_text} · Edição: {s.editing_notes} · Recurso: {s.visual_resource}</p>
              </>
            )}
          </div>
        ))}
      </div>

      <div className="grid2">
        <div className="card">
          <h3>Guia de gravação</h3>
          <ul>{p.recording_guide.steps.map((s, i) => <li key={i}>{s}</li>)}</ul>
          {p.recording_guide.commands.length > 0 && <pre>{p.recording_guide.commands.join("\n")}</pre>}
          <p className="small"><strong>Demonstração:</strong> {p.recording_guide.demo_status} — {p.recording_guide.demo_note}</p>
        </div>
        <div className="card">
          <h3>Publicação</h3>
          {editing ? (
            <div className="form-grid">
              <label className="wide">Legenda<textarea rows={6} value={p.publication.caption} onChange={(e) => setDraft({ ...p, publication: { ...p.publication, caption: e.target.value } })} /></label>
              <label className="wide">Hashtags<input value={p.publication.hashtags.join(" ")} onChange={(e) => setDraft({ ...p, publication: { ...p.publication, hashtags: e.target.value.split(/\s+/).filter(Boolean) } })} /></label>
            </div>
          ) : (
            <>
              <p><strong>Capa:</strong> {p.publication.cover_title}</p>
              <pre className="caption">{p.publication.caption}{"\n\n"}{p.publication.hashtags.join(" ")}</pre>
              <p className="small"><strong>Comentário fixado:</strong> {p.publication.pinned_comment}</p>
            </>
          )}
          <h4>Checklist</h4>
          <ul>{p.publication.final_checklist.map((c, i) => <li key={i}>☐ {c}</li>)}</ul>
        </div>
      </div>

      <div className="card">
        <h3>Recursos visuais</h3>
        <div className="table-wrap"><table>
          <thead><tr><th>Cena</th><th>Tipo</th><th>Descrição</th><th>Licença</th><th>Acessível</th></tr></thead>
          <tbody>{p.visual_resources.map((v, i) => (
            <tr key={i}><td>{v.scene ?? "—"}</td><td>{v.kind}</td><td>{v.description}{v.url && <><br /><a href={v.url} target="_blank" rel="noreferrer noopener" className="small">{v.url}</a></>}</td><td className="small">{v.license_info}</td><td>{v.accessible == null ? "—" : v.accessible ? "sim" : "não"}</td></tr>
          ))}</tbody>
        </table></div>
      </div>

      <div className="card">
        <h3>Registro de checagem</h3>
        <div className="table-wrap"><table>
          <thead><tr><th>Afirmação</th><th>Tipo</th><th>Central</th><th>Evidência</th><th>Resultado</th><th>Observações</th></tr></thead>
          <tbody>{data.fact_checks.map((f, i) => (
            <tr key={i}><td>{f.claim}{f.source_url && <><br /><a className="small" href={f.source_url} target="_blank" rel="noreferrer noopener">{f.source_url}</a></>}</td><td>{f.claim_type}</td><td>{f.is_central ? "sim" : "não"}</td><td>{f.evidence_type}</td><td>{RESULT[f.result] ?? f.result}</td><td className="small">{f.notes}</td></tr>
          ))}</tbody>
        </table></div>
        {p.uncertainties.length > 0 && <><h4>Incertezas</h4><ul>{p.uncertainties.map((u, i) => <li key={i}>{u}</li>)}</ul></>}
        {p.generator_notes.length > 0 && <p className="small muted">Notas do gerador: {p.generator_notes.join(" · ")}</p>}
      </div>
    </section>
  );
}
