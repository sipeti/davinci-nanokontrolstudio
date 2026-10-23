-- nanoKONTROL Studio -> DaVinci Resolve 21 | clean Assignable Mode v1.3
-- ONE guided 28-step setup. No MCU/HUI emulation or Resolve scripting.
-- Scene 1 External LEDs are software-controlled, scoped to the current scene.
-- KORG KONTROL Editor: SCENE 1, CH1, buttons Momentary/CC 127/0,
-- jog Sign Magnitude CC82 Const, first SLIDER CC2, LED Mode External.
local hs = hs
local KEY = "nanokontrol_studio_resolve21_v1"
local stored = hs.settings.get(KEY)
-- Deliberately refuse old experimental/partial bindings; new wizard is atomic.
local cfg = type(stored) == "table" and stored.setupVersion == 2 and stored or nil
local enabled, mode, speed = true, "JOG", 0
local device, deviceName = nil, nil
local learning, draft, pending, step = false, nil, nil, 0
local trimHeld, faderArmed, faderActive = false, false, false
-- 1 jog tick = 1 shuttle gear. Coalesce small MIDI bursts before one J/K/L
-- restart so quick turns cannot repeatedly cancel the pending L/J presses.
local SHUTTLE_WHEEL_BATCH_SECONDS = 0.045
local shuttleSource, shuttlePulses, shuttleTimers, shuttleWheelTimer = nil, 0, {}, nil
local splitBusy, lastMidi = false, "-"
-- Transport state is our last requested action, NOT Resolve's actual play status.
local transportIntent = "stopped"
-- The physical Space key is observed while Resolve is frontmost. Suppress
-- Hammerspoon's own simulated Space so a Korg PLAY is not counted twice.
local SYNTHETIC_SPACE_GUARD_SECONDS = 0.15
local syntheticSpaceUntil = 0
local ledEnabled = true
local ledOutputState, pressedLEDs = {}, {}
local ledOutputStatus = "meg nem tesztelt"
-- Scene 1 configured button CCs; all cleared on init/disable to avoid stale LEDs.
local LED_BUTTONS = {21,22,23,24,25,26,27,28,29,30,31,33,34,35,36,37,
  38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,
  54,55,56,57,58,59,60,61,62,63,80,81}
local LED_BUTTON_SET = {}
for _, cc in ipairs(LED_BUTTONS) do LED_BUTTON_SET[cc] = true end
-- Shared transport/navigation across the five Korg scenes. Other buttons
-- remain Scene 1-only until a future scene-specific mapping is agreed.
local GLOBAL_TRANSPORT = {"cycle","begin","rew","ff","stop","play","trackPrev","trackNext"}
local SCENE_COUNT = 5
local LED_HEARTBEAT_SECONDS = 0.5
local lastLearnProblem = nil
local lastLearnValues = {}
local menu = hs.menubar.new()

local steps = {
  {"cycle",     "CYCLE (JOG / SHUTTLE)"},
  {"begin",     "RETURN TO ZERO"},
  {"rew",       "REW"},
  {"ff",        "FF"},
  {"stop",      "STOP"},
  {"play",      "PLAY"},
  {"undo",      "nagy REC (UNDO)"},
  {"trackPrev", "TRACK balra"},
  {"trackNext", "TRACK jobbra"},
  {"editSelect","MARKER SET (TRIM nyomva tartva)"},
  {"trimLeft",  "MARKER balra (-1 frame)"},
  {"trimRight", "MARKER jobbra (+1 frame)"},
  {"cam1",      "MUTE 1 / CAM1"},
  {"cam2",      "MUTE 2 / CAM2"},
  {"cam3",      "MUTE 3 / CAM3"},
  {"cam4",      "MUTE 4 / CAM4"},
  {"inPoint",   "MUTE 5 / IN"},
  {"outPoint",  "MUTE 6 / OUT"},
  {"clearIO",   "MUTE 7 / CLEAR IN-OUT"},
  {"escape",    "MUTE 8 / ESC"},
  {"cutPage",   "SELECT 1 / CUT PAGE"},
  {"editPage",  "SELECT 2 / EDIT PAGE"},
  {"trimMode",  "SELECT 3 / TRIM"},
  {"normalMode","SELECT 4 / SELECTION"},
  {"splitAll",  "SELECT 5 / Cmd+B (SPLIT)"},
}
local TOTAL = #steps + 3  -- Jog clockwise, jog counterclockwise, 25 buttons, slider1
assert(TOTAL == 28, "unexpected learn step count")

