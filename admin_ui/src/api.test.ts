import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, jsonBody } from "./api";

type MockResponse = {
  ok: boolean;
  status: number;
  statusText: string;
  headers: Headers;
  json: () => Promise<unknown>;
  text: () => Promise<string>;
};

function response(status: number, body: unknown, headers: Record<string, string> = {}): MockResponse {
  const values = new Headers({ "content-type": "application/json", ...headers });
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    headers: values,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

describe("admin api client", () => {
  const events = new EventTarget();

  beforeEach(() => {
    vi.stubGlobal("document", { cookie: "ppg_admin_csrf=csrf-token%2Fvalue" });
    vi.stubGlobal("window", events);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("adds same-origin credentials and CSRF to writes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/api/v1/admin/jobs", { method: "POST", body: jsonBody({ job_type: "quality_gate" }) });

    const [, options] = fetchMock.mock.calls[0];
    expect(options.credentials).toBe("same-origin");
    expect((options.headers as Headers).get("x-csrf-token")).toBe("csrf-token/value");
    expect((options.headers as Headers).get("content-type")).toBe("application/json");
  });

  it("turns revision conflicts into an actionable localized error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(
      409,
      { detail: "旧 revision" },
      { "x-request-id": "req-conflict" },
    )));

    await expect(api("/api/v1/admin/config-drafts/example/publish", { method: "POST" }))
      .rejects.toMatchObject({
        name: "ApiError",
        status: 409,
        requestId: "req-conflict",
        message: expect.stringContaining("请刷新后重试"),
      } satisfies Partial<ApiError>);
  });

  it("announces an expired session on 401", async () => {
    const listener = vi.fn();
    events.addEventListener("admin:unauthorized", listener);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(401, { detail: "会话不存在" })));

    await expect(api("/api/v1/admin/overview")).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledOnce();
    events.removeEventListener("admin:unauthorized", listener);
  });

  it("does not show an expired-session warning for the initial auth probe", async () => {
    const listener = vi.fn();
    events.addEventListener("admin:unauthorized", listener);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(401, { detail: "未登录" })));

    await expect(api("/api/v1/admin/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(listener).not.toHaveBeenCalled();
    events.removeEventListener("admin:unauthorized", listener);
  });
});
