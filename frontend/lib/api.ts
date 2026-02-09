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

  const res = await fetch(`${apiBase}${path}`, {
    method,
    credentials: "include",
    headers,
    body: hasBody ? JSON.stringify(opts.body) : undefined,
  });

  if (res.status === 401) {
    throw new Error("Authentication required. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text();
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

