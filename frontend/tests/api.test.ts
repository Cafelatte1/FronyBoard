import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Unauthorized, api, apiSend, getToken, getUsername, login, logout } from "../src/api";

const fetchMock = vi.fn();

function res(status: number, body?: unknown, statusText = "") {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: () => (body === undefined ? Promise.reject(new Error("no body")) : Promise.resolve(body)),
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("sends the stored session token as a bearer header", async () => {
    localStorage.setItem("fronyboard_session", "tok123");
    fetchMock.mockResolvedValue(res(200, { ok: true }));
    await expect(api("/api/projects")).resolves.toEqual({ ok: true });
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/projects");
    expect(init.headers.Authorization).toBe("Bearer tok123");
  });

  it("throws Unauthorized on 401", async () => {
    fetchMock.mockResolvedValue(res(401));
    await expect(api("/api/projects")).rejects.toBeInstanceOf(Unauthorized);
  });

  it("surfaces the server's error field, falling back to statusText", async () => {
    fetchMock.mockResolvedValue(res(400, { error: "period 1999Q1 not found" }));
    await expect(api("/x")).rejects.toThrow("period 1999Q1 not found");
    fetchMock.mockResolvedValue(res(500, undefined, "Internal Server Error"));
    await expect(api("/x")).rejects.toThrow("Internal Server Error");
  });
});

describe("apiSend", () => {
  it("serializes the body as JSON with the method given", async () => {
    fetchMock.mockResolvedValue(res(200, {}));
    await apiSend("/api/keys", "POST", { name: "pc2" });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe('{"name":"pc2"}');
  });

  it("sends no body or content-type when there is nothing to send", async () => {
    fetchMock.mockResolvedValue(res(200, {}));
    await apiSend("/api/keys/pc2", "DELETE");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
  });
});

describe("login / logout", () => {
  it("stores the token and username on success", async () => {
    fetchMock.mockResolvedValue(res(200, { token: "t1", username: "admin" }));
    await login("admin", "pw");
    expect(getToken()).toBe("t1");
    expect(getUsername()).toBe("admin");
  });

  it("rejects a wrong password without touching storage", async () => {
    fetchMock.mockResolvedValue(res(401));
    await expect(login("admin", "no")).rejects.toThrow("Invalid username or password.");
    expect(getToken()).toBeNull();
  });

  it("clears the session even when the logout call fails", async () => {
    localStorage.setItem("fronyboard_session", "t1");
    localStorage.setItem("fronyboard_user", "admin");
    fetchMock.mockRejectedValue(new Error("network down"));
    await logout();
    expect(getToken()).toBeNull();
    expect(getUsername()).toBeNull();
  });
});
