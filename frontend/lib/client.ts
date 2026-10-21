export class ApiError extends Error {
  status: number;
  payload: unknown;
  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}
export const apiBase = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");
export async function request<T>(
  path: string,
  body?: unknown,
  key?: string,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (key) headers["Idempotency-Key"] = key;
  let response: Response;
  try {
    response = await fetch(`${apiBase}/api/v1${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers,
      credentials: "include",
      cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(90000),
    });
  } catch {
    throw new ApiError(
      0,
      "Cannot reach the server, or the request timed out. Refresh records before retrying; a write may already have completed.",
      null,
    );
  }
  const data =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    let message = typeof detail === "string" ? detail : detail?.message;
    if (detail && typeof detail === "object" && Array.isArray(detail.issues)) {
      const reasons = detail.issues
        .filter((issue: unknown): issue is { message: string; reference?: string } =>
          !!issue && typeof issue === "object" &&
          "message" in issue && typeof issue.message === "string")
        .map((issue: { message: string; reference?: string }) =>
          `${issue.reference ? issue.reference + ": " : ""}${issue.message}`);
      if (reasons.length) message = [message, ...reasons].filter(Boolean).join("\n");
    }
    if (!message && Array.isArray(detail))
      message = detail
        .map(
          (x: { loc?: string[]; msg: string }) =>
            `${x.loc?.slice(1).join(".") || "Input"}: ${x.msg}`,
        )
        .join("; ");
    if (!message)
      message =
        data?.failure_reason ||
        (response.status === 401
          ? "Please sign in again."
          : `Request failed (${response.status}).`);
    throw new ApiError(response.status, message, data);
  }
  return data as T;
}
// Only retry identifiers are persisted, never credentials or request payloads.
// A successful explicit action removes its key; an uncertain failure retains it.
export async function mutation<T>(path: string, body: unknown): Promise<T> {
  const raw = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(path + JSON.stringify(body)),
  );
  const slot =
    "opsflow-write-" +
    Array.from(new Uint8Array(raw), (x) =>
      x.toString(16).padStart(2, "0"),
    ).join("");
  const key = sessionStorage.getItem(slot) || crypto.randomUUID();
  sessionStorage.setItem(slot, key);
  try {
    const result = await request<T>(path, body, key);
    sessionStorage.removeItem(slot);
    return result;
  } catch (e) {
    if (e instanceof ApiError && e.status >= 400 && e.status < 500)
      sessionStorage.removeItem(slot);
    throw e;
  }
}
