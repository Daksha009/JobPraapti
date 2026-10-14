import { describe, it, expect } from "vitest";
import { safeUrl, dateTime, filtersQuery, initials } from "./lib";
describe("links and reporting", () => {
  it("rejects active URL protocols", () => {
    expect(safeUrl("javascript:alert(1)")).toBe("#");
    expect(safeUrl("data:text/html,x")).toBe("#");
    expect(safeUrl("https://linkedin.com/jobs")).toBe(
      "https://linkedin.com/jobs",
    );
  });
  it("renders UTC timestamps on the correct local day", () => {
    expect(dateTime("2026-10-12T20:00:00Z")).toContain("13 Oct 2026");
    expect(dateTime()).toBe("Date not recorded");
  });
  it("encodes filters without leaking empty state", () => {
    expect(filtersQuery({ search: "C++ & Python", platform: "" })).toBe(
      "search=C%2B%2B+%26+Python",
    );
    expect(initials("Test Candidate")).toBe("TC");
  });
});
