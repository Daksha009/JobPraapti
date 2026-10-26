export interface Job {
  id: number;
  title: string;
  company: string;
  platform: string;
  status: string;
  match_score: number;
  url: string;
  location: string;
  applied_at?: string;
  description?: string;
  match_reason?: string;
  generated_answers?: string;
  application_history?: {
    action: string;
    details: string;
    timestamp: string;
  }[];
}
export interface Connection {
  name: string;
  enabled: boolean;
  status: string;
  message?: string;
  url: string;
  checked_at?: string;
  login_url: string;
  email_saved: boolean;
  password_saved: boolean;
  session_saved: boolean;
  daily_limit: number;
}
export interface Run {
  id: string;
  action: string;
  platform: string;
  state: string;
  started_at: string;
  finished_at?: string;
  options: { dry_run: boolean; limit: number };
  message: string;
  result: unknown;
  events?: RunEvent[];
  event_count?: number;
  progress?: RunEvent[];
}
export interface RunEvent {
  id: number;
  timestamp: string;
  stage: string;
  platform?: string;
  state: string;
  message: string;
  current?: number;
  total?: number;
  metrics?: Record<string, number>;
}
export interface Overview {
  total_applications: number;
  applied_today: number;
  period_applications: number;
  total_jobs: number;
  needs_review: number;
  shortlisted: number;
  matched: number;
  average_match: number;
  timezone: string;
  chart: { date: string; count: number }[];
  by_platform: Record<string, number>;
  recent: Job[];
  undated_applications: number;
  activity: {
    id: number;
    title: string;
    company: string;
    platform: string;
    action: string;
    timestamp: string;
  }[];
}
export interface Connections {
  platforms: Connection[];
  ai: { key_saved: boolean; model: string; status: string; message?: string };
}
export interface Profile {
  personal: Record<string, string>;
  preferences: {
    roles: string[];
    skills: string[];
    search_keywords: string[];
    locations: string[];
    exclude_keywords: string[];
    experience_level: string[];
    min_experience_years: number;
    max_experience_years: number;
    min_match_score: number;
    min_salary_lpa: number;
  };
  resume: { summary: string; path: string };
  application_defaults: {
    intro_message: string;
    cover_letter: string;
    answers: Record<string, string | boolean | number>;
    years_of_experience: number;
    notice_period: string;
    expected_ctc: string;
    current_ctc: string;
    willing_to_relocate: boolean;
    compose_narrative_answers?: boolean;
  };
}
let token = "";
export function setToken(value: string) {
  token = value;
}
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch(`/api/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined
        ? {}
        : {
            "X-JobPilot-Token": token,
            ...(form ? {} : { "Content-Type": "application/json" }),
          },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  const data = await response
    .json()
    .catch(() => ({ error: `Request failed (${response.status})` }));
  if (!response.ok)
    throw new Error(data.error || `Request failed (${response.status})`);
  return data as T;
}
export const labels: Record<string, string> = {
  wellfound: "Wellfound",
  hirist: "Hirist",
  cutshort: "Cutshort",
  linkedin: "LinkedIn",
  glassdoor: "Glassdoor",
  foundit: "Foundit",
  gemini: "Gemini",
};
export const label = (value: string) =>
  labels[value] ||
  value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
export const safeUrl = (value: string) => {
  try {
    const u = new URL(value);
    return ["https:", "http:"].includes(u.protocol) ? u.href : "#";
  } catch {
    return "#";
  }
};
export function dateTime(value?: string, timeZone = "Asia/Kolkata") {
  return value
    ? new Intl.DateTimeFormat("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone,
      }).format(
        new Date(/[Zz]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`),
      )
    : "Date not recorded";
}
export function initials(value: string) {
  return (
    value
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0])
      .join("")
      .toUpperCase() || "JP"
  );
}
export function filtersQuery(filters: Record<string, string>) {
  return new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v),
  ).toString();
}
