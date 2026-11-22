-- Reads the Hermes memory file (Obsidian Tasks emoji format) and lays out the skin.
-- Lua 5.1 has no \x escapes, so the emoji markers are written as decimal UTF-8 bytes.
local DUE = '\240\159\147\133'   -- 📅
local ADDED = '\226\158\149'     -- ➕
local DONE = '\226\156\133'      -- ✅
local DOT = '\194\183'           -- ·

local INK, MUTED, LINE = '230,236,234,255', '147,163,166,255', '52,64,63,255'
local COLORS = {
  bad = { '232,104,92,255', '232,104,92,31' },
  today = { '226,140,80,255', '226,140,80,31' },
  soon = { '45,184,166,255', '45,184,166,31' },
  past = { MUTED, nil },
}
local PAD, ROW_H, CHECK_EVERY = 16, 27, 5

function Initialize()
  path = SKIN:GetVariable('MemoryFile')
  W = tonumber(SKIN:GetVariable('Width'))
  maxTasks = tonumber(SKIN:GetVariable('MaxTasks'))
  maxEvents = tonumber(SKIN:GetVariable('MaxEvents'))
  mtime = SKIN:GetMeasure('MeasureMtime')
  tick, lastKey, shapeCount = 0, nil, 0
end

function Update()
  tick = tick + 1
  if tick % CHECK_EVERY ~= 1 then return '' end
  SKIN:Bang('!CommandMeasure', 'MeasureFolder', 'Update')
  local content = readFile(path)
  local stamp = mtime:GetStringValue()
  local today = os.date('*t')
  local key = (content or '<missing>') .. '|' .. stamp .. '|' .. os.date('%Y-%m-%d')
  if key ~= lastKey then
    lastKey = key
    render(content and parse(content), dayStart(today), stamp)
  end
  return ''
end

function readFile(p)
  local f = io.open(p, 'rb')
  if not f then return nil end
  local s = f:read('*a')
  f:close()
  return s
end

function dayStart(t)
  return os.time({ year = t.year, month = t.month, day = t.day, hour = 12 })
end

function toTime(iso)
  if not iso then return nil end
  local y, m, d = iso:match('^(%d%d%d%d)%-(%d%d)%-(%d%d)$')
  if not y then return nil end
  return os.time({ year = tonumber(y), month = tonumber(m), day = tonumber(d), hour = 12 })
end

function strip(s, marker)
  return (s:gsub(marker .. '%s*%S*', ''))
end

