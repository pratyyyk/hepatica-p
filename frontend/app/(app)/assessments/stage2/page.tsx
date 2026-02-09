"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { InlineStatus } from "@/components/Timeline";
import { Button, Card, CardHeader, Field, Input, Pill } from "@/components/ui";
import { apiFetch, uploadFileToUrl } from "@/lib/api";
import { useActivePatientId } from "@/lib/activePatient";
import { useSession } from "@/lib/session";

type UploadTicket = {
  scan_asset_id: string;
  object_key: string;
  upload_url: string;
  expires_in_seconds: number;
};

type FibrosisTop = { stage: string; probability: number };
type FibrosisResponse = {
  prediction_id: string;
  patient_id: string;
  scan_asset_id: string;
  model_version: string;
  softmax_vector: Record<string, number>;
  top1: FibrosisTop;
  top2: FibrosisTop[];
  confidence_flag: string;
  escalation_flag: string;
  quality_metrics: Record<string, unknown>;
  created_at: string;
};

type KnowledgeResponse = {
  patient_id: string;
  blocks: { title: string; content: string; citations: unknown[] }[];
};

type ReportResponse = {
  report_id: string;
  patient_id: string;
  pdf_download_url: string | null;
  report_json: Record<string, unknown>;
  created_at: string;
};

export default function Stage2Page() {
  const { csrfToken, csrfHeaderName } = useSession();
  const { activePatientId } = useActivePatientId();

  const [patientId, setPatientId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [scanAssetId, setScanAssetId] = useState("");

  const [ticket, setTicket] = useState<UploadTicket | null>(null);
  const [fibrosis, setFibrosis] = useState<FibrosisResponse | null>(null);
  const [knowledge, setKnowledge] = useState<KnowledgeResponse | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (activePatientId && !patientId) setPatientId(activePatientId);
  }, [activePatientId, patientId]);

  const topStage = useMemo(() => fibrosis?.top1?.stage, [fibrosis]);

  async function requestUploadUrl(e: FormEvent) {
    e.preventDefault();
    if (!patientId || !file) return;
    setBusy(true);
    setError("");
    setStatus("Requesting upload URL...");
    try {
      const t = await apiFetch<UploadTicket>("/api/v1/scans/upload-url", {
        method: "POST",
        body: {
          patient_id: patientId,
          filename: file.name,
          content_type: file.type || "image/jpeg",
          byte_size: file.size,
        },
        csrfToken,
        csrfHeaderName,
      });
      setTicket(t);
      setScanAssetId(t.scan_asset_id);
      setStatus("Uploading scan...");

      await uploadFileToUrl({
        uploadUrl: t.upload_url,
        file,
        csrfToken,
        csrfHeaderName,
      });

      setStatus("Upload complete");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  async function runStage2() {
    if (!patientId || !scanAssetId) return;
    setBusy(true);
    setError("");
    setStatus("Running Stage 2 inference...");
    try {
      const out = await apiFetch<FibrosisResponse>("/api/v1/assessments/fibrosis", {
        method: "POST",
        body: { patient_id: patientId, scan_asset_id: scanAssetId },
        csrfToken,
        csrfHeaderName,
      });
      setFibrosis(out);
      setStatus("Stage 2 complete");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stage 2 failed");
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  async function generateKnowledge() {
    if (!patientId) return;
    setBusy(true);
    setError("");
    setStatus("Generating knowledge blocks...");
    try {
      const out = await apiFetch<KnowledgeResponse>("/api/v1/knowledge/explain", {
        method: "POST",
        body: { patient_id: patientId, fibrosis_stage: topStage, top_k: 5 },
        csrfToken,
        csrfHeaderName,
      });
      setKnowledge(out);
      setStatus("Knowledge ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Knowledge failed");
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  async function generateReport() {
    if (!patientId) return;
    setBusy(true);
    setError("");
    setStatus("Generating report PDF...");
    try {
      const out = await apiFetch<ReportResponse>("/api/v1/reports", {
        method: "POST",
        body: { patient_id: patientId },
        csrfToken,
        csrfHeaderName,
      });
      setReport(out);
      setStatus("Report ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report failed");
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid2">
      <Card className="fadeIn">
        <CardHeader title="Stage 2 Scan" subtitle="Local upload + fibrosis inference." />
        <form className="stack" onSubmit={requestUploadUrl}>
          <Field label="Patient ID">
            <Input value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="UUID" />
          </Field>

          <Field label="Scan file" hint="JPG/PNG (DICOM accepted)">
            <Input
              type="file"
              accept="image/png,image/jpeg,application/dicom,application/dicom+json"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </Field>

          <div className="row">
            <Button type="submit" disabled={!patientId || !file || busy}>
              {busy ? "Working..." : "Upload Scan"}
            </Button>
            <Button type="button" tone="secondary" disabled={!scanAssetId || busy} onClick={() => void runStage2()}>
              Run Stage 2
            </Button>
          </div>

          {scanAssetId ? (
            <div className="row">
              <Pill tone="ok">scan_asset_id: {scanAssetId}</Pill>
              {ticket?.expires_in_seconds ? <Pill tone="neutral">TTL {ticket.expires_in_seconds}s</Pill> : null}
            </div>
          ) : null}

          {status ? <InlineStatus tone="ok">{status}</InlineStatus> : null}
          {error ? <InlineStatus tone="danger">{error}</InlineStatus> : null}
        </form>
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "80ms" }}>
        <CardHeader title="Inference Output" subtitle="Top stage + flags + softmax." />
        {fibrosis ? (
          <div className="stack">
            <div className="row">
              <Pill tone={fibrosis.confidence_flag === "LOW_CONFIDENCE" ? "warn" : "ok"}>
                {fibrosis.top1.stage} ({fibrosis.top1.probability})
              </Pill>
              <Pill tone={fibrosis.escalation_flag === "NONE" ? "neutral" : "danger"}>{fibrosis.escalation_flag}</Pill>
              <Pill tone="neutral">{fibrosis.model_version}</Pill>
            </div>
            <pre className="json">{JSON.stringify(fibrosis, null, 2)}</pre>
            <div className="row">
              <Button tone="secondary" onClick={() => void generateKnowledge()} disabled={busy}>
                Generate Knowledge
              </Button>
              <Button tone="primary" onClick={() => void generateReport()} disabled={busy}>
                Generate Report PDF
              </Button>
            </div>
          </div>
        ) : (
          <div className="empty">Upload a scan, then run Stage 2.</div>
        )}
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "140ms" }}>
        <CardHeader title="Knowledge" subtitle="RAG-style blocks (local fallback embeddings ok)." />
        {knowledge ? (
          <div className="stack">
            {knowledge.blocks.map((b) => (
              <div key={b.title} className="block">
                <div className="blockTitle">{b.title}</div>
                <div className="blockBody">{b.content}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">Generate knowledge to see clinical guidance blocks.</div>
        )}
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "200ms" }}>
        <CardHeader title="Report PDF" subtitle="Opens via backend endpoint in local mode." />
        {report ? (
          <div className="stack">
            <div className="row">
              <Pill tone="ok">Report: {report.report_id}</Pill>
              {report.pdf_download_url ? (
                <a className="link" href={report.pdf_download_url} target="_blank" rel="noreferrer">
                  Open PDF
                </a>
              ) : (
                <Pill tone="warn">No PDF URL</Pill>
              )}
            </div>
            <pre className="json">{JSON.stringify(report.report_json, null, 2)}</pre>
          </div>
        ) : (
          <div className="empty">Generate a report to get a PDF link.</div>
        )}
      </Card>
    </div>
  );
}

