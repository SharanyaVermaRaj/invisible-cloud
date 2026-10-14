import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { AccessChange, Action } from "./api";

/* ---------- icons (hand-drawn, 24px grid, stroke) ---------- */
const paths: Record<string, ReactNode> = {
  ask: <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 4v-4H5.5A1.5 1.5 0 0 1 4 14.5z" />,
  docs: <><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v4h4M10 12h5M10 16h5" /></>,
  map: <><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></>,
  people: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" /><path d="M16 4.8a3.3 3.3 0 0 1 0 6.4M18 14.8c1.8.7 3 2.4 3.5 5.2" /></>,
  rules: <><path d="M5 4h14v16H5z" /><path d="M9 9h6M9 13h6M9 17h3" /></>,
  history: <><path d="M3.5 12a8.5 8.5 0 1 0 2.5-6" /><path d="M3 4v4h4M12 8v4l3 2" /></>,
  approvals: <><path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z" /><path d="M8.5 12l2.5 2.5 4.5-5" /></>,
  lock: <><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>,
  warn: <><path d="M12 4l9 16H3z" /><path d="M12 10v4M12 17v.5" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" /></>,
  upload: <><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 16v4h16v-4" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  chevron: <path d="M7 10l5 5 5-5" />,
  send: <path d="M4 12l16-8-6 16-3-7z" />,
  open: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 14v6H4V6h6" /></>,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  reset: <><path d="M4 12a8 8 0 1 0 2.3-5.6" /><path d="M4 4v4h4" /></>,
  share: <><circle cx="6" cy="12" r="2.5" /><circle cx="17" cy="6" r="2.5" /><circle cx="17" cy="18" r="2.5" /><path d="M8.3 10.8l6.4-3.6M8.3 13.2l6.4 3.6" /></>,
};

export function Icon({ name, className }: { name: keyof typeof paths | string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
         strokeLinejoin="round" className={className} aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

export function Logo() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#16201B" />
      <rect x="7" y="7" width="7" height="7" rx="1.5" fill="#F2F4F0" />
      <rect x="18.2" y="8.2" width="5.6" height="5.6" rx="1.2" fill="none" stroke="#F2F4F0" strokeWidth="2.4" />
      <rect x="8.2" y="18.2" width="5.6" height="5.6" rx="1.2" fill="none" stroke="#F2F4F0" strokeWidth="2.4" />
      <rect x="18" y="18" width="7" height="7" rx="1.5" fill="#6F7CF0" />
    </svg>
  );
}

/* ---------- people ---------- */
const AVATAR_COLORS = ["#2e3fd1", "#1c7350", "#8a3ea8", "#a8551b", "#0f6b84", "#b12f49", "#4d5b16", "#5b4636"];
export function avatarColor(key: string) {
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}
export function initials(name: string) {
  const parts = name.replace(/\(.*?\)/g, "").trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}
export function Avatar({ person, name, small }: { person: string; name: string; small?: boolean }) {
  return (
    <span className={`avatar${small ? " sm" : ""}`} style={{ background: avatarColor(person) }} title={name}>
      {initials(name)}
    </span>
  );
}

/* ---------- access diff, grouped by person ---------- */
const ACTION_WORD: Record<Action, string> = { read: "Open", edit: "Edit", share: "Share", send: "Send" };

export function AccessDiff({ gained, lost }: { gained: AccessChange[]; lost: AccessChange[] }) {
  const people = new Map<string, { name: string; items: { change: AccessChange; kind: "gain" | "loss" }[] }>();
  for (const [list, kind] of [[gained, "gain"], [lost, "loss"]] as const) {
    for (const c of list) {
      const entry = people.get(c.person) ?? { name: c.person_name, items: [] };
      entry.items.push({ change: c, kind });
      people.set(c.person, entry);
    }
  }
  if (people.size === 0) return <p className="empty-diff">Nobody gains or loses access to any document.</p>;
  return (
    <div className="diff">
      {[...people.entries()].map(([key, { name, items }]) => {
        // Collapse actions per document: "Acme W-2: open, edit, send"
        const docs = new Map<string, { name: string; kind: "gain" | "loss"; actions: Action[] }>();
        for (const { change, kind } of items) {
          const id = `${kind}:${change.resource}`;
          const d = docs.get(id) ?? { name: change.resource_name, kind, actions: [] };
          d.actions.push(change.action);
          docs.set(id, d);
        }
        return (
          <div className="diff-person" key={key}>
            <div className="who"><Avatar person={key} name={name} small />{name}</div>
            <div className="chips">
              {[...docs.entries()].map(([id, d]) => (
                <span key={id} className={`chip ${d.kind}`}
                      aria-label={`${d.kind === "gain" ? "Gains" : "Loses"} ${d.actions.join(", ")} on ${d.name}`}>
                  <b>{d.kind === "gain" ? "+" : "−"}</b>
                  {d.name}
                  <span style={{ opacity: 0.75 }}>({d.actions.map(a => ACTION_WORD[a].toLowerCase()).join(", ")})</span>
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ---------- toasts ---------- */
type ToastMsg = { text: string; error?: boolean; action?: { label: string; run: () => void } };
const ToastCtx = createContext<(t: ToastMsg) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const timer = useRef<number>();
  const show = useCallback((t: ToastMsg) => {
    setToast(t);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), t.error ? 7000 : 5000);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && (
        <div className={`toast${toast.error ? " error" : ""}`} role="status" aria-live="polite">
          <span>{toast.text}</span>
          {toast.action && <button onClick={() => { toast.action!.run(); setToast(null); }}>{toast.action.label}</button>}
        </div>
      )}
    </ToastCtx.Provider>
  );
}

export function timeAgo(iso: string) {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 45) return "just now";
  if (secs < 3600) return `${Math.round(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
