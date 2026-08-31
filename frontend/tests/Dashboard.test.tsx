import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Dashboard from "../src/pages/Dashboard";
import { makeBoard, makeTask } from "./fixtures";

describe("Dashboard", () => {
  it("asks for a project when there is none", () => {
    const empty = makeBoard();
    empty.projects = [];
    render(<Dashboard data={empty} onOpenProject={vi.fn()} onOpenTask={vi.fn()} />);
    expect(screen.getByText(/프로젝트가 없어요/)).toBeInTheDocument();
  });

  it("counts the current period's tasks and lists the WIP ones", () => {
    const data = makeBoard([
      makeTask({ id: "DLY-001", status: "done", meta: { created_at: "2026-07-01 09:00:00", updated_at: "2026-07-01 09:00:00", completed_at: "2026-07-02 09:00:00" } }),
      makeTask({ id: "DLY-002", title: "wire the API", status: "in_progress", branch: "feat/DLY-002/api" }),
      makeTask({ id: "DLY-003", status: "todo" }),
    ]);
    render(<Dashboard data={data} onOpenProject={vi.fn()} onOpenTask={vi.fn()} />);
    expect(screen.getByText("전체 태스크").parentElement).toHaveTextContent("3");
    // the WIP list shows the in_progress task with its branch
    expect(screen.getByText("wire the API")).toBeInTheDocument();
    expect(screen.getByText("feat/DLY-002/api")).toBeInTheDocument();
    expect(screen.queryByText(/진행 중인 태스크가 없어요/)).not.toBeInTheDocument();
  });

  it("shows the empty WIP message when nothing is in progress", () => {
    render(<Dashboard data={makeBoard([makeTask()])} onOpenProject={vi.fn()} onOpenTask={vi.fn()} />);
    expect(screen.getByText(/진행 중인 태스크가 없어요/)).toBeInTheDocument();
  });

  it("opens a project from its card and a task from the WIP list", async () => {
    const user = userEvent.setup();
    const onOpenProject = vi.fn();
    const onOpenTask = vi.fn();
    const wip = makeTask({ id: "DLY-002", title: "wire the API", status: "in_progress" });
    render(<Dashboard data={makeBoard([wip])} onOpenProject={onOpenProject} onOpenTask={onOpenTask} />);
    await user.click(screen.getByText("습관 트래커"));
    expect(onOpenProject).toHaveBeenCalledWith("DLY");
    await user.click(screen.getByText("wire the API"));
    expect(onOpenTask).toHaveBeenCalledWith("DLY", wip);
  });
});
