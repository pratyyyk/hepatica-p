"use client";

import { FormEvent, useMemo, useState } from "react";

type ApiObj = Record<string, unknown>;

const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function callApi<T>(
  path: string,
  method: "GET" | "POST",
  email: string,
  payload?: ApiObj,
): Promise<T> {
  const res = await fetch(`${apiBase}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "x-user-email": email,
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }
  return (await res.json()) as T;
}

export default function HomePage() {
  const [email, setEmail] = useState("doctor@example.com");
  const [authReady, setAuthReady] = useState(false);
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

  async function guarded<T>(fn: () => Promise<T>) {
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      throw e;
    }
  }

  async function handleDevLogin(e: FormEvent) {
    e.preventDefault();
    setStatus("Authenticating...");
    await guarded(async () => {
      await fetch(`${apiBase}/api/v1/auth/dev-login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      setAuthReady(true);
      setStatus("Authenticated as DOCTOR (dev mode)");
    });
  }

  async function createPatient(e: FormEvent) {
    e.preventDefault();
    if (!authReady) return;
    setStatus("Creating patient...");
    const patient = await guarded(() =>
      callApi<ApiObj>("/api/v1/patients", "POST", email, patientForm),
    );
    setPatientResp(patient);
    setActivePatientId(String(patient.id));
    setStatus("Patient created");
  }

  async function loadPatientById() {
    if (!activePatientId) return;
    setStatus("Loading patient...");
    const patient = await guarded(() =>
      callApi<ApiObj>(`/api/v1/patients/${activePatientId}`, "GET", email),
    );
    setPatientResp(patient);
    setStatus("Patient loaded");
  }

  async function runClinical(e: FormEvent) {
    e.preventDefault();
    if (!activePatientId) return;
    setStatus("Running Stage 1 clinical assessment...");
    const payload = { ...clinicalForm, patient_id: activePatientId };
    const out = await guarded(() =>
      callApi<ApiObj>("/api/v1/assessments/clinical", "POST", email, payload),
    );
    setClinicalResp(out);
    setStatus("Stage 1 completed");
  }

  async function createUploadAndUploadFile() {
    if (!activePatientId || !uploadFile) return;
    setStatus("Requesting upload URL...");

    const ticket = await guarded(() =>
      callApi<ApiObj>("/api/v1/scans/upload-url", "POST", email, {
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
    if (!activePatientId || !scanAssetId) return;
    setStatus("Running Stage 2 fibrosis inference...");
    const out = await guarded(() =>
      callApi<ApiObj>("/api/v1/assessments/fibrosis", "POST", email, {
        patient_id: activePatientId,
        scan_asset_id: scanAssetId,
      }),
    );
    setFibrosisResp(out);
    setStatus("Stage 2 completed");
  }

  async function generateKnowledge() {
    if (!activePatientId) return;
    setStatus("Generating knowledge blocks...");
    const out = await guarded(() =>
      callApi<ApiObj>("/api/v1/knowledge/explain", "POST", email, {
        patient_id: activePatientId,
        fibrosis_stage: topStage,
        top_k: 5,
      }),
    );
    setKnowledgeResp(out);
    setStatus("Knowledge blocks ready");
  }

  async function generateReport() {
    if (!activePatientId) return;
    setStatus("Generating report PDF...");
    const out = await guarded(() =>
      callApi<ApiObj>("/api/v1/reports", "POST", email, {
        patient_id: activePatientId,
      }),
    );
    setReportResp(out);
    setStatus("Report generated");
  }

  async function loadTimeline() {
    if (!activePatientId) return;
    setStatus("Loading timeline...");
    const out = await guarded(() =>
      callApi<ApiObj>(`/api/v1/patients/${activePatientId}/timeline`, "GET", email),
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
        {activePatientId && <span className="pill">Patient: {activePatientId}</span>}
      </div>

      <div className="grid">
        <section className="card">
          <h2>Authentication</h2>
          <form onSubmit={handleDevLogin}>
            <div className="field">
              <label>Email</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <button type="submit">Dev Login</button>
          </form>
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
            <button type="submit" disabled={!activePatientId}>
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
              accept="image/png,image/jpeg"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            />
          </div>
          <div className="row">
            <button
              type="button"
              onClick={() => guarded(createUploadAndUploadFile)}
              disabled={!activePatientId || !uploadFile}
            >
              Upload Scan
            </button>
            <button
              type="button"
              className="warn"
              onClick={() => guarded(runFibrosis)}
              disabled={!scanAssetId}
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
            <button type="button" onClick={() => guarded(generateKnowledge)} disabled={!activePatientId}>
              Generate Knowledge
            </button>
            <button type="button" className="secondary" onClick={() => guarded(generateReport)} disabled={!activePatientId}>
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
          <button type="button" onClick={() => guarded(loadTimeline)} disabled={!activePatientId}>
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
