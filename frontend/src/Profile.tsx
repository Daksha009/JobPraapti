import { useEffect, useState, type FormEvent } from "react";
import { FileText, Save, Upload, Sparkles, Check, Plus } from "lucide-react";
import { api, type Profile as ProfileData } from "./lib";
import { Panel } from "./components";

interface ResumeInsights {
  skills: string[];
  search_keywords: string[];
  warning: string;
  pages: number;
  method: string;
}
const listKeys = [
  "roles",
  "skills",
  "search_keywords",
  "locations",
  "exclude_keywords",
  "experience_level",
];
const mergeValues = (current: string, incoming: string[]) => {
  const seen = new Set<string>();
  return [...current.split(","), ...incoming]
    .map((v) => v.trim())
    .filter((v) => v && !seen.has(v.toLowerCase()) && seen.add(v.toLowerCase()))
    .join(", ");
};

export function Profile({
  notify,
}: {
  notify: (message: string, error?: boolean) => void;
}) {
  const [profile, setProfile] = useState<ProfileData>();
  const [resume, setResume] = useState({ present: false, name: "" });
  const [answers, setAnswers] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [loadingError, setLoadingError] = useState("");
  const [lists, setLists] = useState<Record<string, string>>({});
  const [insights, setInsights] = useState<ResumeInsights>();
  useEffect(() => {
    api<{ profile: ProfileData; resume_present: boolean; resume_name: string }>(
      "profile",
    )
      .then((r) => {
        setProfile(r.profile);
        setLists(
          Object.fromEntries(
            listKeys.map((key) => [
              key,
              (
                (r.profile.preferences[
                  key as keyof ProfileData["preferences"]
                ] || []) as string[]
              ).join(", "),
            ]),
          ),
        );
        setResume({ present: r.resume_present, name: r.resume_name });
        setAnswers(
          JSON.stringify(r.profile.application_defaults.answers || {}, null, 2),
        );
      })
      .catch((e) => setLoadingError(e.message));
  }, []);
  if (!profile)
    return (
      <div className="empty">{loadingError || "Loading your profile…"}</div>
    );
  function field(section: keyof ProfileData, key: string, value: unknown) {
    setProfile(
      (p) => p && { ...p, [section]: { ...p[section], [key]: value } },
    );
  }
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    try {
      const form = new FormData(e.currentTarget);
      const lists = Object.fromEntries(
        [
          "roles",
          "skills",
          "search_keywords",
          "locations",
          "exclude_keywords",
          "experience_level",
        ].map((key) => [
          key,
          String(form.get(key) || "")
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
        ]),
      );
      const parsed = JSON.parse(answers);
      if (
        !parsed ||
        Array.isArray(parsed) ||
        typeof parsed !== "object" ||
        Object.values(parsed).some(
          (v) => !["string", "boolean", "number"].includes(typeof v),
        )
      )
        throw new Error(
          "Answers must be a JSON object with text, number or boolean values.",
        );
      await api("profile", {
        profile: {
          ...profile,
          preferences: { ...profile!.preferences, ...lists },
          application_defaults: {
            ...profile!.application_defaults,
            answers: parsed,
          },
        },
      });
      notify("Profile saved. Future runs will use these details.");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    try {
      const data = new FormData();
      data.append("resume", file);
      const result = await api<{ insights: ResumeInsights }>("resume", data);
      acceptInsights(result.insights);
      setResume({ present: true, name: "resume.pdf" });
      notify(
        `Resume saved. ${result.insights.skills.length} skills detected and added to your saved profile. Review or edit them below.`,
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  function acceptInsights(value: ResumeInsights) {
    setInsights(value);
    setLists((current) => ({
      ...current,
      skills: mergeValues(current.skills || "", value.skills),
      search_keywords: mergeValues(
        current.search_keywords || "",
        value.search_keywords,
      ),
    }));
  }
  async function extractSaved() {
    setBusy(true);
    try {
      const result = await api<{ insights: ResumeInsights }>(
        "resume/extract",
        {},
      );
      acceptInsights(result.insights);
      notify(
        `${result.insights.skills.length} resume skills detected and saved. You can edit them below.`,
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save} className="page-enter profile-page">
      <div className="page-title">
        <div>
          <span className="eyebrow">MAKE IT YOURS</span>
          <h1>A profile that opens doors.</h1>
          <p>Your real details. Better matches. Thoughtful applications.</p>
        </div>
        <button className="primary" disabled={busy}>
          <Save size={16} /> {busy ? "Saving…" : "Save profile"}
        </button>
      </div>
      <Panel title="The introduction" eyebrow="01 / ABOUT YOU">
        <div className="form-grid">
          {[
            ["full_name", "Full name"],
            ["first_name", "First name"],
            ["last_name", "Last name"],
            ["email", "Email address"],
            ["phone", "Phone number"],
            ["location", "Based in"],
            ["linkedin_url", "LinkedIn URL"],
            ["github_url", "GitHub URL"],
            ["portfolio_url", "Portfolio URL"],
          ].map(([key, title]) => (
            <label key={key}>
              {title}
              <input
                type={
                  key === "email"
                    ? "email"
                    : key.endsWith("_url")
                      ? "url"
                      : "text"
                }
                value={profile.personal[key] || ""}
                onChange={(e) => field("personal", key, e.target.value)}
                required={["full_name", "email"].includes(key)}
                autoComplete={key === "email" ? "email" : "off"}
              />
            </label>
          ))}
        </div>
      </Panel>
      <Panel title="What comes next" eyebrow="02 / YOUR PREFERENCES">
        <div className="form-grid">
          {[
            ["roles", "Target roles"],
            ["skills", "Your skills"],
            ["search_keywords", "Job search keywords"],
            ["locations", "Preferred locations"],
            ["exclude_keywords", "Exclude keywords"],
            ["experience_level", "Experience levels"],
          ].map(([key, title]) => (
            <label key={key}>
              {title}
              <input
                name={key}
                value={lists[key] || ""}
                onChange={(e) =>
                  setLists((values) => ({ ...values, [key]: e.target.value }))
                }
                onBlur={(e) =>
                  field(
                    "preferences",
                    key,
                    e.target.value
                      .split(",")
                      .map((v) => v.trim())
                      .filter(Boolean),
                  )
                }
              />
              <small>
                {key === "search_keywords"
                  ? "Separate with commas. Put your strongest keywords first; they guide supported searches and ranking."
                  : key === "skills"
                    ? "Resume uploads add skills here. Add, remove or edit any skill; separate with commas."
                    : "Separate with commas"}
              </small>
            </label>
          ))}
          {[
            ["min_experience_years", "Minimum experience (years)", 0, 60],
            ["max_experience_years", "Maximum experience (years)", 0, 60],
            ["min_match_score", "Minimum match score", 0, 100],
            ["min_salary_lpa", "Minimum annual salary (INR LPA)", 0, 1000],
          ].map(([key, title, min, max]) => (
            <label key={key}>
              {title}
              <input
                type="number"
                min={min}
                max={max}
                value={
                  (profile.preferences[
                    key as keyof typeof profile.preferences
                  ] as number) || 0
                }
                onChange={(e) =>
                  field("preferences", String(key), Number(e.target.value))
                }
              />
            </label>
          ))}
        </div>
      </Panel>
      <Panel title="Your story, on paper" eyebrow="03 / RESUME">
        <div className="resume-upload">
          <span className="empty-icon">
            <FileText size={25} />
          </span>
          <div>
            <strong>{resume.present ? resume.name : "Add your resume"}</strong>
            <p>
              {resume.present
                ? "Ready for applications. Upload a new PDF to replace it."
                : "A PDF resume is required for live applications."}
            </p>
          </div>
          <label className="secondary upload-label">
            <Upload size={16} />
            {resume.present ? "Replace PDF" : "Upload PDF"}
            <input
              type="file"
              accept="application/pdf,.pdf"
              disabled={busy}
              onChange={(e) => upload(e.target.files?.[0])}
            />
          </label>
        </div>
        <div className="resume-extraction-intro">
          <div>
            <strong>
              <Sparkles size={16} /> Your resume, ready for discovery.
            </strong>
            <p>
              We extract skills and search keywords on this computer when you
              upload. Existing skills are kept, and you can edit everything.
            </p>
          </div>
          {resume.present && (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={extractSaved}
            >
              <Sparkles size={15} /> Extract from saved resume
            </button>
          )}
        </div>
        {insights && (
          <div className="resume-insights">
            <div className="insight-heading">
              <strong>{insights.skills.length} skills found</strong>
              <span>
                LOCAL EXTRACTION · {insights.pages}{" "}
                {insights.pages === 1 ? "PAGE" : "PAGES"}
              </span>
            </div>
            {insights.warning && (
              <p className="extraction-warning" role="status">
                {insights.warning}
              </p>
            )}
            <div className="skill-chips">
              {insights.skills.map((skill) => {
                const selected = (lists.skills || "")
                  .split(",")
                  .some((v) => v.trim().toLowerCase() === skill.toLowerCase());
                return (
                  <button
                    type="button"
                    key={skill}
                    className={selected ? "selected" : ""}
                    aria-pressed={selected}
                    aria-label={`${selected ? "Remove" : "Add"} ${skill} skill`}
                    onClick={() =>
                      setLists((values) => ({
                        ...values,
                        skills: selected
                          ? values.skills
                              .split(",")
                              .map((v) => v.trim())
                              .filter(
                                (v) => v.toLowerCase() !== skill.toLowerCase(),
                              )
                              .join(", ")
                          : mergeValues(values.skills || "", [skill]),
                      }))
                    }
                  >
                    {selected ? <Check size={13} /> : <Plus size={13} />}{" "}
                    {skill}
                  </button>
                );
              })}
            </div>
            <p className="caption">
              Select a skill to add or remove it. Save profile after edits.
              Search keywords can be edited separately above.
            </p>
          </div>
        )}
        <label>
          Professional summary
          <textarea
            rows={4}
            value={profile.resume.summary || ""}
            onChange={(e) => field("resume", "summary", e.target.value)}
          />
        </label>
      </Panel>
      <Panel title="In your own words" eyebrow="04 / APPLICATION DETAILS">
        <div className="form-grid">
          {[
            ["years_of_experience", "Your experience (years)"],
            ["notice_period", "Notice period"],
            ["expected_ctc", "Expected CTC"],
            ["current_ctc", "Current CTC"],
          ].map(([key, title]) => (
            <label key={key}>
              {title}
              <input
                type={key === "years_of_experience" ? "number" : "text"}
                min={0}
                value={
                  (profile.application_defaults[
                    key as keyof typeof profile.application_defaults
                  ] as string) || ""
                }
                onChange={(e) =>
                  field(
                    "application_defaults",
                    key,
                    key === "years_of_experience"
                      ? Number(e.target.value)
                      : e.target.value,
                  )
                }
              />
            </label>
          ))}
        </div>
        <label className="check-label">
          <input
            type="checkbox"
            checked={Boolean(profile.application_defaults.willing_to_relocate)}
            onChange={(e) =>
              field(
                "application_defaults",
                "willing_to_relocate",
                e.target.checked,
              )
            }
          />{" "}
          Willing to relocate
        </label>
        <label>
          Introduction message
          <textarea
            rows={3}
            value={profile.application_defaults.intro_message || ""}
            onChange={(e) =>
              field("application_defaults", "intro_message", e.target.value)
            }
          />
        </label>
        <label>
          Your reviewed cover letter
          <textarea
            rows={5}
            value={profile.application_defaults.cover_letter || ""}
            onChange={(e) =>
              field("application_defaults", "cover_letter", e.target.value)
            }
          />
        </label>
        <details>
          <summary>Exact screening answers</summary>
          <p className="caption">
            Map exact question labels to truthful answers. Unrecognized
            questions stop for your review.
          </p>
          <textarea
            className="code-input"
            rows={7}
            aria-label="Exact screening answers JSON"
            value={answers}
            onChange={(e) => setAnswers(e.target.value)}
          />
        </details>
      </Panel>
      <div className="form-footer">
        <span>Stored privately on this computer</span>
        <button className="primary" disabled={busy}>
          <Save size={16} /> Save profile
        </button>
      </div>
    </form>
  );
}