local function toast(message, seconds)
  hs.alert.show(message, seconds or 4)
end
local function warnLearnOnce(reason, message)
  -- Jog wheels can send dozens of MIDI messages per second.
  if lastLearnProblem == reason then return end
  lastLearnProblem = reason
  toast("NK: " .. message, 7)
end

local function resolveApp()
  local app = hs.application.frontmostApplication()
  if not app then return nil end
  local title = (app:title() or ""):lower()
  local bundle = (app:bundleID() or ""):lower()
  if title:find("davinci resolve", 1, true)
    or bundle:find("davinciresolve", 1, true) then return app end
  return nil
end
local function key(k, mods)
  if k == "space" then
    -- Event taps can observe our generated keystroke. The 10ms keyStroke
    -- is guarded for 150ms, including delayed macOS event delivery.
    syntheticSpaceUntil = hs.timer.secondsSinceEpoch() + SYNTHETIC_SPACE_GUARD_SECONDS
  end
  hs.eventtap.keyStroke(mods or {}, k, 10000)
end

-- Empirically verified on the user's nanoKONTROL Studio (2026-10-23):
-- MUTE 1 LED only illuminates with hs.midi:sendCommand(channel=0).
-- Hammerspoon defines OUTPUT channel=0 as all-channel broadcast.
-- Explicit output channel=1 returned true but DID NOT light the hardware.
-- Input MIDI channel=0 remains the first physical channel for binding matches.
-- Keep the broadcast restricted to known Scene 1 button CCs.
local function sceneInputChannel()
  return cfg and cfg.wheel and tonumber(cfg.wheel:match("^cc:(%d+):82$")) or nil
end
local function sceneCC(signal)
  if type(signal) ~= "string" then return nil end
  local channel, cc = signal:match("^cc:(%d+):(%d+)$")
  local base = sceneInputChannel()
  channel = tonumber(channel)
  if not channel or not base or channel < base or channel >= base + SCENE_COUNT
    then return nil end
  return tonumber(cc),channel
end
local function ccFromSignal(signal)
  local cc,channel = sceneCC(signal)
  if channel ~= sceneInputChannel() then return nil end
  return cc
end
local function sendLED(cc, on, force)
  if not device or not cfg then return false end
  if not LED_BUTTON_SET[cc] then return false end
  local value = on and 127 or 0
  if not force and not ledEnabled then return false end
  if not force and ledOutputState[cc] == value then return true end
  local inputChannel = sceneInputChannel()
  if inputChannel == nil then return false end
  -- Hardware probe: channel=0 (broadcast) WORKS; channel=1 does not.
  local outputChannel = 0
  local ok, result = pcall(function()
    return device:sendCommand("controlChange",
      {channel=outputChannel, controllerNumber=cc, controllerValue=value})
  end)
  if not ok or result == false then
    ledOutputStatus = "MIDI output hiba"
    hs.printf("[NK LED] SEND_FAILED cc=%d out_channel=%d",cc,outputChannel)
    return false
  end
  ledOutputState[cc] = value
  ledOutputStatus = "API OK / ch0 (hardveres probe PASS)"
  return true
end
local function resetLEDs()
  if not device or not cfg then return end
  pressedLEDs, ledOutputState = {}, {}
  for _, cc in ipairs(LED_BUTTONS) do sendLED(cc, false, true) end
end
local function refreshStateLEDs(force)
  if not cfg or not ledEnabled then return end
  local playCC = ccFromSignal(cfg.buttons.play)
  local cycleCC = ccFromSignal(cfg.buttons.cycle)
  if playCC then sendLED(playCC, transportIntent == "playing", force) end
  if cycleCC then sendLED(cycleCC, mode == "SHUTTLE", force) end
