-- Optional Scene2 event bridge for existing nanoKONTROL MIDI owner.
-- 1 physical Korg hs.midi callback. No Resolve setters, no second listener.
-- Emits clip CC13..20 (C) and candidate MCU faders/buttons (M).
-- Only Fairlight->IAC host feedback can set Scene2 mixer LED states.
-- OFF by default in NK JOG menu. Python consumers are separate processes.
return function(host, isReady)
  assert(type(host) == "table" and type(isReady) == "function")
  local bridge = {
    active = false, events = 0, lastScene = nil, lastCC = {},
    file = nil, timer = nil, ready = false,
    ledSender = nil, ledKnown = {}, lastFeedbackHeartbeat = 0,
    bankIndex = 0, bankStatus = 1, bankListener = nil,
    path = (os.getenv("HOME") or "") ..
      "/Library/Caches/nk-scene2-controller-events.csv",
    feedbackPath = (os.getenv("HOME") or "") ..
      "/Library/Caches/nk-fairlight-mcu-feedback.csv",
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

  -- MIDI feedback is authoritative. No state is inferred from a physical
  -- MUTE/SOLO press, nor from physical MIDI echo. The existing controller
  -- calls setLedSender with its scoped Scene2 MIDI output route.
  function bridge:setLedSender(sender)
    assert(type(sender) == "function")
    self.ledSender = sender
  end

  function bridge:setBankListener(listener)
    assert(type(listener) == "function")
    self.bankListener = listener
  end

  function bridge:clearFeedback()
    if self.ledSender then
      for cc in pairs(self.ledKnown) do self.ledSender(cc, false) end
    end
    self.ledKnown = {}
    self.lastFeedbackHeartbeat = 0
  end

  function bridge:pollFeedback()
    if not self.active or not self.ledSender then return end
    local now = epochMilliseconds()
    local f = io.open(self.feedbackPath, "r")
    if not f then
      if now - self.lastFeedbackHeartbeat > 1800 then self:clearFeedback() end
      return
    end
    local size = f:seek("end") or 0
    -- Read only a bounded tail. No unbounded log growth or file owner races.
    local pos = math.max(0, size - 4096)
    f:seek("set", pos)
    if pos > 0 then f:read("*l") end
    -- The tail is already capped at 4096 BYTES. A separate 150-LINE
    -- limit skipped the MOST RECENT heartbeat and LED updates after a
    -- long session: at 2 Hz the compact CSV contains >150 lines in 4KB.
    -- Read the full bounded tail so we never miss its newest entries.
    for line in f:lines() do
      local stamp, kind, cc, value =
        line:match("^(%d+),([HLB]),(%d+),(%d+)$")
      stamp, cc, value = tonumber(stamp), tonumber(cc), tonumber(value)
      if stamp and stamp <= now and now - stamp <= 1800 then
        if kind == "H" and cc == 0 and value == 0 then
          self:clearFeedback()
        elseif kind == "H" and cc == 0 and value == 1 then
          self.lastFeedbackHeartbeat = stamp
        elseif kind == "B" and (cc == 0 or cc == 1)
          and (value == 0 or value == 1 or value == 2) then
          -- B is written by the ACTUAL MCU worker, never inferred
          -- from a physical SELECT press: 0=pending, 1=8 host faders
          -- observed, 2=unconfirmed. The first bank is the baseline.
          local changed = cc ~= self.bankIndex or value ~= self.bankStatus
          self.bankIndex, self.bankStatus = cc, value
          if value ~= 1 then
            -- While bank translation is pending/uncertain, old-bank
            -- Fairlight MUTE/SOLO LED states must not be shown as current.
            for ledCC in pairs(self.ledKnown) do
              if (ledCC >= 21 and ledCC <= 31) or
                (ledCC >= 33 and ledCC <= 37) then
                self.ledSender(ledCC, false)
                self.ledKnown[ledCC] = nil
              end
            end
          end
          for bankCC=52,53 do
            local desired = (value == 1 and
              ((bankCC == 52 and cc == 0) or
               (bankCC == 53 and cc == 1))) and 127 or 0
            if self.ledKnown[bankCC] ~= desired then
              self.ledKnown[bankCC] = desired
              self.ledSender(bankCC, desired == 127)
            end
          end
          if changed and self.bankListener then
            self.bankListener(cc, value)
          end
        elseif kind == "L" and cc and value
          and ((21 <= cc and cc <= 28)
            or (cc >= 29 and cc <= 31)
            or (cc >= 33 and cc <= 37))
          and (value == 0 or value == 127)
          and now - self.lastFeedbackHeartbeat <= 1800 then
          if self.ledKnown[cc] ~= value then
            local delivered = self.ledSender(cc, value == 127)
            self.ledKnown[cc] = value
            host.printf("[NK SCENE2 LED RX] Fairlight cc=%d state=%d "
              .. "Korg_sent=%s physicalScene=%s",
              cc, value, tostring(delivered), tostring(self.lastScene))
          end
        end
      end
    end
    f:close()
    if now - self.lastFeedbackHeartbeat > 1800 then
      self:clearFeedback()
    elseif self.lastScene == 1 then
      -- Reassert only Fairlight-authoritative LEDs for the active Korg Scene2.
      -- The Korg blanks LEDs on silent Scene switches without a host update.
      for cc, value in pairs(self.ledKnown) do
        self.ledSender(cc, value == 127)
      end
    end
  end

  function bridge:heartbeat()
    if not self.active then return end
    local ready = isReady() == true
    local lostFocus = self.ready and not ready
    self.ready = ready
    write("H", 0, 0, ready and 1 or 0)
    if not ready then
      -- Turn off the last actual Fairlight host LEDs BEFORE revoking
      -- physical Scene2 ownership. Otherwise OFF is skipped by sender.
      self:clearFeedback()
      if lostFocus then
        self.lastCC = {} -- require new pickup on focus return
        self.lastScene = nil
      end
    else
      self:pollFeedback()
    end
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
    self.ledKnown = {}
    self.lastFeedbackHeartbeat = 0
    self.bankIndex, self.bankStatus = 0, 1
    self.file:write("# ts_ms,kind,channel,cc,value; H=heartbeat C=clip M=mixer B=bank R=reset\n")
    self.file:flush()
    self:heartbeat()
    self.timer = host.timer.doEvery(0.5, function() self:heartbeat() end)
    host.printf("[NK SCENE2] INPUT BRIDGE ENABLED; CH1 clip CC13..20 + candidate mixer CCs; file=%s; no Resolve writes",
      self.path)
    return true
  end

  function bridge:stop()
    if not self.active then return end
    self.active = false
    if self.timer then self.timer:stop(); self.timer = nil end
    if self.file then self.file:flush(); self.file:close(); self.file = nil end
    self:clearFeedback()
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
      -- Korg does NOT signal SCENE changes until a physical CC arrives.
      -- On first other-scene CC, blank Scene2's physical mixer LEDs,
      -- but RETAIN the last Fairlight-authoritative state in case it
      -- remains connected/gets refreshed before returning to Scene2.
      if self.lastScene == 1 and self.ledSender then
        for ledCC in pairs(self.ledKnown) do
          self.ledSender(ledCC, false)
        end
      end
      if self.lastScene ~= ch then
        write("R", ch, cc, value)
        self.lastCC = {}
        self.lastScene = ch
      end
      return
    end
    local kind = nil
    if cc >= 13 and cc <= 20 then
      kind = "C" -- proven clip gain rotary mapping
    elseif cc == 52 or cc == 53 then
      kind = "B" -- Scene2 SELECT7/8 -> MCU bank left/right
    elseif (cc >= 2 and cc <= 6) or cc == 8 or cc == 9 or cc == 12
      or (cc >= 21 and cc <= 31)
      or (cc >= 33 and cc <= 37) then
      kind = "M" -- physical Scene2 mixer CC candidate: confirm on hardware
    end
    if not kind then return end
    if self.lastScene ~= 1 then
      self.lastCC = {}
      self.lastScene = 1
    end
    if self.lastCC[cc] == value then return end
    self.lastCC[cc] = value
    if write(kind, ch, cc, value) then
      self.events = self.events + 1
    end
  end

  return bridge
end
