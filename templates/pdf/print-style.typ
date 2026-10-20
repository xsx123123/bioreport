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
#set text(font: report-fonts, size: 10.5pt, lang: report-language)
// CJK glyphs need visibly more leading than Typst's Latin-tuned default.
// 正文两端对齐（justify）+ 首行缩进；标题、列表、代码与表格沿用默认左对齐。
// 不整体 set align —— 保持段落样式为默认，all:true 的首段缩进才在标题后生效。
#set par(justify: true, leading: 0.75em, spacing: 0.85em, linebreaks: "optimized",
  first-line-indent: (amount: 2em, all: true))
// 列表缩进对齐正文首行缩进（2em），使条目作为正文的次级层级呈现。
#set list(indent: 2em)
#set enum(indent: 2em)
#set heading(numbering: "1.1")
#let report-table-counter = counter("report-table")
#let report-figure-numbering(..nums) = {
  let chapter = counter(heading).at(here()).first()
  numbering("1-1", chapter, nums.pos().first())
}
#set figure(numbering: report-figure-numbering, supplement: [#(if report-language == "en" {"Figure"} else {"图"})#h(.25em)])
#show heading.where(level: 1): it => {
  // 一级章节开始时重置图计数，形成“图 章节-序号”（如图 8-1）。
  counter(figure.where(kind: image)).update(0)
  report-table-counter.update(0)
  block(sticky: true, above: 6mm, below: 4mm)[#text(size: 19pt, fill: rgb("#24476a"), weight: "bold")[#it]]
}
#show heading.where(level: 2): it => block(sticky: true, above: 5mm, below: 3mm)[#text(size: 14pt, fill: rgb("#24476a"), weight: "bold")[#it]]
#show heading.where(level: 3): it => block(sticky: true, above: 3mm, below: 2mm)[#text(size: 11pt, weight: "bold")[#it]]
#show heading.where(level: 4): it => block(sticky: true, above: 3mm, below: 2mm)[#text(size: 10.5pt, weight: "bold")[#it]]
#show heading.where(level: 5): it => block(sticky: true, above: 2mm, below: 1.5mm)[#text(size: 10.5pt, weight: "bold")[#it]]
#show heading.where(level: 6): it => block(sticky: true, above: 2mm, below: 1.5mm)[#text(size: 10.5pt, weight: "bold")[#it]]
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
  block(sticky: false)[#figure(
    [#report-observation(id, "figure", "image")#image(path, width: 100%, height: height, fit: "contain")],
    caption: [#report-observation(id, "figure", "caption")#text(caption)], placement: none,
  )]
}
#let report-continuation(id) = context {
  let rows = query(<bioreport-layout>).filter(it => it.value.kind == "table" and it.value.id == id and it.value.part.starts-with("row-"))
  if rows.len() > 0 and here().position().page > calc.min(..rows.map(it => it.value.page)) {
    report-observation(id, "table", "continuation")
    text(if report-language == "en" {"(continued)"} else {"（续表）"})
  }
}
#let report-table(headers, rows, numeric, keep-together: true, note: none, caption: "数据概览", id: "table") = layout(size => {
  let widths = headers.map(h => if h in ("满足阈值差异基因", "padj<0.05 基因数", "参与检验的基因总数", "DEGs Meeting Cutoffs", "Genes with padj < 0.05", "Genes Tested") { 1.7fr } else if h == "SHA256" { 4fr } else if h in ("Description", "通路名称", "数据目录内路径", "统计口径", "Path Relative to Data Directory", "Definition") { 3fr } else if h in ("Gene ID", "Sample", "样本", "项目", "比较组", "Item", "Comparison") { 1.8fr } else { 1fr })
  let body = [
    #report-table-counter.step()
    #block(width: 100%, sticky: true, below: 2mm)[
      #set par(first-line-indent: 0pt, justify: false)
      #align(left, context [
        #report-observation(id, "table", "caption")
        #text(size: 9.5pt, weight: "semibold", fill: rgb("#29445F"))[
          #{if report-language == "en" {"Table"} else {"表"}} #counter(heading).at(here()).first()-#report-table-counter.display("1") #h(.5em)#caption
        ]
      ])
    ]
    #set text(size: 8.8pt)
    #table(
      columns: widths, inset: (x: 6pt, y: 5pt),
      align: (x, y) => if y == 0 { center } else if numeric.at(x) { right } else { left },
      stroke: (x, y) => (bottom: .35pt + rgb("#dce3ec")),
      fill: (x, y) => if y == 0 { rgb("#315f65") } else if calc.even(y) { rgb("#f1f6f5") } else { rgb("#ffffff") },
      table.header(repeat: true, ..headers.enumerate().map(((j, h)) => [#if j == 0 { report-observation(id, "table", "header") }#text(weight: "bold", fill: rgb("#ffffff"), report-cell(if h == "满足阈值差异基因" {"阈值内差异基因"} else if h == "参与检验的基因总数" {"检验基因总数"} else {h}))#if j == 0 { report-continuation(id) }])),
      ..rows.enumerate().map(((i, row)) => row.enumerate().map(((j, cell)) =>
        [#if j == 0 { report-observation(id, "table", "row-" + str(i)) }#if headers.at(j) == "SHA256" { text(font: report-mono-fonts, cell) } else { report-cell(cell) }])).flatten(),
    )
  ]
  let fits = measure(body, width: size.width).height <= 225mm
  report-observation(id, "table", if keep-together and fits { "small" } else { "large" })
  block(breakable: not (keep-together and fits), sticky: false, above: 3mm, below: 3mm)[
    #body
    #if note != none { v(1.5mm); text(size: 9pt, fill: rgb("#53636a"))[#note] }
  ]
})

#let report-sha256-table(headers, rows, numeric, keep-together: true, note: none, caption: "数据概览", id: "table") = layout(size => {
  let body = [
    #report-table-counter.step()
    #block(width: 100%, sticky: true, below: 2mm)[
      #set par(first-line-indent: 0pt, justify: false)
      #align(left, context [#report-observation(id, "table", "caption")
        #text(size: 9.5pt, weight: "semibold", fill: rgb("#29445F"))[#{if report-language == "en" {"Table"} else {"表"}} #counter(heading).at(here()).first()-#report-table-counter.display("1") #h(.5em)#caption]])
    ]
    #set text(size: 8pt)
    #table(columns: (40mm, 58mm, 68mm), inset: (x: 6pt, y: 5pt), align: left,
      stroke: (x, y) => (bottom: .35pt + rgb("#dce3ec")),
      fill: (x, y) => if y == 0 { rgb("#315f65") } else if calc.even(y) { rgb("#f1f6f5") } else { rgb("#ffffff") },
      table.header(repeat: true, ..headers.enumerate().map(((j, h)) => [#if j == 0 { report-observation(id, "table", "header") }#text(weight: "bold", fill: rgb("#ffffff"), report-cell(if h == "满足阈值差异基因" {"阈值内差异基因"} else if h == "参与检验的基因总数" {"检验基因总数"} else {h}))#if j == 0 { report-continuation(id) }])),
      ..rows.enumerate().map(((i, row)) => row.enumerate().map(((j, cell)) =>
        [#if j == 0 { report-observation(id, "table", "row-" + str(i)) }#if j == 0 { text(size: 6.5pt, report-cell(cell)) } else if j == 2 { text(font: report-mono-fonts, size: 8pt, cell) } else { report-cell(cell) }])).flatten(),
    )
  ]
  let fits = measure(body, width: size.width).height <= 225mm
  report-observation(id, "table", if keep-together and fits { "small" } else { "large" })
  block(breakable: not (keep-together and fits), sticky: false, above: 3mm, below: 3mm)[
    #body
    #if note != none { v(1.5mm); text(size: 9pt, fill: rgb("#53636a"))[#note] }
  ]
})

// Pair / triplet / grid: preserve captions and move the reading unit together
// when it fits a page. Oversized groups flow without reducing typography.
#let report-figure-group(items, columns: 1) = layout(size => {
  let body = grid(columns: columns, gutter: 4mm, ..items)
  let fits = measure(body, width: size.width).height <= 110mm
  block(breakable: not fits, body)
})

#let report-metrics(items) = layout(size => {
  if items.len() == 0 { return [] }
  let label-width = (size.width - 8mm) / 3 - 8mm
  let labels = items.map(item => block(width: label-width)[
    #set par(justify: false, first-line-indent: 0pt, leading: .45em)
    #text(size: 10pt, fill: rgb("#53636a"), report-cell(item.at(0)))
  ])
  let label-height = calc.max(..labels.map(body => measure(body, width: label-width).height))
  grid(columns: (1fr, 1fr, 1fr), gutter: 4mm,
    ..items.enumerate().map(((i, item)) => block(width: 100%, breakable: false, inset: 4mm, fill: rgb("#eaf0f7"), radius: 2mm)[
      #report-observation("metric-" + str(i), "metric", "start")
      #set par(justify: false, first-line-indent: 0pt)
      #grid(rows: (label-height, auto), row-gutter: 1.5mm,
        labels.at(i),
        [#report-observation("metric-" + str(i), "metric", "value")#text(size: 21pt, weight: "bold", fill: rgb("#24476a"), item.at(1))],
      )
      #report-observation("metric-" + str(i), "metric", "end")
    ])
  )
})
