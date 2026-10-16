// Shared print contract: A4, sticky headings, indivisible figures, splittable tables.
// Built-in font stack comes from print-context.typ (report-fonts); Typst finds the
// files via TYPST_FONT_PATHS so rendering never depends on system fontconfig.
#set page(
  margin: (top: 26mm, bottom: 24mm, left: 22mm, right: 22mm),
  header: context {
    let current = query(heading.where(level: 1)).filter(it => it.location().position().page <= here().position().page)
    let starts = current.filter(it => it.location().position().page == here().position().page)
    let chapter = if starts.len() > 0 { starts.first().body } else if current.len() > 0 { current.last().body } else { [] }
    align(right, text(size: 8pt, fill: rgb("#68788a"))[#report-project #h(6mm) #chapter])
  },
  footer: align(center, context text(size: 9pt, counter(page).display("1"))),
)
#set text(font: report-fonts, size: 10.5pt, lang: "zh", region: "cn")
// CJK glyphs need visibly more leading than Typst's Latin-tuned default.
// 正文整体居中对齐；标题、列表、代码保持各自对齐。
// 用 set align 而非 show par: set align —— 后者会关闭 all:true 的
// 标题后首段缩进（Typst 0.14 的 first-line-indent 判定依赖段落样式）。
#set align(center)
#show heading: set align(left)
#show list: set align(left)
#show enum: set align(left)
// 仅块级代码保持左对齐；行内代码参与段落流，避免被拆成独立行。
#show raw.where(block: true): set align(left)
#set par(justify: false, leading: 0.85em, spacing: 1.1em, linebreaks: "optimized",
  first-line-indent: (amount: 2em, all: true))
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => block(sticky: true, above: 6mm, below: 4mm)[#text(size: 19pt, fill: rgb("#24476a"), weight: "bold")[#it]]
#show heading.where(level: 2): it => block(sticky: true, above: 5mm, below: 3mm)[#text(size: 14pt, fill: rgb("#24476a"), weight: "bold")[#it]]
#show heading.where(level: 3): it => block(sticky: true, above: 3mm, below: 2mm)[#text(size: 11pt, weight: "bold")[#it]]
#show figure.caption: set text(size: 9pt, fill: rgb("#53636a"))
#show cite: it => { metadata("bioreport-citation"); it }
#show bibliography: it => context {
  if query(metadata.where(value: "bioreport-citation")).len() > 0 {
    layout(size => {
      let fits = measure(it, width: size.width).height <= 225mm
      block(breakable: not fits, it)
    })
  }
}
// Paths, versions and SHA256 hashes render in a monospace stack that still
// falls through to the CJK family for Chinese fragments.
#show raw: set text(font: report-mono-fonts, size: 8.5pt)
#let report-intro(body) = block(sticky: true, below: 3mm)[#text(body)]
#let report-cell(body) = text(body.replace("_", "_\u{200b}").replace("/", "/\u{200b}"))
#let report-observation(id, kind, part) = context [#metadata((id: id, kind: kind, part: part, page: here().position().page, y: here().position().y.pt()))<bioreport-layout>]
#let report-figure(path, caption, ratio, preferred-height: none, id: "figure") = {
  let height = if preferred-height == none { calc.min(166mm * ratio, 190mm) } else { preferred-height }
  figure(
    [#report-observation(id, "figure", "image")#image(path, width: 100%, height: height, fit: "contain")],
    caption: [#report-observation(id, "figure", "caption")#text(caption)], supplement: [图], numbering: "1", placement: none,
  )
}
#let report-continuation(id) = context {
  let rows = query(<bioreport-layout>).filter(it => it.value.kind == "table" and it.value.id == id and it.value.part.starts-with("row-"))
  if rows.len() > 0 and here().position().page > calc.min(..rows.map(it => it.value.page)) {
    report-observation(id, "table", "continuation")
    text("（续表）")
  }
}
#let report-table(headers, rows, numeric, keep-together: true, id: "table") = layout(size => {
  let widths = headers.map(h => if h == "SHA256" { 4fr } else if h in ("Description", "通路名称", "数据目录内路径", "统计口径") { 3fr } else if h in ("Gene ID", "Sample", "样本", "项目", "比较组") { 1.8fr } else { 1fr })
  let body = [
    #set text(size: 9pt)
    #table(
      columns: widths, inset: (x: 5pt, y: 5.5pt),
      align: (x, y) => if numeric.at(x) { right } else { left },
      stroke: (x, y) => (bottom: .35pt + rgb("#dce3ec")),
      fill: (x, y) => if y == 0 { rgb("#eaf0f7") } else if calc.even(y) { rgb("#f6f9fc") } else { none },
      table.header(repeat: true, ..headers.enumerate().map(((j, h)) => [#if j == 0 { report-observation(id, "table", "header") }#text(weight: "bold", report-cell(h))#if j == 0 { report-continuation(id) }])),
      ..rows.enumerate().map(((i, row)) => row.enumerate().map(((j, cell)) =>
        [#if j == 0 { report-observation(id, "table", "row-" + str(i)) }#if headers.at(j) == "SHA256" { text(font: report-mono-fonts, cell) } else { report-cell(cell) }])).flatten(),
    )
  ]
  let fits = measure(body, width: size.width).height <= 225mm
  report-observation(id, "table", if keep-together and fits { "small" } else { "large" })
  block(breakable: not (keep-together and fits), above: 3mm, below: 3mm, body)
})

// Pair / triplet / grid: preserve captions and move the reading unit together
// when it fits a page. Oversized groups flow without reducing typography.
#let report-figure-group(items, columns: 1) = layout(size => {
  let body = grid(columns: columns, gutter: 4mm, ..items)
  let fits = measure(body, width: size.width).height <= 225mm
  block(breakable: not fits, body)
})

#let report-metrics(items) = grid(columns: (1fr, 1fr, 1fr), gutter: 4mm,
  ..items.map(item => block(width: 100%, inset: 4mm, fill: rgb("#eaf0f7"), radius: 2mm)[
    #text(size: 10pt, fill: rgb("#53636a"), item.at(0))
    #linebreak()
    #text(size: 21pt, weight: "bold", fill: rgb("#24476a"), item.at(1))
  ])
)
