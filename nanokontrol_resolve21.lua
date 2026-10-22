-- KORG nanoKONTROL Studio -> DaVinci Resolve 21 (macOS) | v1.2
-- No external Lua modules; needs Hammerspoon and Korg Assignable mode.
-- First connection launches a MIDI learn wizard; bindings persist in hs.settings.

local hs = hs
local KEY = "nanokontrol_studio_resolve21_v1"
local cfg = hs.settings.get(KEY)
local enabled, mode, speed = true, "JOG", 0
local midi, deviceName = nil, nil
-- Wheel shuttle emits RELATIVE steps. Coalesce bursts without dropping MIDI pulses.
local SHUTTLE_BATCH_SECONDS = 0.065
local SHUTTLE_PULSES_PER_GEAR = 4
local shuttlePending, shuttleBatchTimer, shuttleKeyTimers = 0, nil, {}
local learning, learned, learnIndex = false, nil, 0
-- Hold MARKER SET to nudge a selected edit with the jog wheel. Release exits.
local trimHeld = false
-- One-shot MIDI learn for SELECT 5; keep the original 24-button calibration.
local extraLearning = false
local splitBusy = false
-- Experimental FADER 1 shuttle: armed only after physically entering center.
local faderLearning, faderCandidate = false, nil
local faderArmed, faderActive, faderValue = false, false, nil
local faderTimer, faderQueued = nil, nil
local activeShuttleSource = nil
local ledFeedbackEnabled = false -- opt-in, Korg Global LED Mode must be External
local ledState = {transport = nil, page = nil, camera = nil, editmode = nil}
local ledEchoUntil = {}

-- The large wheel must be set in KORG KONTROL Editor:
-- Jog Wheel Type = Sign Magnitude, Acceleration = Const.
local steps = {
  {"cycle", "CYCLE (JOG / SHUTTLE)"},
  {"begin", "|< (ugras a musor elejere)"},
  {"rew", "REW / <<"}, {"ff", "FF / >>"},
  {"stop", "STOP"}, {"play", "PLAY"},
  {"undo", "nagy REC (UNDO)"},
  {"trackPrev", "TRACK balra (elozo vagas)"},
  {"trackNext", "TRACK jobbra (kovetkezo vagas)"},
  {"editSelect", "MARKER SET (vagaspont kivalasztasa)"},
  {"trimLeft", "MARKER balra (-1 frame)"},
  {"trimRight", "MARKER jobbra (+1 frame)"},
  {"cam1", "MUTE 1 - kamera 1"}, {"cam2", "MUTE 2 - kamera 2"},
  {"cam3", "MUTE 3 - kamera 3"}, {"cam4", "MUTE 4 - kamera 4"},
  {"inPoint", "MUTE 5 - IN"}, {"outPoint", "MUTE 6 - OUT"},
  {"clearIO", "MUTE 7 - IN/OUT torles"},
  {"escape", "MUTE 8 - vissza a tobbkameras nezetbe"},
  {"cutPage", "SELECT 1 - CUT oldal"},
  {"editPage", "SELECT 2 - EDIT oldal"},
  {"trimMode", "SELECT 3 - TRIM mod"},
  {"normalMode", "SELECT 4 - normal kijeloles"},
}

local function toast(message, duration)
  hs.alert.show(message, duration or 2.5)
end

local function resolveApp()
  local app = hs.application.frontmostApplication()
  if not app then return nil end
  local name = (app:title() or ""):lower()
  local bundle = (app:bundleID() or ""):lower()
  if name:find("davinci resolve", 1, true)
     or bundle:find("davinciresolve", 1, true) then
    return app
  end
  return nil
end

local function isResolveFrontmost()
  return resolveApp() ~= nil
end

local function key(character, modifiers, delay)
  -- 10 ms is more reliable for Resolve than the previous 1 ms pulse.
  hs.eventtap.keyStroke(modifiers or {}, character, delay or 10000)
end

