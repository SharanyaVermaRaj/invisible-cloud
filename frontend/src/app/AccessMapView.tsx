import { useMemo, useState } from "react";
import { Action, api, Decision, DocumentItem } from "../api";
import { useApp } from "./context";

type Level = "full" | "edit" | "read" | "none";

function levelOf(d: DocumentItem, person: string): Level {
  const a = d.access;
  if (!a) return "none";
  if (a.share.includes(person)) return "full";
  if (a.edit.includes(person)) return "edit";
  if (a.read.includes(person)) return "read";
  return "none";
}
const LEVEL_WORD: Record<Level, string> = {
  full: "can open, edit, send and share", edit: "can open, edit and send", read: "can open", none: "can't open",
};

export function AccessMapView() {
  const { state, name } = useApp();
  const [why, setWhy] = useState<{ person: string; doc: DocumentItem; level: Level; decision?: Decision } | null>(null);

  const columns = useMemo(() => {
    const byClient = new Map<string, DocumentItem[]>();
    for (const d of state.documents) byClient.set(d.client ?? "", [...(byClient.get(d.client ?? "") ?? []), d]);
    return [...byClient.entries()].sort((a, b) => name(a[0]).localeCompare(name(b[0])));
  }, [state.documents, name]);

  const people = useMemo(() => {
    const order = (keys: string[]) => (keys.includes("partner") ? 0 : keys.includes("accountant") ? 1 : 2);
    return [...state.people].sort((a, b) => order(a.roles) - order(b.roles) || a.name.localeCompare(b.name));
  }, [state.people]);

  const explain = async (person: string, doc: DocumentItem) => {
    const level = levelOf(doc, person);
    setWhy({ person, doc, level });
    const action: Action = level === "full" ? "share" : level === "edit" ? "edit" : "read";
    try {
      const decision = await api.can(person, action, doc.key);
      setWhy(w => (w && w.person === person && w.doc.key === doc.key ? { ...w, decision } : w));
    } catch { /* the level is still shown */ }
  };

  return (
    <div>
      <div className="page-head">
        <h2>Who can open what</h2>
        <p>Calculated live from your people, assignments and rules. Click any square to see the reason.</p>
      </div>
      <div className="amap-wrap">
        <table className="amap">
          <thead>
            <tr className="clients">
              <th />
              {columns.map(([client, docs]) => <th key={client} colSpan={docs.length} scope="colgroup">{name(client)}</th>)}
            </tr>
            <tr>
              <th />
              {columns.flatMap(([, docs]) => docs).map(d => <th key={d.key} scope="col">{d.name}</th>)}
            </tr>
          </thead>
          <tbody>
            {people.map(p => (
              <tr key={p.key}>
                <th scope="row">{p.name}<small>{p.title}</small></th>
                {columns.flatMap(([, docs]) => docs).map(d => {
                  const level = levelOf(d, p.key);
                  return (
                    <td key={d.key}>
                      <button className={`c ${level}`} onClick={() => explain(p.key, d)}
                              aria-label={`${p.name} ${LEVEL_WORD[level]} ${d.name}`}>
                        {level === "full" && (
                          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 6.2l2.3 2.3 4.7-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="amap-legend">
          <span><i style={{ background: "var(--ink)" }} />Open, edit, send and share</span>
          <span><i style={{ background: "#46524b" }} />Open, edit and send</span>
          <span><i style={{ background: "#a9b3ac" }} />Open only</span>
          <span><i style={{ background: "var(--sunk)" }} />No access</span>
        </div>
        <div className="why" aria-live="polite">
          {why ? (
            <>
              <b>{name(why.person)}</b> {LEVEL_WORD[why.level]} <b>{why.doc.name}</b>.{" "}
              {why.decision ? why.decision.reason : "Checking the reason…"}
            </>
          ) : (
            <span style={{ color: "var(--ink-3)" }}>Click a square to see which rule decides it.</span>
          )}
        </div>
      </div>
    </div>
  );
}
