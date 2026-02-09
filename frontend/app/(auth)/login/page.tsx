"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

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
  const headline = useMemo(() => (authed ? "You are signed in" : "Sign in to the console"), [authed]);

  async function handleCustom(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await loginDev(customEmail.trim());
      router.push("/patients");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
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
        <div className="heroMark">H</div>
        <h1 className="heroTitle">Hepatica</h1>
        <p className="heroSubtitle">Clinical risk triage + fibrosis staging. Local-only demo flow.</p>
        <div className="heroBadges">
          <Pill tone="ok">No AWS required</Pill>
          <Pill tone="ok">No Firebase required</Pill>
          <Pill tone="neutral">FastAPI + Next.js</Pill>
        </div>
      </div>

      <div className="authGrid">
        <Card>
          <CardHeader title={headline} subtitle="Use demo doctors for 1-click login." />

          {loading ? (
            <div className="empty">Checking session...</div>
          ) : authed ? (
            <div className="stack">
              <p className="muted">Signed in as {session?.email}</p>
              <Button onClick={() => router.push("/patients")}>Go to Patients</Button>
            </div>
          ) : (
            <div className="stack">
              <div className="row">
                <div className="muted">API: {apiBase}</div>
                <Button
                  tone="ghost"
                  type="button"
                  onClick={() => void checkHealth()}
                  disabled={health === "checking"}
                >
                  {health === "checking" ? "Checking..." : "Check backend"}
                </Button>
                {health === "ok" ? <Pill tone="ok">Backend OK</Pill> : null}
                {health === "down" ? <Pill tone="warn">Backend unreachable</Pill> : null}
              </div>
              {!showDevLogin ? (
                <div className="status status-warn">
                  Dev login is disabled in the frontend build. Set `NEXT_PUBLIC_ENABLE_DEV_AUTH=true` in
                  `frontend/.env.local`. (Backend dev login is enabled by default in `ENVIRONMENT=development`;
                  set `ENABLE_DEV_AUTH=true` only if you turned it off.)
                </div>
              ) : (
                <>
                  <div className="demoList">
                    {demoDoctors.map((doc) => (
                      <button
                        key={doc.email}
                        type="button"
                        className="demoCard"
                        onClick={() => {
                          setError("");
                          void loginDev(doc.email)
                            .then(() => router.push("/patients"))
                            .catch((e) => setError(e instanceof Error ? e.message : "Login failed"));
                        }}
                      >
                        <div className="demoName">{doc.name}</div>
                        <div className="demoEmail">{doc.email}</div>
                      </button>
                    ))}
                  </div>

                  <form onSubmit={handleCustom} className="stack">
                    <Field label="Custom demo email" hint="Stored only in your local DB">
                      <Input value={customEmail} onChange={(e) => setCustomEmail(e.target.value)} />
                    </Field>
                    <Button type="submit">Login</Button>
                  </form>
                </>
              )}

              {error ? <div className="status status-danger">{error}</div> : null}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="What you can demo" subtitle="A clean end-to-end flow in minutes." />
          <div className="stack">
            <div className="checkRow">
              <span className="checkDot" />
              Create and manage patients
            </div>
            <div className="checkRow">
              <span className="checkDot" />
              Run Stage 1 clinical assessment
            </div>
            <div className="checkRow">
              <span className="checkDot" />
              Upload a scan locally + run Stage 2 inference
            </div>
            <div className="checkRow">
              <span className="checkDot" />
              Generate a report PDF and open it in-browser
            </div>
            <div className="checkRow">
              <span className="checkDot" />
              Review the patient timeline
            </div>
          </div>
        </Card>
      </div>
    </main>
  );
}