end
local function inputLED(command, meta, signal, value)
  if not cfg or not ledEnabled or command ~= "controlChange" then return end
  local cc = sceneCC(signal)
  if not cc or not LED_BUTTON_SET[cc] then return end
  if value ~= 0 and value ~= 127 then return end
  -- PLAY/CYCLE are persistent *shared* mode indicators on every scene.
  -- The other buttons get momentary physical LED acknowledgment only.
  if cc == ccFromSignal(cfg.buttons.play)
    or cc == ccFromSignal(cfg.buttons.cycle) then
    refreshStateLEDs()
    return
  end
  pressedLEDs[cc] = (value == 127) or nil
  sendLED(cc, value == 127)
end
local function toggleLEDFeedback()
  if ledEnabled then
    -- Disabling explicitly turns every known Scene 1 LED off, including ones
    -- that may have been left on by an earlier external-LED experiment.
    resetLEDs()
    ledEnabled = false
    toast("NK: LED ki, minden Scene 1 LED nullazva", 2.5)
  else
    ledEnabled = true
    resetLEDs()
    refreshStateLEDs()
    toast("NK: LED be (External / csak Scene 1)", 2.5)
  end
end

-- Run ONLY when called in Hammerspoon Console:
-- require("nanokontrol_resolve21").ledProbe()
-- This tests the current physical MIDI destination without adding menu items,
-- making keyboard shortcuts, changing the Scene, or saving settings.
local ledProbeRunning = false
local function ledProbe()
  if ledProbeRunning then
    hs.printf("[NK LED PROBE] mar fut, varjuk meg a végét")
    return false
  end
  if not device or not cfg then
    hs.printf("[NK LED PROBE] NINCS KORG vagy teljes 28/28 kalibracio")
    return false
  end
  local cc = ccFromSignal(cfg.buttons.cam1)
  if not cc then
    hs.printf("[NK LED PROBE] NINCS Scene 1 MUTE1 CC, aktualis: %s",
      tostring(cfg.buttons.cam1))
    return false
  end
  local onlineOK, online = pcall(function() return device:isOnline() end)
  hs.printf("[NK LED PROBE] device=%s online=%s midi_in=%s ledEnabled=%s",
    tostring(deviceName),onlineOK and tostring(online) or "unknown",
    tostring(sceneInputChannel()),tostring(ledEnabled))
  hs.printf("[NK LED PROBE] Figyeld a MUTE 1-et. 1. felvillanas: MIDI channel=1, 2. felvillanas: channel=0 (ALL).")
  local function send(ch,value)
    local ok, result = pcall(function()
      return device:sendCommand("controlChange",
        {channel=ch, controllerNumber=cc, controllerValue=value})
    end)
    hs.printf("[NK LED PROBE] ch=%d cc=%d value=%d pcall=%s result=%s",
      ch,cc,value,tostring(ok),tostring(result))
    return ok and result == true
  end
  ledProbeRunning = true
  send(1,127)
  hs.timer.doAfter(1.5,function()
    send(1,0)
    hs.timer.doAfter(0.6,function()
      send(0,127)
      hs.timer.doAfter(1.5,function()
        send(0,0)
        ledProbeRunning = false
        hs.printf("[NK LED PROBE] kesz. Az API true nem bizonyitja a fizikai LED felvillanasat!")
        -- Restore any locally tracked Play/Cycle indicators.
        refreshStateLEDs()
      end)
    end)
  end)
  return true
end

local function title()
  if learning then menu:setTitle("NK SETUP " .. tostring(step) .. "/28"); return end
  if not enabled then menu:setTitle("NK OFF"); return end
  local label = trimHeld and "TRIM" or (shuttleSource == "fader" and "FADER" or mode)
  if speed ~= 0 then label = label .. " " .. (speed > 0 and "+" or "") .. tostring(speed) end
  menu:setTitle("NK " .. label)
end

local function cancelShuttle()
  if shuttleWheelTimer then shuttleWheelTimer:stop(); shuttleWheelTimer = nil end
  for _, t in ipairs(shuttleTimers) do t:stop() end
  shuttleTimers, shuttlePulses = {}, 0
end
local function stop()
  cancelShuttle()
  speed, shuttleSource, faderArmed, faderActive = 0, nil, false, false
  if resolveApp() then key("k") end
  transportIntent = "stopped"
  refreshStateLEDs()
  title()
