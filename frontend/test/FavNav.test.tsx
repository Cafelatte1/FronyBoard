import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import FavNav from "../src/FavNav";
import { makeBoard, makeTask } from "./fixtures";

describe("FavNav", () => {
  it("is disabled while nothing is starred", () => {
    render(<FavNav data={makeBoard([makeTask()])} favs={new Set()} onOpen={vi.fn()} />);
    const btn = screen.getByTitle("즐겨찾기");
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent("0");
  });

  it("lists the starred projects and opens the one that is picked", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<FavNav data={makeBoard([makeTask()])} favs={new Set(["DLY"])} onOpen={onOpen} />);
    const btn = screen.getByTitle("즐겨찾기");
    expect(btn).toBeEnabled();
    expect(btn).toHaveTextContent("1");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await user.click(btn);
    const item = screen.getByRole("menuitem");
    expect(item).toHaveTextContent("Dailying");
    await user.click(item);
    expect(onOpen).toHaveBeenCalledWith("DLY");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
