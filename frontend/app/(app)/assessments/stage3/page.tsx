"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { InlineStatus } from "@/components/Timeline";
import { Button, Card, CardHeader, Field, Input, Pill } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useActivePatientId } from "@/lib/activePatient";
import { useSession } from "@/lib/session";

type StiffnessResponse = {
  id: string;
  patient_id: string;
  measured_kpa: number;
  cap_dbm: number | null;
  source: string;
  measured_at: string;
  created_at: string;
};

type Stage3Assessment = {
  id: string;
  patient_id: string;
  stiffness_measurement_id: string | null;
  composite_risk_score: number;
  progression_risk_12m: number;
  decomp_risk_12m: number;
  risk_tier: "LOW" | "MODERATE" | "HIGH" | "CRITICAL";
  model_version: string;
  feature_snapshot_json: Record<string, unknown>;
  created_at: string;
};

type Stage3Explainability = {
  patient_id: string;
  stage3_assessment_id: string;
  local_feature_contrib_json: {
    positive?: { feature: string; contribution: number }[];
    negative?: { feature: string; contribution: number }[];
    raw_components?: Record<string, number>;
  };
  global_reference_version: string;
  trend_points_json: {
    visit_index: number;
    assessment_id?: string;
    score: number;
    risk_tier: string;
    alert_state: string;
    created_at: string;
  }[];
};

type AlertItem = {
  id: string;
  alert_type: string;
  severity: string;
  status: string;
  threshold: number;
  score: number;
  created_at: string;
};

type AlertResponse = {
  patient_id: string;
  alerts: AlertItem[];
};

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

function toneFromTier(tier: Stage3Assessment["risk_tier"] | undefined): "neutral" | "ok" | "warn" | "danger" {
  if (tier === "CRITICAL") return "danger";
  if (tier === "HIGH") return "warn";
  if (tier === "MODERATE") return "neutral";
  return "ok";
}