function parse(s)
  s = s:gsub('^\239\187\191', '')
  local tasks, events, section = {}, {}, nil
  for line in (s .. '\n'):gmatch('(.-)\r?\n') do
    local heading = line:match('^##%s+(.-)%s*$')
    if heading then
      section = heading:lower()
    elseif line:match('^%s*[-*] ') then
      local text = line:gsub('^%s*[-*] ', '')
      local box = text:match('^%[(.)%]')
      if box then text = text:gsub('^%[.%]%s*', '') end
      local due = text:match(DUE .. '%s*(%d%d%d%d%-%d%d%-%d%d)')
      text = strip(strip(strip(text, DUE), ADDED), DONE)
      text = text:gsub('%s*%^m%d+%s*$', ''):gsub('%s+', ' '):gsub('^ ', ''):gsub(' $', '')
      local item = { text = text, due = toTime(due), order = #tasks + #events }
      if section == 'tasks' and box ~= 'x' and box ~= 'X' then
        table.insert(tasks, item)
      elseif section == 'events' then
        table.insert(events, item)
      end
    end
  end
  local byDue = function(a, b)
    local da, db = a.due or math.huge, b.due or math.huge
    if da ~= db then return da < db end
    return a.order < b.order
  end
  table.sort(tasks, byDue)
  table.sort(events, byDue)
  return { tasks = tasks, events = events }
end

function daysBetween(t, today)
  return math.floor((t - today) / 86400 + 0.5)
end

function dateLabel(t, diff)
  if diff >= -6 and diff <= 6 then return os.date('%a %d', t):lower() end
  return os.date('%d %b', t):lower()
end

function taskBadge(item, today)
  if not item.due then return nil end
  local diff = daysBetween(item.due, today)
  if diff < 0 then return -diff .. 'd late', 'bad' end
  if diff == 0 then return 'today', 'today' end
  if diff == 1 then return 'tmrw', 'soon' end
  return dateLabel(item.due, diff), 'soon'
end

function eventBadge(item, today)
  if not item.due then return nil end
  local diff = daysBetween(item.due, today)
  if diff < 0 then return os.date('%d %b', item.due):lower(), 'past' end
  if diff == 0 then return 'today', 'today' end
  return dateLabel(item.due, diff), 'soon'
end

function set(meter, option, value)
  SKIN:Bang('!SetOption', meter, option, value)
end

function place(meter, x, y)
  set(meter, 'X', x)
  set(meter, 'Y', y)
  set(meter, 'Hidden', '0')
end

function hide(meter)
  set(meter, 'Hidden', '1')
end

function render(data, today, stamp)
  local shapes, sepAt = {}, nil
  local function shape(s) table.insert(shapes, s) end
  local function dropTrailingSep()
    if sepAt == #shapes then table.remove(shapes) end
  end
  local y = 44
  shape(('Line %d,%d,%d,%d | StrokeWidth 1.5 | Stroke Color 45,184,166,255'):format(PAD, y, W - PAD, y))
  y = y + 8

  local rows = 0
  local function row(text, badge, kind, marker, dim)
    rows = rows + 1
    local tm, bm = 'MeterRow' .. rows .. 'Text', 'MeterRow' .. rows .. 'Badge'
    if marker == 'box' then
      shape(('Rectangle %d,%d,11,11,3 | Fill Color 0,0,0,0 | StrokeWidth 1.5 | Stroke Color %s'):format(PAD, y + 8, MUTED))
    else
      shape(('Ellipse %d,%.1f,2.5 | StrokeWidth 0 | Fill Color %s'):format(PAD + 5, y + 13.5, MUTED))
    end
    local right = W - PAD
    if badge then
      local fg, bg = COLORS[kind][1], COLORS[kind][2]
      set(bm, 'Text', badge)
      set(bm, 'FontColor', fg)
      place(bm, 0, y + 7)
      SKIN:Bang('!UpdateMeter', bm)
      local bw = SKIN:GetMeter(bm):GetW()
      local bh = SKIN:GetMeter(bm):GetH()
      place(bm, right - bw - 6, y + 7)
      if bg then
        shape(('Rectangle %d,%d,%d,%d,4 | StrokeWidth 0 | Fill Color %s'):format(right - bw - 12, y + 6, bw + 12, bh + 2, bg))
      end
      right = right - bw - 12 - 8
    else
      hide(bm)
    end
    set(tm, 'Text', text)
    set(tm, 'FontColor', dim and MUTED or INK)
    set(tm, 'W', right - (PAD + 19))
    place(tm, PAD + 19, y + 4)
    y = y + ROW_H
    shape(('Line %d,%d,%d,%d | StrokeWidth 1 | Stroke Color 52,64,63,153'):format(PAD, y, W - PAD, y))
    sepAt = #shapes
  end

  local function note(text)
    set('MeterNote', 'Text', text)
    place('MeterNote', PAD, y + 4)
    y = y + ROW_H
  end

  hide('MeterNote')
  if not data then
    set('MeterHeader', 'Text', 'MEMORY FILE NOT FOUND')
    note('Check MemoryFile in Tasks.ini')
  else
    local open = #data.tasks
    set('MeterHeader', 'Text', open .. ' open ' .. DOT .. ' ' .. os.date('%a %d %b'):upper())
    for i = 1, math.min(open, maxTasks) do
      local b, k = taskBadge(data.tasks[i], today)
      row(data.tasks[i].text, b, k, 'box', false)
    end
    if open == 0 then
      note('All clear')
    elseif open > maxTasks then
      note('+' .. (open - maxTasks) .. ' more')
    end

    local events = {}
    for _, e in ipairs(data.events) do
      if not e.due or daysBetween(e.due, today) >= -7 then table.insert(events, e) end
    end
    if #events > 0 then
      dropTrailingSep()
      place('MeterLabel', PAD, y + 12)
      y = y + 30
      for i = 1, math.min(#events, maxEvents) do
        local b, k = eventBadge(events[i], today)
        row(events[i].text, b, k, 'dot', k == 'past')
      end
    else
      hide('MeterLabel')
    end
  end
  dropTrailingSep()

  for i = rows + 1, maxTasks + maxEvents do
    hide('MeterRow' .. i .. 'Text')
    hide('MeterRow' .. i .. 'Badge')
  end

  local synced = syncedLabel(stamp, today)
  if synced then
    set('MeterFooter', 'Text', synced)
    place('MeterFooter', W - PAD, y + 8)
    y = y + 24
  else
    hide('MeterFooter')
  end

  local H = y + PAD - 4
  set('MeterBg', 'Shape', ('Rectangle 0.5,0.5,%d,%d,10 | Fill Color 30,30,30,255 | StrokeWidth 1 | Stroke Color %s'):format(W - 1, H - 1, LINE))
  set('MeterGrid', 'W', W - 2)
  set('MeterGrid', 'H', H - 2)
  for i, s in ipairs(shapes) do
    set('MeterCanvas', i == 1 and 'Shape' or 'Shape' .. i, s)
  end
  for i = #shapes + 1, shapeCount do
    set('MeterCanvas', 'Shape' .. i, 'Rectangle 0,0,0,0 | StrokeWidth 0')
  end
  shapeCount = math.max(shapeCount, #shapes)
  SKIN:Bang('!UpdateMeter', '*')
  SKIN:Bang('!Redraw')
end

-- FileView reports the date in the system short format (en-GB: dd/MM/yyyy HH:mm).
function syncedLabel(stamp, today)
  local d, m, yr, hh, mm = stamp:match('(%d+)/(%d+)/(%d+)%D+(%d+):(%d+)')
  if not d then return nil end
  local t = os.time({ year = tonumber(yr), month = tonumber(m), day = tonumber(d), hour = 12 })
  if t == today then return 'synced ' .. hh .. ':' .. mm end
  return 'synced ' .. os.date('%d %b', t):lower()
end
