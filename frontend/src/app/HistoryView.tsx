import { useCallback, useEffect, useState } from "react";
import { api, ApiError, HistoryItem, Preview } from "../api";
import { timeAgo, useToast } from "../ui";
import { ProposalCard } from "./AskView";
import { useApp } from "./context";

export function HistoryView() {
  const { refresh } = useApp();
  const toast = useToast();
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [undoing, setUndoing] = useState<{ id: number; preview: Preview } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setItems(await api.history()); }
    catch (e) { toast({ text: e instanceof ApiError ? e.message : "Couldn't load history.", error: true }); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  const startUndo = async (id: number) => {
    setBusy(true);
    try { setUndoing({ id, preview: await api.undoPreview(id) }); }
    catch (e) { toast({ text: e instanceof ApiError ? e.message : "Couldn't prepare the undo.", error: true }); }
    finally { setBusy(false); }
  };

  const confirmUndo = async () => {
    if (!undoing) return;
    setBusy(true);
    try {
      await api.undo(undoing.id);
      setUndoing(null);
      await Promise.all([load(), refresh()]);
      toast({ text: "Change undone. Everything is back the way it was." });
    } catch (e) {
      toast({ text: e instanceof ApiError ? e.message : "Couldn't undo.", error: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="page-head">
        <h2>History</h2>
        <p>Every change to how the firm works, newest first. Undo any change and everything it affected goes back.</p>
      </div>
      {!items && <p style={{ color: "var(--ink-3)" }}>Loading history{"…"}</p>}
      {items && (
        <ol className="timeline">
          {items.map(c => {
            const isSystem = c.actor === "system";
            const undone = c.reverted_by !== null;
            return (
              <li key={c.id} className={`tl${undone ? " undone" : ""}${isSystem ? " system" : ""}`}>
                <span className="dot" aria-hidden="true" />
                <div className="tl-card">
                  <div className="tl-top">
                    <div>
                      <p className="said">{c.summary}</p>
                      <p className="tl-meta">{isSystem ? "Demo setup" : c.actor_name}, {timeAgo(c.created_at)}</p>
                    </div>
                    {c.undoable && undoing?.id !== c.id && (
                      <button className="btn btn-sm" onClick={() => startUndo(c.id)} disabled={busy}>Undo</button>
                    )}
                    {undone && <span className="badge">Undone</span>}
                  </div>
                  {!isSystem && (
                    <div className="counts">
                      {c.diff.gained.length > 0 && <span className="badge gain">{c.diff.gained.length} access gained</span>}
                      {c.diff.lost.length > 0 && <span className="badge loss">{c.diff.lost.length} access removed</span>}
                      {c.diff.gained.length + c.diff.lost.length === 0 && <span className="badge">No access changed</span>}
                    </div>
                  )}
                  <details>
                    <summary>{c.diff.operations.length} step{c.diff.operations.length === 1 ? "" : "s"}</summary>
                    <ul>{c.diff.operations.map((o, i) => <li key={i}>{o}</li>)}</ul>
                  </details>
                  {undoing?.id === c.id && (
                    <ProposalCard preview={undoing.preview} busy={busy} kicker="Undoing this change will"
                                  confirmLabel="Undo this change" onApply={confirmUndo}
                                  onDiscard={() => setUndoing(null)} />
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
