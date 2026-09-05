import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SearchBar from "../src/SearchBar";
import { makeBoard, makeTask } from "./fixtures";

beforeEach(() => localStorage.clear());

const board = () =>
  makeBoard([
    makeTask({ id: "DLY-001", title: "로깅 파이프라인", content: "jsonl 로그" }),
    makeTask({ id: "DLY-002", title: "검색 기능", status: "in_progress" }),
    makeTask({ id: "DLY-003", title: "정리 1" }),
    makeTask({ id: "DLY-004", title: "정리 2" }),
    makeTask({ id: "DLY-005", title: "정리 3" }),
    makeTask({ id: "DLY-006", title: "정리 4" }),
  ]);

function setup(onPick = vi.fn()) {
  render(<SearchBar data={board()} onPick={onPick} />);
  return { input: screen.getByRole("textbox", { name: "태스크 검색" }), onPick };
}

/** Row titles are split by the highlight <mark>, so match on the whole .gs-title element. */
const title = (text: string) => (_: string, el: Element | null) =>
  el?.classList.contains("gs-title") === true && el.textContent === text;

describe("SearchBar (desktop)", () => {
  it("shows the guide, and recent chips when there are any, on focus", async () => {
    localStorage.setItem("fb.recentSearches", JSON.stringify(["로깅"]));
    const { input } = setup();
    await userEvent.click(input);
    expect(screen.getByText(/프로젝트 키 · 태스크 ID · 제목 · 내용/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "로깅" })).toBeInTheDocument();
  });

  it("groups matches by project and folds them to five rows", async () => {
    const { input } = setup();
    await userEvent.type(input, "정리");
    expect(screen.getByText("태스크 4건")).toBeInTheDocument();
    expect(screen.getByText("Dailying")).toBeInTheDocument();
    expect(screen.getByText(title("정리 4"))).toBeInTheDocument(); // 4 matches fit without folding
    await userEvent.clear(input);
    await userEvent.type(input, "dly");
    expect(screen.getByText("태스크 6건")).toBeInTheDocument();
    expect(screen.queryByText(title("정리 4"))).not.toBeInTheDocument(); // folded behind 모두 보기
    await userEvent.click(screen.getByText("Dailying 결과 6건 모두 보기"));
    expect(screen.getByText(title("정리 4"))).toBeInTheDocument();
  });

  it("highlights the match and shows a snippet for content-only hits", async () => {
    const { input } = setup();
    await userEvent.type(input, "jsonl");
    const mark = screen.getByText("jsonl", { selector: "mark" });
    expect(mark).toBeInTheDocument();
    expect(screen.getByText("로깅 파이프라인")).toBeInTheDocument();
  });

  it("opens a result on click and remembers the query", async () => {
    const { input, onPick } = setup();
    await userEvent.type(input, "검색 기");
    await userEvent.click(screen.getByText("검색 기", { selector: "mark" }));
    expect(onPick).toHaveBeenCalledTimes(1);
    const [key, task] = onPick.mock.calls[0];
    expect(key).toBe("DLY");
    expect(task.id).toBe("DLY-002");
    expect(JSON.parse(localStorage.getItem("fb.recentSearches")!)).toEqual(["검색 기"]);
    expect(input).toHaveValue(""); // the pick clears the field and closes the panel
  });

  it("Enter opens the first result, Escape closes the panel", async () => {
    const { input, onPick } = setup();
    await userEvent.type(input, "로깅{Enter}");
    expect(onPick).toHaveBeenCalledWith("DLY", expect.objectContaining({ id: "DLY-001" }));
    await userEvent.type(input, "로깅");
    expect(screen.getByText("태스크 1건")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByText("태스크 1건")).not.toBeInTheDocument();
  });

  it("says so when nothing matches", async () => {
    const { input } = setup();
    await userEvent.type(input, "결제");
    expect(screen.getByText(/일치하는 태스크가 없습니다/)).toBeInTheDocument();
    expect(screen.getByText(/내용에 있는 단어로도/)).toBeInTheDocument();
  });
});
