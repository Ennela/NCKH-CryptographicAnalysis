// Render the V2 progress report from report.json (a list of typed blocks).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, AlignmentType, ShadingType, BorderStyle, ImageRun, LevelFormat,
  PageBreak, TableOfContents, Header, Footer, PageNumber, ExternalHyperlink,
} = require("docx");

const S = __dirname;
const DOC = JSON.parse(fs.readFileSync(path.join(S, "report.json"), "utf8"));

const F = "Calibri";
const MONO = "Consolas";
const PAGE_W = 11906 - 2 * 1134; // A4 minus 2 cm margins, in DXA
const NAVY = "1F3864";
const NAVY2 = "2E5597";
const GREY = "595959";

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const cellBorders = { top: border, bottom: border, left: border, right: border };

/** Inline runs: a string, or [{t, b, i, c, mono}] */
function runs(x, size = 22) {
  const arr = Array.isArray(x) ? x : [{ t: x }];
  return arr.map((r) => new TextRun({
    text: r.t, bold: r.b, italics: r.i, color: r.c,
    font: r.mono ? MONO : F, size: r.mono ? size - 3 : size,
  }));
}

const P = (x, o = {}) => new Paragraph({
  spacing: { after: o.after ?? 130, before: o.before ?? 0, line: 288 },
  alignment: o.align,
  indent: o.indent,
  children: runs(x, o.size),
});

const H = (text, level) => new Paragraph({
  heading: [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3][level - 1],
  spacing: { before: level === 1 ? 360 : level === 2 ? 260 : 200, after: level === 1 ? 170 : 130 },
  pageBreakBefore: level === 1 && !text.startsWith("Phụ lục A"),
  children: [new TextRun({ text, font: F })],
});

const bullet = (x, lvl = 0) => new Paragraph({
  numbering: { reference: "b", level: lvl },
  spacing: { after: 70, line: 288 },
  children: runs(x),
});

const numbered = (x) => new Paragraph({
  numbering: { reference: "n", level: 0 },
  spacing: { after: 70, line: 288 },
  children: runs(x),
});

function table(block) {
  const pct = block.w;
  const widths = pct.map((w) => Math.round((PAGE_W * w) / 100));
  const size = block.size || 18;
  const cell = (content, i, head, rowOpts = {}) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    borders: cellBorders,
    shading: head
      ? { type: ShadingType.CLEAR, fill: NAVY, color: "FFFFFF" }
      : rowOpts.fill
        ? { type: ShadingType.CLEAR, fill: rowOpts.fill, color: "auto" }
        : undefined,
    margins: { top: 55, bottom: 55, left: 85, right: 85 },
    children: [new Paragraph({
      alignment: (block.right || []).includes(i) && !head ? AlignmentType.RIGHT : AlignmentType.LEFT,
      spacing: { after: 0, line: 252 },
      children: runs(content, size).map((r) => {
        if (head) { r.root && null; }
        return r;
      }),
    })],
  });
  const headRow = new TableRow({
    tableHeader: true,
    children: block.head.map((h, i) => new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      borders: cellBorders,
      shading: { type: ShadingType.CLEAR, fill: NAVY, color: "FFFFFF" },
      margins: { top: 55, bottom: 55, left: 85, right: 85 },
      children: [new Paragraph({
        spacing: { after: 0, line: 252 },
        children: [new TextRun({ text: h, bold: true, color: "FFFFFF", font: F, size })],
      })],
    })),
  });
  const rows = block.rows.map((r) => {
    const cells = Array.isArray(r) ? r : r.c;
    const opts = Array.isArray(r) ? {} : r;
    return new TableRow({ children: cells.map((c, i) => cell(c, i, false, opts)) });
  });
  return new Table({ width: { size: PAGE_W, type: WidthType.DXA }, columnWidths: widths, rows: [headRow, ...rows] });
}

function codeBlock(block) {
  const out = [];
  if (block.caption) {
    out.push(new Paragraph({
      spacing: { before: 120, after: 60 },
      children: [new TextRun({ text: block.caption, italics: true, size: 18, color: GREY, font: F })],
    }));
  }
  block.lines.forEach((ln, idx) => {
    out.push(new Paragraph({
      spacing: { after: 0, line: 240 },
      shading: { type: ShadingType.CLEAR, fill: "F4F4F1", color: "auto" },
      indent: { left: 170, right: 100 },
      border: {
        left: { style: BorderStyle.SINGLE, size: 12, color: "B8B8AE", space: 6 },
        top: idx === 0 ? { style: BorderStyle.SINGLE, size: 2, color: "F4F4F1", space: 4 } : undefined,
        bottom: idx === block.lines.length - 1 ? { style: BorderStyle.SINGLE, size: 2, color: "F4F4F1", space: 4 } : undefined,
      },
      children: [new TextRun({ text: ln === "" ? " " : ln, font: MONO, size: 17 })],
    }));
  });
  out.push(new Paragraph({ spacing: { after: 130 }, children: [] }));
  return out;
}

