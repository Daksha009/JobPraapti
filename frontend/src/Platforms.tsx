import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowUpRight,
  Check,
  KeyRound,
  LockKeyhole,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api, dateTime, label, safeUrl, type Connections } from "./lib";
import { Badge, Modal, PlatformIcon } from "./components";

export function Platforms({
  data,
  busy,
  run,
  refresh,
  notify,
}: {
  data: Connections;
  busy: boolean;
  run: (action: string, platform: string) => void;
  refresh: () => void;
  notify: (message: string, error?: boolean) => void;
}) {
  const [editing, setEditing] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [browser, setBrowser] = useState<{
    same_browser: boolean;
    running: boolean;
    remember: boolean;
  }>();
  const [opening, setOpening] = useState(false);
  const [sessionAction, setSessionAction] = useState<string>();
  const [sessionBusy, setSessionBusy] = useState(false);
  useEffect(() => {
    let mounted = true;
    const check = () =>
      api<{ same_browser: boolean; running: boolean; remember: boolean }>(
        "browser",
      )
        .then((value) => {
          if (mounted) setBrowser(value);
        })
        .catch(() => {
          if (mounted) setBrowser(undefined);
        });
    void check();
    const timer = setInterval(check, 4000);
    window.addEventListener("focus", check);
    return () => {
      mounted = false;
      clearInterval(timer);
      window.removeEventListener("focus", check);
    };
  }, []);
  async function changeSession(action: string) {
    setSessionBusy(true);
    try {
      await api("browser/sign-out", { platform: action });
      notify(
        action === "all"
          ? "Signed out of all job platforms in regular Chrome."
          : `Signed out of ${label(action)} here.`,
      );
      setSessionAction(undefined);
      refresh();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setSessionBusy(false);
    }
  }
  async function openWorkspace() {
    setOpening(true);
    try {
      await api("browser/open", {});
      notify(
        "Opened JobPraapti in regular Chrome. Your existing platform logins stay there.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setOpening(false);
    }
  }
  async function openPlatform(platform: string) {
    setOpening(true);
    try {
      await api("browser/open-platform", { platform });
      notify(
        "Opened in regular Chrome. Sign in there, then select Verify sign-in.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setOpening(false);
    }
  }
  async function connectBrowser() {
    setOpening(true);
    try {
      if (!browser?.running) {
        await api("browser/setup", {});
        notify(
          "Enable remote debugging in the Chrome settings tab, then return and check browser access.",
        );
      } else {
        notify("Allow the connection prompt in regular Chrome to continue.");
        await api("browser/connect", {});
        notify(
          "Regular Chrome connected. Existing sessions are ready to verify.",
        );
      }
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setOpening(false);
    }
  }
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSaving(true);
    try {
      const fields = Object.fromEntries(new FormData(e.currentTarget));
      await api("credentials", { platform: editing, ...fields });
      setEditing(undefined);
      refresh();
      notify("Credentials encrypted and saved.");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="page-enter">
      <div className="page-title">
        <div>
          <span className="eyebrow">MANY PLATFORMS. ONE PLACE.</span>
          <h1>Expand your possibilities.</h1>
          <p>Connect once. Keep your job search in sync.</p>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => run("check", "all")}
        >
          <RefreshCw size={16} /> Check connections
        </button>
      </div>
      <div className="info-banner">
        <ShieldCheck size={22} />
        <div>
          <strong>Private by design</strong>
          <p>
            Passwords are encrypted for your Windows account. Sign in through
            the browser to complete any OTP, SSO, or verification.
          </p>
        </div>
      </div>
      <section
        className={`browser-workspace ${browser?.running ? "connected" : ""}`}
      >
        <span className="workspace-orb" aria-hidden="true">
          <ShieldCheck size={28} />
        </span>
        <div>
          <span className="eyebrow">YOUR CHROME. YOUR SAVED SIGN-INS.</span>
          <h2>
            {browser?.running
              ? "Regular Chrome access is enabled."
              : "Use the Chrome you already know."}
          </h2>
          <p>
            Sign in opens each platform in your regular Chrome profile. Existing
            logins are reused. Complete any OTP or security check there, then
            select Verify sign-in.
          </p>
          <p>
            For automation, enable remote debugging at{" "}
            <code>chrome://inspect/#remote-debugging</code> in regular Chrome
            and allow its connection prompt. Chrome may ask for permission again
            on a new run.
          </p>
          <button
            className="text-button"
            disabled={opening}
            onClick={openWorkspace}
          >
            Open dashboard in regular Chrome <ArrowUpRight size={14} />
          </button>
        </div>
        <button
          className="primary"
          disabled={opening || busy}
          onClick={connectBrowser}
        >
          {opening
            ? "Waiting for Chrome…"
            : browser?.running
              ? "Check browser access"
              : "Set up Chrome access"}
          <ArrowUpRight size={16} />
        </button>
      </section>
      <section className="session-settings">
        <div className="session-toggle">
          <ShieldCheck size={22} />
          <span>
            <strong>Keep me signed in · always on</strong>
            <small>
              Your regular Chrome keeps your sessions. JobPraapti does not clear
              them between runs or submit your password again. Platforms can
              still expire or revoke a session.
            </small>
          </span>
        </div>
        <button
          className="text-button"
          disabled={!browser?.running || busy || sessionBusy}
          onClick={() => setSessionAction("all")}
        >
          <LogOut size={15} /> Sign out of all
        </button>
      </section>
      <div className="connections-grid">
        {data.platforms.map((c) => (
          <section
            className={`connection-card ${!c.enabled ? "disabled" : ""}`}
            key={c.name}
          >
            <div className="connection-card-top">
              <PlatformIcon name={c.name} />
              <Badge value={!c.enabled ? "disabled" : c.status} />
            </div>
            <h2>{label(c.name)}</h2>
            <p>
              {!c.enabled
                ? "On hold, as requested."
                : c.message || "Connect your account to get started."}
            </p>
            <div className="credential-summary">
              <span>
                {c.email_saved ? (
                  <Check size={13} />
                ) : (
                  <span className="tiny-dot" />
                )}{" "}
                Email saved
              </span>
              <span>
                {c.password_saved ? (
                  <Check size={13} />
                ) : (
                  <span className="tiny-dot" />
                )}{" "}
                Password saved
              </span>
            </div>
            <small className="connection-time">
              {c.checked_at
                ? `Checked ${dateTime(c.checked_at)}`
                : "No connection check yet"}
            </small>
            <div className="connection-actions">
              <button
                className="primary"
                disabled={opening || busy || !c.enabled}
                onClick={() => void openPlatform(c.name)}
              >
                {c.status === "connected" ? "Open in Chrome" : "Sign in"}{" "}
                <ArrowUpRight size={16} />
              </button>
              <button
                className="secondary"
                disabled={busy || !c.enabled || !browser?.running}
                onClick={() => run("check", c.name)}
              >
                <Check size={15} /> Verify sign-in
              </button>
              <button
                className="secondary"
                disabled={!c.enabled}
                onClick={() => setEditing(c.name)}
              >
                <KeyRound size={15} /> Credentials
              </button>
              <a
                className="icon-button"
                href={safeUrl(c.url)}
                target="_blank"
                rel="noreferrer"
                aria-label={`Open ${label(c.name)}`}
              >
                <ArrowUpRight size={17} />
              </a>
            </div>
            {c.enabled && (
              <div className="session-card-footer">
                <span>
                  {c.status === "connected" && browser?.remember
                    ? "Session saved on this device"
                    : c.status === "signed_out"
                      ? "Signed out here"
                      : browser?.remember
                        ? "Session saving enabled"
                        : "Sessions managed by regular Chrome"}
                </span>
                <button
                  className="text-button"
                  disabled={
                    !browser?.running ||
                    busy ||
                    sessionBusy ||
                    c.status === "signed_out"
                  }
                  onClick={() => setSessionAction(c.name)}
                >
                  <LogOut size={12} /> Sign out here
                </button>
              </div>
            )}
          </section>
        ))}
      </div>
      <section className="ai-card">
        <span className="ai-icon">
          <Sparkles size={28} />
        </span>
        <div>
          <span className="eyebrow">A LITTLE EXTRA INTELLIGENCE</span>
          <h2>Meet your matching assistant.</h2>
          <p>
            Gemini helps score roles against your profile. Offline keyword
            matching is available when AI is unavailable.
          </p>
          <div className="ai-meta">
            <Badge value={data.ai.status} />
            <span>
              {data.ai.key_saved
                ? "API key securely saved"
                : "No API key saved"}{" "}
              · {data.ai.model}
            </span>
          </div>
        </div>
        <button className="secondary" onClick={() => setEditing("gemini")}>
          <KeyRound size={16} /> Update API key
        </button>
      </section>
      {sessionAction && (
        <Modal
          title={
            sessionAction === "all"
              ? "Sign out of all platforms?"
              : `Sign out of ${label(sessionAction)}?`
          }
          close={() => !sessionBusy && setSessionAction(undefined)}
        >
          <p className="modal-description">
            This closes{" "}
            {sessionAction === "all" ? "job-platform" : label(sessionAction)}{" "}
            tabs in your regular Chrome and clears their sign-in data from that
            profile. This also signs you out during normal browsing in that
            Chrome profile. Your profile and encrypted credentials stay saved.
            Other devices are unaffected.
          </p>
          <button
            className="primary full"
            disabled={sessionBusy}
            onClick={() => void changeSession(sessionAction)}
          >
            {sessionBusy ? "Updating sessions…" : "Sign out here"}
          </button>
        </Modal>
      )}
      {editing && (
        <Modal
          title={
            editing === "gemini"
              ? "Your AI connection"
              : `Connect ${label(editing)}`
          }
          close={() => !saving && setEditing(undefined)}
        >
          <form onSubmit={save}>
            <p className="modal-description">
              New values replace saved credentials. Leave a field empty to keep
              its current value.
            </p>
            {editing === "gemini" ? (
              <label>
                API key
                <input
                  autoComplete="off"
                  name="api_key"
                  type="password"
                  required
                />
              </label>
            ) : (
              <>
                <label>
                  Email address
                  <input
                    autoComplete="off"
                    name="email"
                    type="email"
                    placeholder="Your account email"
                  />
                </label>
                <label>
                  Password
                  <input
                    autoComplete="new-password"
                    name="password"
                    type="password"
                    placeholder="Leave blank to keep the saved password"
                  />
                </label>
              </>
            )}
            <div className="privacy-note">
              <LockKeyhole size={15} /> Encrypted locally. Saved values never
              return to this form.
            </div>
            <button className="primary full" disabled={saving}>
              {saving ? "Saving…" : "Save securely"}
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}