export default function Stage3Page() {
  const { csrfToken, csrfHeaderName } = useSession();
  const { activePatientId } = useActivePatientId();

  const [patientId, setPatientId] = useState("");
  const [kpa, setKpa] = useState("18.5");
  const [cap, setCap] = useState("280");
  const [stiffness, setStiffness] = useState<StiffnessResponse | null>(null);
  const [assessment, setAssessment] = useState<Stage3Assessment | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [explain, setExplain] = useState<Stage3Explainability | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (activePatientId && !patientId) setPatientId(activePatientId);
  }, [activePatientId, patientId]);

  const positiveContribs = useMemo(() => explain?.local_feature_contrib_json.positive || [], [explain]);
  const negativeContribs = useMemo(() => explain?.local_feature_contrib_json.negative || [], [explain]);

  async function refreshExtras(pid: string, stage3AssessmentId?: string) {
    const [alertOut, explainOut] = await Promise.all([
      apiFetch<AlertResponse>(`/api/v1/patients/${pid}/alerts`),
      apiFetch<Stage3Explainability>(
        `/api/v1/patients/${pid}/stage3/explainability${stage3AssessmentId ? `?stage3_assessment_id=${stage3AssessmentId}` : ""}`,
      ),
    ]);
    setAlerts(alertOut.alerts || []);
    setExplain(explainOut);
  }

  async function saveStiffness(e: FormEvent) {
    e.preventDefault();
    if (!patientId) return;
    setBusy(true);
    setError("");
    setStatus("Saving liver stiffness...");
    try {
      const out = await apiFetch<StiffnessResponse>(`/api/v1/patients/${patientId}/stiffness`, {
        method: "POST",
        body: {
          measured_kpa: Number(kpa),
          cap_dbm: cap ? Number(cap) : null,
          source: "MEASURED",
        },
        csrfToken,
        csrfHeaderName,
      });
      setStiffness(out);
      setStatus("Stiffness saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save stiffness");
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  async function runStage3() {
    if (!patientId) return;
    setBusy(true);
    setError("");
    setStatus("Running Stage 3 risk model...");
    try {
      const out = await apiFetch<Stage3Assessment>("/api/v1/assessments/stage3", {
        method: "POST",
        body: {
          patient_id: patientId,
          stiffness_measurement_id: stiffness?.id || undefined,
        },
        csrfToken,
        csrfHeaderName,
      });
      setAssessment(out);
      await refreshExtras(patientId, out.id);
      setStatus("Stage 3 complete");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stage 3 failed");
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid2">
      <Card className="fadeIn">
        <CardHeader title="Stage 3 Monitoring" subtitle="Non-invasive multimodal risk with stiffness and tracking." />
        <form className="stack" onSubmit={saveStiffness}>
          <Field label="Patient ID" hint="Uses active patient when available">
            <Input value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="UUID" />
          </Field>

          <div className="row2">
            <Field label="Liver stiffness (kPa)">
              <Input type="number" step="0.1" value={kpa} onChange={(e) => setKpa(e.target.value)} />
            </Field>
            <Field label="CAP (dB/m)">
              <Input type="number" value={cap} onChange={(e) => setCap(e.target.value)} />
            </Field>
          </div>

          <div className="row">
            <Button type="submit" disabled={!patientId || busy}>
              {busy ? "Working..." : "Save Stiffness"}
            </Button>
            <Button type="button" tone="secondary" onClick={() => void runStage3()} disabled={!patientId || busy}>
              Run Stage 3
            </Button>
          </div>

          {stiffness ? (
            <div className="row">
              <Pill tone="ok">kPa {stiffness.measured_kpa}</Pill>
              <Pill tone="neutral">{stiffness.source}</Pill>
              <Pill tone="neutral">ID {stiffness.id}</Pill>
            </div>
          ) : null}
          {status ? <InlineStatus tone="ok">{status}</InlineStatus> : null}
          {error ? <InlineStatus tone="danger">{error}</InlineStatus> : null}
        </form>
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "80ms" }}>
        <CardHeader title="Risk Output" subtitle="Composite + progression/decompensation risk." />
        {assessment ? (
          <div className="stack">
            <div className="row">
              <Pill tone={toneFromTier(assessment.risk_tier)}>{assessment.risk_tier}</Pill>
              <Pill tone="neutral">Composite {pct(assessment.composite_risk_score)}</Pill>
              <Pill tone="neutral">Progression {pct(assessment.progression_risk_12m)}</Pill>
              <Pill tone="neutral">Decomp {pct(assessment.decomp_risk_12m)}</Pill>
            </div>
            <div className="muted">Model: {assessment.model_version}</div>
            <pre className="json">{JSON.stringify(assessment.feature_snapshot_json, null, 2)}</pre>
          </div>
        ) : (
          <div className="empty">Run Stage 3 to view the monitoring output.</div>
        )}
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "140ms" }}>
        <CardHeader title="AI Alerts" subtitle="Precision-focused in-app alerts (open/ack/closed)." />
        {alerts.length ? (
          <div className="alertTable">
            <div className="alertHead">
              <span>Type</span>
              <span>Severity</span>
              <span>Score</span>
              <span>Status</span>
            </div>
            {alerts.map((a) => (
              <div key={a.id} className="alertRow">
                <span>{a.alert_type}</span>
                <span>{a.severity}</span>
                <span>{a.score.toFixed(3)} / {a.threshold.toFixed(3)}</span>
                <span>{a.status}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">No active alerts yet for this patient.</div>
        )}
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "200ms" }}>
        <CardHeader title="Explainability" subtitle="Local feature contributions + risk trend." />
        {explain ? (
          <div className="stack">
            <div className="xaiCols">
              <div>
                <div className="xaiTitle">Top Positive Drivers</div>
                {positiveContribs.map((item) => (
                  <div key={item.feature} className="contribRow">
                    <span>{item.feature}</span>
                    <div className="contribBar"><span style={{ width: `${Math.min(100, Math.abs(item.contribution) * 500)}%` }} /></div>
                    <span>{item.contribution.toFixed(3)}</span>
                  </div>
                ))}
              </div>
              <div>
                <div className="xaiTitle">Top Negative Drivers</div>
                {negativeContribs.map((item) => (
                  <div key={item.feature} className="contribRow">
                    <span>{item.feature}</span>
                    <div className="contribBar danger"><span style={{ width: `${Math.min(100, Math.abs(item.contribution) * 500)}%` }} /></div>
                    <span>{item.contribution.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="xaiTitle">Risk Trend</div>
            <div className="trendWrap">
              {(explain.trend_points_json || []).map((point) => (
                <div key={point.assessment_id || `${point.visit_index}`} className="trendPoint">
                  <div className="trendDot" style={{ bottom: `${Math.round(point.score * 100)}%` }} />
                  <div className="trendLabel">V{point.visit_index}</div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="empty">Run Stage 3 to load explainability and trend views.</div>
        )}
      </Card>
    </div>
  );
}
