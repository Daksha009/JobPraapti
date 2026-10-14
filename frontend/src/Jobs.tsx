import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Download,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { api, filtersQuery, label, type Connection, type Job } from "./lib";
import { Empty, JobTable, Panel } from "./components";

export function Jobs({
  applied,
  connections,
  timezone,
  openJob,
  revision,
  discover,
}: {
  applied: boolean;
  connections: Connection[];
  timezone: string;
  openJob: (id: number) => void;
  revision: number;
  discover: () => void;
}) {
  const [search, setSearch] = useState(""),
    [platform, setPlatform] = useState(""),
    [status, setStatus] = useState(""),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [page, setPage] = useState(1),
    [rows, setRows] = useState<Job[]>([]),
    [total, setTotal] = useState(0),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const query = filtersQuery({
    search,
    platform,
    from: applied ? from : "",
    to: applied ? to : "",
    status: applied ? "" : status,
    ...(applied
      ? { page: String(page) }
      : { limit: "20", offset: String((page - 1) * 20) }),
  });
  useEffect(() => {
    setPage(1);
  }, [search, platform, status, from, to, applied]);
  useEffect(() => {
    let active = true;
    const id = setTimeout(() => {
      setLoading(true);
      api<{ applications?: Job[]; jobs?: Job[]; total: number }>(
        `${applied ? "applications" : "jobs"}?${query}`,
      )
        .then((r) => {
          if (active) {
            setRows(r.applications || r.jobs || []);
            setTotal(r.total);
            setError("");
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(id);
    };
  }, [query, applied, revision]);
  return (
    <div className="page-enter">
      <div className="page-title">
        <div>
          <span className="eyebrow">
            {applied ? "EVERY MOVE, IN ONE PLACE" : "FIND YOUR FIT"}
          </span>
          <h1>
            {applied
              ? "Small steps. Real progress."
              : "An opportunity worth taking."}
          </h1>
          <p>
            {applied
              ? `Your confirmed applications, with dates and times in ${timezone}.`
              : "Explore matches, review the details, and build your shortlist."}
          </p>
        </div>
        {applied ? (
          <a
            className="secondary"
            href={`/api/applications/export?${query}`}
            download
          >
            <Download size={16} /> Export CSV
          </a>
        ) : (
          <button className="primary" onClick={discover}>
            Discover jobs <ArrowRight size={16} />
          </button>
        )}
      </div>
      <Panel
        title={applied ? "Application history" : "Your opportunities"}
        action={
          <span className="count-label">
            {total || 0} {applied ? "applications" : "roles"}
          </span>
        }
      >
        <div className="filters">
          <label className="search-field">
            <Search size={17} />
            <input
              aria-label="Search roles or companies"
              placeholder="Search roles or companies…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <select
            aria-label="Filter platform"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          >
            <option value="">All platforms</option>
            {connections.map((c) => (
              <option key={c.name} value={c.name}>
                {label(c.name)}
              </option>
            ))}
          </select>
          {applied ? (
            <>
              <label className="date-filter">
                From
                <input
                  aria-label="From date"
                  type="date"
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                />
              </label>
              <label className="date-filter">
                To
                <input
                  aria-label="To date"
                  type="date"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                />
              </label>
            </>
          ) : (
            <select
              value={status}
              aria-label="Filter status"
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">All statuses</option>
              {[
                "new",
                "matched",
                "shortlisted",
                "review",
                "applied",
                "rejected",
                "failed",
                "expired",
                "applying",
              ].map((s) => (
                <option value={s} key={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          )}
          {(search || platform || status || from || to) && (
            <button
              className="text-button"
              onClick={() => {
                setSearch("");
                setPlatform("");
                setStatus("");
                setFrom("");
                setTo("");
              }}
            >
              <SlidersHorizontal size={14} /> Reset
            </button>
          )}
        </div>
        {error ? (
          <div role="alert" className="error-inline">
            {error}
          </div>
        ) : loading ? (
          <div className="loading-row">
            Loading your {applied ? "applications" : "opportunities"}…
          </div>
        ) : rows.length ? (
          <JobTable
            jobs={rows}
            applied={applied}
            timezone={timezone}
            open={openJob}
          />
        ) : (
          <Empty
            title={
              search || platform || status || from || to
                ? "No matches for these filters"
                : applied
                  ? "Your story is just getting started"
                  : "Let’s find your next role"
            }
          >
            {applied
              ? "Confirmed applications will appear here automatically."
              : "Connect a platform and run discovery to see real job opportunities."}
          </Empty>
        )}
        <div className="pagination">
          <span>
            {total
              ? `${(page - 1) * 20 + 1}–${Math.min(page * 20, total)} of ${total}`
              : "0 results"}
          </span>
          <div>
            <button
              className="icon-button"
              aria-label="Previous page"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ArrowLeft size={17} />
            </button>
            <span>Page {page}</span>
            <button
              className="icon-button"
              aria-label="Next page"
              disabled={page * 20 >= total}
              onClick={() => setPage((p) => p + 1)}
            >
              <ArrowRight size={17} />
            </button>
          </div>
        </div>
      </Panel>
    </div>
  );
}
