-- Keep a heading's first prose paragraph with the following reading unit.
-- Metadata is invisible and records the actual first-paragraph page.
function Blocks(blocks)
  local result = pandoc.List()
  local after_heading = false
  local heading_id = ''
  for _, block in ipairs(blocks) do
    if after_heading and block.t == 'Para' then
      result:insert(pandoc.RawBlock('typst', '#block(sticky: true)['))
      block.content:insert(1, pandoc.RawInline('typst', '#report-observation(' .. pandoc.json.encode(heading_id) .. ', "intro", "start")'))
      result:insert(block)
      result:insert(pandoc.RawBlock('typst', ']'))
      after_heading = false
    else
      result:insert(block)
      if block.t == 'Header' then
        after_heading = true
        heading_id = block.identifier
      elseif block.t ~= 'RawBlock' then
        after_heading = false
      end
    end
  end
  return result
end

function Div(div)
  if div.classes:includes('report-lead') then
    local blocks = pandoc.List({pandoc.RawBlock('typst', '#block(sticky: true)[')})
    blocks:extend(div.content)
    blocks:insert(pandoc.RawBlock('typst', ']'))
    return blocks
  end
end
