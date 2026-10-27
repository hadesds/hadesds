import { FormEvent, useState } from "react";
import { api, post, put } from "../api";
import { Empty, ErrorBox, Loading } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useData } from "../components/useData";
import { CATEGORY_LABEL, fmtDateTime } from "../format";
import type { Connector, Source, SourceRun } from "../types";

const EMPTY = { slug: "", name: "", connector_type: "rss", url: "", config: "{}", category: "", priority_tier: 4, fetch_interval_minutes: 60, notes: "" };
type Form = typeof EMPTY;

export default function Sources() {
  const sources = useData<Source[]>("/sources");
  const connectors = useData<Connector[]>("/connectors");
  const [form, setForm] = useState<Form | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<{ id: number; items: SourceRun[] } | null>(null);

  function edit(s: Source) {
    setEditing(s.id);
    setForm({ slug: s.slug, name: s.name, connector_type: s.connector_type, url: s.url ?? "", config: JSON.stringify(s.config, null, 2),
      category: s.category ?? "", priority_tier: s.priority_tier, fetch_interval_minutes: s.fetch_interval_minutes, notes: s.notes ?? "" });
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    let config: unknown;
    try {
      config = JSON.parse(form.config || "{}");
    } catch {
      setError("Configuração deve ser um JSON válido");
      return;
    }
    const body = { ...form, config, url: form.url || null, category: form.category || null, notes: form.notes || null };
    try {
      if (editing) await put(`/sources/${editing}`, body);
      else await post("/sources", body);
      setForm(null);
      setEditing(null);
      setError(null);
      void sources.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function act(path: string) {
    try {
      await post(path);
      void sources.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const selected = connectors.data?.find((c) => c.type === form?.connector_type);
  return (
    <section>
      <div className="page-head">
        <h2>Fontes</h2>
        <button onClick={() => { setEditing(null); setForm({ ...EMPTY }); }}>Adicionar fonte</button>
      </div>
      <ErrorBox message={error ?? sources.error} />
      {form && (
        <form className="card form-grid" onSubmit={save}>
          <h3>{editing ? "Editar fonte" : "Nova fonte"}</h3>
          <label>Identificador (slug)<input required value={form.slug} disabled={Boolean(editing)} onChange={(e) => setForm({ ...form, slug: e.target.value })} /></label>
          <label>Nome<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>Tipo de conector
            <select value={form.connector_type} onChange={(e) => setForm({ ...form, connector_type: e.target.value })}>
              {connectors.data?.map((c) => <option key={c.type} value={c.type}>{c.type}</option>)}
            </select>
          </label>
          <label>URL<input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://" /></label>
          <label>Categoria
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="">(automática)</option>
              {Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label>Nível da fonte
            <select value={form.priority_tier} onChange={(e) => setForm({ ...form, priority_tier: Number(e.target.value) })}>
              <option value={1}>1 — anúncio oficial/documentação</option><option value={2}>2 — repositório/changelog oficial</option>
              <option value={3}>3 — newsletter</option><option value={4}>4 — portal especializado</option><option value={5}>5 — independente/agregador</option>
            </select>
          </label>
          <label>Intervalo de coleta (min)<input type="number" min={15} value={form.fetch_interval_minutes} onChange={(e) => setForm({ ...form, fetch_interval_minutes: Number(e.target.value) })} /></label>
          <label className="wide">Configuração (JSON)
            <textarea rows={4} value={form.config} onChange={(e) => setForm({ ...form, config: e.target.value })} />
            {selected && <span className="muted small">{selected.description} Campos: {Object.entries(selected.config_fields).map(([k, v]) => `${k} (${v})`).join("; ") || "nenhum"}</span>}
          </label>
          <label className="wide">Notas<input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
          <div className="actions wide"><button type="submit">Salvar</button><button type="button" className="secondary" onClick={() => setForm(null)}>Cancelar</button></div>
        </form>
      )}
      <Loading show={sources.loading && !sources.data} />
      {sources.data?.length === 0 && <Empty>Nenhuma fonte cadastrada.</Empty>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Fonte</th><th>Tipo</th><th>Nível</th><th>Categoria</th><th>Última coleta</th><th>Situação</th><th></th></tr></thead>
          <tbody>
            {sources.data?.map((s) => (
              <tr key={s.id} className={s.enabled ? "" : "dim"}>
                <td><strong>{s.name}</strong><br /><span className="muted small">{s.url ?? (s.config.sender as string) ?? s.slug}</span></td>
                <td>{s.connector_type}</td>
                <td>{s.priority_tier}</td>
                <td>{s.category ? CATEGORY_LABEL[s.category] : "auto"}</td>
                <td>{fmtDateTime(s.last_run_at)}{s.last_run && <><br /><span className="small">{s.last_run.items_new} novas / {s.last_run.items_found} lidas</span></>}</td>
                <td>{!s.enabled ? <span className="badge badge-neutral">Desativada</span> : s.last_error ? <span className="badge badge-bad" title={s.last_error}>Falha</span> : s.last_run ? <StatusBadge status={s.last_run.status} /> : <span className="badge badge-neutral">Sem coleta</span>}
                  {s.last_error && <div className="small error-text">{s.last_error}</div>}</td>
                <td className="actions-col">
                  <button className="link" onClick={() => edit(s)}>Editar</button>
                  <button className="link" onClick={() => act(`/sources/${s.id}/toggle`)}>{s.enabled ? "Desativar" : "Ativar"}</button>
                  <button className="link" onClick={() => act(`/sources/${s.id}/collect`)}>Coletar</button>
                  <button className="link" onClick={async () => setRuns({ id: s.id, items: await api<SourceRun[]>(`/sources/${s.id}/runs`) })}>Histórico</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {runs && (
        <div className="card">
          <div className="page-head"><h3>Histórico de coletas</h3><button className="link" onClick={() => setRuns(null)}>Fechar</button></div>
          <table>
            <thead><tr><th>Início</th><th>Status</th><th>Lidas</th><th>Novas</th><th>Duplicadas</th><th>Erro</th></tr></thead>
            <tbody>{runs.items.map((r) => <tr key={r.id}><td>{fmtDateTime(r.started_at)}</td><td><StatusBadge status={r.status} /></td><td>{r.items_found}</td><td>{r.items_new}</td><td>{r.items_duplicate}</td><td className="small">{r.error ?? "—"}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
