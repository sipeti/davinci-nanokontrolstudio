-- nanoKONTROL Studio -> DaVinci Resolve 21 | clean Assignable Mode v1.3
-- ONE guided 28-step setup. No MCU/HUI emulation or Resolve scripting.
-- Shared JOG/SHUTTLE + transport for all five Assignable scenes.
-- KORG KONTROL Editor: each scene's jog = Sign Magnitude / Const / CC82;
-- incoming MIDI channels increase by scene. Scene 1 Slider1 stays CC2.
-- The physical controller must be written via Write Scene Data per scene.
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
-- Transport state is a best-effort estimate of the last observed action,
-- never a Resolve playback API reading. After startup it's UNKNOWN.
local transportIntent, transportDirection = "unknown", 0
-- Signed last requested JKL gear: 0 = STOP, +1 = L/PLAY 1x,
-- +2..+4 = fast forward; -1..-4 = reverse (J, JJ...).
-- Separate from 'speed', which is only the knob/fader shuttle position.
local transportGear = nil
-- Suppress Korg-generated synthetic J/K/L/Space in the keyboard event tap,
-- otherwise we'd double count actions we already handled as MIDI.
local SYNTHETIC_KEY_GUARD_SECONDS = 0.15
local syntheticKeyUntil = {space=0,j=0,k=0,l=0}
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
-- Scene 1 output 0 and Scene 2 output 1 were verified on real hardware.
-- Scene 3-5 output channels 2-4 need physical confirmation. Only the
-- five shared transport/mode status CCs are sent beyond Scene 1.
-- External LED mode + Write Scene Data are required separately per scene.
local SHARED_LED_OUTPUT_CHANNELS = {0,1,2,3,4}
local SHARED_LED_NAMES = {"play","stop","rew","ff","cycle"}
local warnedContinuousScenes = {}
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
  if syntheticKeyUntil[k] ~= nil and (not mods or #mods == 0) then
    -- The 10ms keyStroke can be observed by our event tap synchronously or
    -- slightly later: guard it before emitting.
    syntheticKeyUntil[k] = hs.timer.secondsSinceEpoch() + SYNTHETIC_KEY_GUARD_SECONDS
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
local function sendLED(cc, on, force, outputChannel)
  if not device or not cfg then return false end
  if not LED_BUTTON_SET[cc] then return false end
  local value = on and 127 or 0
  if not force and not ledEnabled then return false end
  -- Preserve the working Scene 1 route (0); other shared status CCs
  -- use independently cached output routes 1-4 for Scenes 2-5.
  outputChannel = outputChannel or 0
  local cacheKey = outputChannel * 128 + cc
  if not force and ledOutputState[cacheKey] == value then return true end
  if sceneInputChannel() == nil then return false end
  local ok, result = pcall(function()
    return device:sendCommand("controlChange",
      {channel=outputChannel, controllerNumber=cc, controllerValue=value})
  end)
  if not ok or result == false then
    ledOutputStatus = "MIDI output hiba"
    hs.printf("[NK LED] SEND_FAILED cc=%d out_channel=%d",cc,outputChannel)
    return false
  end
  ledOutputState[cacheKey] = value
  ledOutputStatus = "API OK / Scenes 1-2 verified; 3-5 unverified"
  return true
end
local function resetLEDs()
  if not device or not cfg then return end
  pressedLEDs, ledOutputState = {}, {}
  for _, cc in ipairs(LED_BUTTONS) do sendLED(cc, false, true) end
  -- Clear shared status on the other scenes too, without sending Scene 1
  -- editing-button CCs to their MIDI output routes.
  for _, outputChannel in ipairs(SHARED_LED_OUTPUT_CHANNELS) do
    if outputChannel ~= 0 then
      for _, name in ipairs(SHARED_LED_NAMES) do
        local cc = ccFromSignal(cfg.buttons[name])
        if cc then sendLED(cc, false, true, outputChannel) end
      end
    end
  end
end
local function refreshStateLEDs(force)
  if not cfg or not ledEnabled then return end
  local moving = transportIntent == "playing" or transportIntent == "shuttle"
  local states = {
    play=moving,
    stop=transportIntent == "stopped",
    rew=transportIntent == "shuttle" and transportDirection < 0,
    -- A single L (+1) is 1x PLAY, NOT fast-forward. The second L
    -- (+2) and above are accelerated and illuminate FF.
    ff=transportIntent == "shuttle" and (transportGear or 0) >= 2,
    cycle=mode == "SHUTTLE",
  }
  for _, name in ipairs(SHARED_LED_NAMES) do
    local cc = ccFromSignal(cfg.buttons[name])
    if cc then
      for _, outputChannel in ipairs(SHARED_LED_OUTPUT_CHANNELS) do
        sendLED(cc, states[name], force, outputChannel)
      end
    end
  end
end
local function inputLED(command, meta, signal, value)
  if not cfg or not ledEnabled or command ~= "controlChange" then return end
  local cc = sceneCC(signal)
  if not cc or not LED_BUTTON_SET[cc] then return end
  if value ~= 0 and value ~= 127 then return end
  -- Transport LEDs are persistent shared state, never momentary echoes.
  -- A release must NOT turn STOP/REW/FF off again.
  if cc == ccFromSignal(cfg.buttons.play)
    or cc == ccFromSignal(cfg.buttons.stop)
    or cc == ccFromSignal(cfg.buttons.rew)
    or cc == ccFromSignal(cfg.buttons.ff)
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
        -- The probe temporarily changed a physical LED; restore it
        -- even when our software-side CC cache claims it is unchanged.
        refreshStateLEDs(true)
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
  transportIntent, transportDirection, transportGear = "stopped", 0, 0
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
  transportDirection = target > 0 and 1 or (target < 0 and -1 or 0)
  transportGear = target
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
local function wheel(value, scene1Wheel)
  -- Only CC82 Sign Magnitude is admitted, and all scenes share the SAME
  -- mode and shuttle speed. MARKER SET trim is Scene 1-specific.
  if type(value) ~= "number" or value < 1 or value > 127 or faderActive then return end
  local direction = value <= 64 and 1 or -1
  if trimHeld and scene1Wheel then
    key(direction > 0 and "." or ",")
  elseif mode == "JOG" then
    -- Frame nudging is navigation, not an explicit transport command.
    -- Keep the last known PLAY/STOP/REW/FF intent and persistent LEDs
    -- intact; only PLAY/STOP/JKL/SHUTTLE may change transport status.
    -- Otherwise one wheel tick while playing blanks the PLAY LEDs.
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
    -- A single REW from STOP means reverse 1x. Keep wheel speed in sync.
    shuttle(-1,"rew")
  elseif name == "ff" then
    -- Deliberately start at forward 2x (K, L, L), not forward 1x.
    -- Using the shared shuttle setter lets one counterclockwise wheel
    -- pulse subsequently step from +2 to +1.
    shuttle(2,"ff")
  elseif name == "stop" then stop()
  elseif name == "play" then
    -- PLAY is a normal-speed command when rewinding or fast-shuttling.
    -- From +2 it must DOWN-SHIFT to +1 (K, L), not pause via Space.
    -- From -1 it changes direction to normal forward 1x.
    if transportIntent == "shuttle" and transportGear ~= 1 then
      faderArmed, faderActive = false, false
      shuttle(1,"play")
    else
      -- Preserve the familiar PLAY -> PLAY = pause/stop behavior when
      -- already at normal speed (or Space-toggle when stopped).
      local wasRunning = (transportIntent == "playing"
        or transportIntent == "shuttle" or speed ~= 0)
      cancelShuttle()
      speed, shuttleSource, faderArmed, faderActive = 0, nil, false, false
      key("space")
      transportIntent, transportDirection, transportGear =
        wasRunning and "stopped" or "playing", 0, wasRunning and 0 or 1
      refreshStateLEDs()
      title()
    end
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
  transportIntent, transportDirection, transportGear = "stopped", 0, 0
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
  -- The Korg changes scene without sending a dedicated scene-change event.
  -- Any observed CC from Scene 2..5 invalidates the Scene 1 absolute
  -- shuttle fader's previously learned neutral position. Without this,
  -- returning to Scene 1 can leave faderActive blocking the JOG wheel or
  -- let a stale high/low physical fader take over transport immediately.
  -- Do NOT stop the current transport here; navigation/JOG is shared.
  if command == "controlChange" then
    local _, incomingScene = sceneCC(signal)
    local scene1 = sceneInputChannel()
    if incomingScene and scene1 and incomingScene ~= scene1 then
      if faderArmed or faderActive then
        hs.printf("[NK FADER] other scene input; rearm at Scene 1 neutral before shuttle fader use")
      end
      faderArmed, faderActive = false, false
      trimHeld = false -- stale Scene 1 MARKER/trim must not survive scene switch
    end
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
  if command == "controlChange" then
    local wheelCC, channel = sceneCC(signal)
    if wheelCC and wheelCC == ccFromSignal(cfg.wheel) then
      -- A scene's wheel must be configured to exactly the learned Scene 1
      -- CC82 Sign Magnitude format. No implicit CC86 Continuous decoder.
      wheel(value, channel == sceneInputChannel())
      return
    end
    if wheelCC == 86 and channel ~= sceneInputChannel()
      and not warnedContinuousScenes[channel] then
      warnedContinuousScenes[channel] = true
      hs.printf("[NK JOG] Scene %d wheel CC86 ignored: configure Sign Magnitude / Const / CC82, then Write Scene Data",
        channel - sceneInputChannel() + 1)
    end
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
-- The hardware SCENE button can blank locally-held External LEDs without
-- emitting any MIDI event. Reassert PLAY/STOP/REW/FF/CYCLE every 0.5 s
-- on all five output routes. Scenes 3-5 still need physical LED testing.
-- Other scenes never receive Scene 1-only editing button CCs.
-- No Resolve polling, no changed key actions, no rerunning the 28-step wizard.
local ledHeartbeat = hs.timer.doEvery(LED_HEARTBEAT_SECONDS,function()
  if ledEnabled and enabled and device and cfg and not learning
    and not ledProbeRunning then
    refreshStateLEDs(true) -- bypass cache: scene switch may have blanked LEDs
  end
end)

-- Observe *human* Space/J/K/L keys in Resolve, letting all events through.
-- Our synthetic Korg shortcuts have already updated state in MIDI actions
-- and are suppressed above via syntheticKeyUntil. This does NOT detect clicks.
local function onKeyboardDown(event)
  if not cfg or not enabled or learning or not resolveApp() then return false end
  local code = event:getKeyCode()
  local observed = nil
  for _, name in ipairs({"space","j","k","l"}) do
    if code == hs.keycodes.map[name] then observed=name;break end
  end
  if not observed then return false end
  local flags = event:getFlags()
  if flags.cmd or flags.alt or flags.ctrl or flags.shift or flags.fn then
    return false
  end
  local repeated = event:getProperty(hs.eventtap.event.properties.keyboardEventAutorepeat)
  if repeated and repeated ~= 0 then return false end
  if hs.timer.secondsSinceEpoch() < syntheticKeyUntil[observed] then
    return false -- do not count the Korg's simulated shortcut again
  end
  local wasRunning = transportIntent == "playing"
    or transportIntent == "shuttle" or speed ~= 0
  -- Consecutive physical J or L presses raise that direction's gear;
  -- switching direction starts at first gear. Resolve gets the real key.
  local nextGear
  if observed == "j" then
    nextGear = transportIntent == "shuttle" and transportDirection < 0
      and math.max(-4,(transportGear or 0)-1) or -1
  elseif observed == "l" then
    nextGear = transportIntent == "shuttle" and transportDirection > 0
      and math.min(4,(transportGear or 0)+1) or 1
  elseif observed == "k" or wasRunning then
    nextGear = 0
  else
    nextGear = 1
  end
  cancelShuttle()
  -- Reuse the same signed speed on the physical keyboard and the
  -- SHUTTLE wheel; after a real L,L, wheel-left means +2 -> +1.
  speed = mode == "SHUTTLE" and nextGear or 0
  shuttleSource = speed ~= 0 and "keyboard" or nil
  faderArmed, faderActive = false, false
  transportGear = nextGear
  if nextGear == 0 then
    transportIntent, transportDirection = "stopped", 0
  elseif observed == "j" or observed == "l" then
    transportIntent, transportDirection = "shuttle", nextGear < 0 and -1 or 1
  else
    transportIntent, transportDirection = "playing", 0
  end
  refreshStateLEDs()
  title()
  hs.printf("[NK TRANSPORT] physical %s => %s dir=%d gear=%d (local estimate)",
    observed,transportIntent,transportDirection,transportGear or 0)
  return false -- never consume physical keys; Resolve gets the original
end
local tapStarted, keyboardTap = pcall(function()
  return hs.eventtap.new({hs.eventtap.event.types.keyDown},
    onKeyboardDown):start()
end)
if not tapStarted or not keyboardTap then
  hs.printf("[NK PLAY] Keyboard Space watcher unavailable; check Hammerspoon Input Monitoring / Accessibility.")
  keyboardTap = nil -- fail open; working MIDI/JOG/PLAY must not crash
end
title()
return {setup=beginLearn, ledProbe=ledProbe,
  ledHeartbeat=ledHeartbeat, keyboardTap=keyboardTap,
  isResolveFrontmost=function() return resolveApp() ~= nil end}
