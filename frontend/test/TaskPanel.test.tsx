import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TaskPanel from "../src/TaskPanel";
import { makeTask, server } from "./fixtures";

const months = [{ id: "M1", month: "2026-07", status: "active" as const, task_counts: {} }];

describe("TaskPanel", () => {
  it("stays mounted but hidden while no task is open", () => {
    render(
      <TaskPanel
        task={null}
        projectKey={null}
        months={months}
        tz={server.timezone}
        board={{}}
        onOpenTask={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("complementary", { hidden: true })).toHaveAttribute("aria-hidden", "true");
  });

  it("shows the full record: fields, tags, markdown content and server-time meta", () => {
    const task = makeTask({
      id: "DLY-007",
      title: "polish the panel",
      status: "in_progress",
      week: 2,
      branch: "feat/DLY-007/panel",
      tags: ["frontend", "design"],
      content: "## Why\n작업 이유\n- [x] 됐고\n`code` 조각",
    });
    render(
      <TaskPanel
        task={task}
        projectKey="DLY"
        months={months}
        tz={server.timezone}
        board={{}}
        onOpenTask={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("DLY-007")).toBeInTheDocument();
    expect(screen.getByText("polish the panel")).toBeInTheDocument();
    expect(screen.getByText("2026-07 · W2")).toBeInTheDocument(); // month id resolved to the calendar month
    expect(screen.getByText("feat/DLY-007/panel")).toBeInTheDocument();
    expect(screen.getByText("frontend")).toBeInTheDocument();
    // markdown made it to the DOM as structure, not raw text
    expect(screen.getByText("Why")).toBeInTheDocument();
    expect(screen.getByText("☑ 됐고")).toBeInTheDocument();
    expect(screen.getByText("code").tagName).toBe("CODE");
    // naive-UTC created_at rendered in the server's zone (KST, +9h)
    expect(screen.getByText("meta · KST (UTC+9)")).toBeInTheDocument();
    expect(screen.getAllByText("2026-07-01 18:00:00")).toHaveLength(2); // created_at + updated_at
  });

  it("shows the cancel reason and a content placeholder when they apply", () => {
    const task = makeTask({ status: "cancelled", cancel_reason: "범위에서 제외", content: undefined });
    render(
      <TaskPanel
        task={task}
        projectKey="DLY"
        months={months}
        tz={server.timezone}
        board={{}}
        onOpenTask={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("범위에서 제외")).toBeInTheDocument();
    expect(screen.getByText(/This task has no/)).toBeInTheDocument();
    expect(screen.getByText("content", { selector: "code" })).toBeInTheDocument();
  });

  it("renders follows / followed by buttons and derives followed by from the board", () => {
    const a = makeTask({ id: "DLY-001", title: "core loop" });
    const b = makeTask({ id: "DLY-002", title: "second leg", follows: ["DLY-001"] });
    const c = makeTask({ id: "FAU-001", title: "auth handoff", follows: ["DLY-001"] });
    const onOpenTask = vi.fn();
    render(
      <TaskPanel
        task={a}
        projectKey="DLY"
        months={months}
        tz={server.timezone}
        board={{ DLY: [a, b], FAU: [c] }}
        onOpenTask={onOpenTask}
        onClose={vi.fn()}
      />,
    );
    const followedBy = screen.getByRole("button", { name: /followed by/ });
    expect(followedBy).toHaveTextContent("2");
    const follows = screen.getByRole("button", { name: /^follows/ });
    expect(follows).toBeDisabled();
    expect(follows).toHaveTextContent("0");

    fireEvent.click(followedBy);
    expect(screen.getByRole("menuitem", { name: "DLY-002" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: "FAU-001" }));
    expect(onOpenTask).toHaveBeenCalledWith("FAU", c);
  });

  it("shows a placeholder title for an id that is not on the board", () => {
    const task = makeTask({ id: "DLY-009", follows: ["ZZZ-001"] });
    render(
      <TaskPanel
        task={task}
        projectKey="DLY"
        months={months}
        tz={server.timezone}
        board={{ DLY: [task] }}
        onOpenTask={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^follows/ }));
    fireEvent.mouseEnter(screen.getByRole("menuitem", { name: "ZZZ-001" }));
    expect(screen.getByText("Not on this board")).toBeInTheDocument();
  });
});
