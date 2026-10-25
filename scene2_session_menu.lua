-- Optional Scene 2 test-session launcher. No MIDI callback, no auto-start.
-- Invoked only when operator selects START in the existing NK JOG menu.
return function(host, bridge, options)
  assert(type(host) == "table" and type(bridge) == "table")
  options = options or {}
  local home = os.getenv("HOME") or ""
  local runner = options.runner or
    (home .. "/Library/Application Support/NK Scene2/scripts/scene2_combined_bench.py")
  local python = options.python or "/opt/homebrew/bin/python3"
  -- Durable MCU dependencies. /tmp/nk-mcu-venv disappears after reboot.
  local mcuPython = options.mcuPython or
    (home .. "/Library/Application Support/NK Scene2/venv/bin/python3")
  local logPath = options.logPath or (home .. "/Library/Logs/nk-scene2-session.log")
  local project = options.project or "hajoagyu_261022 testing"
  local self = {task = nil, log = nil, stopping = false}

  function self:isRunning()
    return self.task ~= nil and self.task:isRunning()
  end

  function self:stop()
    if not self:isRunning() then return false end
    self.stopping = true
    self.task:interrupt() -- parent sends SIGINT to both workers in finally
    return true
  end

  function self:start()
    if self:isRunning() then return true end
    local file = io.open(runner, "r")
    if not file then
      host.alert.show("Scene 2 tesztindito hianyzik: telepitsd a scripts mappat", 6)
      return false
    end
    file:close()
    local venv = io.open(mcuPython, "r")
    if not venv then
      host.alert.show("Scene 2 MCU Python hianyzik: telepitsd a tartos venv-et", 6)
      return false
    end
    venv:close()
    local choice = host.dialog.blockAlert(
      "Scene 2 TEST: kliphangero + Fairlight mixer",
      "Csak a mentett '" .. project ..
      "' projektben! A forgopotik tenylegesen modositjak a klipeket, "
      .. "a tolopotik a mixert. Leallitashoz NK JOG > Scene 2 TEST: STOP.",
      "Inditas", "Megse", "warning")
    if choice ~= "Inditas" then return false end
    if not bridge.active and not bridge:start() then
      host.alert.show("Scene 2 input bridge inditasa sikertelen", 6)
      return false
    end
    self.log = io.open(logPath, "w")
    if not self.log then
      host.alert.show("Scene 2 log nem irhato: " .. logPath, 6)
      return false
    end
    self.stopping = false
    local args = {
      runner, "--run-until-stopped", "--low-latency",
      "--mcu-python", mcuPython,
      "--write-test-copy", "--expected-project", project,
      "--confirmed-backup", "--confirmed-no-automation",
      "--max-clip-writes", "0"
    }
    local function append(out, err)
      if self.log then
        self.log:write(out or "", err or "")
        self.log:flush()
      end
    end
    local task = host.task.new(python, function(code, out, err)
      append(out, err)
      self.task = nil
      if self.log then self.log:close(); self.log = nil end
      host.printf("[NK SCENE2 SESSION] exit=%s stopped=%s log=%s",
        tostring(code), tostring(self.stopping), logPath)
      if not self.stopping and code ~= 0 then
        host.alert.show("Scene 2 teszt leallt: nezd meg a logot", 6)
      end
      self.stopping = false
    end, function(_, out, err)
      append(out, err) -- stream; don't let long-running hs.task buffers fill
      return true
    end, args)
    if not task or not task:start() then
      if self.log then self.log:close(); self.log = nil end
      host.alert.show("Scene 2 Python folyamat inditasa sikertelen", 6)
      return false
    end
    self.task = task
    host.alert.show("Scene 2 teszt aktiv (STOP: NK JOG menu)", 3)
    return true
  end

  function self:toggle()
    if self:isRunning() then return self:stop() end
    return self:start()
  end

  return self
end
