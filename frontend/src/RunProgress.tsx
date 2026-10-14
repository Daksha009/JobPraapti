import { useEffect, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  Check,
  CircleDashed,
  Compass,
  Send,
  Sparkles,
} from "lucide-react";
import { Badge, PlatformIcon } from "./components";
import { dateTime, label, type Run } from "./lib";
import { applicationOutcomes, duration, progressUnits, runMetrics, stageProgress } from "./progress";

export function RunProgress({ run, timezone }: { run: Run; timezone: string }) {
  const [now, setNow] = useState(Date.now());
  const [filter, setFilter] = useState("all");
  const live = ["queued", "running"].includes(run.state);
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [live]);
  useEffect(() => setFilter("all"), [run.id]);
  const events = run.events || [];
  const units = run.progress || progressUnits(events);
  const metrics = runMetrics(run);
  const outcomes = applicationOutcomes(run);
  const stages =
    run.action === "pipeline"
      ? ["discover", "match", "apply"]
      : [
          (
            {
              scrape: "discover",
              check: "connect",
              login: "connect",
            } as Record<string, string>
          )[run.action] || run.action,
        ];
  const platforms = [
    ...new Set(
      units.map((e) => e.platform).filter((p): p is string => Boolean(p)),
    ),
  ];
  const recent = events.at(-1);
  const icons = {
    discover: Compass,
    match: Sparkles,
    apply: Send,
    connect: Activity,
  };
  return (
    <section
      className={`mission-control ${live ? "is-live" : ""}`}
      aria-label="Run progress"
    >
      <div className="mission-heading">
        <div>
          <span className="eyebrow">
            <span className={live ? "live-dot" : "tiny-dot"} /> YOUR SEARCH, IN
            MOTION
          </span>
          <h2>{live ? "Every move. In view." : "Your run, at a glance."}</h2>
          <p>
            {label(run.platform)} · {dateTime(run.started_at, timezone)}
          </p>
        </div>
        <div className="mission-state">
          <Badge value={run.state} />
          <span className="mode-label">
            {["apply", "pipeline"].includes(run.action)
              ? run.options.dry_run
                ? "DRY RUN · NO SUBMISSIONS"
                : "LIVE APPLICATIONS"
              : label(run.action)}
          </span>
          <strong>{duration(run.started_at, run.finished_at || now)}</strong>
          <small>{live ? "elapsed" : "duration"}</small>
        </div>
      </div>
      <div className="progress-stages">
        {stages.map((stage, index) => {
          const entries = units.filter((e) => e.stage === stage);
          const global = entries.find((e) => !e.platform);
          const nextStarted = units.some(
            (e) => stages.indexOf(e.stage) > index,
          );
          const attention = entries.some((e) =>
            ["attention", "failed"].includes(e.state),
          );
          const done =
            global?.state === "completed" ||
            nextStarted ||
            (entries.length > 0 && entries.every((e) => e.state !== "running"));
          const running = live && entries.length > 0 && !done;
          const state = attention
            ? "attention"
            : done
              ? "completed"
              : running
                ? "running"
                : entries.length
                  ? "stopped"
                  : live
                    ? "waiting"
                    : "not run";
          const count = stageProgress(units, stage);
          const Icon = icons[stage as keyof typeof icons] || Activity;
          return (
            <div className={`progress-stage ${state}`} key={stage}>
              <span className="stage-icon">
                {done && !attention ? <Check size={23} /> : <Icon size={23} />}
              </span>
              <small>0{index + 1}</small>
              <h3>{label(stage)}</h3>
              <span className="stage-status">{label(state)}</span>
              {count?.total != null && (
                <>
                  <progress
                    value={count.current || 0}
                    max={Math.max(1, count.total)}
                    aria-label={`${label(stage)} items processed`}
                  />
                  <span className="caption">
                    {count.total === 0 ? "No eligible candidates" : `${count.current} / ${count.total} processed across platforms`}
                  </span>
                </>
              )}
            </div>
          );
        })}
      </div>
      <div className="run-counters">
        {[
          ["jobs_found", "Discovered"],
          ["jobs_new", "New roles"],
          ["jobs_duplicate", "Duplicates"],
          ["scored", "Scored"],
          [
            run.options.dry_run ? "dry_run" : "applied",
            run.options.dry_run ? "Dry-run checks" : "Confirmed",
          ],
          ["review", "For review"],
        ].map(([key, title]) => (
          <div key={key}>
            <strong>{metrics[key] ?? 0}</strong>
            <span>{title}</span>
          </div>
        ))}
      </div>
      <div className="run-current" role="status">
        {live ? <Activity size={19} /> : <CircleDashed size={19} />}
        <div>
          <span>
            {live
              ? recent?.platform
                ? label(recent.platform)
                : "LOCAL WORKER"
              : "RUN OUTCOME"}
          </span>
          <p>{run.message || "Waiting for the local worker"}</p>
        </div>
      </div>
      {outcomes.length > 0 && (
        <section className="application-outcomes" aria-label="Application outcomes">
          <h3>What happened at Apply</h3>
          <p>Results from this run. A completed match does not mean every job met your application filters.</p>
          <div>
            {outcomes.map((outcome) => (
              <article key={outcome.platform}>
                <div><PlatformIcon name={outcome.platform} /><strong>{label(outcome.platform)}</strong><Badge value={outcome.state} /></div>
                <p>{outcome.message}</p>
                {outcome.eligibility && (
                  <small>{outcome.eligibility.considered} scored/shortlisted · {outcome.eligibility.below_score} below {outcome.eligibility.min_score} points · {outcome.eligibility.eligible} eligible · {outcome.eligibility.selected} selected</small>
                )}
                {outcome.needsLogin && <a href="#platforms">Verify platform sign-in →</a>}
              </article>
            ))}
          </div>
        </section>
      )}
      {platforms.length > 0 && (
        <div className="run-platforms">
          {platforms.map((platform) => {
            const latest = units.filter((e) => e.platform === platform).at(-1)!;
            return (
              <div key={platform}>
                <PlatformIcon name={platform} />
                <span>
                  <strong>{label(platform)}</strong>
                  <small>
                    {label(latest.stage)} ·{" "}
                    {label(
                      !live && latest.state === "running"
                        ? "stopped"
                        : latest.state,
                    )}
                  </small>
                </span>
              </div>
            );
          })}
        </div>
      )}
      <div className="event-heading">
        <div>
          <h3>Activity stream</h3>
          <p>
            {events.length < (run.event_count || 0)
              ? `Latest ${events.length} of ${run.event_count} events`
              : `${events.length} recorded events`}{" "}
            · newest first
          </p>
        </div>
        <div>
          <select
            aria-label="Filter run events by platform"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All platforms</option>
            {platforms.map((p) => (
              <option value={p} key={p}>
                {label(p)}
              </option>
            ))}
          </select>
          <a
            className="icon-button"
            href={`/api/runs/${run.id}/events`}
            download
            aria-label="Download complete run timeline"
          >
            <ArrowDownToLine size={18} />
          </a>
        </div>
      </div>
      <ol className="event-stream">
        {events
          .filter((e) => filter === "all" || e.platform === filter)
          .slice()
          .reverse()
          .map((e) => (
            <li key={e.id} className={e.state}>
              <time dateTime={e.timestamp}>
                {new Date(e.timestamp).toLocaleTimeString("en-IN", {
                  timeZone: timezone,
                  hour12: false,
                })}
              </time>
              <span className="event-dot" />
              <div>
                <strong>
                  {label(e.stage)}
                  {e.platform ? ` / ${label(e.platform)}` : ""}
                </strong>
                <p>{e.message}</p>
                {e.metrics && Object.keys(e.metrics).length > 0 && (
                  <small>
                    {Object.entries(e.metrics)
                      .map(([k, v]) => `${label(k)}: ${v}`)
                      .join(" · ")}
                  </small>
                )}
              </div>
            </li>
          ))}
      </ol>
      {!events.length && (
        <p className="no-events">
          {live
            ? "The worker is starting. Live updates appear here every two seconds."
            : "This run predates detailed activity tracking. Its saved result is available below."}
        </p>
      )}
    </section>
  );
}
