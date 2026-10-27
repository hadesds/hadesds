export function ErrorBox({ message }: { message: string | null }) {
  return message ? <div className="alert alert-bad" role="alert">{message}</div> : null;
}

export function Loading({ show }: { show: boolean }) {
  return show ? <p className="muted">Carregando…</p> : null;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}
