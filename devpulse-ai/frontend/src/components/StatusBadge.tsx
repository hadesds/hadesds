import { STATUS_LABEL, statusTone } from "../format";

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${statusTone(status)}`}>{STATUS_LABEL[status] ?? status}</span>;
}
