import { useCallback, useEffect, useRef, useState } from "react";
import gsap from "gsap";
import {
  ArrowUpRight,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  Compass,
  LayoutDashboard,
  LockKeyhole,
  Menu,
  Network,
  Play,
  RefreshCw,
  Settings2,
  Sparkles,
  Square,
  UserRound,
  Workflow,
  X,
} from "lucide-react";
import {
  api,
  dateTime,
  initials,
  label,
  safeUrl,
  setToken,
  type Connections,
  type Job,
  type Overview as OverviewData,
  type Run,
} from "./lib";
import { Badge, Modal, PlatformIcon } from "./components";
import { Overview } from "./Overview";
import { BrandMark } from "./BrandMark";
import { Jobs } from "./Jobs";
import { Platforms } from "./Platforms";
import { Profile } from "./Profile";
import { Automation, RunDialog } from "./Automation";

const navigation = [
  { id: "overview", title: "Overview", icon: LayoutDashboard },
  { id: "applications", title: "Applications", icon: BriefcaseBusiness },
  { id: "opportunities", title: "Opportunities", icon: Compass },
  { id: "platforms", title: "Platforms", icon: Network },
  { id: "automation", title: "Automation", icon: Workflow },
  { id: "profile", title: "My profile", icon: UserRound },
];
export default function App() {
  const [view, setView] = useState(
      navigation.some((n) => n.id === location.hash.slice(1))
        ? location.hash.slice(1)
        : "overview",
    ),
    [menu, setMenu] = useState(false),
    [bootstrap, setBootstrap] = useState<{
      user: { name: string; location: string };
      timezone: string;
    }>(),
    [data, setData] = useState<OverviewData>(),
    [connections, setConnections] = useState<Connections>(),
    [runs, setRuns] = useState<Run[]>([]),
    [days, setDays] = useState(14),
    [revision, setRevision] = useState(0),
    [runModal, setRunModal] = useState(""),
    [job, setJob] = useState<Job>(),
    [toast, setToast] = useState<{ message: string; error: boolean }>(),
    [loadError, setLoadError] = useState(""),
    [jobBusy, setJobBusy] = useState(false),
    [confirmApplied, setConfirmApplied] = useState(false);
  const main = useRef<HTMLDivElement>(null);
  const notify = useCallback(
    (message: string, error = false) => setToast({ message, error }),
    [],
  );
  const navigate = useCallback((page: string) => {
    location.hash = page;
    setView(page);
    setMenu(false);
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);
  const refresh = useCallback(async () => {
    try {
      const [o, c, r] = await Promise.all([
        api<OverviewData>(`overview?days=${days}`),
        api<Connections>("connections"),
        api<{ runs: Run[] }>("runs"),
      ]);
      setData(o);
      setConnections(c);
      setRuns(r.runs);
      setLoadError("");
    } catch (e) {
      setLoadError((e as Error).message);
    }
  }, [days]);
  useEffect(() => {
    api<{
      token: string;
      user: { name: string; location: string };
      timezone: string;
    }>("bootstrap")
      .then((r) => {
        setToken(r.token);
        setBootstrap(r);
      })
      .catch((e) => setLoadError(e.message));
  }, []);
  useEffect(() => {
    if (bootstrap) void refresh();
  }, [bootstrap, refresh, revision]);
  useEffect(() => {
    if (!bootstrap) return;
    const id = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 2000);
    const focus = () => {
      void refresh();
    };
    window.addEventListener("focus", focus);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", focus);
    };
  }, [bootstrap, refresh]);
  useEffect(() => {
    const listener = () => {
      const next = location.hash.slice(1);
      setView(navigation.some((n) => n.id === next) ? next : "overview");
    };
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(undefined), 6000);
    return () => clearTimeout(id);
  }, [toast]);
  useEffect(() => {
    if (!main.current || !data) return;
    const context = gsap.context(() => {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      gsap.fromTo(
        ".page-enter",
        { opacity: 0, y: 14 },
        { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" },
      );
      gsap.fromTo(
        ".metric",
        { opacity: 0, y: 12 },
        { opacity: 1, y: 0, duration: 0.45, stagger: 0.07, delay: 0.12 },
      );
      gsap.to(".orbit-art", {
        rotation: 4,
        yoyo: true,
        repeat: -1,
        duration: 7,
        ease: "sine.inOut",
      });
    }, main);
    return () => context.revert();
  }, [view, Boolean(data)]);
  const active = runs.find((r) => ["queued", "running"].includes(r.state));
  async function run(action: string, platform: string) {
    try {
      await api("runs", { action, platform });
      setRevision((v) => v + 1);
      notify(
        action === "login"
          ? "Opening your sign-in browser. Complete sign-in, then choose Verify sign-in."
          : "Connection check started.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  async function openJob(id: number) {
    try {
      setJob(await api<Job>(`jobs/${id}`));
      setConfirmApplied(false);
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  async function status(value: string) {
    if (!job) return;
    setJobBusy(true);
    try {
      await api(
        `jobs/${job.id}/${value === "recover" ? "recover" : "status"}`,
        { status: value },
      );
      setJob(undefined);
      setRevision((v) => v + 1);
      notify(
        value === "recover"
          ? "Interrupted application moved to review. Verify its outcome on the platform."
          : `Job marked ${value}.`,
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setJobBusy(false);
    }
  }
  async function stop() {
    try {
      const r = await api<{ cancelled: boolean }>("runs/cancel", {});
      notify(
        r.cancelled
          ? "Stop requested. The worker tab will close; your sign-in tabs stay open."
          : "The worker is starting or already finished. Try again in a moment.",
      );
      void refresh();
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  async function verify() {
    try {
      await api("runs/verify-login", {});
      notify("Checking the session in your sign-in browser.");
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  const ready = bootstrap && data && connections;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {menu && (
        <button
          aria-label="Close navigation"
          className="sidebar-backdrop"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <a
          className="brand"
          href="#overview"
          onClick={() => navigate("overview")}
        >
          <span className="brand-mark">
            <BrandMark size={26} />
          </span>
          JobPraapti<span className="brand-period">.</span>
        </a>
        <div className="workspace-label">
          <span className="workspace-icon">
            <BriefcaseBusiness size={16} />
          </span>
          <div>
            Personal workspace<small>YOUR NEXT CHAPTER</small>
          </div>
          <LockKeyhole size={13} />
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ id, title, icon: Icon }, i) => (
            <button
              className={`${view === id ? "active" : ""} ${i === 4 ? "nav-separated" : ""}`}
              aria-current={view === id ? "page" : undefined}
              onClick={() => navigate(id)}
              key={id}
            >
              <Icon size={18} />
              <span>{title}</span>
              {id === "applications" && data && (
                <small>{data.total_applications}</small>
              )}
              {view === id && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-card">
            <span className="sidebar-card-icon">
              <Sparkles size={21} />
            </span>
            <strong>Ready for what’s next?</strong>
            <p>
              Your next opportunity starts
              <br />
              with one small move.
            </p>
            <button
              onClick={() => setRunModal("pipeline")}
              disabled={Boolean(active)}
            >
              Start a run <ArrowUpRight size={16} />
            </button>
          </div>
          <div className="local-status">
            <span className="live-dot" /> Running locally{" "}
            <LockKeyhole size={12} />
          </div>
          <button className="user-card" onClick={() => navigate("profile")}>
            <span className="avatar">
              {initials(bootstrap?.user.name || "Your workspace")}
            </span>
            <span>
              <strong>{bootstrap?.user.name || "Your workspace"}</strong>
              <small>Personal account</small>
            </span>
            <Settings2 size={16} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMenu(true)}
            >
              <Menu size={22} />
            </button>
            <span className="breadcrumb">
              Workspace <ChevronRight size={13} />
              <strong>
                {navigation.find((n) => n.id === view)?.title || "Overview"}
              </strong>
            </span>
          </div>
          <div>
            <span className="today-date">
              {new Date().toLocaleDateString("en-IN", {
                weekday: "short",
                day: "numeric",
                month: "short",
                timeZone: bootstrap?.timezone || "Asia/Kolkata",
              })}
            </span>
            <span className="private-pill">
              <LockKeyhole size={12} /> Private workspace
            </span>
            <button
              className="icon-button"
              aria-label="Refresh workspace"
              onClick={() => {
                setRevision((v) => v + 1);
                notify("Workspace refreshed.");
              }}
            >
              <RefreshCw size={17} />
            </button>
          </div>
        </header>
        <main id="main-content" ref={main}>
          {loadError && (
            <div role="alert" className="error-inline">
              {loadError}{" "}
              <button className="text-button" onClick={() => location.reload()}>
                Reload workspace
              </button>
            </div>
          )}
          {active && (
            <div className="active-run">
              <span className="spinner" />
              <div>
                <strong>
                  {active.action === "login"
                    ? `Sign in to ${label(active.platform)}`
                    : `${label(active.action)} in progress`}
                </strong>
                <p>{active.message}</p>
              </div>
              {active.action === "login" && (
                <button className="primary" onClick={verify}>
                  <Check size={15} /> Verify sign-in
                </button>
              )}
              <button className="secondary" onClick={stop}>
                <Square size={13} /> Stop
              </button>
              {view !== "automation" && (
                <button
                  className="text-button"
                  onClick={() => navigate("automation")}
                >
                  View live progress <ArrowUpRight size={15} />
                </button>
              )}
            </div>
          )}
          {!ready ? (
            <div className="app-loading">
              <span className="brand-mark">
                <BrandMark />
              </span>
              <h2>Opening your workspace…</h2>
              <p>Your next chapter is loading.</p>
            </div>
          ) : (
            <>
              {view === "overview" && (
                <Overview
                  data={data}
                  connections={connections.platforms}
                  name={bootstrap.user.name}
                  days={days}
                  setDays={setDays}
                  navigate={navigate}
                  start={() => setRunModal("pipeline")}
                  openJob={openJob}
                />
              )}
              {["applications", "opportunities"].includes(view) && (
                <Jobs
                  key={view}
                  applied={view === "applications"}
                  connections={connections.platforms}
                  timezone={bootstrap.timezone}
                  openJob={openJob}
                  revision={revision}
                  discover={() => setRunModal("scrape")}
                />
              )}
              {view === "platforms" && (
                <Platforms
                  data={connections}
                  busy={Boolean(active)}
                  run={run}
                  refresh={() => setRevision((v) => v + 1)}
                  notify={notify}
                />
              )}
              {view === "profile" && <Profile notify={notify} />}{" "}
              {view === "automation" && (
                <Automation
                  runs={runs}
                  busy={Boolean(active)}
                  start={() => setRunModal("pipeline")}
                  timezone={bootstrap.timezone}
                />
              )}
            </>
          )}
          <footer className="maker-footer">
            <span className="maker-mark" aria-hidden="true">
              <Sparkles size={18} />
            </span>
            <p>
              Made by <strong>Daksh</strong> for the ones who seek opportunity.
            </p>
            <span className="maker-signature">keep reaching ↗</span>
          </footer>
        </main>
      </div>
      {toast && (
        <div
          className={`toast ${toast.error ? "error" : ""}`}
          role={toast.error ? "alert" : "status"}
        >
          {toast.error ? <X size={19} /> : <Check size={19} />}
          <span>{toast.message}</span>
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast(undefined)}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {runModal && connections && (
        <RunDialog
          initial={runModal}
          connections={connections.platforms}
          close={() => setRunModal("")}
          started={() => {
            setRevision((v) => v + 1);
            navigate("automation");
          }}
          notify={notify}
        />
      )}
      {job && (
        <Modal
          title="A closer look"
          wide
          close={() => !jobBusy && setJob(undefined)}
        >
          <div className="job-detail-heading">
            <PlatformIcon name={job.platform} />
            <div>
              <h2>{job.title}</h2>
              <p>
                {job.company} · {job.location || label(job.platform)}
              </p>
            </div>
            <Badge value={job.status} />
          </div>
          <div className="detail-meta">
            <span>
              Match score{" "}
              <strong>
                {job.match_score
                  ? `${Math.round(job.match_score)}%`
                  : "Not scored"}
              </strong>
            </span>
            <a
              className="secondary"
              href={safeUrl(job.url)}
              target="_blank"
              rel="noreferrer"
            >
              Open job <ArrowUpRight size={16} />
            </a>
          </div>
          {job.applied_at && (
            <p className="caption">
              Applied {dateTime(job.applied_at, bootstrap?.timezone)}
            </p>
          )}
          {job.match_reason && (
            <div className="info-banner">{job.match_reason}</div>
          )}
          <h3>About the role</h3>
          <div className="job-description">
            {job.description ||
              "Open the original listing for the full job description."}
          </div>
          {Boolean(job.application_history?.length) && (
            <>
              <h3>Application timeline</h3>
              <ol className="timeline">
                {job.application_history?.map((event, i) => (
                  <li key={i}>
                    <strong>{label(event.action)}</strong>
                    <small>
                      {dateTime(event.timestamp, bootstrap?.timezone)}
                    </small>
                    <p>{event.details}</p>
                  </li>
                ))}
              </ol>
            </>
          )}
          <div className="detail-actions">
            <button
              className="secondary"
              disabled={jobBusy || ["applied", "applying"].includes(job.status)}
              onClick={() => status("shortlisted")}
            >
              Shortlist
            </button>
            <button
              className="secondary"
              disabled={jobBusy || ["applied", "applying"].includes(job.status)}
              onClick={() => status("review")}
            >
              Needs review
            </button>
            <button
              className="text-button"
              disabled={jobBusy || ["applied", "applying"].includes(job.status)}
              onClick={() => status("rejected")}
            >
              Reject
            </button>
            {job.status !== "applied" && job.status !== "applying" && (
              <button
                className="primary"
                disabled={jobBusy}
                onClick={() => setConfirmApplied(true)}
              >
                Mark as applied
              </button>
            )}
          </div>
          {job.status === "applying" && (
            <div className="confirm-box">
              <p>
                After the worker has stopped, recover this job to review. Check
                the platform for an existing application before retrying.
              </p>
              <button
                className="secondary"
                disabled={jobBusy || Boolean(active)}
                onClick={() => status("recover")}
              >
                Recover interrupted job
              </button>
            </div>
          )}
          {confirmApplied && (
            <div className="confirm-box">
              <p>
                Only confirm if this application was submitted successfully on{" "}
                {label(job.platform)}. This records the current time as your
                manual confirmation.
              </p>
              <button
                className="primary"
                disabled={jobBusy}
                onClick={() => status("applied")}
              >
                Confirm application submitted
              </button>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
