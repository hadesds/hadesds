const TOKEN_KEY = "devpulse.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* armazenamento indisponível: a sessão dura até recarregar a página */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (typeof d === "string" ? d : d.erro ?? d.msg ?? JSON.stringify(d))).join("; ");
  return "Erro inesperado";
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(`/api${path}`, { ...options, headers });
  if (res.status === 401 && path !== "/auth/login") {
    setToken(null);
    window.dispatchEvent(new Event("devpulse:logout"));
  }
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      message = detailMessage((await res.json()).detail);
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(res.status, message);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
