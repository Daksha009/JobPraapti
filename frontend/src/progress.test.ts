import { describe, it, expect } from "vitest";
import {
  applicationOutcomes,
  duration,
  progressUnits,
  runMetrics,
  stageProgress,
} from "./progress";
import type { Run, RunEvent } from "./lib";
describe("live run accounting", () => {
  it("preserves known candidate counts after historical error resets", () => {
    const events = [
      { stage: "apply", platform: "hirist", current: 2, total: 5 },
      { stage: "apply", platform: "linkedin", current: 0, total: 1 },
      {
        stage: "apply",
        platform: "hirist",
        current: 0,
        total: 0,
        state: "attention",
      },
      {
        stage: "apply",
        platform: "linkedin",
        current: 0,
        total: 0,
        state: "attention",
      },
    ] as RunEvent[];
    const units = progressUnits(events);
    expect(stageProgress(units, "apply")).toEqual({ current: 2, total: 6 });
    expect(units[0].state).toBe("attention");
    expect(events[2].total).toBe(0);
  });
  it("aggregates every platform instead of showing the final empty queue", () => {
    const units = [
      { stage: "apply", platform: "hirist", current: 0, total: 5 },
      { stage: "apply", platform: "linkedin", current: 1, total: 1 },
      { stage: "apply", platform: "glassdoor", current: 0, total: 0 },
    ] as RunEvent[];
    expect(stageProgress(units, "apply")).toEqual({ current: 1, total: 6 });
    expect(
      stageProgress(
        [...units, { stage: "apply", current: 1, total: 6 } as RunEvent],
        "apply",
      ),
    ).toEqual({ current: 1, total: 6 });
  });
  it("explains blockers in historical results without rewriting run history", () => {
    const run = {
      action: "pipeline",
      result: {
        applications: [
          {
            platform: "hirist",
            error: "Login required: python -m jobpilot login -p hirist",
          },
          {
            platform: "glassdoor",
            message: "No eligible matched or shortlisted jobs",
          },
        ],
      },
    } as Run;
    const outcomes = applicationOutcomes(run);
    expect(outcomes[0].needsLogin).toBe(true);
    expect(outcomes[0].message).toContain("during this run");
    expect(outcomes[1].needsLogin).toBe(false);
    expect(outcomes[1].message).toContain("No eligible");
  });
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
