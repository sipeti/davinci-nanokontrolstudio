-- Scene 2 v1.5: automatic, quiet Hammerspoon session lifecycle.
-- Exactly one physical Korg MIDI listener; no dialog or project-name input.
return function(host, bridge, options)
  assert(type(host) == "table" and type(bridge) == "table")
  options = options or {}
  local home = os.getenv("HOME") or ""
  local base = home .. "/Library/Application Support/NK Scene2/"
  local runner = options.runner or (base .. "scripts/scene2_combined_bench.py")
  local python = options.python
  if not python then
    local f = io.open(base .. "resolve-python.path", "r")
    if f then python = f:read("*l"); f:close() end
    if not python or python == "" then python = "/opt/homebrew/bin/python3" end
  end
  local mcuPython = options.mcuPython or (base .. "venv/bin/python3")
  local logPath = options.logPath or (home .. "/Library/Logs/nk-scene2-session.log")
  local key = "nk-scene2-autostart-enabled"
  local enabled = not host.settings or host.settings.get(key) ~= false
  if options.autoEnabled ~= nil then enabled = options.autoEnabled end
  local ready = options.ready or function() return false end
  local appRunning = options.appRunning or function() return true end
  local clock = options.clock or function()
    if host.timer and host.timer.secondsSinceEpoch then
      return host.timer.secondsSinceEpoch()
    end
    return os.time()
  end
  local self = {
    task = nil, log = nil, timer = nil, stopping = false,
    enabled = enabled, retryAt = 0, shutdownRequested = false,
    lastError = nil, strip8Enabled = true, bankPagesEnabled = false
  }

  function self:isRunning()
    return self.task ~= nil and self.task:isRunning()
  end

  function self:isEnabled()
    return self.enabled
  end

  function self:isStrip8Enabled()
    return self.strip8Enabled
  end

  function self:isBankPagesEnabled()
    return self.bankPagesEnabled
  end

  function self:toggleBankPages()
    if self.shutdownRequested or not self.enabled then return false end
    -- The current MCU bank is host-controlled, not resettable by a
    -- speculative MIDI command. Leave the trial only from A1..A8.
    if self.bankPagesEnabled and
      (bridge.bankIndex ~= 0 or bridge.bankStatus ~= 1) then
      host.printf("[NK BANK] Return to confirmed A1-A8 with SELECT7 before disabling bank pages")
      if host.alert then
        host.alert.show("NK: elobb SELECT 7 -> A1-A8, majd bank lapozas KI", 4)
      end
      return false
    end
    self.bankPagesEnabled = not self.bankPagesEnabled
    if self.bankPagesEnabled then self.strip8Enabled = true end
    if self:isRunning() then
      self:stop()
    elseif self.task == nil then
      self.retryAt = 0
      self:ensureRunning()
    end
    return true
  end

  -- Default: all 8 MCU faders active. The current bank can contain Bus1
  -- in a smaller project, so users can turn strip8 off from NK JOG.
  -- No additional MIDI gate or protocol, no persistent setting.
  function self:toggleStrip8()
    if self.shutdownRequested or not self.enabled
      or self.bankPagesEnabled then return false end
    self.strip8Enabled = not self.strip8Enabled
    host.printf("[NK SCENE2] eighth MCU strip=%s (current Resolve bank)",
                tostring(self.strip8Enabled))
    if self:isRunning() then
      self:stop()  -- same workers restart and rearm physical pickup
    elseif self.task == nil then
      self.retryAt = 0
      self:ensureRunning()
    end
    return true
  end

  function self:stop()
    if not self:isRunning() or self.stopping then return false end
    self.stopping = true
    self.task:interrupt()
    return true
  end

  function self:pause()
    self.enabled = false
    if host.settings then host.settings.set(key, false) end
    self:stop()
    if bridge.active then bridge:stop() end
    return true
  end

  local function preflight()
    local files = {runner, python, mcuPython}
    for _, path in ipairs(files) do
      local f = io.open(path, "r")
      if not f then return false, "missing runtime: " .. path end
      f:close()
    end
    return true
  end

  function self:start()
    if self.shutdownRequested or not self.enabled or self.task ~= nil
      or self.stopping or not ready() then return false end
    local ok, reason = preflight()
    if not ok then
      if self.lastError ~= reason then
        host.printf("[NK SCENE2 AUTO] %s", reason)
        self.lastError = reason
      end
      self.retryAt = clock() + 10
      return false
    end
    if not bridge.active and not bridge:start() then
      self.retryAt = clock() + 10
      return false
    end
    local log, err = io.open(logPath, "a")
    if not log then
      host.printf("[NK SCENE2 AUTO] cannot write log: %s", tostring(err))
      self.retryAt = clock() + 10
      return false
    end
    self.log = log
    self.stopping = false
    self.lastError = nil
    local args = {
      runner, "--auto-run", "--mcu-python", mcuPython,
      "--resolve-python", python
    }
    if not self.strip8Enabled then
      args[#args + 1] = "--disable-strip8"
    end
    if self.bankPagesEnabled then
      args[#args + 1] = "--enable-bank-pages"
    end
    local function append(out, errText)
      if self.log then
        self.log:write(out or "", errText or "")
        self.log:flush()
      end
    end
    local task = host.task.new(python, function(code, out, errText)
      append(out, errText)
      self.task = nil
      if self.log then self.log:close(); self.log = nil end
      host.printf("[NK SCENE2 AUTO] exit=%s; requested_stop=%s",
                  tostring(code), tostring(self.stopping))
      -- Automatic retry is bounded, with fresh pickup on every worker start.
      self.retryAt = clock() + (self.stopping and 1 or 10)
      self.stopping = false
    end, function(_, out, errText)
      append(out, errText)
      return true
    end, args)
    if not task or not task:start() then
      if self.log then self.log:close(); self.log = nil end
      self.retryAt = clock() + 10
      return false
    end
    self.task = task
    host.printf("[NK SCENE2 AUTO] started; clip/mixer now follow Resolve")
    return true
  end

  function self:ensureRunning()
    if self.shutdownRequested or not self.enabled then return false end
    if self:isRunning() then
      if not appRunning() then self:stop() end
      return true
    end
    if self.task ~= nil or self.stopping or clock() < self.retryAt then
      return false
    end
    return self:start()
  end

  function self:resume()
    self.enabled = true
    if host.settings then host.settings.set(key, true) end
    self.retryAt = 0
    return self:ensureRunning()
  end

  function self:toggle()
    if self.enabled then return self:pause() end
    self:resume()
    return true
  end

  function self:shutdown()
    self.shutdownRequested = true
    if self.timer then self.timer:stop(); self.timer = nil end
    self:stop()
    if bridge.active then bridge:stop() end
  end

  -- Timer never prompts or starts a Resolve session when the app is absent.
  if options.timer ~= false and host.timer and host.timer.doEvery then
    self.timer = host.timer.doEvery(1.0, function() self:ensureRunning() end)
  end
  return self
end
