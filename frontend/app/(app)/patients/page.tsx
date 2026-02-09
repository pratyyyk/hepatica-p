"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { Card, CardHeader, Button, Field, Input, Select, Textarea, Pill } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { setActivePatientId, useActivePatientId } from "@/lib/activePatient";
import { useSession } from "@/lib/session";

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

export default function PatientsPage() {
  const { csrfToken, csrfHeaderName } = useSession();
  const { activePatientId } = useActivePatientId();

  const [rows, setRows] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const [form, setForm] = useState({
    external_id: "",
    sex: "F",
    age: 45,
    bmi: 28,
    type2dm: false,
    notes: "",
  });

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const payload = await apiFetch<Patient[]>("/api/v1/patients?limit=50&offset=0");
      setRows(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load patients");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function createPatient(e: FormEvent) {
    e.preventDefault();
    setStatus("Creating patient...");
    setError("");
    try {
      const created = await apiFetch<Patient>("/api/v1/patients", {
        method: "POST",
        body: form,
        csrfToken,
        csrfHeaderName,
      });
      setActivePatientId(created.id);
      setStatus("Patient created");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
      setStatus("");
    }
  }

  return (
    <div className="grid2">
      <Card className="fadeIn">
        <CardHeader title="Patients" subtitle="Your recent patients (local DB)." />
        {loading ? (
          <div className="empty">Loading...</div>
        ) : error ? (
          <div className="status status-danger">{error}</div>
        ) : rows.length ? (
          <div className="list">
            {rows.map((p) => (
              <div key={p.id} className="listRow">
                <div className="listMain">
                  <div className="listTitle">
                    <Link
                      className="link"
                      href={`/patients/${p.id}`}
                      onClick={() => setActivePatientId(p.id)}
                    >
                      {p.external_id}
                    </Link>
                  </div>
                  <div className="listMeta">
                    <Pill tone={p.id === activePatientId ? "ok" : "neutral"}>{p.id}</Pill>
                    {p.sex ? <Pill tone="neutral">{p.sex}</Pill> : null}
                    {typeof p.age === "number" ? <Pill tone="neutral">Age {p.age}</Pill> : null}
                    {typeof p.bmi === "number" ? <Pill tone="neutral">BMI {p.bmi}</Pill> : null}
                    {p.type2dm ? <Pill tone="warn">T2DM</Pill> : <Pill tone="neutral">No T2DM</Pill>}
                  </div>
                </div>
                <Button
                  tone="secondary"
                  onClick={() => {
                    setActivePatientId(p.id);
                  }}
                >
                  Set Active
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">No patients yet. Create your first patient.</div>
        )}
        <div className="row">
          <Button tone="ghost" onClick={() => void refresh()}>
            Refresh
          </Button>
        </div>
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "80ms" }}>
        <CardHeader title="Create Patient" subtitle="Use a unique External ID." />
        <form onSubmit={createPatient} className="stack">
          <Field label="External ID" hint="Example: P-001">
            <Input
              value={form.external_id}
              onChange={(e) => setForm({ ...form, external_id: e.target.value })}
              required
            />
          </Field>

          <div className="row2">
            <Field label="Sex">
              <Select value={form.sex} onChange={(e) => setForm({ ...form, sex: e.target.value })}>
                <option value="F">F</option>
                <option value="M">M</option>
              </Select>
            </Field>
            <Field label="Age">
              <Input
                type="number"
                value={form.age}
                onChange={(e) => setForm({ ...form, age: Number(e.target.value) })}
              />
            </Field>
          </div>

          <div className="row2">
            <Field label="BMI">
              <Input
                type="number"
                step="0.1"
                value={form.bmi}
                onChange={(e) => setForm({ ...form, bmi: Number(e.target.value) })}
              />
            </Field>
            <Field label="Type 2 DM">
              <Select
                value={form.type2dm ? "yes" : "no"}
                onChange={(e) => setForm({ ...form, type2dm: e.target.value === "yes" })}
              >
                <option value="no">No</option>
                <option value="yes">Yes</option>
              </Select>
            </Field>
          </div>

          <Field label="Notes" hint="Optional">
            <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </Field>

          {status ? <div className="status status-ok">{status}</div> : null}
          {error ? <div className="status status-danger">{error}</div> : null}

          <div className="row">
            <Button type="submit">Create</Button>
            <Button type="button" tone="ghost" onClick={() => setForm({ ...form, external_id: "" })}>
              Clear
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

