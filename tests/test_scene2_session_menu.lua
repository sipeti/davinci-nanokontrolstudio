-- Offline: menu starts only after explicit confirmation, stops with SIGINT.
local factory = dofile("scene2_session_menu.lua")
local started, stopped, dialogResult = 0, 0, "Megse"
local argv
local activeTask
local alerts = {}
local host = {
  alert = {show=function(s) alerts[#alerts+1]=s end},
  dialog = {blockAlert=function(...) return dialogResult end},
  printf = function(...) end,
  task = {new=function(path, finished, stream, args)
    assert(path == "/opt/homebrew/bin/python3")
    argv = args
    activeTask = {
      running = false,
      start = function(self) self.running=true; started=started+1; return self end,
      isRunning = function(self) return self.running end,
      interrupt = function(self) self.running=false; stopped=stopped+1; return self end,
    }
    return activeTask
  end}
}
local bridge = {active=false, start=function(self) self.active=true; return true end}
local s = factory(host, bridge, {runner="/dev/null",
  mcuPython="/dev/null", logPath="/dev/null"})
assert(s:isRunning() == false)
assert(s:start() == false) -- user cancelled
assert(started == 0 and bridge.active == false)
dialogResult = "Inditas"
assert(s:start() == true)
assert(s:isRunning() == true and bridge.active == true)
assert(started == 1)
assert(table.concat(argv, " "):find("--run-until-stopped",1,true))
assert(table.concat(argv, " "):find("--low-latency",1,true))
assert(table.concat(argv, " "):find("--mcu-python /dev/null",1,true))
assert(table.concat(argv, " "):find("--max-clip-writes 0",1,true))
assert(s:toggle() == true and stopped == 1)
assert(s:isRunning() == false)
print("SCENE2_SESSION_MENU_TEST=PASS")
