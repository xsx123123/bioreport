// Inspect actual heading locations rather than occurrences in the TOC.
#context {
  for it in query(heading) {
    let position = it.location().position()
    [#metadata((id: repr(it.body), kind: "heading", part: "start", page: position.page, y: position.y.pt()))<bioreport-layout>]
  }
}
