"use client";

import { FormEvent, useEffect, useState } from "react";

import { Button, Card, CardHeader, Field, Input, Pill, Textarea } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useActivePatientId } from "@/lib/activePatient";
import { useSession } from "@/lib/session";

type AssistantCitation = {
  source_doc: string;
  page_number: number;
  snippet: string;
};

type AssistantPatientSummary = {
  external_id: string;
  stage1_risk_tier: string | null;
  stage1_probability: number | null;
  stage2_top_stage: string | null;
  stage2_top_probability: number | null;
  stage3_risk_tier: string | null;
  stage3_composite_risk: number | null;
  open_alerts: number;
};

type AssistantResponse = {
  patient_id: string | null;
  reply: string;
  suggestions: string[];
  citations: AssistantCitation[];
  patient_summary: AssistantPatientSummary | null;
};

type ChatItem = {
  id: string;
  role: "user" | "assistant";
  text: string;
  suggestions?: string[];
  citations?: AssistantCitation[];
  summary?: AssistantPatientSummary | null;
};

function pct(value: number | null | undefined) {
  if (typeof value !== "number") return "-";
  return `${(value * 100).toFixed(1)}%`;
}

export default function AssistantPage() {
  const { csrfToken, csrfHeaderName } = useSession();
  const { activePatientId } = useActivePatientId();

  const [patientId, setPatientId] = useState("");
  const [message, setMessage] = useState("Summarize this patient's Stage 1, Stage 2, and Stage 3 risk status.");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<ChatItem[]>([
    {
      id: "assistant-welcome",
      role: "assistant",
      text:
        "I am your clinical assistant. Ask for risk summary, next-step recommendations, or report-ready interpretation across Stage 1, Stage 2, and Stage 3.",
      suggestions: [
        "Summarize current risk and open alerts.",
        "What should I do next for this patient?",
        "Explain why Stage 1 probability can stay near 0.82.",
      ],
    },
  ]);

  useEffect(() => {
    if (activePatientId) {
      setPatientId(activePatientId);
    }
  }, [activePatientId]);

  async function sendPrompt(prompt: string) {
    const trimmed = prompt.trim();
    if (!trimmed || busy) return;

    setError("");
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      {
        id: `u-${Date.now()}`,
        role: "user",
        text: trimmed,
      },
    ]);

    try {
      const out = await apiFetch<AssistantResponse>("/api/v1/assistant/chat", {
        method: "POST",
        body: {
          message: trimmed,
          patient_id: patientId || undefined,
        },
        csrfToken,
        csrfHeaderName,
      });

      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: out.reply,
          suggestions: out.suggestions,
          citations: out.citations,
          summary: out.patient_summary,
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Assistant request failed";
      setError(msg);
      setMessages((prev) => [
        ...prev,
        {
          id: `a-err-${Date.now()}`,
          role: "assistant",
          text: `I could not complete that request: ${msg}`,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const prompt = message;
    setMessage("");
    await sendPrompt(prompt);
  }

  return (
    <div className="grid2 assistantGrid">
      <Card className="fadeIn">
        <CardHeader
          title="Doctor Assistant"
          subtitle="Clinical chat support for triage, risk interpretation, and follow-up planning."
        />
        <form className="stack" onSubmit={onSubmit}>
          <Field label="Patient Context" hint="Optional but recommended">
            <Input
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              placeholder="Uses active patient when set"
            />
          </Field>

          <Field label="Ask Assistant">
            <Textarea
              rows={4}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Ask for integrated risk summary, alerts review, or recommendations"
              disabled={busy}
            />
          </Field>

          <div className="row">
            <Button type="submit" disabled={busy || !message.trim()}>
              {busy ? "Thinking..." : "Send"}
            </Button>
            <Button
              type="button"
              tone="ghost"
              onClick={() => {
                setMessages((prev) => prev.slice(0, 1));
                setError("");
              }}
              disabled={busy}
            >
              Clear Chat
            </Button>
          </div>

          {activePatientId ? (
            <div className="row">
              <Pill tone="ok">Active patient: {activePatientId.slice(0, 8)}...{activePatientId.slice(-4)}</Pill>
            </div>
          ) : (
            <div className="row">
              <Pill tone="warn">No active patient selected</Pill>
            </div>
          )}

          {error ? <div className="status status-danger">{error}</div> : null}
        </form>
      </Card>

      <Card className="fadeIn" style={{ animationDelay: "80ms" }}>
        <CardHeader title="Conversation" subtitle="Patient-safe guidance. Final decisions remain clinician-led." />

        <div className="assistantTranscript">
          {messages.map((item) => (
            <div
              key={item.id}
              className={`assistantBubble ${item.role === "user" ? "assistantBubbleUser" : "assistantBubbleBot"}`}
            >
              <div className="assistantRole">{item.role === "user" ? "You" : "Assistant"}</div>
              <div className="assistantText">{item.text}</div>

              {item.summary ? (
                <div className="assistantSummary">
                  <div className="assistantSummaryHead">Patient Snapshot: {item.summary.external_id}</div>
                  <div className="assistantSummaryGrid">
                    <div><span>Stage 1</span><strong>{item.summary.stage1_risk_tier || "-"} ({pct(item.summary.stage1_probability)})</strong></div>
                    <div><span>Stage 2</span><strong>{item.summary.stage2_top_stage || "-"} ({pct(item.summary.stage2_top_probability)})</strong></div>
                    <div><span>Stage 3</span><strong>{item.summary.stage3_risk_tier || "-"} ({pct(item.summary.stage3_composite_risk)})</strong></div>
                    <div><span>Open Alerts</span><strong>{item.summary.open_alerts}</strong></div>
                  </div>
                </div>
              ) : null}

              {item.citations?.length ? (
                <div className="assistantCitations">
                  <div className="assistantCitationsHead">Evidence</div>
                  {item.citations.map((c, idx) => (
                    <div key={`${c.source_doc}-${c.page_number}-${idx}`} className="assistantCitationRow">
                      <span>{c.source_doc} p.{c.page_number}</span>
                      <p>{c.snippet}</p>
                    </div>
                  ))}
                </div>
              ) : null}

              {item.role === "assistant" && item.suggestions?.length ? (
                <div className="assistantSuggestions">
                  {item.suggestions.map((suggestion, idx) => (
                    <button
                      key={`${item.id}-s-${idx}`}
                      type="button"
                      className="assistantSuggestionBtn"
                      disabled={busy}
                      onClick={() => {
                        setMessage("");
                        void sendPrompt(suggestion);
                      }}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
