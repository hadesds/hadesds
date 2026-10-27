import { post } from "../api";
import { Empty, ErrorBox, Loading } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useData } from "../components/useData";
import { fmtDate, fmtDateTime } from "../format";
import type { Delivery } from "../types";

const RESENDABLE = ["failed", "failed_auth", "needs_review", "blocked"];

export default function Deliveries() {
  const { data, error, loading, reload } = useData<Delivery[]>("/deliveries");
  async function resend(d: Delivery) {
    const warn = d.status === "needs_review" ? "O envio anterior foi interrompido e pode ter chegado. Reenviar mesmo assim?" : "Reenviar esta entrega?";
    if (!window.confirm(warn)) return;
    await post(`/deliveries/${d.id}/resend`);
    void reload();
  }
  return (
    <section>
      <h2>Entregas</h2>
      <p className="muted small">"Aceita pelo provedor" significa que o servidor SMTP ou a API do WhatsApp aceitou a mensagem; a confirmação de leitura/entrega não é recebida nesta versão local.</p>
      <ErrorBox message={error} />
      <Loading show={loading && !data} />
      {data?.length === 0 && <Empty>Nenhuma entrega registrada.</Empty>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Edição</th><th>Canal</th><th>Destinatário</th><th>Status</th><th>Tentativas</th><th>Identificador do provedor</th><th>Último erro</th><th></th></tr></thead>
          <tbody>
            {data?.map((d) => (
              <tr key={d.id}>
                <td>{fmtDate(d.edition_date)}</td>
                <td>{d.channel === "email" ? "E-mail" : "WhatsApp"}</td>
                <td>{d.recipient}</td>
                <td><StatusBadge status={d.status} />{d.sent_at && <div className="small">{fmtDateTime(d.sent_at)}</div>}</td>
                <td>{d.attempts}{d.next_attempt_at && d.status === "retrying" && <div className="small">próxima: {fmtDateTime(d.next_attempt_at)}</div>}</td>
                <td className="small mono">{d.provider_message_id ?? "—"}</td>
                <td className="small">{d.last_error ?? "—"}</td>
                <td>{RESENDABLE.includes(d.status) && <button className="link" onClick={() => resend(d)}>Reenviar</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
