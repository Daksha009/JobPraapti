import { useState } from "react";
import { api, type Job } from "./lib";

type Answer = string | boolean | number;
type RecordData = {
  version: number;
  entries: {
    question: string;
    answer: Answer;
    source: string;
    evidence?: string;
  }[];
  unresolved: string[];
  overrides: Record<string, Answer>;
  validation_errors?: string[];
  submission_started?: boolean;
};

export function readAnswers(raw?: string): RecordData {
  try {
    const value = JSON.parse(raw || "{}");
    if (value?.version === 1)
      return {
        ...value,
        entries: value.entries || [],
        unresolved: value.unresolved || [],
        overrides: value.overrides || {},
      };
  } catch {
    /* Old jobs may not have a structured answer record. */
  }
  return { version: 1, entries: [], unresolved: [], overrides: {} };
}

export function JobAnswers({
  job,
  disabled,
  notify,
}: {
  job: Job;
  disabled: boolean;
  notify: (message: string, error?: boolean) => void;
}) {
  const [record, setRecord] = useState(() =>
    readAnswers(job.generated_answers),
  );
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Record<string, Answer>>(
    record.overrides,
  );
  const [busy, setBusy] = useState(false);
  const questions = [
    ...new Set([
      ...record.unresolved,
      ...record.entries.map((e) => e.question),
      ...Object.keys(record.overrides),
    ]),
  ];
  async function prepare() {
    setBusy(true);
    try {
      const result = await api<{ record: RecordData; prepared: boolean }>(
        `jobs/${job.id}/answers/prepare`,
        { question },
      );
      setRecord(result.record);
      setQuestion("");
      notify(
        result.prepared
          ? "Answer prepared from your saved details."
          : "This question needs your answer or more resume/job evidence. Enter it below.",
      );
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    try {
      const nonempty = Object.fromEntries(
        Object.entries(answers).filter(
          ([, value]) => typeof value !== "string" || value.trim(),
        ),
      );
      await api(`jobs/${job.id}/answers`, { answers: nonempty });
      notify(
        "Answers saved for this job. Verify its application status before retrying.",
      );
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="job-answers">
      <h3>Application answers</h3>
      <p className="caption">
        Use these answers in the open application tab. Edits apply only to this
        job. Saving does not submit or retry an application.
      </p>
      {!disabled && (
        <div className="answer-item">
          <label>
            Question from the application
            <textarea
              rows={2}
              maxLength={2000}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Paste a screening or written question"
            />
          </label>
          <button
            className="secondary"
            disabled={busy || !question.trim()}
            onClick={prepare}
          >
            Prepare answer
          </button>
        </div>
      )}
      {record.submission_started && (
        <p className="info-banner">
          Submit was clicked. Check the platform for confirmation before
          starting another application.
        </p>
      )}
      {questions.map((question) => {
        const entry = record.entries.find((e) => e.question === question);
        const value = answers[question];
        const boolean = typeof (value ?? entry?.answer) === "boolean";
        return (
          <div className="answer-item" key={question}>
            <label>
              {question}
              {boolean ? (
                <select
                  disabled={disabled || busy}
                  value={value === undefined ? "" : String(value)}
                  onChange={(e) =>
                    setAnswers({
                      ...answers,
                      [question]:
                        e.target.value === "" ? "" : e.target.value === "true",
                    })
                  }
                >
                  <option value="">
                    Use saved answer
                    {entry ? ` (${entry.answer ? "Yes" : "No"})` : ""}
                  </option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              ) : (
                <textarea
                  rows={3}
                  disabled={disabled || busy}
                  value={String(value ?? "")}
                  placeholder={entry ? String(entry.answer) : "Add your answer"}
                  onChange={(e) =>
                    setAnswers({ ...answers, [question]: e.target.value })
                  }
                />
              )}
            </label>
            {record.validation_errors?.includes(question) && (
              <p className="info-banner">
                The platform rejected this answer. Check the required format in
                the open application and save a corrected answer here.
              </p>
            )}
            {entry && (
              <p className="caption">
                {entry.source === "resume_and_job"
                  ? "Prepared from your resume and this role"
                  : "Saved answer"}
                : {String(entry.answer)}
              </p>
            )}
            {entry?.evidence && (
              <details>
                <summary>Resume evidence</summary>
                <p>{entry.evidence}</p>
              </details>
            )}
          </div>
        );
      })}
      <button
        className="secondary"
        disabled={disabled || busy || !questions.length}
        onClick={save}
      >
        {busy ? "Saving…" : "Save job answers"}
      </button>
    </section>
  );
}
