import { describe, expect, it } from "vitest";
import { parseMd } from "../src/markdown";

describe("parseMd", () => {
  it("maps # and ## to h2, ### to h3, and skips blank lines", () => {
    const blocks = parseMd("# 제목\n\n## 소제목\n### 세부");
    expect(blocks.map((b) => b.kind)).toEqual(["h2", "h2", "h3"]);
  });

  it("keeps fenced code verbatim, markdown inside included", () => {
    const blocks = parseMd("```\n**not bold**\n`raw`\n```");
    expect(blocks).toEqual([{ kind: "code", text: "**not bold**\n`raw`" }]);
  });

  it("renders bullets, checkboxes and ordered items as list lines", () => {
    const [ul, unchecked, checked, ol] = parseMd("- 항목\n- [ ] 할 일\n- [x] 한 일\n1. 첫째");
    expect(ul).toMatchObject({ kind: "li", spans: [{ text: "· 항목" }] });
    expect(unchecked.kind === "li" && unchecked.spans[0].text).toBe("☐  할 일");
    expect(checked.kind === "li" && checked.spans[0].text).toBe("☑  한 일");
    expect(ol).toMatchObject({ kind: "li", spans: [{ text: "1. 첫째" }] });
  });

  it("reads > lines as quotes and everything else as paragraphs", () => {
    expect(parseMd("> 인용\n본문").map((b) => b.kind)).toEqual(["quote", "p"]);
  });

  it("splits inline code / bold / italic into spans", () => {
    const blocks = parseMd("a `code` **bold** _em_ z");
    expect(blocks[0].kind === "p" && blocks[0].spans).toEqual([
      { kind: "text", text: "a " },
      { kind: "code", text: "code" },
      { kind: "text", text: " " },
      { kind: "strong", text: "bold" },
      { kind: "text", text: " " },
      { kind: "em", text: "em" },
      { kind: "text", text: " z" },
    ]);
  });

  it("passes HTML through as plain text, never as markup", () => {
    const blocks = parseMd("<b>tag</b>");
    expect(blocks[0].kind === "p" && blocks[0].spans).toEqual([{ kind: "text", text: "<b>tag</b>" }]);
  });
});
