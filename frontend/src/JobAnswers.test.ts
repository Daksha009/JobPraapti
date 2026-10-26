import { describe, it, expect } from "vitest";
import { readAnswers } from "./JobAnswers";

describe("application answer records", () => {
  it("handles old jobs without drafts", () => {
    expect(readAnswers().entries).toEqual([]);
    expect(readAnswers("invalid").unresolved).toEqual([]);
    expect(readAnswers('{"version":2}').overrides).toEqual({});
  });
  it("keeps explicit false, zero, evidence and submission uncertainty", () => {
    const record = readAnswers(
      JSON.stringify({
        version: 1,
        entries: [
          {
            question: "Why?",
            answer: "Example",
            source: "resume_and_job",
            evidence: "Resume bullet",
          },
        ],
        overrides: { "Consent?": false, Experience: 0 },
        submission_started: true,
      }),
    );
    expect(record.overrides["Consent?"]).toBe(false);
    expect(record.overrides.Experience).toBe(0);
    expect(record.entries[0].evidence).toBe("Resume bullet");
    expect(record.submission_started).toBe(true);
  });
});
