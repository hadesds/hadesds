const TZ = "America/Fortaleza";

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : "—";
}

export function fmtSeconds(s: number | null | undefined): string {
  if (s == null) return "—";
  return s >= 60 ? `${Math.floor(s / 60)}min${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}

export const CATEGORY_LABEL: Record<string, string> = {
  desenvolvimento: "Desenvolvimento", ia: "IA", infraestrutura: "Infraestrutura", seguranca: "Segurança", mercado: "Mercado",
};

export const STATUS_LABEL: Record<string, string> = {
  pending: "Pendente", running: "Executando", completed: "Concluída", failed: "Falhou", skipped: "Ignorada",
  success: "Sucesso", partial: "Parcial", sent: "Aceita pelo provedor", sending: "Enviando", retrying: "Nova tentativa",
  failed_auth: "Falha de autenticação", blocked: "Bloqueada", needs_review: "Revisar", disabled: "Canal desativado",
  draft: "Rascunho", verified: "Verificado", rejected: "Reprovado", recorded: "Gravado", published: "Publicado",
  verified_with_warnings: "Verificado com ressalvas",
};

export function statusTone(status: string): "ok" | "warn" | "bad" | "neutral" {
  if (["completed", "success", "sent", "verified", "recorded", "published"].includes(status)) return "ok";
  if (["failed", "failed_auth", "rejected"].includes(status)) return "bad";
  if (["pending", "running", "retrying", "sending", "partial", "needs_review", "blocked", "verified_with_warnings"].includes(status)) return "warn";
  return "neutral";
}
