-- Standalone timestamped MIDI evidence for Scene 1 vs Scene 2 rotary 4.
-- INPUT ONLY. No Resolve access, shortcut generation, MIDI output or settings.
-- Hammerspoon Console:
-- dofile("/tmp/nk-scene2-timestamped.lua")
-- nkMidiTs.mark("SCENE1"); turn physical rotary 4 on Scene 1.
-- Change physical Korg scene.
-- nkMidiTs.mark("SCENE2"); turn physical rotary 4 on Scene 2.
-- nkMidiTs.stop()
if type(_G.nkMidiTs) == "table"
  and type(_G.nkMidiTs.stop) == "function" then
  _G.nkMidiTs.stop()
end

local home = os.getenv("HOME")
if not home then
  hs.printf("[NK TS] BLOCKED: HOME unavailable; WRITES=0")
  return nil
end
local deviceName
for _, name in ipairs(hs.midi.devices()) do
  local lower = name:lower()
  if lower:find("nanokontrol", 1, true)
    and lower:find("studio", 1, true) then
    deviceName = name
    break
  end
end
if not deviceName then
  hs.printf("[NK TS] BLOCKED: nanoKONTROL Studio unavailable; WRITES=0")
  return nil
end
local device = hs.midi.new(deviceName)
if not device then
  hs.printf("[NK TS] BLOCKED: cannot open MIDI device; WRITES=0")
  return nil
end
local startNs = hs.timer.absoluteTime()
local basename = string.format("nk-midi-timestamped-%s-%d.csv",
  os.date("!%Y%m%dT%H%M%SZ"),
  math.floor(startNs / 1000000) % 100000000)
local path = home .. "/Library/Caches/" .. basename
local file = io.open(path, "w")
if not file then
  hs.printf("[NK TS] BLOCKED: cannot open timestamped CSV; WRITES=0")
  device:callback(nil)
  return nil
end

local probe = {
  device = device, file = path, phase = "UNMARKED",
  active = true, events = 0, count = {}, samples = {},
  timer = nil,
}

local function timeParts()
  local wall = hs.timer.secondsSinceEpoch()
  return math.floor(wall * 1000 + 0.5),
    math.floor((hs.timer.absoluteTime() - startNs) / 1000000 + 0.5)
end

local function safeField(value)
  return tostring(value or ""):gsub("[\r\n,]", " ")
end

local function record(kind, ch, cc, value, raw, midiTimestamp)
  local epochMs, elapsedMs = timeParts()
  local line = string.format("%s,%d,%d,%s,%s,%s,%s,%s,%s\n",
    kind, epochMs, elapsedMs, probe.phase,
    ch == nil and "" or tostring(ch),
    cc == nil and "" or tostring(cc),
    value == nil and "" or tostring(value),
    safeField(raw), safeField(midiTimestamp))
  local result = file:write(line)
  if not result then
    hs.printf("[NK TS] CSV_WRITE_FAILED; stopping; WRITES=0")
    probe.stop()
    return nil
  end
  return epochMs, elapsedMs
end

function probe.mark(phase)
  if not probe.active then return false end
  if phase ~= "SCENE1" and phase ~= "SCENE2" then
    hs.printf("[NK TS] INVALID_MARKER: only SCENE1 or SCENE2")
    return false
  end
  probe.phase = phase
  if not record("MARK") then return false end
  file:flush()
  hs.printf("[NK TS] MARK=%s; turn ONLY rotary 4; WRITES=0", phase)
  return true
end

function probe.stop()
  if not probe.active then return end
  probe.active = false
  if probe.timer then probe.timer:stop(); probe.timer = nil end
  device:callback(nil)
  file:flush()
  file:close()
  if _G.nkMidiTs == probe then _G.nkMidiTs = nil end
  hs.printf("[NK TS] STOP; EVENTS=%d; WRITES=0", probe.events)
  local keys = {}
  for key in pairs(probe.count) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do
    local sample = probe.samples[key]
    hs.printf("[NK TS] %s COUNT=%d FIRST_MS=%d RAW=%s",
      key, probe.count[key], sample.ms, sample.raw)
  end
  hs.printf("[NK TS] FILE=%s", path)
end

file:write("kind,epoch_ms,elapsed_ms,phase,channel,cc,value,raw_hex,midi_timestamp\n")
file:flush()

device:callback(function(_, _, command, _, meta)
  if not probe.active or command ~= "controlChange"
    or type(meta) ~= "table" then return end
  local ch, cc, value =
    meta.channel, meta.controllerNumber, meta.controllerValue
  if type(ch) ~= "number" or type(cc) ~= "number"
    or type(value) ~= "number"
    or ch < 0 or ch > 15 or cc < 0 or cc > 127
    or value < 0 or value > 127 then return end
  -- The Hammerspoon input channel is 0..15 (distinct from MIDI
  -- output sendCommand where channel 0 has all-channels semantics).
  local raw = meta.data or ""
  local epochMs, elapsedMs = record("CC", ch, cc, value, raw, meta.timestamp)
  if not epochMs then return end
  probe.events = probe.events + 1
  local key = string.format("%s CHANNEL=%d CC=%d",
    probe.phase, ch, cc)
  probe.count[key] = (probe.count[key] or 0) + 1
  if not probe.samples[key] then
    probe.samples[key] = {ms=elapsedMs, raw=safeField(raw)}
  end
  if probe.events % 100 == 0 then file:flush() end
  if probe.events >= 12000 then
    hs.printf("[NK TS] EVENT_CAP=12000; auto stop; WRITES=0")
    probe.stop()
  end
end)
_G.nkMidiTs = probe
probe.timer = hs.timer.doAfter(120, function()
  if probe.active then
    hs.printf("[NK TS] TIMEOUT=120s; stopping; WRITES=0")
    probe.stop()
  end
end)
hs.printf("[NK TS] READY; mark SCENE1, rotate knob4; mark SCENE2, rotate knob4; then stop(); WRITES=0")
return probe
