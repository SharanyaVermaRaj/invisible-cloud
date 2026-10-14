import { FormEvent, useMemo, useRef, useState } from "react";
import { api, ApiError, DocumentItem, money } from "../api";
import { Avatar, Icon, useToast } from "../ui";
import { useApp } from "./context";

const KIND_TAG: Record<string, string> = {
  tax_return: "TAX", w2: "W-2", payroll_report: "PAY", financial_statement: "FIN",
  invoice: "INV", engagement_letter: "ENG", other: "DOC",
};

export function DocumentsView() {
  const { state, refresh, name } = useApp();
  const toast = useToast();
  const [uploading, setUploading] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const { me } = state;

  const groups = useMemo(() => {
    const byClient = new Map<string, DocumentItem[]>();
    for (const d of state.documents) {
      const k = d.client ?? "unfiled";
      byClient.set(k, [...(byClient.get(k) ?? []), d]);
    }
    return [...byClient.entries()].sort((a, b) => name(a[0]).localeCompare(name(b[0])));
  }, [state.documents, name]);

  const uploadTargets = state.client_services.filter(cs => me.is_admin || cs.assignees.includes(me.key));

  const send = async (d: DocumentItem) => {
    setBusyKey(d.key);
    try {
      const r = await api.send(d.key);
      await refresh();
      toast({ text: r.status === "pending"
        ? `Sent for approval. A ${name(d.approval?.approver_role).toLowerCase()} needs to sign off first.`
        : `${d.name} sent to ${name(d.client)}.` });
    } catch (e) {
      toast({ text: e instanceof ApiError ? e.message : "Couldn't send it.", error: true });
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div>
      <div className="page-head">
        <h2>{me.is_admin ? "All documents" : "Your documents"}</h2>
        <p>
          {me.is_admin
            ? "Every file is stored here and protected by the firm's rules. Nobody configures folder permissions."
            : "These are the documents the firm's rules let you open right now."}
        </p>
      </div>

      <div className="toolbar">
        <span className="lockline">
          {state.documents.length} document{state.documents.length === 1 ? "" : "s"}
          {state.hidden_documents > 0 && <> visible to you. <Icon name="lock" />{state.hidden_documents} hidden by the firm's rules.</>}
        </span>
        {uploadTargets.length > 0 && (
          <button className="btn btn-primary" onClick={() => setUploading(true)}><Icon name="upload" className="" />Upload document</button>
        )}
      </div>

      {groups.length === 0 && (
        <div className="empty">
          <h3>No documents for you yet</h3>
          <p>When a partner assigns you to a client, their documents show up here automatically.</p>
        </div>
      )}

      {groups.map(([client, docs]) => (
        <section className="client-group" key={client}>
          <h3>{name(client)}<small>{docs.length} document{docs.length === 1 ? "" : "s"}</small></h3>
          <div className="doc-list">
            {docs.map(d => (
              <DocRow key={d.key} d={d} busy={busyKey === d.key} onSend={() => send(d)} />
            ))}
          </div>
        </section>
      ))}

      {uploading && <UploadDrawer targets={uploadTargets} onClose={() => setUploading(false)} />}
    </div>
  );
}

function DocRow({ d, busy, onSend }: { d: DocumentItem; busy: boolean; onSend: () => void }) {
  const { state, name } = useApp();
  const canRead = d.my_access.read.allowed;
  const canSend = d.my_access.send.allowed;
  const readers = d.access?.read ?? [];
  const delivery = d.delivery;
  return (
    <div className={`doc${canRead ? "" : " locked"}`}>
      <div className="icon" aria-hidden="true">{KIND_TAG[d.kind] ?? "DOC"}</div>
      <div className="title">
        <b>{d.name}</b>
        <span>
          {d.kind_label.charAt(0).toUpperCase() + d.kind_label.slice(1)}
          {d.amount != null && <>, <span className="num">{money(d.amount)}</span></>}
        </span>
      </div>
      <div className="meta">
        {name(d.client_service)}
        {state.me.is_admin && readers.length > 0 && (
          <div className="avatars who-col" style={{ marginTop: 6 }} aria-label={`Can open: ${readers.map(name).join(", ")}`}>
            {readers.map(p => <Avatar key={p} person={p} name={name(p)} small />)}
          </div>
        )}
      </div>
      <div className="status">
        {delivery?.status === "pending" && <span className="badge hold">Awaiting approval</span>}
        {delivery?.status === "sent" && <span className="badge gain">Sent to client</span>}
        {delivery?.status === "rejected" && <span className="badge loss">Approval declined</span>}
      </div>
      <div className="actions">
        {canRead && d.has_file && (
          <a className="btn btn-sm" href={api.fileUrl(d.key)} target="_blank" rel="noreferrer">
            <Icon name="open" className="" />Open
          </a>
        )}
        {canSend && delivery?.status !== "pending" && (
          <button className="btn btn-sm" onClick={onSend} disabled={busy} title={d.approval?.reason}>
            <Icon name="send" className="" />{d.approval ? "Send for approval" : delivery?.status === "sent" ? "Send again" : "Send to client"}
          </button>
        )}
      </div>
    </div>
  );
}

function UploadDrawer({ targets, onClose }: { targets: { key: string; name: string }[]; onClose: () => void }) {
  const { state, refresh } = useApp();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [cs, setCs] = useState(targets[0]?.key ?? "");
  const [kind, setKind] = useState("other");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) { setError("Choose a file to upload."); return; }
    if (amount && Number.isNaN(Number(amount.replace(/[$,]/g, "")))) { setError("Amount must be a number, like 7200."); return; }
    setBusy(true); setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("title", title || file.name.replace(/\.[^.]+$/, ""));
    form.append("client_service", cs);
    form.append("kind", kind);
    form.append("amount", amount);
    try {
      await api.upload(form);
      await refresh();
      toast({ text: "Uploaded. The firm's rules already decide who can open it." });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="drawer-back" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="drawer" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="upload-title">
        <h2 id="upload-title">Upload a document</h2>
        <p style={{ margin: 0, color: "var(--ink-2)" }}>
          You don't set permissions. Choose where it belongs and the firm's rules take care of the rest.
        </p>
        <div className={`dropzone${file ? " has-file" : ""}`} onClick={() => fileRef.current?.click()}
             onDragOver={e => e.preventDefault()}
             onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
             role="button" tabIndex={0} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") fileRef.current?.click(); }}>
          {file ? <>{file.name}<br /><small>Click to choose a different file</small></> : <>Drop a file here, or click to choose<br /><small>PDF, image, text, CSV, Word or Excel, up to 5 MB</small></>}
          <input ref={fileRef} type="file" hidden accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,.docx,.xlsx"
                 onChange={e => setFile(e.target.files?.[0] ?? null)} />
        </div>
        <div className="field">
          <label htmlFor="up-title">Title</label>
          <input id="up-title" value={title} onChange={e => setTitle(e.target.value)} placeholder={file?.name ?? "Acme Q4 payroll report"} maxLength={200} />
        </div>
        <div className="field">
          <label htmlFor="up-cs">Belongs to</label>
          <select id="up-cs" value={cs} onChange={e => setCs(e.target.value)}>
            {targets.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}
          </select>
          <small>People assigned to this client service will be able to open it.</small>
        </div>
        <div className="field">
          <label htmlFor="up-kind">Kind of document</label>
          <select id="up-kind" value={kind} onChange={e => setKind(e.target.value)}>
            {state.kinds.map(k => <option key={k.key} value={k.key}>{k.label.charAt(0).toUpperCase() + k.label.slice(1)}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="up-amount">Amount (optional)</label>
          <input id="up-amount" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} placeholder="7200" />
          <small>Used by approval rules, like "tax returns over $5,000 need partner approval".</small>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div style={{ display: "flex", gap: 10, marginTop: "auto" }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Uploading…" : "Upload document"}</button>
        </div>
      </form>
    </div>
  );
}
