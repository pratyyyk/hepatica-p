"use client";

import { ReactNode } from "react";

export interface TimelineEvent {
  id: string;
  event_type: string;
  event_payload: Record<string, unknown>;
  created_at: string;
}

function formatWhen(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) {
    return <div className="empty">No timeline events yet.</div>;
  }

  return (
    <div className="timeline">
      {events.map((e) => (
        <div key={e.id} className="timelineItem">
          <div className="timelineDot" />
          <div className="timelineBody">
            <div className="timelineRow">
              <strong className="timelineType">{e.event_type}</strong>
              <span className="timelineWhen">{formatWhen(e.created_at)}</span>
            </div>
            <pre className="json">{JSON.stringify(e.event_payload, null, 2)}</pre>
          </div>
        </div>
      ))}
    </div>
  );
}

export function InlineStatus({ tone = "neutral", children }: { tone?: "neutral" | "ok" | "warn" | "danger"; children: ReactNode }) {
  return <div className={`status status-${tone}`}>{children}</div>;
}

