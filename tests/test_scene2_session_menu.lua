-- Scene 2 product mode starts silently with Resolve, stops on pause.
local factory = dofile("scene2_session_menu.lua")
local now = 100
local ready, runningApp = false, true
local starts, interrupts, bridgeStarts, bridgeStops = 0, 0, 0, 0
local stored = false -- legacy persisted pause must NOT disable login startup
local reloads = 0
local timer = nil
local lastArgs, currentTask
local host = {
  printf=function(...) end,
  reload=function() reloads=reloads+1 end,
  settings={
    get=function(key) return stored end,
    set=function(key, value) stored=value end,
  },
  timer={doEvery=function(interval, cb)
    assert(interval==1)
    timer={callback=cb,stopped=false,stop=function(self) self.stopped=true end}
    return timer
  end},
  task={new=function(_, finished, streamed, args)
    assert(type(streamed)=="function")
    lastArgs=args
    currentTask={
      running=false, done=finished,
      start=function(self)
        assert(not self.running)
        self.running=true; starts=starts+1
        return self
      end,
      isRunning=function(self) return self.running end,
      interrupt=function(self)
        self.running=false; interrupts=interrupts+1
      end
    }
    return currentTask
  end},
}
local bridge={
  active=false, bankIndex=0, bankStatus=1,
  start=function(self)
    self.active=true; bridgeStarts=bridgeStarts+1; return true
  end,
  stop=function(self)
    self.active=false; bridgeStops=bridgeStops+1
  end,
}
local function make(opts)
  opts=opts or {}
  opts.runner="/dev/null"
  opts.python="/dev/null"
  opts.mcuPython="/dev/null"
  opts.logPath="/dev/null"
  opts.ready=function() return ready end
  opts.appRunning=function() return runningApp end
  opts.clock=function() return now end
  return factory(host,bridge,opts)
end

local s=make()
assert(s:isEnabled() and not s:isRunning())
timer.callback()
assert(starts==0, "no launch until Resolve becomes active")
ready=true
timer.callback()
assert(starts==1 and s:isRunning() and bridgeStarts==1)
local cmd=table.concat(lastArgs," ")
assert(cmd:find("--auto-run",1,true))
assert(not cmd:find("--expected-project",1,true))
assert(not cmd:find("--confirmed-backup",1,true))
assert(not cmd:find("--allow-named-project",1,true))
assert(stored==false, "legacy persisted pause must be ignored on startup")
assert(s:isBankPagesEnabled(), "two-bank mode starts automatically")
timer.callback()
assert(starts==1, "single Python task owner")
assert(s:pause() and stored==false and interrupts==1)
assert(not bridge.active and bridgeStops==1)
currentTask.done(130, "", "")
timer.callback()
assert(starts==1, "paused session must not restart")
assert(not s:isEnabled())
assert(s:resume() and stored==false and starts==2)
currentTask.running=false
currentTask.done(1,"","")
timer.callback()
assert(starts==2, "unexpected error must back off")
now=111
timer.callback()
assert(starts==3, "bounded automatic recovery")
runningApp=false
timer.callback()
assert(interrupts==2, "quitting Resolve stops workers")
currentTask.done(130,"","")
assert(not bridge.active,
  "Resolve quit must close the idle bridge after the workers exit")
ready=false
now=113
timer.callback()
assert(starts==3)
runningApp=true
ready=true
now=114
timer.callback()
assert(starts==4, "Resolve reopen automatically reactivates")
s:shutdown()
assert(timer.stopped and interrupts==3)
assert(stored==false, "normal operation never writes persistent pause")
currentTask.done(130,"","")
local paused=make({timer=false,autoEnabled=false})
assert(not paused:isEnabled())
assert(not paused:ensureRunning())
paused:shutdown()

-- A8 was physically verified in Resolve (Bus1 unchanged).
-- Default 1..8 uses exactly the existing MCU worker and command.
-- A local off-switch lets users avoid Bus1 in a shorter mixer bank.
ready=true
runningApp=true
local strip8=make({timer=false})
assert(strip8:isEnabled() and strip8:isStrip8Enabled())
assert(strip8:isBankPagesEnabled())
assert(strip8:toggleBankPages() and not strip8:isBankPagesEnabled(),
  "channel 8 can only be disabled after turning off banking")
assert(strip8:isRunning(), "bank toggle starts the worker automatically")
assert(not table.concat(lastArgs," "):find("--disable-strip8",1,true))
assert(strip8:toggleStrip8() and not strip8:isStrip8Enabled())
assert(not currentTask:isRunning(), "toggle stops the running worker")
currentTask.done(130, "", "")
now=now+2
assert(strip8:ensureRunning())
assert(table.concat(lastArgs," "):find("--disable-strip8",1,true))
assert(strip8:pause() and not strip8:isStrip8Enabled(),
  "pause must preserve user's explicit strip8 choice")
currentTask.done(130, "", "")
assert(not strip8:toggleStrip8(), "no strip8 change while paused")
assert(strip8:resume(), "resume starts the same selected bank mode")
assert(table.concat(lastArgs," "):find("--disable-strip8",1,true))
assert(strip8:toggleStrip8() and strip8:isStrip8Enabled())
currentTask.done(130, "", "")
now=now+2
assert(strip8:ensureRunning())
assert(not table.concat(lastArgs," "):find("--disable-strip8",1,true))
strip8:shutdown()
local bank=make({timer=false})
assert(bank:isBankPagesEnabled(), "banking starts on by default")
assert(bank:start(), "new manager starts two-bank mode")
assert(bank:isStrip8Enabled(), "bank pages require eight enabled MCU strips")
assert(table.concat(lastArgs," "):find("--enable-bank-pages",1,true))
assert(not bank:toggleStrip8(), "cannot disable strip8 during bank preview")
bridge.bankIndex=1
assert(not bank:toggleBankPages(),
  "bank2 cannot silently be mistaken for bank1 on restart")
bridge.bankIndex=0
assert(bank:toggleBankPages() and not bank:isBankPagesEnabled())
bank:shutdown()
local fresh=make({timer=false})
assert(fresh:isStrip8Enabled(),
  "eight channels default ON after a new manager instance")
fresh:shutdown()
local restart=make({timer=false})
ready=true
bridge.bankIndex,bridge.bankStatus=0,1
assert(restart:start())
local initial=reloads
assert(restart:restart() and interrupts>0, "restart must stop workers")
assert(reloads==initial, "reload must wait for supervisor exit")
currentTask.done(130,"","")
assert(reloads==initial+1, "worker exit triggers one reload")
restart:shutdown()
local stopped=make({timer=false})
bridge.bankIndex=1
assert(not stopped:canRestart(), "bank2 must return to bank1 before restart")
assert(not stopped:restart(), "unconfirmed bank must not be mislabeled")
bridge.bankIndex=0
bridge.bankStatus=0
assert(not stopped:restart(), "pending bank must not restart")
bridge.bankStatus=1
assert(stopped:restart() and reloads==initial+2,
  "idle restart immediately reloads controller")
stopped:shutdown()
print("SCENE2_AUTO_SESSION_TEST=PASS")
