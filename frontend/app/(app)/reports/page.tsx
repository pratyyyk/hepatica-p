"use client";

import { FormEvent, useEffect, useState } from "react";

import { InlineStatus } from "@/components/Timeline";
import { Button, Card, CardHeader, Field, Input, Pill } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useActivePatientId } from "@/lib/activePatient";
import { useSession } from "@/lib/session";

type ReportResponse = {
  report_id: string;
  patient_id: string;
  pdf_download_url: string | null;
  report_json: Record<string, unknown>;
  created_at: string;
};

export default function ReportsPage() {
  const { csrfToken, csrfHeaderName } = useSession();
  const { activePatientId } = useActivePatientId();

  const [patientId, setPatientId] = useState("");
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (activePatientId && !patientId) setPatientId(activePatientId);
  }, [activePatientId, patientId]);

  async function generate(e: FormEvent) {
    e.preventDefault();
    if (!patientId) return;
    setBusy(true);
    setError("");
    setStatus("Generating report...");
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
      setError(err instanceof Error ? err.message : "Report generation failed");
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid2">
      <Card className="fadeIn">
        <CardHeader title="Generate Report" subtitle="Creates PDF + JSON payload." />
        <form className="stack" onSubmit={generate}>
          <Field label="Patient ID">
            <Input value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="UUID" />
          </Field>
          <div className="row">
            <Button type="submit" disabled={!patientId || busy}>
              {busy ? "Working..." : "Generate"}
            </Button>
          </div>
          {status ? <InlineStatus tone="ok">{status}</InlineStatus> : null}
          {error ? <InlineStatus tone="danger">{error}</InlineStatus> : null}
        </form>
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "80ms" }}>
        <CardHeader title="Latest Output" subtitle="Open PDF in a new tab." />
        {report ? (
          <div className="stack">
            <div className="row">
              <Pill tone="ok">{report.report_id}</Pill>
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
          <div className="empty">Generate a report to see the JSON + PDF link.</div>
        )}
      </Card>
    </div>
  );
}