local function switchPage(page)
  local app = resolveApp()
  if not app then
    toast("NK: aktiv Resolve ablak szukseges", 2.5)
    return
  end
  -- Native Workspace menu bypasses Shift+3/4 keyboard layout collisions.
  local ok, chosen = pcall(function()
    return app:selectMenuItem({"Workspace", "Switch to Page", page})
  end)
  if ok and chosen then
    hs.printf("[NK] Workspace > Switch to Page > %s", page)
    return true
  end
  -- Safe failure: do NOT send Shift+3 (can trigger different editing action).
  hs.printf("[NK] Workspace > Switch to Page > %s not accessible", page)
  toast("NK: Workspace > Switch to Page > " .. page .. " nem elerheto", 3)
  return false
end



local menu = hs.menubar.new()

-- Local feedback is the last command requested here, not verified Resolve state.
local ledButtonNames = {"cycle", "play", "stop", "rew", "ff", "cam1", "cam2",
  "cam3", "cam4", "cutPage", "editPage", "trimMode", "normalMode", "editSelect",
  "splitAll", "undo"}
local function ledWanted(name)
  if name == "cycle" then return mode == "SHUTTLE" end
  for _, group in ipairs({"transport", "page", "camera", "editmode"}) do
    if ledState[group] == name then return true end
  end
  return false
end
local function sendLED(name, on)
  if not midi or not cfg or not cfg.buttons then return false end
  local signal = cfg.buttons[name]
  if type(signal) ~= "string" then return false end
  local channel, number = signal:match("^cc:(%d+):(%d+)$")
  local cmd, meta
  if channel then
    cmd = "controlChange"
    meta = {channel = tonumber(channel), controllerNumber = tonumber(number),
      controllerValue = on and 127 or 0}
  else
    channel, number = signal:match("^note:(%d+):(%d+)$")
    if not channel then return false end
    cmd = on and "noteOn" or "noteOff"
    meta = {channel = tonumber(channel), note = tonumber(number), velocity = on and 127 or 64}
  end
  local value = cmd == "controlChange" and meta.controllerValue or (on and 127 or 64)
  ledEchoUntil[signal .. ":" .. tostring(value)] = hs.timer.secondsSinceEpoch() + 0.08
  local ok, sent = pcall(function() return midi:sendCommand(cmd, meta) end)
  return ok and sent ~= false
end
local function refreshLEDs()
  if not ledFeedbackEnabled then return end
  for _, name in ipairs(ledButtonNames) do sendLED(name, ledWanted(name)) end
end
local function clearLEDs()
  for _, name in ipairs(ledButtonNames) do sendLED(name, false) end
end
local function setLedState(group, name)
  ledState[group] = name
  refreshLEDs()
end
local function flashLED(name, seconds)
  if not ledFeedbackEnabled then return end
  sendLED(name, true)
  hs.timer.doAfter(seconds or 0.18, function()
    if ledFeedbackEnabled then sendLED(name, false) end
  end)
end
local function toggleLEDFeedback()
  if not midi or not cfg then toast("NK: elobb csatlakoztasd a Korgot", 3); return end
  if ledFeedbackEnabled then
    clearLEDs()
    ledFeedbackEnabled = false
    toast("NK: LED feedback KI", 2)
  else
    ledFeedbackEnabled = true
    refreshLEDs()
    toast("NK: LED feedback BE - Korg Global LED Mode: External", 4)
  end
end
local function isLEDReflection(signal, value)
  local tag = signal .. ":" .. tostring(value)
  local deadline = ledEchoUntil[tag]
  if not deadline then return false end
  ledEchoUntil[tag] = nil
  return hs.timer.secondsSinceEpoch() < deadline
end

local function updateTitle()
  local title = "NK " .. (trimHeld and "TRIM" or mode)
  if activeShuttleSource == "fader" and speed ~= 0 then
    title = "NK FADER " .. (speed > 0 and "+" or "") .. tostring(speed)
  elseif mode == "SHUTTLE" and speed ~= 0 then
    title = title .. " " .. (speed > 0 and "+" or "") .. tostring(speed)
  end
  if not enabled then title = "NK OFF" end
  if learning then title = "NK SETUP" end
  menu:setTitle(title)
