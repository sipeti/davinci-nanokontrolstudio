-- Offline: per-session exact project, explicit approval, low latency, STOP.
local factory = dofile("scene2_session_menu.lua")
local started, stopped, answer, project = 0, 0, "Megse", "My Project"
local argv, saved
local host = {
  alert = {show=function(_) end},
  dialog = {
    textPrompt=function(...) return "Tovabb", project end,
    blockAlert=function(...) return answer end,
  },
  settings = {
    get=function(key) return saved end,
    set=function(key, value) saved = value end,
  },
  printf = function(...) end,
  task = {new=function(path, finished, stream, args)
    assert(path == "/opt/homebrew/bin/python3")
    argv = args
    return {
      running=false,
      start=function(self) self.running=true; started=started+1; return self end,
      isRunning=function(self) return self.running end,
      interrupt=function(self) self.running=false; stopped=stopped+1; return self end,
    }
  end}
}
local bridge = {active=false, start=function(self) self.active=true; return true end}
local s = factory(host, bridge, {runner="/dev/null", mcuPython="/dev/null",
  logPath="/dev/null"})
assert(not s:isRunning())
assert(not s:start() and started==0) -- cancelled
answer = "Inditas"
project = "  " -- invalid project name
assert(not s:start() and started==0)
project = "Real Production Project"
assert(s:start() and s:isRunning())
local joined = table.concat(argv, " ")
assert(joined:find("--low-latency",1,true))
assert(joined:find("--allow-named-project",1,true))
assert(joined:find("--expected-project Real Production Project",1,true))
assert(joined:find("--max-clip-writes 0",1,true))
assert(started==1 and saved==project and bridge.active)
assert(s:toggle() and stopped==1 and not s:isRunning())
print("SCENE2_SESSION_MENU_TEST=PASS")
