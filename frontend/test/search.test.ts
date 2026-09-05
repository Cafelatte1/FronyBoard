import { describe, expect, it } from "vitest";
import { searchTasks } from "../src/search";
import { makeBoard, makeTask } from "./fixtures";

const board = () =>
  makeBoard([
    makeTask({ id: "DLY-001", title: "로깅 파이프라인", content: "## Why\njsonl 로그를 남긴다", status: "done" }),
    makeTask({ id: "DLY-002", title: "검색 기능", content: "드롭다운", status: "in_progress", branch: "feat/DLY-002/search" }),
    makeTask({ id: "DLY-003", title: "정리", status: "cancelled", cancel_reason: "x", tags: ["infra"] }),
  ]);

describe("searchTasks", () => {
  it("matches title, id and content, case-insensitively", () => {
    expect(searchTasks(board(), "로깅")[0].rows.map((r) => r.task.id)).toEqual(["DLY-001"]);
    expect(searchTasks(board(), "dly-00").length).toBe(1);
    expect(searchTasks(board(), "DLY-00")[0].total).toBe(3); // cancelled included
    expect(searchTasks(board(), "jsonl")[0].rows[0].task.id).toBe("DLY-001");
  });

  it("matches the project key, pulling in every task of that project", () => {
    expect(searchTasks(board(), "dly")[0].total).toBe(3);
  });

  it("does not search branch or tags", () => {
    expect(searchTasks(board(), "feat/")).toEqual([]);
    expect(searchTasks(board(), "infra")).toEqual([]);
  });

  it("returns an empty list for a blank query", () => {
    expect(searchTasks(board(), "  ")).toEqual([]);
  });

  it("highlights the matched span in id and title", () => {
    const row = searchTasks(board(), "검색")[0].rows[0];
    expect(row.title).toEqual({ pre: "", hit: "검색", post: " 기능" });
    expect(row.id.hit).toBe("");
    expect(row.snippet).toBeNull(); // the title already shows why it matched
  });

  it("builds a snippet only for content-only matches", () => {
    const row = searchTasks(board(), "jsonl")[0].rows[0];
    expect(row.snippet).not.toBeNull();
    expect(row.snippet!.hit).toBe("jsonl");
    expect(row.snippet!.pre + row.snippet!.hit + row.snippet!.post).toContain("jsonl 로그를 남긴다");
  });

  it("sorts rows by status order and labels the quarter span", () => {
    const g = searchTasks(board(), "dly")[0];
    expect(g.rows.map((r) => r.task.status)).toEqual(["in_progress", "done", "cancelled"]);
    expect(g.period).toBe("2026Q3");
    expect(g.name).toBe("Dailying");
  });
});