function image(block) {
  const data = fs.readFileSync(path.join(S, block.file));
  const w = block.width || 630;
  const h = Math.round(w * block.ratio);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 140, after: 60 },
      children: [new ImageRun({ type: "png", data, transformation: { width: w, height: h } })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 160 },
      children: [new TextRun({ text: block.caption, italics: true, size: 18, color: GREY, font: F })],
    }),
  ];
}

function callout(block) {
  const fill = { info: "EAF1FB", warn: "FDF3E3", ok: "E9F5EC", note: "F3F3F0" }[block.kind || "info"];
  const edge = { info: "2E5597", warn: "C07800", ok: "2E7D32", note: "8A8A82" }[block.kind || "info"];
  const kids = [];
  if (block.title) {
    kids.push(new TextRun({ text: block.title, bold: true, font: F, size: 21 }));
    kids.push(new TextRun({ text: "", break: 1 }));
  }
  (Array.isArray(block.text) ? block.text : [block.text]).forEach((t, i) => {
    if (i > 0) kids.push(new TextRun({ text: "", break: 1 }));
    kids.push(new TextRun({ text: t, font: F, size: 21 }));
  });
  return new Paragraph({
    spacing: { before: 140, after: 160, line: 288 },
    shading: { type: ShadingType.CLEAR, fill, color: "auto" },
    indent: { left: 140, right: 140 },
    border: {
      left: { style: BorderStyle.SINGLE, size: 18, color: edge, space: 10 },
      top: { style: BorderStyle.SINGLE, size: 2, color: fill, space: 8 },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: fill, space: 8 },
      right: { style: BorderStyle.SINGLE, size: 2, color: fill, space: 8 },
    },
    children: kids,
  });
}

// ── assemble ─────────────────────────────────────────────────────────
const children = [];

// cover
children.push(
  new Paragraph({ spacing: { before: 1500, after: 100 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: DOC.org, font: F, size: 24, color: GREY })] }),
  new Paragraph({ spacing: { before: 600, after: 140 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "BÁO CÁO TIẾN ĐỘ", bold: true, font: F, size: 44, color: NAVY })] }),
  new Paragraph({ spacing: { after: 400 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "ĐỀ TÀI NGHIÊN CỨU KHOA HỌC SINH VIÊN", bold: true, font: F, size: 26, color: NAVY2 })] }),
  new Paragraph({ spacing: { after: 700 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: DOC.title, font: F, size: 28, italics: true })] }),
);
DOC.cover.forEach(([k, v]) => children.push(new Paragraph({
  spacing: { after: 110 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: k + ": ", bold: true, font: F, size: 22 }),
             new TextRun({ text: v, font: F, size: 22 })],
})));
children.push(new Paragraph({ children: [new PageBreak()] }));

// table of contents
children.push(new Paragraph({
  spacing: { after: 220 },
  children: [new TextRun({ text: "MỤC LỤC", bold: true, font: F, size: 30, color: NAVY })],
}));
children.push(new TableOfContents("Mục lục", { hyperlink: true, headingStyleRange: "1-2" }));
children.push(new Paragraph({ children: [new PageBreak()] }));

for (const b of DOC.blocks) {
  switch (b.t) {
    case "h1": children.push(H(b.x, 1)); break;
    case "h2": children.push(H(b.x, 2)); break;
    case "h3": children.push(H(b.x, 3)); break;
    case "p": children.push(P(b.x, b)); break;
    case "b": children.push(bullet(b.x, b.lvl || 0)); break;
    case "n": children.push(numbered(b.x)); break;
    case "table": children.push(table(b)); children.push(new Paragraph({ spacing: { after: 60 }, children: [] }));
      if (b.caption) children.push(new Paragraph({
        spacing: { after: 170 },
        children: [new TextRun({ text: b.caption, italics: true, size: 18, color: GREY, font: F })] }));
      break;
    case "img": image(b).forEach((x) => children.push(x)); break;
    case "code": codeBlock(b).forEach((x) => children.push(x)); break;
    case "callout": children.push(callout(b)); break;
    case "pb": children.push(new Paragraph({ children: [new PageBreak()] })); break;
    default: throw new Error("unknown block " + b.t);
  }
}

const doc = new Document({
  creator: "Nhóm NCKH",
  title: DOC.title,
  description: "Báo cáo tiến độ lần 2",
  styles: {
    default: { document: { run: { font: F, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: NAVY, font: F }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 25, bold: true, color: NAVY2, font: F }, paragraph: { outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, color: "404040", font: F }, paragraph: { outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "b", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 460, hanging: 240 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 880, hanging: 240 } } } }] },
      { reference: "n", levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    headers: { default: new Header({ children: [new Paragraph({
      alignment: AlignmentType.RIGHT,
      children: [new TextRun({ text: DOC.runningHead, size: 16, color: GREY, font: F })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: GREY, font: F })] })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(path.join(S, DOC.outfile), buf);
  console.log("written", DOC.outfile, (buf.length / 1024 / 1024).toFixed(2) + " MB");
});
