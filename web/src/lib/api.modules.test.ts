// Module API client: login stores the token; module calls hit the right method+path+body.

import { afterEach, describe, expect, it, vi } from "vitest";

import { api, getToken, setToken } from "./api";

function mockFetch(status = 200, body: unknown = {}) {
  const fn = vi.fn(async (_url: string, _init?: RequestInit) => ({
    ok: status < 400,
    status,
    statusText: "OK",
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function call(fn: ReturnType<typeof mockFetch>, i = 0): { url: string; init: RequestInit } {
  const c = fn.mock.calls[i]!;
  return { url: String(c[0]), init: c[1] ?? {} };
}

afterEach(() => {
  vi.unstubAllGlobals();
  setToken("");
});

describe("module api client", () => {
  it("login stores the returned token (it doubles as the bearer)", async () => {
    mockFetch(200, { ok: true, token: "tok_123" });
    await api.login("hunter2");
    expect(getToken()).toBe("tok_123");
  });

  it("create task POSTs the body to /api/tasks", async () => {
    const fn = mockFetch(200, { id: "task_1", title: "x" });
    await api.tasks.create({ title: "x" });
    const { url, init } = call(fn);
    expect(url).toContain("/api/tasks");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ title: "x" });
  });

  it("research run posts query + depth", async () => {
    const fn = mockFetch(200, { id: "rsch_1", status: "done" });
    await api.research.run("why", "quick");
    expect(JSON.parse(String(call(fn).init.body))).toEqual({ query: "why", depth: "quick" });
  });

  it("delete uses DELETE", async () => {
    const fn = mockFetch(200, { ok: true });
    await api.tasks.remove("task_9");
    expect(call(fn).init.method).toBe("DELETE");
    expect(call(fn).url).toContain("/api/tasks/task_9");
  });

  it("throws ApiError carrying the status on failure", async () => {
    mockFetch(401, { detail: "nope" });
    await expect(api.tasks.list()).rejects.toMatchObject({ status: 401 });
  });
});
