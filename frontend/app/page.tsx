"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type ApiObj = Record<string, unknown>;

interface AuthSession {
  authenticated: boolean;
  user_id: string;
  email: string;
  role: string;
  csrf_token: string | null;
  csrf_header_name: string;
}

const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const authProvider = (process.env.NEXT_PUBLIC_AUTH_PROVIDER || "firebase").toLowerCase();
const showDevLogin = process.env.NEXT_PUBLIC_ENABLE_DEV_AUTH === "true";

export default function HomePage() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);

  const [devEmail, setDevEmail] = useState("doctor@example.com");
  const [firebaseEmail, setFirebaseEmail] = useState("");
  const [firebasePassword, setFirebasePassword] = useState("");
  const [activePatientId, setActivePatientId] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [scanAssetId, setScanAssetId] = useState("");

  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const [patientResp, setPatientResp] = useState<ApiObj | null>(null);
  const [clinicalResp, setClinicalResp] = useState<ApiObj | null>(null);
  const [fibrosisResp, setFibrosisResp] = useState<ApiObj | null>(null);
  const [knowledgeResp, setKnowledgeResp] = useState<ApiObj | null>(null);
  const [reportResp, setReportResp] = useState<ApiObj | null>(null);
  const [timelineResp, setTimelineResp] = useState<ApiObj | null>(null);

  const [patientForm, setPatientForm] = useState({
    external_id: "",
    sex: "F",
    age: 45,
    bmi: 28,
    type2dm: false,
    notes: "",
  });

  const [clinicalForm, setClinicalForm] = useState({
    ast: 70,
    alt: 50,
    platelets: 150,
    ast_uln: 40,
    age: 45,
    bmi: 28,
    type2dm: false,
  });

  const topStage = useMemo(() => {
    const top = fibrosisResp?.top1 as ApiObj | undefined;
    return (top?.stage as string | undefined) || undefined;
  }, [fibrosisResp]);

  const authReady = !!session?.authenticated;

  async function bootstrapSession() {
    setSessionLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/auth/session`, {
        method: "GET",
        credentials: "include",
      });
      if (!res.ok) {
        setSession(null);
        return;
      }
      const payload = (await res.json()) as AuthSession;
      setSession(payload);
      setStatus(`Authenticated as ${payload.email}`);
    } catch {
      setSession(null);
    } finally {
      setSessionLoading(false);
    }
  }

  useEffect(() => {
    void bootstrapSession();
  }, []);

  async function apiCall<T>(
    path: string,
    method: "GET" | "POST",
    payload?: ApiObj,
  ): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (method !== "GET" && session?.csrf_token) {
      headers[session.csrf_header_name] = session.csrf_token;
    }

    const res = await fetch(`${apiBase}${path}`, {
      method,
      credentials: "include",
      headers,
      body: payload ? JSON.stringify(payload) : undefined,
    });

    if (res.status === 401) {
      setSession(null);
      throw new Error("Authentication required. Please sign in again.");
    }

    if (!res.ok) {
      throw new Error(await res.text());
    }

    return (await res.json()) as T;
  }

  async function guarded<T>(fn: () => Promise<T>) {
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      throw e;
    }
  }

  function startCognitoLogin() {
    window.location.href = `${apiBase}/api/v1/auth/login`;
  }

  async function handleFirebaseLogin(e: FormEvent) {
    e.preventDefault();
    setStatus("Authenticating with Firebase...");
    await guarded(async () => {
      const res = await fetch(`${apiBase}/api/v1/auth/firebase-login`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email: firebaseEmail, password: firebasePassword }),
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      await bootstrapSession();
    });
  }

  async function handleDevLogin(e: FormEvent) {
    e.preventDefault();
    if (!showDevLogin) return;

    setStatus("Authenticating via local dev login...");
    await guarded(async () => {
      const res = await fetch(`${apiBase}/api/v1/auth/dev-login`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email: devEmail }),
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      await bootstrapSession();
    });
  }

  async function handleLogout() {
    setStatus("Logging out...");
    await guarded(async () => {
      await apiCall<{ ok: boolean; message: string }>("/api/v1/auth/logout", "POST", {});
      setSession(null);
      setActivePatientId("");
      setScanAssetId("");
      setStatus("Logged out");
    });
  }

  async function createPatient(e: FormEvent) {
    e.preventDefault();
    if (!authReady) return;
    setStatus("Creating patient...");
    const patient = await guarded(() =>
      apiCall<ApiObj>("/api/v1/patients", "POST", patientForm),
    );
    setPatientResp(patient);
    setActivePatientId(String(patient.id));
    setStatus("Patient created");
  }

  async function loadPatientById() {
    if (!activePatientId || !authReady) return;
    setStatus("Loading patient...");
    const patient = await guarded(() =>
      apiCall<ApiObj>(`/api/v1/patients/${activePatientId}`, "GET"),
    );
    setPatientResp(patient);
    setStatus("Patient loaded");
  }

  async function runClinical(e: FormEvent) {
    e.preventDefault();
    if (!activePatientId || !authReady) return;
    setStatus("Running Stage 1 clinical assessment...");
    const payload = { ...clinicalForm, patient_id: activePatientId };
    const out = await guarded(() =>
      apiCall<ApiObj>("/api/v1/assessments/clinical", "POST", payload),
    );
    setClinicalResp(out);
    setStatus("Stage 1 completed");
  }

  async function createUploadAndUploadFile() {
    if (!activePatientId || !uploadFile || !authReady) return;
    setStatus("Requesting upload URL...");

    const ticket = await guarded(() =>
      apiCall<ApiObj>("/api/v1/scans/upload-url", "POST", {
        patient_id: activePatientId,
        filename: uploadFile.name,
        content_type: uploadFile.type || "image/jpeg",
        byte_size: uploadFile.size,
      }),
    );

    const uploadUrl = String(ticket.upload_url);
    setScanAssetId(String(ticket.scan_asset_id));

    setStatus("Uploading file to object storage...");
    const putResp = await fetch(uploadUrl, {
      method: "PUT",
      headers: {
        "Content-Type": uploadFile.type || "image/jpeg",
      },
      body: uploadFile,
    });

    if (!putResp.ok) {
      throw new Error(`Upload failed (${putResp.status})`);
    }
    setStatus("Upload completed");
  }

  async function runFibrosis() {
    if (!activePatientId || !scanAssetId || !authReady) return;
    setStatus("Running Stage 2 fibrosis inference...");
    const out = await guarded(() =>
      apiCall<ApiObj>("/api/v1/assessments/fibrosis", "POST", {
        patient_id: activePatientId,
        scan_asset_id: scanAssetId,
      }),
    );
    setFibrosisResp(out);
    setStatus("Stage 2 completed");
  }

  async function generateKnowledge() {
    if (!activePatientId || !authReady) return;
    setStatus("Generating knowledge blocks...");
    const out = await guarded(() =>
      apiCall<ApiObj>("/api/v1/knowledge/explain", "POST", {
        patient_id: activePatientId,
        fibrosis_stage: topStage,
        top_k: 5,
      }),
    );
    setKnowledgeResp(out);
    setStatus("Knowledge blocks ready");
  }

  async function generateReport() {
    if (!activePatientId || !authReady) return;
    setStatus("Generating report PDF...");
    const out = await guarded(() =>
      apiCall<ApiObj>("/api/v1/reports", "POST", {
        patient_id: activePatientId,
      }),
    );
    setReportResp(out);
    setStatus("Report generated");
  }

  async function loadTimeline() {
    if (!activePatientId || !authReady) return;
    setStatus("Loading timeline...");
    const out = await guarded(() =>
      apiCall<ApiObj>(`/api/v1/patients/${activePatientId}/timeline`, "GET"),
    );
    setTimelineResp(out);
    setStatus("Timeline loaded");
  }

  return (
    <main>
      <h1>Hepatica Doctor Dashboard</h1>
      <p>Stage 1 risk triage + Stage 2 fibrosis assessment + report + timeline</p>

      <div className="row" style={{ marginTop: 12 }}>
        <span className="pill">Role: DOCTOR</span>
        <span className="pill">API: {apiBase}</span>
        {session?.email && <span className="pill">User: {session.email}</span>}
        {activePatientId && <span className="pill">Patient: {activePatientId}</span>}
      </div>

      <div className="grid">
        <section className="card">
          <h2>Authentication</h2>
          {sessionLoading ? (
            <p>Checking session...</p>
          ) : authReady ? (
            <>
              <p>Authenticated session is active.</p>
              <div className="row" style={{ marginTop: 10 }}>
                <button type="button" onClick={handleLogout}>
                  Logout
                </button>
              </div>
            </>
          ) : (
            <>
              {authProvider === "cognito" ? (
                <>
                  <p>Sign in using Cognito Hosted UI.</p>
                  <div className="row" style={{ marginTop: 10 }}>
                    <button type="button" onClick={startCognitoLogin}>
                      Sign in with Cognito
                    </button>
                  </div>
                </>
              ) : (
                <form onSubmit={handleFirebaseLogin}>
                  <p>Sign in using Firebase credentials.</p>
                  <div className="field">
                    <label>Email</label>
                    <input
                      type="email"
                      value={firebaseEmail}
                      onChange={(e) => setFirebaseEmail(e.target.value)}
                      required
                    />
                  </div>
                  <div className="field">
                    <label>Password</label>
                    <input
                      type="password"
                      value={firebasePassword}
                      onChange={(e) => setFirebasePassword(e.target.value)}
                      required
                    />
                  </div>
                  <button type="submit">Sign in with Firebase</button>
                </form>
              )}
              {showDevLogin && (
                <form onSubmit={handleDevLogin} style={{ marginTop: 12 }}>
                  <div className="field">
                    <label>Local Dev Email</label>
                    <input
                      value={devEmail}
                      onChange={(e) => setDevEmail(e.target.value)}
                      required
                    />
                  </div>
                  <button type="submit" className="secondary">
                    Dev Login (Local Only)
                  </button>
                </form>
              )}
            </>
          )}
        </section>

        <section className="card">
          <h2>Patient</h2>
          <form onSubmit={createPatient}>
            <div className="field">
              <label>External ID</label>
              <input
                value={patientForm.external_id}
                onChange={(e) => setPatientForm({ ...patientForm, external_id: e.target.value })}
                required
              />
            </div>
            <div className="row">
              <div className="field" style={{ flex: 1 }}>
                <label>Sex</label>
                <select
                  value={patientForm.sex}
                  onChange={(e) => setPatientForm({ ...patientForm, sex: e.target.value })}
                >
                  <option>F</option>
                  <option>M</option>
                </select>
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Age</label>
                <input
                  type="number"
                  value={patientForm.age}
                  onChange={(e) => setPatientForm({ ...patientForm, age: Number(e.target.value) })}
                />
              </div>
            </div>
            <div className="field">
              <label>BMI</label>
              <input
                type="number"
                step="0.1"
                value={patientForm.bmi}
                onChange={(e) => setPatientForm({ ...patientForm, bmi: Number(e.target.value) })}
              />
            </div>
            <div className="row">
              <button type="submit" disabled={!authReady}>
                Create Patient
              </button>
              <button
                className="secondary"
                type="button"
                onClick={loadPatientById}
                disabled={!authReady || !activePatientId}
              >
                Load by Patient ID
              </button>
            </div>
          </form>
          {patientResp && <pre>{JSON.stringify(patientResp, null, 2)}</pre>}
        </section>

        <section className="card">
          <h2>Stage 1: Clinical Risk</h2>
          <form onSubmit={runClinical}>
            <div className="row">
              <div className="field" style={{ flex: 1 }}>
                <label>AST</label>
                <input
                  type="number"
                  value={clinicalForm.ast}
                  onChange={(e) => setClinicalForm({ ...clinicalForm, ast: Number(e.target.value) })}
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>ALT</label>
                <input
                  type="number"
                  value={clinicalForm.alt}
                  onChange={(e) => setClinicalForm({ ...clinicalForm, alt: Number(e.target.value) })}
                />
              </div>
            </div>
            <div className="row">
              <div className="field" style={{ flex: 1 }}>
                <label>Platelets</label>
                <input
                  type="number"
                  value={clinicalForm.platelets}
                  onChange={(e) =>
                    setClinicalForm({ ...clinicalForm, platelets: Number(e.target.value) })
                  }
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>AST ULN</label>
                <input
                  type="number"
                  value={clinicalForm.ast_uln}
                  onChange={(e) => setClinicalForm({ ...clinicalForm, ast_uln: Number(e.target.value) })}
                />
              </div>
            </div>
            <div className="row">
              <div className="field" style={{ flex: 1 }}>
                <label>Age</label>
                <input
                  type="number"
                  value={clinicalForm.age}
                  onChange={(e) => setClinicalForm({ ...clinicalForm, age: Number(e.target.value) })}
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>BMI</label>
                <input
                  type="number"
                  step="0.1"
                  value={clinicalForm.bmi}
                  onChange={(e) => setClinicalForm({ ...clinicalForm, bmi: Number(e.target.value) })}
                />
              </div>
            </div>
            <button type="submit" disabled={!activePatientId || !authReady}>
              Run Stage 1
            </button>
          </form>
          {clinicalResp && <pre>{JSON.stringify(clinicalResp, null, 2)}</pre>}
        </section>

        <section className="card">
          <h2>Stage 2: Upload + Fibrosis</h2>
          <div className="field">
            <label>Scan File (JPG/PNG)</label>
            <input
              type="file"
              accept="image/png,image/jpeg,application/dicom"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            />
          </div>
          <div className="row">
            <button
              type="button"
              onClick={() => guarded(createUploadAndUploadFile)}
              disabled={!activePatientId || !uploadFile || !authReady}
            >
              Upload Scan
            </button>
            <button
              type="button"
              className="warn"
              onClick={() => guarded(runFibrosis)}
              disabled={!scanAssetId || !authReady}
            >
              Run Stage 2
            </button>
          </div>
          {scanAssetId && <p style={{ marginTop: 8 }}>scan_asset_id: {scanAssetId}</p>}
          {fibrosisResp && <pre>{JSON.stringify(fibrosisResp, null, 2)}</pre>}
        </section>

        <section className="card">
          <h2>Knowledge + Report</h2>
          <div className="row">
            <button
              type="button"
              onClick={() => guarded(generateKnowledge)}
              disabled={!activePatientId || !authReady}
            >
              Generate Knowledge
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => guarded(generateReport)}
              disabled={!activePatientId || !authReady}
            >
              Generate Report PDF
            </button>
          </div>
          {knowledgeResp && <pre>{JSON.stringify(knowledgeResp, null, 2)}</pre>}
          {reportResp && (
            <div className="result">
              <strong>Report Ready</strong>
              <pre>{JSON.stringify(reportResp, null, 2)}</pre>
              {(reportResp.pdf_download_url as string | undefined) && (
                <a href={String(reportResp.pdf_download_url)} target="_blank">
                  Open PDF
                </a>
              )}
            </div>
          )}
        </section>

        <section className="card">
          <h2>Timeline</h2>
          <button type="button" onClick={() => guarded(loadTimeline)} disabled={!activePatientId || !authReady}>
            Refresh Timeline
          </button>
          {timelineResp && <pre>{JSON.stringify(timelineResp, null, 2)}</pre>}
        </section>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <strong>Status:</strong> {status || "Idle"}
        {error && <small className="error">{error}</small>}
      </div>
    </main>
  );
}
