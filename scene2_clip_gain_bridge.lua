-- Optional Scene 2 *input-only* event bridge for existing nanoKONTROL owner.
-- Loaded by nanokontrol_resolve21.lua when placed next to init.lua.
-- No extra hs.midi.new/callback; NO Resolve setters and NO MIDI output.
-- Off by default; enabled explicitly via the existing NK JOG menu.
-- Python consumer: scripts/scene2_continuous_clip_gain.py.
return function(host, isReady)
  assert(type(host) == "table" and type(isReady) == "function")
  local bridge = {
    active = false, events = 0, lastScene = nil, lastCC = {},
    file = nil, timer = nil, ready = false,
    path = (os.getenv("HOME") or "") ..
      "/Library/Caches/nk-scene2-controller-events.csv",
  }

  local function epochMilliseconds()
    return math.floor(host.timer.secondsSinceEpoch() * 1000 + 0.5)
  end

  local function write(kind, channel, cc, value)
    if not bridge.active or not bridge.file then return false end
    local line = string.format("%d,%s,%d,%d,%d\n",
      epochMilliseconds(), kind, channel, cc, value)
    if not bridge.file:write(line) then
      host.printf("[NK SCENE2] input bridge write FAILED; disabled")
      bridge:stop()
      return false
    end
    bridge.file:flush() -- Python tailer requires low latency/freshness
    return true
  end

  function bridge:heartbeat()
    if not self.active then return end
    local ready = isReady() == true
    if self.ready and not ready then
      self.lastCC = {}    -- require new knob pickup upon focus return
      self.lastScene = nil
    end
    self.ready = ready
    write("H", 0, 0, ready and 1 or 0)
  end

  function bridge:start()
    if self.active then return true end
    if not os.getenv("HOME") then
      host.printf("[NK SCENE2] BLOCKED: HOME missing")
      return false
    end
    local f = io.open(self.path, "w")
    if not f then
      host.printf("[NK SCENE2] BLOCKED: input log cannot be opened")
      return false
    end
    self.file = f
    self.active = true
    self.ready = false
    self.lastScene = nil
    self.lastCC = {}
    self.events = 0
    self.file:write("# ts_ms,kind,channel,cc,value; H=heartbeat C=Scene2 CC R=reset\n")
    self.file:flush()
    self:heartbeat()
    self.timer = host.timer.doEvery(0.5, function() self:heartbeat() end)
    host.printf("[NK SCENE2] INPUT BRIDGE ENABLED; CH1 CC13..20; file=%s; no Resolve writes",
      self.path)
    return true
  end

  function bridge:stop()
    if not self.active then return end
    self.active = false
    if self.timer then self.timer:stop(); self.timer = nil end
    if self.file then self.file:flush(); self.file:close(); self.file = nil end
    host.printf("[NK SCENE2] INPUT BRIDGE STOP; captured=%d; no Resolve writes",
      self.events)
  end

  function bridge:publish(command, meta)
    if not self.active or command ~= "controlChange"
      or type(meta) ~= "table" then return end
    local ch, cc, value =
      meta.channel, meta.controllerNumber, meta.controllerValue
    if type(ch) ~= "number" or type(cc) ~= "number"
      or type(value) ~= "number" or ch < 0 or ch > 15
      or cc < 0 or cc > 127 or value < 0 or value > 127 then return end
    if not isReady() then
      if self.ready then self:heartbeat() end
      return
    end
    if ch ~= 1 then
      -- Scene1/3..5 must never be mistaken for Scene2 clip gain.
      if self.lastScene ~= ch then
        write("R", ch, cc, value)
        self.lastCC = {}
        self.lastScene = ch
      end
      return
    end
    if not (13 <= cc and cc <= 20) then return end
    if self.lastScene ~= 1 then
      self.lastCC = {}
      self.lastScene = 1
    end
    if self.lastCC[cc] == value then return end
    self.lastCC[cc] = value
    if write("C", ch, cc, value) then
      self.events = self.events + 1
    end
  end

  return bridge
end
