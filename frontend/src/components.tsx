import { useEffect, useRef, type ReactNode } from "react";
import { ArrowUpRight, Check, Inbox, X } from "lucide-react";
import { createPortal } from "react-dom";
import { dateTime, initials, label, type Job } from "./lib";

export function PlatformIcon({ name }: { name: string }) {
  return (
    <span aria-hidden="true" className={`platform-icon ${name}`}>
      {(
        {
          linkedin: "in",
          wellfound: "w:",
          hirist: "h",
          cutshort: "c/",
          glassdoor: "g",
          foundit: "f",
        } as Record<string, string>
      )[name] || name.slice(0, 2)}
    </span>
  );
}
export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value}`}>
      {value === "connected" && <Check size={12} />} {label(value)}
    </span>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Inbox size={26} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);
  return createPortal(
    <dialog
      ref={ref}
      className={`modal ${wide ? "wide" : ""}`}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="modal-content">
        <div className="modal-heading">
          <h2>{title}</h2>
          <button
            className="icon-button"
            onClick={close}
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>,
    document.body,
  );
}
export function JobTable({
  jobs,
  applied = false,
  open,
  timezone,
}: {
  jobs: Job[];
  applied?: boolean;
  open: (id: number) => void;
  timezone: string;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Role & company</th>
            <th>Platform</th>
            <th>{applied ? "Applied on" : "Status"}</th>
            <th>Match</th>
            <th>
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>
                <button className="job-title" onClick={() => open(job.id)}>
                  <span className="company-avatar">
                    {initials(job.company)}
                  </span>
                  <span>
                    <strong>{job.title}</strong>
                    <small>
                      {job.company}
                      {!applied && job.location && ` · ${job.location}`}
                    </small>
                  </span>
                </button>
              </td>
              <td>
                <span className="platform-cell">
                  <PlatformIcon name={job.platform} />
                  {label(job.platform)}
                </span>
              </td>
              <td>
                {applied ? (
                  <span className="date-cell">
                    {dateTime(job.applied_at, timezone)}
                  </span>
                ) : (
                  <Badge value={job.status} />
                )}
              </td>
              <td>
                <span
                  className={`match-score ${job.match_score >= 70 ? "high" : ""}`}
                >
                  {job.match_score ? `${Math.round(job.match_score)}%` : "—"}
                </span>
              </td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`View ${job.title}`}
                  onClick={() => open(job.id)}
                >
                  <ArrowUpRight size={18} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
