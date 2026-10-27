import { FormEvent, useState } from "react";
import { api } from "../api";
import { Empty, ErrorBox, Loading } from "../components/Feedback";
import { useData } from "../components/useData";
import { CATEGORY_LABEL, fmtDateTime } from "../format";
import type { NewsDetail, NewsItem } from "../types";

const ACCESS: Record<string, string> = { full: "conteúdo completo", partial: "parcial", summary_only: "só resumo", unavailable: "indisponível", restricted: "restrito" };

export default function News() {
  const [filters, setFilters] = useState({ q: "", category: "", date_from: "", date_to: "", min_score: "" });
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams(Object.entries({ ...Object.fromEntries(new URLSearchParams(query)), page: String(page) }).filter(([, v]) => v));
  const list = useData<{ total: number; items: NewsItem[] }>(`/news?${params.toString()}`);
  const [detail, setDetail] = useState<NewsDetail | null>(null);

  function search(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    setQuery(new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString());
  }

  return (
    <section>
      <h2>Notícias</h2>
      <form className="filters" onSubmit={search}>
        <input placeholder="Palavra-chave" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
        <select value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}>
          <option value="">Todas as categorias</option>
          {Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <label className="inline">De <input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} /></label>
        <label className="inline">Até <input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} /></label>
        <input type="number" placeholder="Pontuação mín." min={0} max={100} value={filters.min_score} onChange={(e) => setFilters({ ...filters, min_score: e.target.value })} />
        <button type="submit">Filtrar</button>
      </form>
      <ErrorBox message={list.error} />
      <Loading show={list.loading && !list.data} />
      {list.data?.items.length === 0 && <Empty>Nenhuma notícia encontrada.</Empty>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Título</th><th>Fonte</th><th>Publicação</th><th>Coleta</th><th>Categoria</th><th>Pontuação</th><th>Verificação</th></tr></thead>
          <tbody>
            {list.data?.items.map((n) => (
              <tr key={n.id} className="clickable" onClick={async () => setDetail(await api<NewsDetail>(`/news/${n.id}`))}>
                <td><strong>{n.title}</strong><br /><span className="muted small">{ACCESS[n.content_access] ?? n.content_access}{n.content_type !== "fact" ? ` · ${n.content_type}` : ""}</span></td>
                <td>{n.source?.name}</td>
                <td>{fmtDateTime(n.published_at)}{n.published_at_inferred && <span className="muted small"> (data da newsletter)</span>}</td>
                <td>{fmtDateTime(n.discovered_at)}</td>
                <td>{n.category ? CATEGORY_LABEL[n.category] : "—"}</td>
                <td>{n.editorial_score?.toFixed(0) ?? "—"}</td>
                <td className="small">{n.verification_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {list.data && list.data.total > 30 && (
        <div className="pager">
          <button className="secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>Anterior</button>
          <span>Página {page} de {Math.ceil(list.data.total / 30)}</span>
          <button className="secondary" disabled={page * 30 >= list.data.total} onClick={() => setPage(page + 1)}>Próxima</button>
        </div>
      )}
      {detail && (
        <div className="drawer" role="dialog" aria-label="Detalhes da notícia">
          <div className="page-head"><h3>{detail.title}</h3><button className="link" onClick={() => setDetail(null)}>Fechar</button></div>
          <p><a href={detail.url} target="_blank" rel="noreferrer noopener">{detail.url}</a></p>
          <p className="small">Publicada: {fmtDateTime(detail.published_at)} · Atualizada na fonte: {fmtDateTime(detail.source_updated_at)} · Coletada: {fmtDateTime(detail.discovered_at)}</p>
          {detail.extraction_error && <div className="alert">Limitação de acesso: {detail.extraction_error}</div>}
          <p>{detail.summary}</p>
          <h4>Referências</h4>
          <ul>{detail.references.map((r, i) => <li key={i}>{r.source} ({r.type}) — <a href={r.url} target="_blank" rel="noreferrer noopener">{r.url}</a></li>)}</ul>
          <h4>Notícias relacionadas (mesmo acontecimento)</h4>
          {detail.related.length ? <ul>{detail.related.map((r) => <li key={r.id}>{r.title} — {r.source?.name}</li>)}</ul> : <p className="muted">Nenhuma.</p>}
          <h4>Pontuações</h4>
          {detail.scores.map((s, i) => (
            <div key={i} className="small">
              <strong>{s.total.toFixed(0)}</strong> ({s.method}) {s.eligible ? "elegível" : `inelegível: ${s.reason}`}
              <div className="muted">{Object.entries(s.components).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}</div>
            </div>
          ))}
          <h4>Trecho acessível</h4>
          <pre className="excerpt">{detail.content_excerpt || "—"}</pre>
        </div>
      )}
    </section>
  );
}
