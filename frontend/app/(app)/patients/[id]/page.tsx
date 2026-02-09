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

export default function PatientDetailPage() {
  const params = useParams<{ id: string }>();
  const patientId = params.id;

  const [patient, setPatient] = useState<Patient | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const p = await apiFetch<Patient>(`/api/v1/patients/${patientId}`);
      const t = await apiFetch<TimelineResponse>(`/api/v1/patients/${patientId}/timeline`);
      setPatient(p);
      setTimeline(t.events || []);
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
    </div>
  );
}
