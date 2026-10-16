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
#set par(justify: true, leading: 0.85em, spacing: 1.1em, linebreaks: "optimized")
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => block(sticky: true, above: 6mm, below: 4mm)[#text(size: 19pt, fill: rgb("#24476a"), weight: "bold")[#it]]
#show heading.where(level: 2): it => block(sticky: true, above: 5mm, below: 3mm)[#text(size: 14pt, fill: rgb("#24476a"), weight: "bold")[#it]]
#show heading.where(level: 3): it => block(sticky: true, above: 3mm, below: 2mm)[#text(size: 11pt, weight: "bold")[#it]]
#show figure.caption: set text(size: 9pt, fill: rgb("#53636a"))
#show cite: it => { metadata("bioreport-citation"); it }
#show bibliography: it => context {
  if query(metadata.where(value: "bioreport-citation")).len() > 0 { it }
}
// Paths, versions and SHA256 hashes render in a monospace stack that still
// falls through to the CJK family for Chinese fragments.
#show raw: set text(font: report-mono-fonts, size: 8.5pt)
#let report-intro(body) = block(sticky: true, below: 3mm)[#text(body)]
#let report-cell(body) = text(body.replace("_", "_\u{200b}").replace("/", "/\u{200b}"))
#let report-figure(path, caption, ratio) = {
  let height = calc.min(170mm * ratio, 190mm)
  figure(
    image(path, width: 100%, height: height, fit: "contain"),
    caption: text(caption), supplement: [图], numbering: "1", placement: none,
  )
}
#let report-table(headers, rows, numeric) = {
  let widths = headers.map(h => if h in ("Description", "通路名称", "数据目录内路径", "统计口径") { 3fr } else if h in ("Gene ID", "Sample", "样本", "项目", "比较组") { 1.8fr } else { 1fr })
  block(breakable: true, above: 3mm, below: 3mm)[
    #set text(size: 9pt)
    #table(
      columns: widths, inset: (x: 5pt, y: 5.5pt),
      align: (x, y) => if numeric.at(x) { right } else { left },
      stroke: (x, y) => (bottom: .35pt + rgb("#dce3ec")),
      fill: (x, y) => if y == 0 { rgb("#eaf0f7") } else if calc.even(y) { rgb("#f6f9fc") } else { none },
      table.header(repeat: true, ..headers.map(h => text(weight: "bold", report-cell(h)))),
      ..rows.flatten().map(cell => report-cell(cell)),
    )
  ]
}
