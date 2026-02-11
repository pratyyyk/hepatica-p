"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Timeline, TimelineEvent } from "@/components/Timeline";
import { Button, Card, CardHeader, Pill } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { setActivePatientId } from "@/lib/activePatient";

type Patient = {
  id: string;
  external_id: string;
  sex: string | null;
  age: number | null;
  bmi: number | null;
  type2dm: boolean;
  notes: string | null;
  created_at: string;
};

type TimelineResponse = { patient_id: string; events: TimelineEvent[] };
type Stage3HistoryResponse = {
  patient_id: string;
  assessments: {
    id: string;
    composite_risk_score: number;
    progression_risk_12m: number;
    decomp_risk_12m: number;
    risk_tier: "LOW" | "MODERATE" | "HIGH" | "CRITICAL";
    created_at: string;
  }[];
};
type Stage3AlertsResponse = {
  patient_id: string;
  alerts: {
    id: string;
    alert_type: string;
    severity: string;
    status: string;
    score: number;
    threshold: number;
    created_at: string;
  }[];
};

export default function PatientDetailPage() {
  const params = useParams<{ id: string }>();
  const patientId = params.id;

  const [patient, setPatient] = useState<Patient | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [stage3History, setStage3History] = useState<Stage3HistoryResponse["assessments"]>([]);
  const [stage3Alerts, setStage3Alerts] = useState<Stage3AlertsResponse["alerts"]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const p = await apiFetch<Patient>(`/api/v1/patients/${patientId}`);
      const t = await apiFetch<TimelineResponse>(`/api/v1/patients/${patientId}/timeline`);
      let s3h: Stage3HistoryResponse["assessments"] = [];
      let s3a: Stage3AlertsResponse["alerts"] = [];
      try {
        const history = await apiFetch<Stage3HistoryResponse>(`/api/v1/patients/${patientId}/stage3/history`);
        s3h = history.assessments || [];
      } catch {
        s3h = [];
      }
      try {
        const alerts = await apiFetch<Stage3AlertsResponse>(`/api/v1/patients/${patientId}/alerts`);
        s3a = alerts.alerts || [];
      } catch {
        s3a = [];
      }
      setPatient(p);
      setTimeline(t.events || []);
      setStage3History(s3h);
      setStage3Alerts(s3a);
      setActivePatientId(patientId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load patient");
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="grid2">
      <Card className="fadeIn">
        <CardHeader title="Patient" subtitle="Details + identifiers." />
        {loading ? (
          <div className="empty">Loading...</div>
        ) : error ? (
          <div className="status status-danger">{error}</div>
        ) : patient ? (
          <div className="stack">
            <div className="row">
              <Pill tone="ok">{patient.external_id}</Pill>
              <Pill tone="neutral">{patient.id}</Pill>
              {patient.sex ? <Pill tone="neutral">{patient.sex}</Pill> : null}
              {typeof patient.age === "number" ? <Pill tone="neutral">Age {patient.age}</Pill> : null}
              {typeof patient.bmi === "number" ? <Pill tone="neutral">BMI {patient.bmi}</Pill> : null}
              {patient.type2dm ? <Pill tone="warn">T2DM</Pill> : <Pill tone="neutral">No T2DM</Pill>}
            </div>
            {patient.notes ? <div className="note">{patient.notes}</div> : <div className="muted">No notes.</div>}
            <div className="row">
              <Button tone="secondary" onClick={() => setActivePatientId(patient.id)}>
                Set Active
              </Button>
              <Button tone="ghost" onClick={() => void refresh()}>
                Refresh
              </Button>
            </div>
          </div>
        ) : (
          <div className="empty">Patient not found.</div>
        )}
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "80ms" }}>
        <CardHeader title="Timeline" subtitle="Audit-friendly flow history." />
        {loading ? <div className="empty">Loading...</div> : <Timeline events={timeline} />}
        <div className="row">
          <Button tone="ghost" onClick={() => void refresh()}>
            Refresh Timeline
          </Button>
        </div>
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "140ms" }}>
        <CardHeader title="Stage 3 Monitoring" subtitle="Latest multimodal scores + alerts." />
        {loading ? (
          <div className="empty">Loading...</div>
        ) : (
          <div className="stack">
            {stage3History.length ? (
              <div className="list">
                {stage3History.slice(0, 4).map((s3) => (
                  <div key={s3.id} className="listRow">
                    <div className="listMain">
                      <div className="listTitle">{s3.risk_tier}</div>
                      <div className="listMeta">
                        <Pill tone="neutral">Composite {(s3.composite_risk_score * 100).toFixed(1)}%</Pill>
                        <Pill tone="neutral">12m Progress {(s3.progression_risk_12m * 100).toFixed(1)}%</Pill>
                        <Pill tone="neutral">12m Decomp {(s3.decomp_risk_12m * 100).toFixed(1)}%</Pill>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty">No Stage 3 assessments yet.</div>
            )}

            <div className="xaiTitle">Alerts</div>
            {stage3Alerts.length ? (
              <div className="alertTable">
                <div className="alertHead">
                  <span>Type</span>
                  <span>Severity</span>
                  <span>Score</span>
                  <span>Status</span>
                </div>
                {stage3Alerts.slice(0, 6).map((a) => (
                  <div key={a.id} className="alertRow">
                    <span>{a.alert_type}</span>
                    <span>{a.severity}</span>
                    <span>{a.score.toFixed(3)} / {a.threshold.toFixed(3)}</span>
                    <span>{a.status}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty">No active Stage 3 alerts.</div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