end
local function shuttle(target, source)
  target = math.max(-4, math.min(4, target))
  if speed == target and (target == 0 or shuttleSource == source) then return end
  cancelShuttle()
  if not resolveApp() then return end
  key("k")
  speed, shuttleSource = target, target == 0 and nil or source
  transportIntent = target == 0 and "stopped" or "shuttle"
  refreshStateLEDs()
  title()
  local direction = target > 0 and "l" or "j"
  for i = 1, math.abs(target) do
    local t = hs.timer.doAfter(0.025 + (i-1)*0.070, function()
      if enabled and not learning and resolveApp()
        and speed == target and shuttleSource == source then key(direction) end
    end)
    shuttleTimers[#shuttleTimers+1] = t
  end
end
local function level(value)
  if value >= 60 and value <= 68 then return 0 end
  if value < 60 then return -math.min(4, math.ceil((60-value)/15)) end
  return math.min(4, math.ceil((value-68)/15))
end
local function fader(value)
  local target = level(value)
  if not faderArmed then
    if target == 0 then faderArmed = true end
    return
  end
  if target == 0 then
    if faderActive then shuttle(0,"fader") end
    faderActive = false
  else
    faderActive = true
    shuttle(target,"fader")
  end
end
local function wheel(value)
  if value == 0 or value > 127 or faderActive then return end
  local direction = value <= 64 and 1 or -1
  if trimHeld then
    key(direction > 0 and "." or ",")
  elseif mode == "JOG" then
    -- An external nudge may pause/shift playback; avoid stale PLAY LED.
    if transportIntent ~= "stopped" then
      transportIntent = "unknown"
      refreshStateLEDs()
    end
    key(direction > 0 and "right" or "left")
  else
    -- One physical wheel pulse changes one shuttle gear. A rapid string of
    -- pulses is applied together after 45 ms instead of issuing STOP for
    -- every pulse (which could cancel all pending J/L events).
    shuttlePulses = math.max(-8,math.min(8,shuttlePulses + direction))
    if not shuttleWheelTimer then
      shuttleWheelTimer = hs.timer.doAfter(SHUTTLE_WHEEL_BATCH_SECONDS,function()
        shuttleWheelTimer = nil
        local delta = shuttlePulses
        shuttlePulses = 0
        if delta ~= 0 and enabled and not learning and not faderActive
          and mode == "SHUTTLE" and resolveApp() then
          shuttle(speed + delta,"wheel")
        end
      end)
    end
  end
end

local function changePage(page)
  local app = resolveApp()
  if not app then return end
  local ok, result = pcall(function()
    return app:selectMenuItem({"Workspace","Switch to Page",page})
  end)
  if not ok or not result then toast("NK: " .. page .. " page menu nem elerheto") end
end
local function action(name)
  if name == "cycle" then
    stop()
    mode = mode == "JOG" and "SHUTTLE" or "JOG"
    refreshStateLEDs()
    title()
  elseif name == "begin" then key("left",{"cmd"})
  elseif name == "rew" then
    stop(); key("j")
    transportIntent = "shuttle"
  elseif name == "ff" then
    stop(); key("l")
    transportIntent = "shuttle"
  elseif name == "stop" then stop()
  elseif name == "play" then
    -- Do NOT send K first: PLAY is a true Space toggle. A second PLAY
    -- pauses/stops rather than sending K then immediately restarting.
    local wasRunning = (transportIntent == "playing"
      or transportIntent == "shuttle" or speed ~= 0)
    cancelShuttle()
    speed, shuttleSource, faderArmed, faderActive = 0, nil, false, false
    key("space")
    transportIntent = wasRunning and "stopped" or "playing"
    refreshStateLEDs()
    title()
  elseif name == "undo" then key("z",{"cmd"})
  elseif name == "trackPrev" then key("up")
  elseif name == "trackNext" then key("down")
  elseif name == "trimLeft" then key(",")
  elseif name == "trimRight" then key(".")
  elseif name == "inPoint" then key("i")
  elseif name == "outPoint" then key("o")
  elseif name == "clearIO" then key("x",{"alt"})
  elseif name == "escape" then key("escape")
  elseif name == "cutPage" then stop(); changePage("Cut")
  elseif name == "editPage" then stop(); changePage("Edit")
  elseif name == "trimMode" then key("t")
  elseif name == "normalMode" then key("a")
  elseif name == "splitAll" then
    if splitBusy then return end
    splitBusy = true
    key("a", {"cmd","shift"})
    hs.timer.doAfter(0.06, function()
      splitBusy = false
      if enabled and not learning and resolveApp() then key("b", {"cmd"}) end
    end)
  else
    local camera = name:match("^cam([1-4])$")
    if camera then key(camera) end
  end
end

local function midiSignal(command, meta)
  if command == "controlChange" and meta.controllerNumber ~= nil then
    return ("cc:%s:%s"):format(meta.channel,meta.controllerNumber),meta.controllerValue
  end
  if (command == "noteOn" or command == "noteOff") and meta.note ~= nil then
    return ("note:%s:%s"):format(meta.channel,meta.note),meta.velocity
  end
  return nil,nil
end
-- Raw MIDI evidence, recorded in Hammerspoon -> Console ONLY during the
-- 28-step wizard. Logs incoming channel as reported by Hammerspoon (0-based),
-- CC/Note, value and the change since the previous event on that controller.
local function logLearnMidi(command, meta, signal, value)
  local movement = "-"
  if command == "controlChange" and type(value) == "number" then
    local previous = lastLearnValues[signal]
    if previous ~= nil then
      local change = value - previous
      movement = string.format("%+d", change)
    end
    lastLearnValues[signal] = value
  end
  hs.printf("[NK MIDI] step=%d/%d type=%s channel=%s controller=%s value=%s delta=%s raw=%s",
    step, TOTAL, tostring(command), tostring(meta.channel),
    tostring(signal), tostring(value), movement, tostring(meta.data or "-"))
end

local function buttonPress(command, value)
  return (command == "controlChange" and value == 127)
    or (command == "noteOn" and value > 0)
end
local function buttonRelease(command, value)
  return (command == "controlChange" and value == 0)
    or command == "noteOff"
    or (command == "noteOn" and value == 0)
end

local function stepText()
  local prompt
  if step == 1 then prompt = "Forditsd a JOG-ot JOBBRA"
  elseif step == 2 then prompt = "Forditsd a JOG-ot BALRA"
  elseif step == TOTAL then
    prompt = "FADER 1 (bal szelso TOLOPOTI): teljesen LE, majd FEL (CC 2)"
  else prompt = "Nyomd meg ES ENGEDD EL: " .. steps[step-2][2]
  end
  lastLearnProblem = nil
  toast("NK SETUP " .. step .. "/" .. TOTAL .. "\n" .. prompt, 8)
  title()
end
local function beginLearn()
  if not device then toast("NK: nincs nanoKONTROL Studio USB MIDI"); return end
  stop()
  learning, pending, step = true,nil,1
  lastLearnValues = {}
  draft = {setupVersion=2,buttons={},wheel=nil,faderShuttle=nil}
  stepText()
end
local function cancelLearn()
  learning, draft, pending, step = false,nil,nil,0
  title()
  toast("NK: a regi beallitas megmaradt; nem tortent mentés",3)
end
local function finishLearn()
  assert(draft.wheel and draft.faderShuttle, "incomplete calibration")
  for _,item in ipairs(steps) do assert(draft.buttons[item[1]], "missing "..item[1]) end
  hs.settings.set(KEY,draft) -- commit only after ALL 28 steps
  cfg = draft
  resetLEDs()
  transportIntent = "stopped"
  learning, draft, pending, step = false,nil,nil,0
  faderArmed, faderActive, trimHeld = false,false,false
  mode, speed = "JOG",0
  refreshStateLEDs()
  title()
  toast("NK: TELJES 28/28 kalibracio KESZ (Scene 1)!",6)
end

local function learn(command,meta)
  local signal,value = midiSignal(command,meta)
  if not signal or value==nil then return end
  if step == 1 then
    -- A Continuous wheel can emit a CC in 1..64 and accidentally pass the
    -- original check; its reverse movement then gets stuck forever on 2/28.
    if command ~= "controlChange" then return end
    if not signal:match("^cc:%d+:82$") then
      if signal:match("^cc:%d+:86$") then
        warnLearnOnce("cc86", "CC86 erkezik! A Korg meg Continuous modban lehet. Scene 1 -> Communication -> Write Scene Data.")
      end
      return
    end
    if value < 1 or value > 64 then
      warnLearnOnce("wrongCW", "JOG JOBBRA: CC82 1..64 vart, kapott: " .. signal .. "=" .. value)
      return
    end
    draft.wheel = signal
    step=2
    stepText()
    return
  end
  if step == 2 then
    if signal ~= draft.wheel then
      if command == "controlChange" and signal:match("^cc:%d+:86$") then
        warnLearnOnce("cc86", "CC86 erkezik! Varjuk a CC82-t. Korg Editor -> Communication -> Write Scene Data.")
      end
      return
    end
    if value < 65 or value > 127 then
      warnLearnOnce("wrongCCW", "JOG BALRA: CC82 65..127 vart, kapott: " .. signal .. "=" .. value .. ". Ird ki a Scene 1-et a Korgra!")
      return
    end
    step=3
    stepText()
    return
  end
  if step == TOTAL then
    -- MIDI channel 1 appears as channel=0 in Hammerspoon callback metadata.
    -- Follow the channel captured on the wheel; do not hardcode 0 or 1.
    local wheelChannel = draft.wheel:match("^cc:(%d+):82$")
    if signal ~= "cc:" .. tostring(wheelChannel) .. ":2"
       or command ~= "controlChange" then return end
    if not draft.faderMin or value < draft.faderMin then draft.faderMin = value end
    if not draft.faderMax or value > draft.faderMax then draft.faderMax = value end
    if draft.faderMin <= 15 and draft.faderMax >= 112 then
      draft.faderShuttle = signal
      draft.faderMin,draft.faderMax = nil,nil
      finishLearn()
    end
    return
  end
  local name = steps[step-2][1]
  -- CC 0..20 are knobs/sliders. Channel is 0-based on this Hammerspoon API.
  if command == "controlChange" then
    local chan,num = signal:match("^cc:(%d+):(%d+)$")
    local wheelChannel = draft.wheel:match("^cc:(%d+):82$")
    if not chan or chan ~= wheelChannel or tonumber(num) <= 20 then return end
  end
  if not pending then
    if not buttonPress(command,value) or signal == draft.wheel then return end
    for _,registered in pairs(draft.buttons) do
      if registered == signal then
        toast("NK: ez a gomb mar be van tanitva: " .. signal,2)
        return
      end
    end
    pending = signal
    return
  end
  if signal ~= pending then return end
  if not buttonRelease(command,value) then return end
  draft.buttons[name] = signal
  pending = nil
  step = step+1
  stepText()
end

local function midiCallback(_,_,command,_,meta)
  local signal,value = midiSignal(command,meta)
  if not signal then return end
  lastMidi = signal .. "=" .. tostring(value)
  if learning then
    logLearnMidi(command,meta,signal,value)
    learn(command,meta)
    return
  end
  -- Echo physical CC to its own LED, independent of the learned action.
  -- When another app has focus, acknowledge the key but do not edit Resolve.
  inputLED(command,meta,signal,value)
  if not enabled or not cfg then return end
  if signal == cfg.buttons.editSelect and buttonRelease(command,value) then
    trimHeld = false
    title()
    return
  end
  if not resolveApp() then
    faderArmed = false
    return
  end
  if command == "controlChange" and signal == cfg.faderShuttle then
    fader(value)
    return
  end
  if command == "controlChange" and signal == cfg.wheel then
    wheel(value)
    return
  end
  if not buttonPress(command,value) then return end
  -- Every Scene keeps the same CC numbers for the physical transport strip,
  -- but switches incoming MIDI channel (Scene 1: ch0, Scene 2: ch1, ...).
  -- Share transport and navigation only; scene-specific functions remain
  -- untouched and require the exact Scene 1 learned binding.
  local cc,channel = sceneCC(signal)
  if cc and channel ~= sceneInputChannel() then
    for _,name in ipairs(GLOBAL_TRANSPORT) do
      if cc == ccFromSignal(cfg.buttons[name]) then
        action(name)
        return
      end
    end
    return
  end
  if signal == cfg.buttons.editSelect then
    if speed ~= 0 then stop() end
    key("v")
    trimHeld = true
    title()
    return
  end
  for name,binding in pairs(cfg.buttons) do
    if binding == signal then action(name); return end
  end
end

local function attach()
  local found
  for _,name in ipairs(hs.midi.devices()) do
    local low = name:lower()
    if low:find("nanokontrol",1,true) and low:find("studio",1,true) then
      found = name
      break
    end
  end
  if found == deviceName and device then return end
  if device then device:callback(nil) end
  device, deviceName = nil,nil
  faderArmed, faderActive = false,false
  if not found then title(); return end
  device = hs.midi.new(found)
  if not device then title(); return end
  deviceName = found
  device:callback(midiCallback)
  if cfg and ledEnabled then
    resetLEDs()
    refreshStateLEDs()
  end
  if not cfg then
    hs.timer.doAfter(0.7,function() if device and not cfg and not learning then beginLearn() end end)
  end
  title()
end

menu:setMenu(function()
  return {
    {title="Eszkoz: "..(deviceName or "nem csatlakozik").." | Scene 1 / Assignable",disabled=true},
    {title=cfg and "Kalibracio: 28/28 OK" or "Kalibracio: TELJES BETANITAS SZUKSEGES",disabled=true},
    {title=learning and "Betanitas: "..step.."/28 | utolso MIDI: "..lastMidi or
      "JOG: "..mode.." | utolso MIDI: "..lastMidi,disabled=true},
    {title="LED (Scene 1 External): "..(ledEnabled and "BE" or "KI")
      .." | MIDI kimenet: "..ledOutputStatus,disabled=true},
    {title="LED visszajelzes BE/KI (KI minden LED-et torol)",fn=toggleLEDFeedback,
      disabled=not cfg or not device},
    {title="TELJES UJRABETANITAS (28 lepes)",fn=beginLearn,disabled=not device},
    {title="Betanitas MEGSZAKITASA",fn=cancelLearn,disabled=not learning},
    {title=enabled and "Vezerles SZUNETELTETESE" or "Vezerles BEKAPCSOLASA",
      fn=function()
        if enabled then stop() end
        enabled = not enabled
        title()
      end},
  }
end)
hs.midi.deviceCallback(function() attach() end)
attach()
-- The hardware SCENE button is a local selector: it can reset the visible
-- External LED state without emitting a scene-change MIDI event. The previous
-- MIDI send cache therefore cannot tell when PLAY/CYCLE lamps were cleared.
-- Reassert ONLY the two shared mode LEDs, at 2 CC messages every 0.5 s.
-- No Resolve polling, no changed key actions, no rerunning the 28-step wizard.
local ledHeartbeat = hs.timer.doEvery(LED_HEARTBEAT_SECONDS,function()
  if ledEnabled and enabled and device and cfg and not learning
    and not ledProbeRunning then
    refreshStateLEDs(true) -- bypass cache: scene switch may have blanked LEDs
  end
end)

-- Observe the *human* Space key; do not consume it. This corrects PLAY LED
-- after starting/pausing with the keyboard instead of the Korg. It cannot
-- detect clicking the Resolve GUI or playback already running at startup.
local function onKeyboardDown(event)
  if not cfg or not enabled or learning or not resolveApp() then return false end
  if event:getKeyCode() ~= hs.keycodes.map.space then return false end
  local flags = event:getFlags()
  if flags.cmd or flags.alt or flags.ctrl or flags.shift or flags.fn then
    return false
  end
  local repeated = event:getProperty(hs.eventtap.event.properties.keyboardEventAutorepeat)
  if repeated and repeated ~= 0 then return false end
  if hs.timer.secondsSinceEpoch() < syntheticSpaceUntil then
    return false -- do not double-count our own Korg PLAY synthetic Space
  end
  local wasRunning = transportIntent == "playing"
    or transportIntent == "shuttle" or speed ~= 0
  cancelShuttle()
  speed, shuttleSource, faderArmed, faderActive = 0, nil, false, false
  transportIntent = wasRunning and "stopped" or "playing"
  refreshStateLEDs()
  title()
  hs.printf("[NK PLAY] physical SPACE => %s (local estimate)",transportIntent)
  return false -- important: let the physical key reach DaVinci Resolve
end
local keyboardTap = hs.eventtap.new(
  {hs.eventtap.event.types.keyDown}, onKeyboardDown):start()
title()
return {setup=beginLearn, ledProbe=ledProbe,
  ledHeartbeat=ledHeartbeat, keyboardTap=keyboardTap,
  isResolveFrontmost=function() return resolveApp() ~= nil end}
