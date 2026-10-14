import { describe, it, expect } from "vitest";
import { duration, progressUnits, runMetrics } from "./progress";
import type { Run, RunEvent } from "./lib";
describe("live run accounting", () => {
  it("merges snapshots without double-counting repeated polling or per-job totals", () => {
    const event = {
      stage: "apply",
      platform: "linkedin",
      state: "running",
      timestamp: "2026-10-13T10:00:00Z",
      message: "Working",
      id: 1,
      current: 1,
      total: 5,
      metrics: { dry_run: 1 },
    } as RunEvent;
    const events = [
      event,
      { ...event, id: 2, current: 2, metrics: { dry_run: 2 } },
      { ...event, id: 3, platform: "wellfound", metrics: { dry_run: 1 } },
    ];
    expect(runMetrics({ events } as Run).dry_run).toBe(3);
    expect(progressUnits([...events, events[1]])[0].current).toBe(2);
  });
  it("retains counts when a terminal message has no new metrics", () => {
    const base = {
      id: 1,
      stage: "match",
      state: "running",
      timestamp: "2026-10-13T10:00:00Z",
      message: "Scoring",
      current: 3,
      total: 5,
      metrics: { scored: 3 },
    } as RunEvent;
    const [unit] = progressUnits([
      base,
      {
        ...base,
        id: 2,
        state: "failed",
        current: undefined,
        total: undefined,
        metrics: undefined,
      },
    ]);
    expect(unit.current).toBe(3);
    expect(unit.metrics?.scored).toBe(3);
    expect(unit.state).toBe("failed");
  });
  it("formats actual duration without a fabricated ETA", () => {
    expect(duration("2026-10-13T10:00:00Z", "2026-10-13T10:02:07Z")).toBe(
      "2m 7s",
    );
  });
});
