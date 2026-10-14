// Typed client for the Python API. Every request carries the persona being viewed.

export type Action = "read" | "edit" | "share" | "send";

export interface Decision { allowed: boolean; reason: string; rule: string | null }
export interface Person {
  key: string; name: string; title: string; email: string;
  roles: string[]; assignments: string[]; contact_for: string[];
}
export interface ClientService {
  key: string; name: string; client: string | null; service: string | null;
  assignees: string[]; documents: string[];
}
export interface RuleItem {
  key: string; version: number; text: string; type: string; description: string;
  definition: Record<string, unknown>;
}
export interface DocumentItem {
  key: string; name: string; kind: string; kind_label: string; amount: number | null;
  filename: string | null; size: number | null; client_service: string | null; client: string | null;
  has_file: boolean; my_access: Record<Action, Decision>;
  approval: { rule: string; approver_role: string; reason: string } | null;
  delivery?: { id: number; status: "pending" | "sent" | "rejected"; requested_by: string;
               decided_by: string | null; created_at: string; decided_at: string | null };
  access?: Record<Action, string[]>;
}
export interface Approval {
  id: number; document: string; document_name: string; requested_by: string;
  requested_by_name: string; amount: number | null; reason: string; created_at: string;
}
export interface AppState {
  workspace: { name: string; created_at: string };
  ai_enabled: boolean;
  suggestions: string[];
  me: { key: string; name: string; title: string; roles: string[]; is_admin: boolean };
  names: Record<string, string>;
  people: Person[];
  roles: { key: string; name: string }[];
  clients: { key: string; name: string; contacts: string[]; services: string[] }[];
  services: { key: string; name: string }[];
  client_services: ClientService[];
  rules: RuleItem[];
  documents: DocumentItem[];
  hidden_documents: number;
  approvals: Approval[];
  kinds: { key: string; label: string }[];
}
export interface AccessChange {
  person: string; person_name: string; action: Action; resource: string; resource_name: string;
}
export interface Conflict { kind: string; rules: string[]; message: string }
export interface Resolution {
  id: string; label: string; changes: string[]; proposal: Proposal | null;
  gained: AccessChange[]; lost: AccessChange[]; operations: string[];
}
export interface Proposal { summary: string; operations: Record<string, unknown>[] }
export interface Preview {
  summary: string; operations: string[]; gained: AccessChange[]; lost: AccessChange[];
  conflicts: Conflict[]; resolutions: Resolution[]; proposal: Proposal;
}
export type AskResult =
  | ({ type: "proposal" } & Preview)
  | { type: "question"; text: string }
  | { type: "answer"; text: string };
export interface HistoryItem {
  id: number; actor: string; actor_name: string; summary: string; created_at: string;
  diff: { operations: string[]; gained: AccessChange[]; lost: AccessChange[] };
  undoable: boolean; reverted_by: number | null; reverts: number | null;
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public body: any) { super(message); }
}

const PERSONA_KEY = "ic.persona";
export function getPersona(): string | null {
  try { return localStorage.getItem(PERSONA_KEY); } catch { return null; }
}
export function setPersona(key: string | null) {
  try { key ? localStorage.setItem(PERSONA_KEY, key) : localStorage.removeItem(PERSONA_KEY); } catch { /* private mode */ }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const persona = getPersona();
  if (persona) headers["X-Acting-As"] = persona;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: payload, credentials: "same-origin" });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0, null);
  }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) {
    const detail = typeof data?.detail === "string" ? data.detail
      : Array.isArray(data?.detail) ? "Some of the details aren't valid." : `Request failed (${res.status}).`;
    throw new ApiError(detail, res.status, data);
  }
  return data as T;
}

export const api = {
  state: () => request<AppState>("GET", "/api/state"),
  reset: () => request<{ ok: true }>("POST", "/api/workspace/reset"),
  ask: (text: string) => request<AskResult>("POST", "/api/ask", { text }),
  preview: (p: Proposal) => request<Preview>("POST", "/api/changes/preview", p),
  apply: (p: Proposal) => request<{ id: number }>("POST", "/api/changes", p),
  history: () => request<HistoryItem[]>("GET", "/api/history"),
  undoPreview: (id: number) => request<Preview>("POST", `/api/history/${id}/undo/preview`),
  undo: (id: number) => request<{ id: number }>("POST", `/api/history/${id}/undo`),
  upload: (form: FormData) => request<{ key: string }>("POST", "/api/documents", form),
  send: (key: string) => request<{ status: string }>("POST", `/api/documents/${key}/send`),
  decide: (id: number, decision: "approve" | "reject") =>
    request<{ status: string }>("POST", `/api/approvals/${id}/${decision}`, { note: "" }),
  can: (person: string, action: Action, resource: string) =>
    request<Decision>("GET", `/api/can?person=${encodeURIComponent(person)}&action=${action}&resource=${encodeURIComponent(resource)}`),
  fileUrl: (key: string) => {
    const persona = getPersona();
    return `/api/documents/${encodeURIComponent(key)}/file${persona ? `?as=${encodeURIComponent(persona)}` : ""}`;
  },
};

export const money = (n: number | null | undefined) =>
  n == null ? "" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
