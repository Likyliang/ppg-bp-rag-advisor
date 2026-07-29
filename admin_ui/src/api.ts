export type Json = Record<string, any>;

export class ApiError extends Error {
  status: number;
  requestId: string;

  constructor(message: string, status: number, requestId = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
  }
}

function cookie(name: string): string {
  const prefix = `${name}=`;
  const match = document.cookie.split("; ").find((part) => part.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : "";
}

export async function api<T = Json>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof ArrayBuffer) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const method = (options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = cookie("ppg_admin_csrf");
    if (csrf) headers.set("x-csrf-token", csrf);
  }
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof body === "object" ? body.detail : body;
    const raw = typeof detail === "string" ? detail : JSON.stringify(detail || response.statusText);
    const prefix: Record<number, string> = {
      401: "登录已失效，请重新登录",
      403: "当前角色没有执行此操作的权限",
      409: "数据已被其他人更新，请刷新后重试",
      422: "提交内容未通过校验",
      428: "缺少版本校验信息，请刷新后重试",
      429: "请求过于频繁，请稍后再试",
    };
    const message = prefix[response.status]
      ? `${prefix[response.status]}${raw && raw !== prefix[response.status] ? `：${raw}` : ""}`
      : raw;
    const requestId = response.headers.get("x-request-id") || "";
    const isAuthProbe = path.endsWith("/auth/me") || path.endsWith("/auth/login");
    if (response.status === 401 && !isAuthProbe) {
      window.dispatchEvent(new CustomEvent("admin:unauthorized"));
    }
    throw new ApiError(message, response.status, requestId);
  }
  return body as T;
}

export const jsonBody = (value: unknown): string => JSON.stringify(value);
