/** Tiny markdown reader for task `content` — headings, lists, quotes, fenced code,
    and inline code / bold / italic. No HTML passthrough; everything is text. */

export type Block =
  | { kind: "h2" | "h3" | "p" | "li" | "quote"; spans: Span[] }
  | { kind: "code"; text: string };

export type Span = { kind: "text" | "code" | "strong" | "em"; text: string };

export function parseMd(src: string): Block[] {
  const out: Block[] = [];
  const lines = src.split("\n");
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (ln.trim() === "") {
      i++;
      continue;
    }
    if (ln.startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++;
      out.push({ kind: "code", text: buf.join("\n") });
      continue;
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(ln);
    if (h) {
      out.push({ kind: h[1].length === 1 ? "h2" : h[1].length === 2 ? "h2" : "h3", spans: inline(h[2]) });
      i++;
      continue;
    }
    if (ln.startsWith("> ")) {
      out.push({ kind: "quote", spans: inline(ln.slice(2)) });
      i++;
      continue;
    }
    const li = /^\s*[-*]\s+(.*)$/.exec(ln);
    if (li) {
      const box = /^\[( |x)\]\s+(.*)$/.exec(li[1]);
      const text = box ? (box[1] === "x" ? "☑  " : "☐  ") + box[2] : "· " + li[1];
      out.push({ kind: "li", spans: inline(text) });
      i++;
      continue;
    }
    const ol = /^\s*(\d+)\.\s+(.*)$/.exec(ln);
    if (ol) {
      out.push({ kind: "li", spans: inline(`${ol[1]}. ${ol[2]}`) });
      i++;
      continue;
    }
    out.push({ kind: "p", spans: inline(ln) });
    i++;
  }
  return out;
}

function inline(text: string): Span[] {
  const out: Span[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*|_[^_]+_)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push({ kind: "text", text: text.slice(last, m.index) });
    const tok = m[0];
    if (tok.startsWith("`")) out.push({ kind: "code", text: tok.slice(1, -1) });
    else if (tok.startsWith("**")) out.push({ kind: "strong", text: tok.slice(2, -2) });
    else out.push({ kind: "em", text: tok.slice(1, -1) });
    last = m.index + tok.length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out.length ? out : [{ kind: "text", text }];
}
