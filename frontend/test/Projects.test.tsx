import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Projects from "../src/pages/Projects";
import { makeBoard, makeTask } from "./fixtures";

beforeEach(() => localStorage.clear()); // favorites live in localStorage

const noop = { setOpenKey: vi.fn(), onOpenTask: vi.fn() };

describe("project list", () => {
  it("asks for a project when there is none", () => {
    const empty = makeBoard();
    empty.projects = [];
    render(<Projects data={empty} openKey={null} {...noop} />);
    expect(screen.getByText(/프로젝트가 없어요/)).toBeInTheDocument();
  });

  it("renders a card per project with its key, name and progress", () => {
    const data = makeBoard([makeTask({ status: "done" }), makeTask({ id: "DLY-002" })]);
    render(<Projects data={data} openKey={null} {...noop} />);
    expect(screen.getByText("DLY")).toBeInTheDocument();
    expect(screen.getByText("Dailying")).toBeInTheDocument();
    expect(screen.getByText("1/2 · 50%")).toBeInTheDocument();
  });

  it("opens the detail when a card is clicked", async () => {
    const setOpenKey = vi.fn();
    render(<Projects data={makeBoard()} openKey={null} setOpenKey={setOpenKey} onOpenTask={vi.fn()} />);
    await userEvent.click(screen.getByText("Dailying"));
    expect(setOpenKey).toHaveBeenCalledWith("DLY");
  });
});

describe("project detail task table", () => {
  const tasks = [
    makeTask({ id: "DLY-001", title: "first todo" }),
    makeTask({ id: "DLY-002", title: "second todo" }),
    makeTask({ id: "DLY-003", title: "the wip one", status: "in_progress" }),
    makeTask({ id: "DLY-004", title: "dropped", status: "cancelled", cancel_reason: "descoped" }),
  ];

  function renderDetail(list = tasks) {
    return render(<Projects data={makeBoard(list)} openKey="DLY" {...noop} />);
  }

  it("hides cancelled tasks by default", () => {
    renderDetail();
    expect(screen.getByText("first todo")).toBeInTheDocument();
    expect(screen.getByText("the wip one")).toBeInTheDocument();
    expect(screen.queryByText("dropped")).not.toBeInTheDocument();
    expect(screen.getByText(/3건/)).toHaveTextContent("2026Q3 · 3건 / 전체 4건");
  });

  it("filters by status from the filter menu", async () => {
    const user = userEvent.setup();
    const { container } = renderDetail();
    await user.click(screen.getByTitle("필터"));
    const menu = within(container.querySelector(".menu")!);
    await user.click(menu.getByText("진행중"));
    expect(screen.getByText("the wip one")).toBeInTheDocument();
    expect(screen.queryByText("first todo")).not.toBeInTheDocument();
  });

  it("shows cancelled tasks when the toggle is on", async () => {
    const user = userEvent.setup();
    const { container } = renderDetail();
    await user.click(screen.getByTitle("필터"));
    await user.click(within(container.querySelector(".menu")!).getByText("취소된 태스크 포함"));
    expect(screen.getByText("dropped")).toBeInTheDocument();
  });

  it("tells apart 'no tasks yet' from 'nothing matches the filter'", async () => {
    const user = userEvent.setup();
    const { container, unmount } = renderDetail([makeTask()]);
    await user.click(screen.getByTitle("필터"));
    await user.click(within(container.querySelector(".menu")!).getByText("블록"));
    expect(screen.getByText("조건에 맞는 태스크가 없어요.")).toBeInTheDocument();
    unmount();

    renderDetail([]);
    expect(screen.getByText(/아직 기간 파일의 태스크가 없어요/)).toBeInTheDocument();
  });

  it("starts on the page holding the focused task after a search pick", () => {
    const tasks = Array.from({ length: 12 }, (_, i) =>
      makeTask({ id: `DLY-${String(i + 1).padStart(3, "0")}`, title: `task ${i + 1}` }),
    );
    render(
      <Projects data={makeBoard(tasks)} openKey="DLY" focus={{ period: "2026Q3", taskId: "DLY-012", nonce: 1 }} {...noop} />,
    );
    expect(screen.getByText("11–12 / 12")).toBeInTheDocument();
    expect(screen.getByText("task 12")).toBeInTheDocument();
  });

  it("un-hides cancelled tasks when the focused task is cancelled", () => {
    const tasks = [
      makeTask(),
      makeTask({ id: "DLY-002", title: "dropped", status: "cancelled", cancel_reason: "x" }),
    ];
    render(
      <Projects data={makeBoard(tasks)} openKey="DLY" focus={{ period: "2026Q3", taskId: "DLY-002", nonce: 1 }} {...noop} />,
    );
    expect(screen.getByText("dropped")).toBeInTheDocument();
  });

  it("pages long lists ten rows at a time", () => {
    renderDetail(
      Array.from({ length: 12 }, (_, i) =>
        makeTask({ id: `DLY-${String(i + 1).padStart(3, "0")}`, title: `task ${i + 1}` }),
      ),
    );
    expect(screen.getByText("1–10 / 12")).toBeInTheDocument();
    expect(screen.getAllByText(/^task \d+$/)).toHaveLength(10);
  });
});

describe("roadmap checklist", () => {
  const withChecklist = (items: { text: string; done: boolean }[]) => {
    const data = makeBoard([makeTask()]);
    data.roadmaps.DLY.years["2026"].overview.checklist = items;
    return data;
  };

  it("hides done items by default and reveals them from the toggle", async () => {
    const data = withChecklist([
      { text: "design", done: true },
      { text: "build", done: false },
      { text: "ship", done: true },
    ]);
    render(<Projects data={data} openKey="DLY" {...noop} />);
    expect(screen.getByText("build")).toBeInTheDocument();
    expect(screen.queryByText("design")).not.toBeInTheDocument();
    expect(screen.getByText("2/3")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "완료 2개 보기" }));
    expect(screen.getByText("design")).toBeInTheDocument();
    expect(screen.getByText("ship")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "완료 2개 숨기기" }));
    expect(screen.queryByText("design")).not.toBeInTheDocument();
  });

  it("says so when every item is done", () => {
    render(<Projects data={withChecklist([{ text: "design", done: true }])} openKey="DLY" {...noop} />);
    expect(screen.getByText("남은 항목이 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "완료 1개 보기" })).toBeInTheDocument();
  });

  it("offers no toggle while nothing is done", () => {
    render(<Projects data={withChecklist([{ text: "build", done: false }])} openKey="DLY" {...noop} />);
    expect(screen.getByText("build")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /완료 \d+개/ })).not.toBeInTheDocument();
  });
});

