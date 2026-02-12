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
  report_json: ReportPayload;
  created_at: string;
};

type ReportPayload = {
  executive_summary?: {
    overall_posture?: string;
    stage1_risk_tier?: string;
    stage2_top_stage?: string;
    stage3_status?: string;
    stage3_risk_tier?: string;
    stage3_composite_risk_score?: number;
    active_alert_count?: number;
  };
  integrated_assessment?: {
    concordance_summary?: string;
    key_drivers?: string[];
    recommended_actions?: string[];
  };
  stage_availability?: {
    stage1?: { status?: string; reason?: string };
    stage2?: { status?: string; reason?: string };
    stage3?: { status?: string; reason?: string };
  };
  report_meta?: {
    generated_at_utc?: string;
    monitoring_cadence_weeks?: number;
  };
  [key: string]: unknown;
};

function pct(value: number | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "N/A";
  return `${(value * 100).toFixed(1)}%`;
}

export default function ReportsPage() {
  const { csrfToken, csrfHeaderName } = useSession();
  const { activePatientId } = useActivePatientId();

  const [patientId, setPatientId] = useState("");
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (activePatientId) setPatientId(activePatientId);
  }, [activePatientId]);

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
              {report.report_json?.executive_summary?.overall_posture ? (
                <Pill tone="neutral">Overall {report.report_json.executive_summary.overall_posture}</Pill>
              ) : null}
              {report.pdf_download_url ? (
                <a className="link" href={report.pdf_download_url} target="_blank" rel="noreferrer">
                  Open PDF
                </a>
              ) : (
                <Pill tone="warn">No PDF URL</Pill>
              )}
            </div>

            <div className="riskMetricGrid">
              <div className="riskMetric">
                <div className="riskMetricLabel">Stage 1</div>
                <div className="riskMetricValue">{report.report_json.executive_summary?.stage1_risk_tier || "N/A"}</div>
              </div>
              <div className="riskMetric">
                <div className="riskMetricLabel">Stage 2</div>
                <div className="riskMetricValue">{report.report_json.executive_summary?.stage2_top_stage || "N/A"}</div>
              </div>
              <div className="riskMetric">
                <div className="riskMetricLabel">Stage 3</div>
                <div className="riskMetricValue">{report.report_json.executive_summary?.stage3_risk_tier || "N/A"}</div>
              </div>
              <div className="riskMetric">
                <div className="riskMetricLabel">Stage 3 Composite</div>
                <div className="riskMetricValue">{pct(report.report_json.executive_summary?.stage3_composite_risk_score)}</div>
              </div>
              <div className="riskMetric">
                <div className="riskMetricLabel">Open Alerts</div>
                <div className="riskMetricValue">{report.report_json.executive_summary?.active_alert_count ?? 0}</div>
              </div>
              <div className="riskMetric">
                <div className="riskMetricLabel">Monitoring Cadence</div>
                <div className="riskMetricValue">
                  {report.report_json.report_meta?.monitoring_cadence_weeks
                    ? `${report.report_json.report_meta.monitoring_cadence_weeks} weeks`
                    : "N/A"}
                </div>
              </div>
            </div>

            <div className="block">
              <div className="blockTitle">Integrated Assessment</div>
              <div className="blockBody">{report.report_json.integrated_assessment?.concordance_summary || "N/A"}</div>
              {(report.report_json.integrated_assessment?.key_drivers || []).length ? (
                <div className="reportList">
                  {(report.report_json.integrated_assessment?.key_drivers || []).map((driver) => (
                    <div className="reportListItem" key={driver}>{driver}</div>
                  ))}
                </div>
              ) : null}
              {(report.report_json.integrated_assessment?.recommended_actions || []).length ? (
                <>
                  <div className="xaiTitle">Recommended Next Actions</div>
                  <div className="reportList">
                    {(report.report_json.integrated_assessment?.recommended_actions || []).map((action) => (
                      <div className="reportListItem" key={action}>{action}</div>
                    ))}
                  </div>
                </>
              ) : null}
            </div>

            <div className="reportAvailabilityTable">
              <div className="reportAvailabilityHead">
                <span>Stage</span>
                <span>Status</span>
                <span>Reason</span>
              </div>
              {(["stage1", "stage2", "stage3"] as const).map((key) => {
                const item = report.report_json.stage_availability?.[key];
                return (
                  <div key={key} className="reportAvailabilityRow">
                    <span>{key.toUpperCase()}</span>
                    <span>{item?.status || "N/A"}</span>
                    <span>{item?.reason || "N/A"}</span>
                  </div>
                );
              })}
            </div>

            <details className="jsonDetails">
              <summary>Raw report payload</summary>
              <pre className="json">{JSON.stringify(report.report_json, null, 2)}</pre>
            </details>
          </div>
        ) : (
          <div className="empty">Generate a report to see the JSON + PDF link.</div>
        )}
      </Card>
    </div>
  );
}