end

local function cancelShuttle()
  if shuttleBatchTimer then shuttleBatchTimer:stop(); shuttleBatchTimer = nil end
  for _, t in ipairs(shuttleKeyTimers) do t:stop() end
  shuttleKeyTimers = {}
  shuttlePending = 0
end

local function stopPlayback()
  cancelShuttle()
  if faderTimer then faderTimer:stop(); faderTimer = nil end
  faderQueued = nil
  key("k")
  speed = 0
  activeShuttleSource = nil
  faderArmed, faderActive = false, false
  updateTitle()
end

local function switchMode()
  stopPlayback()  -- no queued J/L events can resume after STOP
  mode = (mode == "JOG") and "SHUTTLE" or "JOG"
  updateTitle()
  toast("KORG wheel: " .. mode)
end

local function setShuttle(target, source)
  target = math.max(-4, math.min(4, target))
  source = source or "wheel"
  if target == speed and (target == 0 or activeShuttleSource == source) then return end
  for _, t in ipairs(shuttleKeyTimers) do t:stop() end
  shuttleKeyTimers = {}
  key("k")
  speed = target
  activeShuttleSource = target == 0 and nil or source
  updateTitle()
  if target == 0 then return end
  local direction = target > 0 and "l" or "j"
  for n = 1, math.abs(target) do
    local t = hs.timer.doAfter(0.025 + (n - 1) * 0.070, function()
      if enabled and activeShuttleSource == source and
         (source == "fader" or mode == "SHUTTLE") and isResolveFrontmost() then
        key(direction)
      end
    end)
    shuttleKeyTimers[#shuttleKeyTimers + 1] = t
  end
end

local function flushShuttle()
  shuttleBatchTimer = nil
  local pulses = shuttlePending
  shuttlePending = 0
  if pulses == 0 or not enabled or mode ~= "SHUTTLE" or not isResolveFrontmost() then
    return
  end
  local amount = 1 + math.floor((math.abs(pulses) - 1) / SHUTTLE_PULSES_PER_GEAR)
  local delta = pulses > 0 and amount or -amount
  if not faderActive then setShuttle(speed + delta, "wheel") end
end

-- Center = MIDI values 60..68. Outside: reverse/forward up to four JKL gears.
local function faderLevel(value)
  if value >= 60 and value <= 68 then return 0 end
  if value < 60 then return -math.min(4, math.ceil((60 - value) / 15)) end
  return math.min(4, math.ceil((value - 68) / 15))
end
local function faderShuttle(value)
  if type(value) ~= "number" or value < 0 or value > 127 then return end
  faderValue = value
  local target = faderLevel(value)
  if not faderArmed then
    if target == 0 then
      faderArmed = true
      toast("NK: FADER 1 aktiv (kozepalas utan)", 1.6)
    end
    return
  end
  if target == 0 then
    if faderTimer then faderTimer:stop(); faderTimer = nil end
    faderQueued = nil
    if faderActive or activeShuttleSource == "fader" then
      faderActive = false
      setShuttle(0, "fader")
    end
    return
  end
  faderActive = true
  faderQueued = target
  if not faderTimer then
    -- Aggregate rapid fader events; center/STOP remain immediate.
    faderTimer = hs.timer.doAfter(0.065, function()
      faderTimer = nil
      local requested = faderQueued
      faderQueued = nil
      if requested and faderArmed and enabled and isResolveFrontmost() then
        setShuttle(requested, "fader")
      end
    end)
  end
end

local function wheel(value)
  if not value or value == 0 or value > 127 then return end
  local direction = value <= 64 and 1 or -1
  -- Do not nudge trims/frames while the fader is driving active playback.
  if faderActive then return end
  -- A press-and-hold modifier takes precedence over both JOG and SHUTTLE.
  if trimHeld then
    key(direction > 0 and "." or ",")
  elseif mode == "JOG" then
    key(direction > 0 and "right" or "left")
  else
    -- Earlier version lost all pulses within 100 ms. Instead aggregate them
    -- and apply one deterministic speed change for each small MIDI burst.
    shuttlePending = math.max(-40, math.min(40, shuttlePending + direction))
    if not shuttleBatchTimer then
      shuttleBatchTimer = hs.timer.doAfter(SHUTTLE_BATCH_SECONDS, flushShuttle)
    end
  end
end

local function action(name)
  if name == "cycle" then switchMode()
  elseif name == "begin" then key("left", {"cmd"})
  elseif name == "rew" then
    cancelShuttle(); speed = 0; activeShuttleSource = nil; faderArmed, faderActive = false, false
    updateTitle(); key("j")
  elseif name == "ff" then
    cancelShuttle(); speed = 0; activeShuttleSource = nil; faderArmed, faderActive = false, false
    updateTitle(); key("l")
  elseif name == "stop" then stopPlayback()
  elseif name == "play" then
    cancelShuttle(); speed = 0; activeShuttleSource = nil; faderArmed, faderActive = false, false
    updateTitle(); key("space")
  elseif name == "undo" then key("z", {"cmd"})
  elseif name == "trackPrev" then key("up")
  elseif name == "trackNext" then key("down")
  elseif name == "editSelect" then key("v") -- handled with press/release in midiCallback
  elseif name == "splitAll" then
    if splitBusy then return end
    if hs.accessibilityState and not hs.accessibilityState(false) then
      toast("NK: engedelyezd a Hammerspoon Accessibility hozzafereset!", 4)
      return
    end
    -- Resolve gives a manual clip selection priority over track selectors.
    -- Deselect first, then split on the enabled/unlocked target tracks.
    splitBusy = true
    key("a", {"cmd", "shift"})
    hs.timer.doAfter(0.060, function()
      splitBusy = false
      if enabled and isResolveFrontmost() then key("b", {"cmd"}) end
    end)
  elseif name == "trimLeft" then key(",")
  elseif name == "trimRight" then key(".")
  elseif name == "inPoint" then key("i")
  elseif name == "outPoint" then key("o")
  elseif name == "clearIO" then key("x", {"alt"})
  elseif name == "escape" then key("escape")
  elseif name == "cutPage" then
    if speed ~= 0 or shuttleBatchTimer then stopPlayback() end
    switchPage("Cut")
  elseif name == "editPage" then
    if speed ~= 0 or shuttleBatchTimer then stopPlayback() end
    switchPage("Edit")
  elseif name == "trimMode" then key("t")
  elseif name == "normalMode" then key("a")
  else
    local camera = name:match("^cam([1-4])$")
    if camera then key(camera) end
  end
end

local function midiSignal(command, meta)
  if command == "controlChange" and meta.controllerNumber ~= nil then
    return "cc:" .. tostring(meta.channel) .. ":" .. tostring(meta.controllerNumber), meta.controllerValue
  end
  if (command == "noteOn" or command == "noteOff") and meta.note ~= nil then
    return "note:" .. tostring(meta.channel) .. ":" .. tostring(meta.note), meta.velocity
  end
  return nil, nil
end

local function showLearnStep()
  if learnIndex == 1 then
    toast("SETUP 1/26: forgasd a JOG tarcsat JOBBRA!", 7)
  elseif learnIndex == 2 then
    toast("SETUP 2/26: forgasd a JOG tarcsat BALRA!", 7)
  elseif learnIndex <= #steps + 2 then
    local item = steps[learnIndex - 2]
    toast("SETUP " .. learnIndex .. "/" .. (#steps + 2) .. "\nNyomd meg: " .. item[2], 8)
  end
end

local function startLearning()
  if not midi then
    toast("Csatlakoztasd a nanoKONTROL Studio-t (USB MIDI)!")
    return
  end
  extraLearning = false
  trimHeld = false
  learning, learned, learnIndex = true, {buttons = {}}, 1
  updateTitle()
  showLearnStep()
end

local function finishLearning()
  if not hs.settings.set then return end
  hs.settings.set(KEY, learned)
  cfg, learning, learned = learned, false, nil
  mode, speed = "JOG", 0
  updateTitle()
  toast("Kalibralas kesz. Nyisd meg a DaVinci Resolve-ot!", 5)
end

local function learn(command, meta)
  local signal, value = midiSignal(command, meta)
  if not signal or value == nil then return end
  if learnIndex == 1 then
    if command ~= "controlChange" or value < 1 or value > 64 then return end
    learned.wheel = signal
  elseif learnIndex == 2 then
    if signal ~= learned.wheel or value < 65 or value > 127 then
      -- Don't advance until Korg Sign Magnitude sends a CCW tick.
      return
    end
  else
    -- Learn on press only, never on release or fader/pot CC values.
    if command == "controlChange" and value < 64 then return end
    if command == "noteOn" and value == 0 then return end
    if signal == learned.wheel then
      toast("A JOG wheel jelet ne rendeld gombhoz!", 2)
      return
    end
    for _, previous in pairs(learned.buttons) do
      if previous == signal then
        toast("Ez a MIDI jel mar szerepel. Masik gombot nyomj!", 2)
        return
      end
    end
    local item = steps[learnIndex - 2]
    learned.buttons[item[1]] = signal
  end
  learnIndex = learnIndex + 1
  if learnIndex > #steps + 2 then
    finishLearning()
  else
    showLearnStep()
  end
end

local function isPress(command, value)
  if command == "controlChange" then return type(value) == "number" and value >= 64 end
  if command == "noteOn" then return type(value) == "number" and value > 0 end
  return false
end

-- Explicit, opt-in LED output test. Does not change Korg Global LED Mode.
-- The Korg expects CC On/Off on the same CC number as the physical button.
local ledProbeSignal, ledProbeTimer = nil, nil
local function ledProbeMute1()
  local binding = cfg and cfg.buttons and cfg.buttons.cam1
  local channel, controller
  if type(binding) == "string" then
    channel, controller = binding:match("^cc:(%d+):(%d+)$")
  end
  if not midi or not channel or not controller then
    toast("NK: LED probahoz Korg MIDI es betanitott MUTE 1 CC kell", 4)
    return
  end
  if not midi.sendCommand then
    toast("NK: a MIDI kimenet nem tamogatott", 3)
    return
  end
  if ledProbeTimer then
    ledProbeTimer:stop()
    ledProbeTimer = nil
  end
  local target = midi
  local function send(value)
    if midi ~= target then return false end
    local ok, sent = pcall(function()
      return target:sendCommand("controlChange", {
        channel = tonumber(channel),
        controllerNumber = tonumber(controller),
        controllerValue = value,
      })
    end)
    return ok and sent ~= false
  end
  -- Guard against any device/driver MIDI echo being mistaken for a CAM 1 press.
  ledProbeSignal = binding
  if not send(127) then
    ledProbeSignal = nil
    toast("NK: LED MIDI output sikertelen; nem valtozott a kiosztas", 4)
    return
  end
  ledProbeTimer = hs.timer.doAfter(0.7, function()
    send(0)
    ledProbeSignal = nil
    ledProbeTimer = nil
  end)
  toast("NK: MUTE 1 LED proba (700 ms). Korg Global LED Mode: External", 4)
end

local function beginFaderLearning()
  if not cfg or not midi or learning then
    toast("NK: elobb kell a teljes MIDI kiosztas", 3)
    return
  end
  extraLearning = false
  faderLearning, faderCandidate = true, nil
  faderArmed, faderActive = false, false
  toast("NK: mozgasd a FADER 1-et legalabb 5 MIDI-egyseggel!", 5)
end

local function learnFader(signal, value, command)
  if command ~= "controlChange" or type(value) ~= "number" then return end
  if signal == cfg.wheel then return end
  for _, binding in pairs(cfg.buttons or {}) do
    if signal == binding then return end
  end
  if not faderCandidate or faderCandidate.signal ~= signal then
    faderCandidate = {signal = signal, value = value}
    return
  end
  if math.abs(value - faderCandidate.value) < 5 then return end
  cfg.faderShuttle = signal
  hs.settings.set(KEY, cfg)
  faderLearning, faderCandidate = false, nil
  toast("NK: FADER 1 betanitva: " .. signal .. " - huzd kozepre!", 4)
end

local function beginExtraLearning()
  if not cfg or not midi or learning then
    toast("NK: elobb legyen teljes, mukodo MIDI kiosztas", 3)
    return
  end
  faderLearning, faderCandidate = false, nil
  extraLearning = true
  toast("NK: most nyomd meg egyszer a szabad SELECT 5 gombot!", 5)
end

local function midiCallback(_, _, command, _, meta)
  local signal, value = midiSignal(command, meta)
  if not signal then return end
  if ledProbeSignal and signal == ledProbeSignal then return end
  if learning then learn(command, meta); return end
  if faderLearning then learnFader(signal, value, command); return end
  local pressed = isPress(command, value)
  if extraLearning then
    if not pressed then return end
    if signal == cfg.wheel then
      toast("NK: a JOG tarcsat ne valaszd gombnak!", 2)
      return
    end
    for name, binding in pairs(cfg.buttons or {}) do
      if binding == signal and name ~= "splitAll" then
        toast("NK: ez a gomb mar hasznalatban van. Nyomj SELECT 5-ot!", 3)
        return
      end
    end
    cfg.buttons.splitAll = signal
    hs.settings.set(KEY, cfg)
    extraLearning = false
    toast("NK: SELECT 5 = split all (Cmd+B). A tobbi gomb valtozatlan!", 4)
    return
  end
  if not cfg then return end
  -- Unlike old press-only handling, MARKER SET must also handle RELEASE.
  -- Process release regardless of app focus so TRIM cannot remain latched.
  if cfg.buttons and cfg.buttons.editSelect == signal then
    if not pressed then
      if trimHeld then trimHeld = false; updateTitle() end
      return
    end
    if not enabled or not isResolveFrontmost() then return end
    if mode == "SHUTTLE" then stopPlayback() end
    key("v")
    trimHeld = true
    updateTitle()
    return
  end
  if not enabled or not isResolveFrontmost() then return end
  if command == "controlChange" then
    if cfg.faderShuttle == signal then
      faderShuttle(value)
      return
    end
    -- Korg screenshot: Continuous uses CC86, Sign Magnitude uses CC82.
    -- Migrate ONLY when the actual CC82 signal arrives, preserving 24 button binds.
    local channel = cfg.wheel and cfg.wheel:match("^cc:(%d+):86$")
    if channel and signal == "cc:" .. channel .. ":82" then
      cfg.wheel = signal
      hs.settings.set(KEY, cfg)
      hs.printf("[NK] wheel migrated from CC86 to CC82; button bindings kept")
      toast("NK: JOG CC82 felismerve, 24 gomb megtartva")
    end
    if signal == cfg.wheel then
      wheel(value)
      return
    end
  end
  -- Press only: Korg Momentary CC sends 127 down and 0 up.
  if not pressed then return end
  for name, binding in pairs(cfg.buttons or {}) do
    if binding == signal then action(name); return end
  end
end

local function attach()
  local found
  local names = hs.midi.devices()
  for _, name in ipairs(names) do
    local low = name:lower()
    if low:find("nanokontrol", 1, true) and low:find("studio", 1, true) then
      found = name
      break
    end
  end
  if not found then
    names = hs.midi.virtualSources()
    for _, name in ipairs(names) do
      local low = name:lower()
      if low:find("nanokontrol", 1, true) and low:find("studio", 1, true) then
        found = name
        break
      end
    end
  end
  if found == deviceName and midi then return end
  if midi then midi:callback(nil) end
  midi, deviceName = nil, nil
  if not found then return end
  midi = hs.midi.new(found)
  if midi then
    deviceName = found
    midi:callback(midiCallback)
    if not cfg and not learning then
      hs.timer.doAfter(1.0, function() if not cfg and not learning then startLearning() end end)
    end
  end
end

menu:setMenu(function()
  return {
    {title = "Eszkoz: " .. (deviceName or "nincs csatlakoztatva"), disabled = true},
    {title = "Uzemmod: " .. (trimHeld and "TRIM (MARKER SET nyomva)" or mode) .. (speed ~= 0 and " (" .. speed .. ")" or ""), disabled = true},
    {title = "Jog MIDI: " .. (cfg and cfg.wheel or "nincs beallitva"), disabled = true},
    {title = "FADER 1: " .. (cfg and (cfg.faderShuttle or "nincs betanitva") or "nincs konfiguracio")
       .. " | " .. (faderArmed and "READY" or "huzd kozepre")
       .. " | MIDI " .. tostring(faderValue or "?"), disabled = true},
    {title = "FADER 1 SHUTTLE betanitasa (2 MIDI ertek)", fn = beginFaderLearning,
      disabled = not cfg or not midi or learning},
    {title = "FADER 1 betanitas megszakitasa", disabled = not faderLearning,
      fn = function() faderLearning, faderCandidate = false, nil end},
    {title = "LED kimenet teszt (MUTE 1, 700ms)", fn = ledProbeMute1,
      disabled = not midi or not cfg or not cfg.buttons or not cfg.buttons.cam1},
    {title = "Hammerspoon Accessibility: " .. ((hs.accessibilityState and hs.accessibilityState(false)) and "OK" or "HIANYZIK"), disabled = true},
    {title = "Accessibility engedely kerese", fn = function()
      if hs.accessibilityState then hs.accessibilityState(true) end
    end},
    {title = "Resolve aktiv: " .. (isResolveFrontmost() and "igen" or "nem"), disabled = true},
    {title = "Cut oldal teszt (menu)", fn = function() switchPage("Cut") end},
    {title = "Edit oldal teszt (menu)", fn = function() switchPage("Edit") end},
    {title = cfg and "MIDI kiosztas: beallitva" or "MIDI kiosztas: kalibralni kell", disabled = true},
    {title = cfg and cfg.buttons and cfg.buttons.splitAll and "SELECT 5 (Cmd+B): beallitva" or "SELECT 5 (Cmd+B): meg nincs betanitva", disabled = true},
    {title = extraLearning and "SELECT 5 tanitasa folyamatban..." or "SELECT 5 (Cmd+B) egyszeri betanitasa", fn = beginExtraLearning, disabled = not cfg or not midi or learning},
    {title = "SELECT 5 tanitas megszakitasa", disabled = not extraLearning,
      fn = function() extraLearning = false; toast("SELECT 5 tanitas megszakitva", 2) end},
    {title = "-"},
    {title = "Ujrakalibralas (26 lepes)", fn = startLearning},
    {title = learning and "Kalibralas megszakitasa" or "Kalibralas nincs folyamatban", disabled = not learning,
      fn = function() learning = false; learned = nil; updateTitle() end},
    {title = enabled and "Vezerles szuneteltetese" or "Vezerles bekapcsolasa", fn = function()
      if enabled and isResolveFrontmost() then
        stopPlayback()
      else
        speed = 0
      end
      enabled = not enabled
      trimHeld = false
      extraLearning = false
      faderLearning, faderCandidate = false, nil
      faderArmed, faderActive = false, false
      updateTitle()
    end},
  }
end)

hs.midi.deviceCallback(function() attach() end)
attach()
updateTitle()

-- Keep menu + callback alive as long as Hammerspoon loads this module.
return {setup = startLearning, isResolveFrontmost = isResolveFrontmost}

-- END v1.2: experimental FADER 1 shuttle and LED probe on draft branch; main unchanged