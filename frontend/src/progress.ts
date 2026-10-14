import type { Run, RunEvent } from "./lib";

// Counters are cumulative snapshots per stage and platform, never increments.
export function progressUnits(events: RunEvent[]) {
  const units = new Map<string, RunEvent>();
  for (const event of events) {
    const key = `${event.stage}:${event.platform || "all"}`;
    const previous = units.get(key);
    units.set(key, {
      ...previous,
      ...Object.fromEntries(
        Object.entries(event).filter(([, value]) => value != null),
      ),
      metrics: { ...previous?.metrics, ...event.metrics },
    } as RunEvent);
  }
  return [...units.values()];
}
export function runMetrics(run: Run) {
  const totals: Record<string, number> = {};
  for (const unit of run.progress || progressUnits(run.events || [])) {
    for (const [name, value] of Object.entries(unit.metrics || {}))
      totals[name] = (totals[name] || 0) + value;
  }
  return totals;
}

export function stageProgress(units: RunEvent[], stage: string) {
  const entries = units.filter(
    (unit) => unit.stage === stage && unit.total != null,
  );
  const global = entries.find((unit) => !unit.platform);
  if (global) return { current: global.current || 0, total: global.total! };
  if (!entries.length) return undefined;
  return entries.reduce(
    (sum, unit) => ({
      current: sum.current + (unit.current || 0),
      total: sum.total + unit.total!,
    }),
    { current: 0, total: 0 },
  );
}

type ApplicationResult = {
  platform: string;
  error?: string;
  blocker?: string;
  message?: string;
  applied?: number;
  review?: number;
  failed?: number;
  dry_run?: number;
  selected?: number;
  processed?: number;
  skipped?: number;
  eligibility?: {
    considered: number;
    below_score: number;
    min_score: number;
    experience_mismatch: number;
    excluded_title: number;
    eligible: number;
    selected: number;
  };
};

export function applicationOutcomes(run: Run) {
  const result = run.result as
    { applications?: ApplicationResult[] } | ApplicationResult[] | null;
  const rows = Array.isArray(result)
    ? run.action === "apply"
      ? result
      : []
    : result?.applications || [];
  return rows.map((row) => {
    const needsLogin =
      row.blocker === "authentication" ||
      /login required|sign-in could not be verified/i.test(row.error || "");
    const state =
      row.error || row.review || row.failed ? "attention" : "completed";
    const message = needsLogin
      ? "Sign-in was not verified during this run. Open Platforms and verify the session before trying again."
      : row.error ||
        row.message ||
        `${row.applied || 0} confirmed · ${row.dry_run || 0} dry-run checks · ${row.review || 0} for review · ${row.skipped || 0} skipped`;
    return { ...row, state, message, needsLogin };
  });
}
export function duration(start: string, end: string | number) {
  const seconds = Math.max(
    0,
    Math.floor((new Date(end).getTime() - new Date(start).getTime()) / 1000),
  );
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
