import { FormEvent, useEffect, useState } from "react";
import { post, put } from "../api";
import { ErrorBox, Loading } from "../components/Feedback";
import { useData } from "../components/useData";
import { CATEGORY_LABEL } from "../format";
import type { SettingsView } from "../types";

type Field = { key: string; label: string; type: "text" | "number" | "time" | "bool"; hint?: string };
const FIELDS: { title: string; fields: Field[] }[] = [
  { title: "Agenda (America/Fortaleza)", fields: [
    { key: "edition_main_time", label: "Edição principal", type: "time" },
    { key: "edition_secondary_time", label: "Edição complementar (opcional)", type: "text", hint: "HH:MM ou vazio" },
    { key: "edition_catchup_until", label: "Recuperar edição perdida até", type: "time", hint: "depois disso, a edição do dia não é enviada" },
    { key: "collect_interval_minutes", label: "Coleta a cada (min)", type: "number" },
  ] },
  { title: "Editorial", fields: [
    { key: "daily_script_limit", label: "Roteiros por dia (máx. 3)", type: "number" },
    { key: "min_editorial_score", label: "Pontuação mínima", type: "number" },
    { key: "exceptional_score", label: "Pontuação de acontecimento excepcional", type: "number", hint: "permite repetir categoria" },
    { key: "max_per_category", label: "Máximo por categoria/dia", type: "number" },
    { key: "freshness_hours", label: "Janela de atualidade (h)", type: "number" },
    { key: "topic_retention_days", label: "Não repetir tema por (dias)", type: "number" },
    { key: "max_extractions_per_run", label: "Páginas abertas por edição", type: "number" },
  ] },
  { title: "Entregas", fields: [
    { key: "email_recipient", label: "E-mail destinatário", type: "text" },
    { key: "whatsapp_recipient", label: "WhatsApp destinatário (E.164)", type: "text", hint: "+5598999999999" },
    { key: "whatsapp_recipient_opt_in", label: "Destinatário aceitou receber mensagens (opt-in)", type: "bool" },
  ] },
  { title: "IA", fields: [
    { key: "llm_provider", label: "Provedor (anthropic | openai_compatible | none)", type: "text" },
    { key: "llm_model_script", label: "Modelo dos roteiros", type: "text" },
    { key: "llm_model_fast", label: "Modelo econômico (pontuação)", type: "text" },
    { key: "llm_max_calls_per_day", label: "Limite de chamadas por dia", type: "number" },
  ] },
];

export default function SettingsPage() {
  const { data, error, loading, setData } = useData<SettingsView>("/settings");
  const [values, setValues] = useState<SettingsView["editable"]>({});
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (data) setValues(data.editable); }, [data]);

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      const res = await put<Pick<SettingsView, "editable" | "integrations">>("/settings", values);
      setData({ ...data!, ...res });
      setMsg("Configurações salvas. O worker reprograma a agenda em alguns segundos.");
    } catch (err) {
      setMsg((err as Error).message);
    }
  }

  async function test(channel: string) {
    if (!window.confirm(`Enviar uma mensagem REAL de teste por ${channel}?`)) return;
    try {
      const r = await post<{ ok: boolean; error: string | null; provider_message_id: string | null }>(`/integrations/${channel}/test`);
      setMsg(r.ok ? `Teste aceito pelo provedor (id ${r.provider_message_id ?? "—"}).` : `Falhou: ${r.error}`);
    } catch (err) {
      setMsg((err as Error).message);
    }
  }

  if (!data) return <><ErrorBox message={error} /><Loading show={loading} /></>;
  const cats = (values.priority_categories as string[]) ?? [];
  const integ = data.integrations;
  return (
    <section>
      <h2>Configurações</h2>
      {msg && <div className="alert">{msg}</div>}
      <form onSubmit={save}>
        {FIELDS.map((group) => (
          <div className="card form-grid" key={group.title}>
            <h3 className="wide">{group.title}</h3>
            {group.fields.map((f) => (
              <label key={f.key} className={f.type === "bool" ? "inline wide" : ""}>
                {f.type === "bool" ? (
                  <><input type="checkbox" checked={Boolean(values[f.key])} onChange={(e) => setValues({ ...values, [f.key]: e.target.checked })} /> {f.label}</>
                ) : (
                  <>{f.label}<input type={f.type === "number" ? "number" : f.type === "time" ? "time" : "text"} value={String(values[f.key] ?? "")}
                    onChange={(e) => setValues({ ...values, [f.key]: f.type === "number" ? Number(e.target.value) : e.target.value })} /></>
                )}
                {f.hint && <span className="muted small">{f.hint}</span>}
              </label>
            ))}
            {group.title === "Editorial" && (
              <fieldset className="wide">
                <legend>Categorias prioritárias</legend>
                {data.categories.map((c) => (
                  <label key={c} className="inline">
                    <input type="checkbox" checked={cats.includes(c)} onChange={(e) => setValues({ ...values, priority_categories: e.target.checked ? [...cats, c] : cats.filter((x) => x !== c) })} />
                    {CATEGORY_LABEL[c]}
                  </label>
                ))}
              </fieldset>
            )}
          </div>
        ))}
        <button type="submit">Salvar configurações</button>
      </form>
      <div className="card">
        <h3>Integrações (definidas no .env)</h3>
        <p className="muted small">Credenciais nunca são exibidas nem editadas pelo painel.</p>
        <table>
          <tbody>
            <tr><th>E-mail (SMTP)</th><td>{integ.email.enabled ? "ativado" : "desativado"} · {(integ.email.missing as string[]).length ? `faltando: ${(integ.email.missing as string[]).join(", ")}` : "credenciais presentes"}</td><td><button className="link" onClick={() => test("email")}>Enviar teste</button></td></tr>
            <tr><th>WhatsApp Business</th><td>{integ.whatsapp.enabled ? "ativado" : "desativado"} · modo {String(integ.whatsapp.mode)} · {(integ.whatsapp.missing as string[]).length ? `faltando: ${(integ.whatsapp.missing as string[]).join(", ")}` : "credenciais presentes"}</td><td><button className="link" onClick={() => test("whatsapp")}>Enviar teste</button></td></tr>
            <tr><th>IA</th><td>{String(integ.llm.provider)} · chave {integ.llm.api_key_configured ? "configurada" : "ausente"}</td><td /></tr>
            <tr><th>Caixa de newsletters</th><td>{String(integ.newsletter_mailbox.provider)} {integ.newsletter_mailbox.address ? `(${String(integ.newsletter_mailbox.address)})` : ""}</td><td /></tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
