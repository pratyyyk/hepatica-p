"use client";

import { FormEvent, useEffect, useState } from "react";

import { InlineStatus } from "@/components/Timeline";
import { Button, Card, CardHeader, Field, Input, Pill, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useActivePatientId } from "@/lib/activePatient";
import { useSession } from "@/lib/session";

type ClinicalResponse = {
  id: string;
  patient_id: string;
  fib4: number;
  apri: number;
  risk_tier: "LOW" | "MODERATE" | "HIGH";
  probability: number;
  model_version: string;
  created_at: string;
};

export default function Stage1Page() {
  const { csrfToken, csrfHeaderName } = useSession();
  const { activePatientId } = useActivePatientId();

  const [patientId, setPatientId] = useState("");
  const [form, setForm] = useState({
    ast: 90,
    alt: 70,
    platelets: 130,
    ast_uln: 40,
    age: 49,
    bmi: 29.3,
    type2dm: true,
  });

  const [result, setResult] = useState<ClinicalResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (activePatientId && !patientId) setPatientId(activePatientId);
  }, [activePatientId, patientId]);

  async function runStage1(e: FormEvent) {
    e.preventDefault();
    if (!patientId) return;
    setBusy(true);
    setError("");
    try {
      const out = await apiFetch<ClinicalResponse>("/api/v1/assessments/clinical", {
        method: "POST",
        body: { ...form, patient_id: patientId },
        csrfToken,
        csrfHeaderName,
      });
      setResult(out);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stage 1 failed");
    } finally {
      setBusy(false);
    }
  }

  const tierTone = result?.risk_tier === "HIGH" ? "danger" : result?.risk_tier === "MODERATE" ? "warn" : "ok";

  return (
    <div className="grid2">
      <Card className="fadeIn">
        <CardHeader title="Stage 1 Assessment" subtitle="Clinical risk triage (rule + optional ML)." />
        <form className="stack" onSubmit={runStage1}>
          <Field label="Patient ID" hint="Uses the active patient when available">
            <Input value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="UUID" />
          </Field>

          <div className="row2">
            <Field label="AST">
              <Input type="number" value={form.ast} onChange={(e) => setForm({ ...form, ast: Number(e.target.value) })} />
            </Field>
            <Field label="ALT">
              <Input type="number" value={form.alt} onChange={(e) => setForm({ ...form, alt: Number(e.target.value) })} />
            </Field>
          </div>

          <div className="row2">
            <Field label="Platelets">
              <Input
                type="number"
                value={form.platelets}
                onChange={(e) => setForm({ ...form, platelets: Number(e.target.value) })}
              />
            </Field>
            <Field label="AST ULN">
              <Input
                type="number"
                value={form.ast_uln}
                onChange={(e) => setForm({ ...form, ast_uln: Number(e.target.value) })}
              />
            </Field>
          </div>

          <div className="row2">
            <Field label="Age">
              <Input type="number" value={form.age} onChange={(e) => setForm({ ...form, age: Number(e.target.value) })} />
            </Field>
            <Field label="BMI">
              <Input
                type="number"
                step="0.1"
                value={form.bmi}
                onChange={(e) => setForm({ ...form, bmi: Number(e.target.value) })}
              />
            </Field>
          </div>

          <Field label="Type 2 DM">
            <Select
              value={form.type2dm ? "yes" : "no"}
              onChange={(e) => setForm({ ...form, type2dm: e.target.value === "yes" })}
            >
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </Select>
          </Field>

          <div className="row">
            <Button disabled={!patientId || busy} type="submit">
              {busy ? "Running..." : "Run Stage 1"}
            </Button>
          </div>

          {error ? <InlineStatus tone="danger">{error}</InlineStatus> : null}
        </form>
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "80ms" }}>
        <CardHeader title="Result" subtitle="Risk tier + probability (0–0.95)." />
        {result ? (
          <div className="stack">
            <div className="row">
              <Pill tone={tierTone}>{result.risk_tier}</Pill>
              <Pill tone="neutral">Prob {result.probability}</Pill>
              <Pill tone="neutral">FIB-4 {result.fib4}</Pill>
              <Pill tone="neutral">APRI {result.apri}</Pill>
            </div>
            <div className="muted">Model: {result.model_version}</div>
            <pre className="json">{JSON.stringify(result, null, 2)}</pre>
          </div>
        ) : (
          <div className="empty">Run Stage 1 to see outputs.</div>
        )}
      </Card>
    </div>
  );
}
