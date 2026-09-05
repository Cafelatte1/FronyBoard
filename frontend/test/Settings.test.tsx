import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Settings from "../src/pages/Settings";
import { makeBoard } from "./fixtures";

const fetchMock = vi.fn();

function keysRes(keys: unknown[]) {
  return { ok: true, status: 200, statusText: "", json: () => Promise.resolve({ keys }) };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  localStorage.setItem("fronyboard_user", "admin");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("Settings", () => {
  it("shows the account and the server facts", async () => {
    fetchMock.mockResolvedValue(keysRes([]));
    render(<Settings data={makeBoard()} onAuthFail={vi.fn()} />);
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByText("aira v0.16.1")).toBeInTheDocument();
    expect(screen.getByText("C:/data/fronyboard")).toBeInTheDocument();
    expect(screen.getByText("1 · 2026Q3")).toBeInTheDocument();
    expect(await screen.findByText("발급된 키가 없어요")).toBeInTheDocument();
  });

  it("lists the issued API keys once they load", async () => {
    fetchMock.mockResolvedValue(
      keysRes([{ name: "pc1", fingerprint: "frony_ab…cd", created_at: "2026-08-01 00:00:00" }]),
    );
    render(<Settings data={makeBoard()} onAuthFail={vi.fn()} />);
    expect(await screen.findByText("pc1")).toBeInTheDocument();
    expect(screen.getByText("frony_ab…cd")).toBeInTheDocument();
    expect(screen.queryByText("발급된 키가 없어요")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/keys", expect.anything());
  });

  it("kicks back to login when the keys call is unauthorized", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 401, statusText: "", json: () => Promise.resolve({}) });
    const onAuthFail = vi.fn();
    render(<Settings data={makeBoard()} onAuthFail={onAuthFail} />);
    await vi.waitFor(() => expect(onAuthFail).toHaveBeenCalled());
  });
});
