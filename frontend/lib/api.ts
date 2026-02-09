"use client";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiOptions {
  method?: HttpMethod;
  body?: unknown;
  headers?: Record<string, string>;
  csrfToken?: string | null;
  csrfHeaderName?: string;
}

export const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function isJsonResponse(contentType: string | null) {
  return !!contentType && contentType.toLowerCase().includes("application/json");
}

function sameOrigin(urlA: string, urlB: string) {
  try {
    return new URL(urlA).origin === new URL(urlB).origin;
  } catch {
    return false;
  }
}

function formatErrorDetail(detail: unknown): string {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;

  // FastAPI default: { "detail": ... }
  if (typeof detail === "object" && detail && "detail" in detail) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return formatErrorDetail((detail as any).detail);
  }

  // Validation errors (Pydantic): list of { loc, msg, type, ... }
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first && typeof first === "object") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const loc = (first as any).loc;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const msg = (first as any).msg;
      if (Array.isArray(loc) && typeof msg === "string") {
        return `Validation error: ${loc.join(".")}: ${msg}`;
      }
    }
    return "Validation error";
  }

  // Domain errors: { reason, codes?, code? }
  if (typeof detail === "object" && detail) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const reason = (detail as any).reason;
    if (typeof reason === "string") return reason;
  }

  try {
    return JSON.stringify(detail);
  } catch {
    return "Request failed";
  }
}

export async function apiFetch<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const method = opts.method || "GET";
  const headers: Record<string, string> = {
    ...(opts.headers || {}),
  };

  const hasBody = method !== "GET" && method !== "DELETE" && opts.body !== undefined;
  if (hasBody) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  if (method !== "GET" && opts.csrfToken && opts.csrfHeaderName) {
    headers[opts.csrfHeaderName] = opts.csrfToken;
  }

  let res: Response;
  try {
    res = await fetch(`${apiBase}${path}`, {
      method,
      credentials: "include",
      headers,
      body: hasBody ? JSON.stringify(opts.body) : undefined,
    });
  } catch (err) {
    const hint =
      `Cannot reach API at ${apiBase}. ` +
      `Is the backend running and CORS allowing this origin? ` +
      `Try: cd backend && cp .env.example .env && uvicorn app.main:app --reload --port 8000`;
    throw new Error(hint, { cause: err instanceof Error ? err : undefined });
  }

  if (res.status === 401) {
    throw new Error("Authentication required. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const contentType = res.headers.get("content-type");
    if (isJsonResponse(contentType) && text) {
      try {
        const parsed = JSON.parse(text) as unknown;
        throw new Error(formatErrorDetail(parsed), { cause: parsed });
      } catch {
        // fall through to raw text
      }
    }
    throw new Error(text || `Request failed (${res.status})`);
  }

  const contentType = res.headers.get("content-type");
  if (!isJsonResponse(contentType)) {
    return (await res.text()) as unknown as T;
  }
  return (await res.json()) as T;
}

export interface UploadResult {
  ok: boolean;
  status: number;
}

export async function uploadFileToUrl(params: {
  uploadUrl: string;
  file: File;
  csrfToken?: string | null;
  csrfHeaderName?: string;
}): Promise<UploadResult> {
  const { uploadUrl, file } = params;

  const isBackendUpload = sameOrigin(uploadUrl, apiBase);
  const headers: Record<string, string> = {
    "Content-Type": file.type || "application/octet-stream",
  };

  if (isBackendUpload && params.csrfToken && params.csrfHeaderName) {
    headers[params.csrfHeaderName] = params.csrfToken;
  }

  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers,
    credentials: isBackendUpload ? "include" : "omit",
    body: file,
  });

  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(msg || `Upload failed (${res.status})`);
  }

  return { ok: true, status: res.status };
}
