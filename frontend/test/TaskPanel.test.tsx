import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TaskPanel from "../src/TaskPanel";
import { makeTask, server } from "./fixtures";

describe("TaskPanel", () => {
  it("stays mounted but hidden while no task is open", () => {
    render(
      <TaskPanel
        task={null}
        projectKey={null}
        tz={server.timezone}
        board={{}}
        onOpenTask={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("complementary", { hidden: true })).toHaveAttribute("aria-hidden", "true");
  });

  it("shows the full record: fields, tags, plain-text content and server-time meta", () => {
    const task = makeTask({
      id: "DLY-007",
      title: "polish the panel",
      status: "in_progress",
      branch: "feat/DLY-007/panel",
      tags: ["frontend", "design"],
      content: "resolve `profile_mismatch` in **auth**",
    });
    render(
      <TaskPanel
        task={task}
        projectKey="DLY"
        tz={server.timezone}
        board={{}}
        onOpenTask={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("DLY-007")).toBeInTheDocument();
    expect(screen.getByText("polish the panel")).toBeInTheDocument();
    expect(screen.getByText("feat/DLY-007/panel")).toBeInTheDocument();
    expect(screen.getByText("frontend")).toBeInTheDocument();
    // content is one line with inline markdown: `code` and **bold** render as elements
    expect(screen.getByText("profile_mismatch").tagName).toBe("CODE");
    expect(screen.getByText("auth").tagName).toBe("STRONG");
    // naive-UTC created_at rendered in the server's zone (KST, +9h)
    expect(screen.getByText("meta · KST (UTC+9)")).toBeInTheDocument();
    expect(screen.getAllByText("2026-07-01 18:00:00")).toHaveLength(2); // created_at + updated_at
  });

  it("shows the cancel reason and a dimmed dash when content is missing", () => {
    const task = makeTask({ status: "cancelled", cancel_reason: "범위에서 제외", content: undefined });
    render(
      <TaskPanel
        task={task}
        projectKey="DLY"
        tz={server.timezone}
        board={{}}
        onOpenTask={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("범위에서 제외")).toBeInTheDocument();
    expect(screen.getByText("—", { selector: ".panel-note" })).toHaveClass("dim");
  });

  it("lists the earlier tasks a task depends on and opens one", () => {
    const a = makeTask({ id: "DLY-001", title: "core loop" });
    const b = makeTask({ id: "DLY-002", title: "second leg", depends_on: ["DLY-001"] });
    const onOpenTask = vi.fn();
    render(
      <TaskPanel
        task={b}
        projectKey="DLY"
        tz={server.timezone}
        board={{ DLY: [a, b] }}
        onOpenTask={onOpenTask}
        onClose={vi.fn()}
      />,
    );
    const dependsOn = screen.getByRole("button", { name: /^depends on/ });
    expect(dependsOn).toHaveTextContent("1");

    fireEvent.click(dependsOn);
    fireEvent.click(screen.getByRole("menuitem", { name: "DLY-001" }));
    expect(onOpenTask).toHaveBeenCalledWith("DLY", a);
  });

  it("shows a placeholder title for an id that is not on the board", () => {
    const task = makeTask({ id: "DLY-009", depends_on: ["ZZZ-001"] });
    render(
      <TaskPanel
        task={task}
        projectKey="DLY"
        tz={server.timezone}
        board={{ DLY: [task] }}
        onOpenTask={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^depends on/ }));
    fireEvent.mouseEnter(screen.getByRole("menuitem", { name: "ZZZ-001" }));
    expect(screen.getByText("Not on this board")).toBeInTheDocument();
  });
});
