import { useState, type FormEvent } from "react";
import {
  ArrowUpRight,
  Clock3,
  FlaskConical,
  Play,
  Workflow,
} from "lucide-react";
import { api, dateTime, label, type Connection, type Run } from "./lib";
import { Badge, Empty, Modal, Panel } from "./components";
import { RunProgress } from "./RunProgress";

export function RunDialog({
  connections,
  close,
  started,
  notify,
  initial = "pipeline",
}: {
  connections: Connection[];
  close: () => void;
  started: () => void;
  notify: (message: string, error?: boolean) => void;
  initial?: string;
}) {
  const [action, setAction] = useState(initial),
    [platform, setPlatform] = useState("all"),
    [dry, setDry] = useState(true),
    [limit, setLimit] = useState(5),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false);
  const submits = ["pipeline", "apply"].includes(action);
  async function start(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("runs", {
        action,
        platform,
        dry_run: dry,
        limit,
        confirm_live: confirmed,
      });
      started();
      close();
      notify(
        dry
          ? "Dry run started. No applications will be submitted."
          : "Run started.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Make your next move" close={() => !busy && close()}>
      <form onSubmit={start}>
        <p className="modal-description">
          Choose what to run. Your worker handles one operation at a time.
        </p>
        <div className="form-grid">
          <label>
            Operation
            <select
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                setConfirmed(false);
              }}
            >
              <option value="pipeline">Discover → match → apply</option>
              <option value="scrape">Discover jobs</option>
              <option value="match">Score all unscored jobs</option>
              <option value="apply">Apply to eligible matches</option>
              <option value="check">Check connections</option>
            </select>
          </label>
          <label>
            Platform
            <select
              value={platform}
              disabled={action === "match"}
              onChange={(e) => setPlatform(e.target.value)}
            >
              <option value="all">All enabled platforms</option>
              {connections
                .filter((c) => c.enabled)
                .map((c) => (
                  <option key={c.name} value={c.name}>
                    {label(c.name)}
                  </option>
                ))}
            </select>
          </label>
        </div>
        {submits && (
          <>
            <label>
              Maximum attempts per platform
              <input
                type="number"
                min={1}
                max={100}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
              />
            </label>
            <div className="mode-options">
              <button
                type="button"
                className={dry ? "selected" : ""}
                onClick={() => {
                  setDry(true);
                  setConfirmed(false);
                }}
              >
                <FlaskConical size={22} />
                <strong>Dry run</strong>
                <span>Preview candidates. No submission.</span>
              </button>
              <button
                type="button"
                className={!dry ? "selected live" : ""}
                onClick={() => setDry(false)}
              >
                <Play size={22} />
                <strong>Live applications</strong>
                <span>Submit eligible, complete forms.</span>
              </button>
            </div>
            {!dry && (
              <label className="check-label live-confirm">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                  required
                />{" "}
                I have reviewed my profile and answers. Submit applications to
                eligible jobs within this limit.
              </label>
            )}
            <p className="caption">
              Unknown questions and uncertain submissions stop for review. Daily
              limits and duplicate checks still apply.
            </p>
          </>
        )}
        <button
          className="primary full"
          disabled={busy || (submits && !dry && !confirmed)}
        >
          <Play size={16} />
          {busy ? "Starting…" : submits && dry ? "Start dry run" : "Start run"}
        </button>
      </form>
    </Modal>
  );
}
export function Automation({
  runs,
  busy,
  start,
  timezone,
}: {
  runs: Run[];
  busy: boolean;
  start: () => void;
  timezone: string;
}) {
  const [selected, setSelected] = useState<string>();
  const current =
    runs.find((r) => ["queued", "running"].includes(r.state)) ||
    runs.find((r) => r.id === selected) ||
    runs[0];
  return (
    <div className="page-enter">
      <div className="page-title">
        <div>
          <span className="eyebrow">A CLEARER PATH FORWARD</span>
          <h1>Give your search momentum.</h1>
          <p>
            Launch a workflow, follow its progress, and keep the full history.
          </p>
        </div>
        <button className="primary" disabled={busy} onClick={start}>
          <Play size={16} /> New run
        </button>
      </div>
      {current && <RunProgress run={current} timezone={timezone} />}
      {!current && (
        <section className="workflow-card">
          {[
            {
              n: "01",
              title: "Discover",
              detail: "Find roles on your connected platforms.",
            },
            {
              n: "02",
              title: "Match",
              detail: "Score opportunities against your profile.",
            },
            {
              n: "03",
              title: "Apply",
              detail: "Fill known answers. Review the rest.",
            },
          ].map((step, i) => (
            <div key={step.n}>
              <span>{step.n}</span>
              <h2>{step.title}</h2>
              <p>{step.detail}</p>
              {i < 2 && <ArrowUpRight size={22} />}
            </div>
          ))}
        </section>
      )}
      <div className="info-banner">
        <Workflow size={22} />
        <div>
          <strong>Steady progress, with you in control</strong>
          <p>
            Dry runs are the default. A job counts as applied only after
            confirmation, or your explicit review decision.
          </p>
        </div>
      </div>
      <Panel
        title="Run history"
        action={<span className="count-label">Latest {runs.length} runs</span>}
      >
        {runs.length ? (
          <div className="run-list">
            {runs.map((run) => (
              <article key={run.id} className="run-item">
                <div className="run-icon">
                  <Clock3 size={21} />
                </div>
                <div className="run-copy">
                  <div>
                    <h3>
                      {run.action === "pipeline"
                        ? "Full workflow"
                        : label(run.action)}
                    </h3>
                    <Badge value={run.state} />
                    {["apply", "pipeline"].includes(run.action) && (
                      <span className="mode-label">
                        {run.options.dry_run ? "Dry run" : "Live"}
                      </span>
                    )}
                  </div>
                  <p>
                    {label(run.platform)} · {dateTime(run.started_at, timezone)}
                  </p>
                  <p>{run.message}</p>
                  <button
                    className="text-button"
                    disabled={busy && run.id !== current?.id}
                    onClick={() => {
                      setSelected(run.id);
                      document
                        .querySelector(".mission-control")
                        ?.scrollIntoView({
                          behavior: window.matchMedia(
                            "(prefers-reduced-motion: reduce)",
                          ).matches
                            ? "instant"
                            : "smooth",
                        });
                    }}
                  >
                    View timeline <ArrowUpRight size={14} />
                  </button>
                  {run.result != null && (
                    <details>
                      <summary>View result</summary>
                      <pre>{JSON.stringify(run.result, null, 2)}</pre>
                    </details>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty title="Ready when you are">
            Your runs, connection checks, and sign-in sessions will appear here.
          </Empty>
        )}
      </Panel>
    </div>
  );
}
