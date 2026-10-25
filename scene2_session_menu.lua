-- Optional Scene 2 per-project session launcher. Never owns MIDI input.
-- All audio writes require an explicit project name and user confirmation.
return function(host, bridge, options)
  assert(type(host) == "table" and type(bridge) == "table")
  options = options or {}
  local home = os.getenv("HOME") or ""
  local runner = options.runner or
    (home .. "/Library/Application Support/NK Scene2/scripts/scene2_combined_bench.py")
  local python = options.python
  if not python then
    local saved = io.open(
      home .. "/Library/Application Support/NK Scene2/resolve-python.path", "r")
    if saved then
      python = saved:read("*l")
      saved:close()
    end
    if not python or python == "" then python = "/opt/homebrew/bin/python3" end
  end
  local mcuPython = options.mcuPython or
    (home .. "/Library/Application Support/NK Scene2/venv/bin/python3")
  local logPath = options.logPath or (home .. "/Library/Logs/nk-scene2-session.log")
  local settingsKey = "nk-scene2-last-approved-project"
  local defaultProject = options.project or
    (host.settings and host.settings.get(settingsKey)) or ""
  local self = {task = nil, log = nil, stopping = false}

  function self:isRunning()
    return self.task ~= nil and self.task:isRunning()
  end

  function self:stop()
    if not self:isRunning() then return false end
    self.stopping = true
    self.task:interrupt() -- parent SIGINT; workers release MCU TOUCH/buttons
    return true
  end

  function self:start()
    if self:isRunning() then return true end
    local file = io.open(runner, "r")
    if not file then
      host.alert.show("Scene 2 Python indito nincs telepitve", 6)
      return false
    end
    file:close()
    local venv = io.open(mcuPython, "r")
    if not venv then
      host.alert.show("Scene 2 MIDI Python-kornyezet hianyzik", 6)
      return false
    end
    venv:close()

    local button, project = host.dialog.textPrompt(
      "Scene 2: Resolve projekt engedelyezese",
      "Add meg a Resolve-ban megnyitott projekt PONTOS nevet. " ..
      "Mas projektben a hangeroiras le lesz tiltva.",
      defaultProject, "Tovabb", "Megse")
    if button ~= "Tovabb" or not project then return false end
    project = project:match("^%s*(.-)%s*$")
    if project == "" or #project > 200 then
      host.alert.show("Scene 2: ervenytelen projektnev", 5)
      return false
    end

    local choice = host.dialog.blockAlert(
      "Scene 2: valodi hangeroiras",
      "Projekt: " .. project ..
      "\nMegvan a projektmentes? A lejátszas ALL, nincs gain keyframe " ..
      "vagy Fairlight hangerőautomatizacio? A forgopotik a klipek " ..
      "AudioVolume erteket, a tolopotik a Fairlight mixert allitjak.",
      "Inditas", "Megse", "warning")
    if choice ~= "Inditas" then return false end

    if not bridge.active and not bridge:start() then
      host.alert.show("Scene 2 MIDI bridge inditasa sikertelen", 6)
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
      "--mcu-python", mcuPython, "--write-approved-project",
      "--allow-named-project", "--expected-project", project,
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
        host.alert.show("Scene 2 megallt: nezd meg a session naplot", 6)
      end
      self.stopping = false
    end, function(_, out, err)
      append(out, err)
      return true
    end, args)
    if not task or not task:start() then
      if self.log then self.log:close(); self.log = nil end
      host.alert.show("Scene 2 Python inditas sikertelen", 6)
      return false
    end
    self.task = task
    defaultProject = project
    if host.settings then host.settings.set(settingsKey, project) end
    host.alert.show("Scene 2 aktiv - STOP: NK JOG menu", 3)
    return true
  end

  function self:toggle()
    if self:isRunning() then return self:stop() end
    return self:start()
  end
  return self
end
