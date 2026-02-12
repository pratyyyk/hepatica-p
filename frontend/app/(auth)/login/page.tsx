"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { HepaticaLogo } from "@/components/HepaticaLogo";
import { Button, Card, CardHeader, Field, Input, Pill } from "@/components/ui";
import { apiBase } from "@/lib/api";
import { useSession } from "@/lib/session";

const showDevLogin = process.env.NEXT_PUBLIC_ENABLE_DEV_AUTH === "true";

const demoDoctors = [
  { name: "Dr Asha Singh", email: "asha.singh@demo.hepatica" },
  { name: "Dr Maya Chen", email: "maya.chen@demo.hepatica" },
  { name: "Dr Alex Rivera", email: "alex.rivera@demo.hepatica" },
];

export default function LoginPage() {
  const router = useRouter();
  const { session, loading, loginDev } = useSession();
  const [customEmail, setCustomEmail] = useState("doctor@example.com");
  const [error, setError] = useState("");
  const [health, setHealth] = useState<"idle" | "checking" | "ok" | "down">("idle");

  const authed = !!session?.authenticated;
  const headline = useMemo(() => (authed ? "Session active" : "Sign in"), [authed]);

  async function startDemoLogin(email: string) {
    setError("");
    try {
      await loginDev(email);
      router.push("/patients");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  async function handleCustom(e: FormEvent) {
    e.preventDefault();
    await startDemoLogin(customEmail.trim());
  }

  async function checkHealth() {
    setHealth("checking");
    try {
      const res = await fetch(`${apiBase}/healthz`, { cache: "no-store" });
      setHealth(res.ok ? "ok" : "down");
    } catch {
      setHealth("down");
    }
  }

  useEffect(() => {
    if (!loading && !authed && health === "idle") {
      void checkHealth();
    }
  }, [authed, health, loading]);

  return (
    <main className="authWrap">
      <div className="authHero">
        <div className="heroMark">
          <HepaticaLogo size={52} />
        </div>
        <div>
          <h1 className="heroTitle">Hepatica Console</h1>
          <p className="heroSubtitle">Clinical liver risk assessment workspace for local evaluation workflows.</p>
        </div>
        <div className="heroBadges">
          <Pill tone="neutral">Environment: Local</Pill>
          <Pill tone="neutral">Access: Clinician</Pill>
          <Pill tone={health === "ok" ? "ok" : health === "down" ? "warn" : "neutral"}>
            API {health === "ok" ? "Online" : health === "down" ? "Offline" : "Checking"}
          </Pill>
        </div>
      </div>

      <div className="authGrid">
        <Card className="authCardMain">
          <CardHeader title={headline} subtitle="Choose a clinician profile or use a local demo email." />

          {loading ? (
            <div className="empty">Checking session...</div>
          ) : authed ? (
            <div className="stack">
              <p className="muted">Signed in as {session?.email}</p>
              <Button onClick={() => router.push("/patients")}>Go to Patients</Button>
            </div>
          ) : (
            <div className="stack authStack">
              <div className="authSection">
                <div className="authSectionHead">
                  <div className="authSectionTitle">System Connection</div>
                  <Button
                    tone="ghost"
                    type="button"
                    onClick={() => void checkHealth()}
                    disabled={health === "checking"}
                  >
                    {health === "checking" ? "Checking..." : "Check backend"}
                  </Button>
                </div>
                <div className="authEndpoint">
                  <span>API endpoint</span>
                  <code>{apiBase}</code>
                  {health === "ok" ? <Pill tone="ok">Connected</Pill> : null}
                  {health === "down" ? <Pill tone="warn">Unreachable</Pill> : null}
                </div>
              </div>
              {!showDevLogin ? (
                <div className="status status-warn">
                  Dev login is disabled in the frontend build. Set `NEXT_PUBLIC_ENABLE_DEV_AUTH=true` in
                  `frontend/.env.local`. (Backend dev login is enabled by default in `ENVIRONMENT=development`;
                  set `ENABLE_DEV_AUTH=true` only if you turned it off.)
                </div>
              ) : (
                <>
                  <div className="authSection">
                    <div className="authSectionTitle">Quick Sign-In</div>
                    <div className="authSectionHint">Select a clinician profile</div>
                    <div className="demoList">
                      {demoDoctors.map((doc) => (
                        <button
                          key={doc.email}
                          type="button"
                          className="demoCard"
                          onClick={() => void startDemoLogin(doc.email)}
                        >
                          <div className="demoName">{doc.name}</div>
                          <div className="demoEmail">{doc.email}</div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <form onSubmit={handleCustom} className="authSection authInlineForm">
                    <Field label="Custom demo email" hint="Stored only in local DB">
                      <Input value={customEmail} onChange={(e) => setCustomEmail(e.target.value)} />
                    </Field>
                    <div className="authActions">
                      <Button type="submit">Enter Console</Button>
                    </div>
                  </form>
                </>
              )}

              {error ? <div className="status status-danger">{error}</div> : null}
            </div>
          )}
        </Card>

        <Card className="authCardSide">
          <CardHeader title="Workflow Overview" subtitle="Recommended sequence for the full assessment run." />
          <ol className="demoFlow">
            <li>
              <span className="demoStepNum">1</span>
              <div>
                <strong>Authenticate clinician session</strong>
                <p>Use one-click credentials or a local demo email.</p>
              </div>
            </li>
            <li>
              <span className="demoStepNum">2</span>
              <div>
                <strong>Register or select a patient</strong>
                <p>Capture baseline demographics and risk context.</p>
              </div>
            </li>
            <li>
              <span className="demoStepNum">3</span>
              <div>
                <strong>Run Stage 1, Stage 2, and Stage 3</strong>
                <p>Review clinical scores, imaging risk, and monitoring output.</p>
              </div>
            </li>
            <li>
              <span className="demoStepNum">4</span>
              <div>
                <strong>Generate report and review timeline</strong>
                <p>Export consolidated findings with explainability context.</p>
              </div>
            </li>
          </ol>
          <div className="authTip">
            This demo keeps data in your local database and does not transmit patient data externally.
          </div>
        </Card>
      </div>
    </main>
  );
}
