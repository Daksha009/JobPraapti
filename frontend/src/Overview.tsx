import { OpportunityScene } from "./OpportunityScene";
import { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  Compass,
  FileCheck2,
  Layers,
  Play,
  Sparkles,
} from "lucide-react";
import { Badge, Empty, JobTable, Panel, PlatformIcon } from "./components";
import { label, type Overview as OverviewData, type Connection } from "./lib";

export function Overview({
  data,
  connections,
  name,
  days,
  setDays,
  navigate,
  start,
  openJob,
}: {
  data: OverviewData;
  connections: Connection[];
  name: string;
  days: number;
  setDays: (days: number) => void;
  navigate: (page: string) => void;
  start: () => void;
  openJob: (id: number) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(4, ...data.chart.map((d) => d.count));
  const metrics = [
    {
      title: "Applications sent",
      value: data.total_applications,
      detail: `${data.applied_today} sent today`,
      icon: FileCheck2,
      style: "orange",
    },
    {
      title: "Jobs discovered",
      value: data.total_jobs,
      detail: "Across your platforms",
      icon: Compass,
      style: "blue",
    },
    {
      title: "Shortlisted",
      value: data.shortlisted,
      detail: "Saved for your next step",
      icon: Layers,
      style: "purple",
    },
    {
      title: "Needs your review",
      value: data.needs_review,
      detail: "A little human touch",
      icon: CheckCheck,
      style: "green",
    },
  ];
  return (
    <div className="overview page-enter">
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">
            <span className="live-dot" /> YOUR NEXT CHAPTER STARTS HERE
          </span>
          <h1>
            A little more focus.
            <br />A lot more possibility<span>.</span>
          </h1>
          <p>
            Good to see you, {name.split(" ")[0] || "there"}. Bring your job
            search
            <br className="desktop-break" /> together, and make your next move
            count.
          </p>
          <button className="primary" onClick={start}>
            <Play size={15} fill="currentColor" /> Start a run{" "}
            <ArrowUpRight size={17} />
          </button>
          <span className="hero-footnote">
            You choose when applications go live.
          </span>
        </div>
        <OpportunityScene />
      </section>
      <div className="metric-grid">
        {metrics.map(({ title, value, detail, icon: Icon, style }) => (
          <button
            className="metric"
            key={title}
            onClick={() =>
              navigate(
                title === "Applications sent"
                  ? "applications"
                  : "opportunities",
              )
            }
          >
            <div className="metric-top">
              <span>{title}</span>
              <span className={`metric-icon ${style}`}>
                <Icon size={19} />
              </span>
            </div>
            <strong>{value.toLocaleString()}</strong>
            <div className="metric-bottom">
              <small>{detail}</small>
              <ArrowUpRight size={16} />
            </div>
          </button>
        ))}
      </div>
      <div className="overview-grid">
        <Panel
          title="Making moves"
          eyebrow="APPLICATION ACTIVITY"
          action={
            <select
              aria-label="Chart period"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              {[7, 14, 30, 90].map((d) => (
                <option key={d} value={d}>
                  Last {d} days
                </option>
              ))}
            </select>
          }
        >
          <div className="chart-summary">
            <strong>{data.period_applications}</strong>
            <span>applications in this period</span>
            <span className="legend">
              <i /> Applications sent
            </span>
          </div>
          <div
            className="chart"
            role="img"
            aria-label={`${data.period_applications} applications in the last ${days} days`}
          >
            <div className="chart-grid">
              {[
                max,
                Math.round(max * 0.75),
                Math.round(max * 0.5),
                Math.round(max * 0.25),
                0,
              ].map((n, i) => (
                <div key={i}>
                  <span>{n}</span>
                </div>
              ))}
            </div>
            <div className="chart-bars">
              {data.chart.map((point, i) => (
                <div
                  className={`chart-column ${hover === i ? "hover" : ""}`}
                  key={point.date}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  <button
                    aria-label={`${point.date}: ${point.count} applications`}
                    onFocus={() => setHover(i)}
                    onBlur={() => setHover(null)}
                    style={{
                      height: `${Math.max(1, (point.count / max) * 100)}%`,
                    }}
                    className={point.count ? "" : "zero"}
                  />
                  {hover === i && (
                    <div className="chart-tooltip">
                      {new Date(`${point.date}T12:00:00`).toLocaleDateString(
                        "en-IN",
                        { day: "numeric", month: "short" },
                      )}
                      <strong>{point.count} applications</strong>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
          <div className="chart-dates">
            {[
              data.chart[0],
              data.chart[Math.floor(days / 2)],
              data.chart.at(-1),
            ].map((p) => (
              <span key={p?.date}>
                {p &&
                  new Date(p.date + "T12:00:00").toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                  })}
              </span>
            ))}
          </div>
          {data.undated_applications > 0 && (
            <p className="caption">
              {data.undated_applications} older applications have no recorded
              date and are excluded from the chart.
            </p>
          )}
        </Panel>
        <Panel
          title="Your platforms"
          eyebrow="ONE CONNECTED WORKSPACE"
          action={
            <button
              className="icon-button"
              aria-label="Manage platforms"
              onClick={() => navigate("platforms")}
            >
              <ArrowUpRight size={20} />
            </button>
          }
        >
          <div className="platform-list">
            {connections
              .filter((c) => c.enabled)
              .map((c) => (
                <button
                  key={c.name}
                  className="platform-row"
                  onClick={() => navigate("platforms")}
                >
                  <PlatformIcon name={c.name} />
                  <span>
                    <strong>{label(c.name)}</strong>
                    <small>{data.by_platform[c.name] || 0} applications</small>
                  </span>
                  <span
                    className={`connection-dot ${c.status === "connected" ? "connected" : ""}`}
                  />
                  <small>
                    {c.status === "connected" ? "Connected" : "Sign in"}
                  </small>
                </button>
              ))}
          </div>
          <button
            className="text-button platform-manage"
            onClick={() => navigate("platforms")}
          >
            Manage connections <ArrowRight size={15} />
          </button>
        </Panel>
      </div>
      <Panel
        title="Your latest applications"
        action={
          <button
            className="text-button"
            onClick={() => navigate("applications")}
          >
            View all applications <ArrowRight size={15} />
          </button>
        }
      >
        {data.recent.length ? (
          <JobTable
            jobs={data.recent}
            applied
            open={openJob}
            timezone={data.timezone}
          />
        ) : (
          <Empty
            title="Your next opportunity is out there"
            action={
              <button
                className="secondary"
                onClick={() => navigate("platforms")}
              >
                Connect your platforms <ArrowRight size={15} />
              </button>
            }
          >
            Sign in to your platforms, discover roles, and track every confirmed
            application here.
          </Empty>
        )}
      </Panel>
      <div className="bottom-note">
        <Badge value="private" />
        <span>Your workspace stays on this computer.</span>
        <span>
          Built for your next big thing <Sparkles size={13} />
        </span>
      </div>
    </div>
  );
}
