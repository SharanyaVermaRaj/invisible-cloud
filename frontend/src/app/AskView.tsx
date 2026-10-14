import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { api, ApiError, AskResult, Preview, Proposal, Resolution } from "../api";
import { AccessDiff, Icon, useToast } from "../ui";
import { useApp } from "./context";

export function AskView() {
  const { state, refresh } = useApp();
  const toast = useToast();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AskResult | null>(null);
  const [asked, setAsked] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setBusy(true); setError(null); setResult(null); setAsked(value);
    try {
      setResult(await api.ask(value));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  const apply = async (proposal: Proposal) => {
    setBusy(true);
    try {
      const applied = await api.apply(proposal);
      await refresh();
      setResult(null); setText("");
      toast({
        text: "Change applied. Every document now follows it.",
        action: { label: "Undo", run: async () => {
          try { await api.undo(applied.id); await refresh(); toast({ text: "Change undone." }); }
          catch (err) { toast({ text: err instanceof ApiError ? err.message : "Couldn't undo.", error: true }); }
        } },
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.body?.preview) {
        setResult({ type: "proposal", ...err.body.preview });
      } else {
        toast({ text: err instanceof ApiError ? err.message : "Couldn't apply the change.", error: true });
      }
    } finally {
      setBusy(false);
    }
  };

  const discard = (message = "Discarded. Nothing changed.") => {
    setResult(null);
    toast({ text: message });
    inputRef.current?.focus();
  };

  return (
    <div>
      {!state.ai_enabled && (
        <div className="notice hold">
          <Icon name="warn" />
          <p>The AI isn't switched on for this server yet, so plain-English changes won't work. Add an
            ANTHROPIC_API_KEY to the server's settings to turn it on. Everything else in the demo works.</p>
        </div>
      )}

      <form className="ask" onSubmit={submit}>
        <label htmlFor="ask-input">What changed at the firm?</label>
        <textarea
          id="ask-input" ref={inputRef} rows={2} value={text} maxLength={1000}
          placeholder="Mike is no longer handling Acme's payroll. Sarah will handle it."
          onChange={e => setText(e.target.value)} onKeyDown={onKey} disabled={busy}
        />
        <div className="ask-bar">
          <small>Describe a change, add a rule, or ask a question. Nothing changes until you confirm.</small>
          <button className="btn btn-brand" type="submit" disabled={busy || !text.trim() || !state.ai_enabled}>
            Preview change
          </button>
        </div>
        <div className="tries">
          <h3>Try saying</h3>
          <ul>
            {state.suggestions.map(s => (
              <li key={s}>
                <button type="button" onClick={() => { setText(s); inputRef.current?.focus(); }}>{s}</button>
              </li>
            ))}
          </ul>
        </div>
      </form>

      {busy && !result && (
        <div className="thinking" role="status">
          <span className="dots"><i /><i /><i /></span>Reading your firm's setup and working out what changes{"…"}
        </div>
      )}
      {error && <div className="notice loss" style={{ marginTop: 24 }}><Icon name="warn" /><p>{error}</p></div>}

      {result?.type === "proposal" && (
        <ProposalCard preview={result} busy={busy} onApply={apply} onDiscard={discard} />
      )}
      {result?.type === "question" && (
        <div className="result">
          <div className="result-head">
            <p className="kicker">One detail first</p>
            <p className="said">{result.text}</p>
          </div>
          <div className="result-foot">
            <span className="note">Add the detail to your sentence above and preview again.</span>
            <button className="btn" onClick={() => { setResult(null); inputRef.current?.focus(); }}>Edit my sentence</button>
          </div>
        </div>
      )}
      {result?.type === "answer" && (
        <div className="result">
          <div className="result-head">
            <p className="kicker">You asked</p>
            <p className="said">{asked}</p>
          </div>
          <div className="answer">{result.text}</div>
        </div>
      )}
    </div>
  );
}

export function ProposalCard({ preview, busy, onApply, onDiscard, confirmLabel = "Apply change", kicker = "Here's what I understood" }: {
  preview: Preview; busy: boolean; onApply: (p: Proposal) => void; onDiscard: (msg?: string) => void;
  confirmLabel?: string; kicker?: string;
}) {
  const hasConflict = preview.conflicts.length > 0;
  return (
    <div className="result">
      <div className="result-head">
        <p className="kicker">{kicker}</p>
        <p className="said">{"“"}{preview.summary}{"”"}</p>
      </div>
      <div className="result-body">
        <section>
          <h4>What will change</h4>
          <ul className="ops">{preview.operations.map((o, i) => <li key={i}>{o}</li>)}</ul>
        </section>
        <section>
          <h4>Who gains and loses access</h4>
          <AccessDiff gained={preview.gained} lost={preview.lost} />
        </section>
        {hasConflict && (
          <section className="conflict">
            <h4><Icon name="warn" />This clashes with {preview.conflicts.length > 1 ? "existing rules" : "an existing rule"}</h4>
            {preview.conflicts.map((c, i) => <p key={i}>{c.message}</p>)}
            {preview.resolutions.length > 0 && (
              <div className="options">
                {preview.resolutions.map(r => (
                  <ResolutionOption key={r.id} r={r} busy={busy} onApply={onApply} onDiscard={onDiscard} />
                ))}
              </div>
            )}
          </section>
        )}
      </div>
      <div className="result-foot">
        <span className="note">{hasConflict ? "Choose how to resolve the clash, or discard." : "Nothing has changed yet."}</span>
        <button className="btn" onClick={() => onDiscard()} disabled={busy}>Discard</button>
        {!hasConflict && (
          <button className="btn btn-primary" onClick={() => onApply(preview.proposal)} disabled={busy}>
            {confirmLabel}
          </button>
        )}
      </div>
    </div>
  );
}

function ResolutionOption({ r, busy, onApply, onDiscard }: {
  r: Resolution; busy: boolean; onApply: (p: Proposal) => void; onDiscard: (msg?: string) => void;
}) {
  const moves = r.gained.length + r.lost.length;
  return (
    <div className="option">
      <h5>{r.label}</h5>
      <ul>{r.changes.map((c, i) => <li key={i}>{c}</li>)}</ul>
      {r.proposal && moves > 0 && (
        <span className="badge" style={{ alignSelf: "flex-start" }}>
          {r.gained.length} access gained, {r.lost.length} lost
        </span>
      )}
      <button className="btn btn-sm btn-primary" disabled={busy}
              onClick={() => r.proposal ? onApply(r.proposal) : onDiscard("Kept the existing rule. Nothing changed.")}>
        {r.label}
      </button>
    </div>
  );
}
