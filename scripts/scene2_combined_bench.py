#!/usr/bin/env python3
"""Scene 2 runtime: Fairlight MCU mixer and per-clip gain.

The Hammerspoon session manager starts both workers when Resolve is ready.
One physical Korg MIDI listener publishes events to the two workers.
Finite manual research mode still uses explicit test-project consent.
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

EVENTS = Path.home() / "Library/Caches/nk-scene2-controller-events.csv"
MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
MCU_CONSENT = "I CONFIRMED A BACKED-UP DISPOSABLE FAIRLIGHT PROJECT"
CLIP_CONSENT = "YES, THIS IS A BACKED-UP TEST PROJECT"
NAMED_CONSENT = "YES, BACKUP EXISTS, PLAYHEAD STOPPED, NO GAIN AUTOMATION"


def parser():
    p = argparse.ArgumentParser(description="Finite combined Scene 2 hardware bench")
    p.add_argument("--seconds", type=int, default=90)
    p.add_argument("--auto-run", action="store_true",
                   help="normal product mode: no prompts, follow active Resolve project")
    p.add_argument("--disable-strip8", action="store_true",
                   help="exclude the eighth MCU bank strip (may be Bus1 "
                        "in projects with fewer than eight audio tracks)")
    p.add_argument("--enable-bank-pages", action="store_true",
                   help="two eight-channel banks via SELECT7/8 (up to A16)")
    p.add_argument("--run-until-stopped", action="store_true",
                   help="explicit Ctrl+C mode (test copy only for writes)")
    p.add_argument("--write-approved-project", "--write-test-copy",
                   dest="write_test_copy", action="store_true",
                   help="Enable mixer and clip writes for one exact project")
    p.add_argument("--allow-named-project", action="store_true",
                   help="Explicitly permit a named non-test project with backup")
    p.add_argument("--expected-project")
    p.add_argument("--confirmed-backup", action="store_true")
    p.add_argument("--confirmed-no-automation", action="store_true")
    p.add_argument("--max-clip-writes", type=int, default=None)
    p.add_argument("--low-latency", action="store_true",
                   help="opt-in 20ms clip poll and no extra per-write wait")
    p.add_argument("--mcu-python", default="/tmp/nk-mcu-venv/bin/python3")
    p.add_argument("--resolve-python", default="/opt/homebrew/bin/python3")
    return p


def commands(args, scripts):
    mcu = [args.mcu_python, str(scripts / "fairlight_mcu_continuous.py"),
           "--input-port", "IAC Driver NK FL From Resolve",
           "--output-port", "IAC Driver NK FL To Resolve",
           "--seconds", str(args.seconds)]
    if args.run_until_stopped:
        mcu.append("--continuous")
    clip = [args.resolve_python, str(scripts / "scene2_continuous_clip_gain.py"),
            "--seconds", str(args.seconds)]
    if args.low_latency:
        clip.append("--low-latency")
    if args.auto_run:
        # Existing proven MCU faders 1..7 and MUTE/SOLO remain unchanged.
        mcu += ["--enable-output", "--consent", MCU_CONSENT]
        # Eight audio tracks are now physically verified. The eighth
        # physical slider is CC12; the current MCU strip8 can be A8 or
        # another channel (including Bus1) depending on the Resolve bank.
        # Allow a simple user override, without touching the MCU protocol.
        if not args.disable_strip8:
            mcu.append("--enable-strip8-bus1")
        if args.enable_bank_pages:
            mcu.append("--enable-bank-pages")
            clip.append("--follow-mcu-bank")
        clip += ["--follow-active-project", "--unlimited-writes"]
    if args.write_test_copy:
        mcu += ["--enable-output", "--consent", MCU_CONSENT]
        clip += ["--write-approved-project", "--expected-project", args.expected_project,
                 "--confirmed-no-automation", "--consent",
                 NAMED_CONSENT if args.allow_named_project else CLIP_CONSENT]
        if args.allow_named_project:
            clip.append("--allow-named-project")
        if args.max_clip_writes == 0:
            clip.append("--unlimited-writes")
        else:
            clip.extend(["--max-writes", str(args.max_clip_writes)])
    env = os.environ.copy()
    env["PYTHONPATH"] = MODULES + (os.pathsep + env["PYTHONPATH"]
                                    if env.get("PYTHONPATH") else "")
    return [("MCU", mcu, None), ("CLIP", clip, env)]


def stop_running(processes):
    """SIGINT allows the MCU worker to release touch/buttons in its finally."""
    for process in processes.values():
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
    for process in processes.values():
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def supervise(specs):
    running = {}
    finished = {}
    try:
        for name, cmd, env in specs:
            process = subprocess.Popen(cmd, env=env, start_new_session=True)
            running[name] = process
            print("SCENE2_COMBINED=WORKER_START; worker=%s; pid=%d" %
                  (name, process.pid), flush=True)
        while running:
            for name, process in list(running.items()):
                status = process.poll()
                if status is None:
                    continue
                finished[name] = status
                del running[name]
                print("SCENE2_COMBINED=WORKER_END; worker=%s; exit=%d" %
                      (name, status), flush=True)
                if status != 0:
                    print("SCENE2_COMBINED=HALT; %s worker failed" % name,
                          flush=True)
                    return 1
            if running:
                time.sleep(0.05)
        print("SCENE2_COMBINED=COMPLETE; mcu=%d; clip=%d" %
              (finished["MCU"], finished["CLIP"]), flush=True)
        return 0
    except KeyboardInterrupt:
        print("SCENE2_COMBINED=STOP; Ctrl+C", flush=True)
        return 130
    except OSError as exc:
        print("SCENE2_COMBINED=HALT; worker launch failed: %s" % exc,
              flush=True)
        return 1
    finally:
        stop_running(running)


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.disable_strip8 and not args.auto_run:
        p.error("--disable-strip8 requires --auto-run")
    if args.enable_bank_pages and (not args.auto_run or args.disable_strip8):
        p.error("--enable-bank-pages needs --auto-run and all 8 MCU strips")
    if args.auto_run:
        if (args.write_test_copy or args.allow_named_project or
                args.expected_project or args.confirmed_backup or
                args.confirmed_no_automation or args.max_clip_writes is not None or
                args.run_until_stopped or args.seconds != 90):
            p.error("--auto-run cannot be mixed with manual test controls")
        args.run_until_stopped = True
        args.low_latency = True
        args.max_clip_writes = 0
        args.seconds = 0
    if args.run_until_stopped and not args.auto_run:
        if args.seconds != 90:
            p.error("--run-until-stopped cannot be combined with --seconds")
        args.seconds = 0
    elif not args.auto_run and not 5 <= args.seconds <= 180:
        p.error("--seconds must be 5..180 (bounded MCU bench)")
    if args.max_clip_writes is None:
        args.max_clip_writes = (0 if args.run_until_stopped and
                               args.write_test_copy else 12)
    if not (1 <= args.max_clip_writes <= 256 or
            args.max_clip_writes == 0 and args.run_until_stopped
            and (args.write_test_copy or args.auto_run)):
        p.error("clip writes: 1..256, or 0 only for a continuous test copy")
    if args.allow_named_project and not args.write_test_copy:
        p.error("--allow-named-project requires --write-approved-project")
    if args.write_test_copy and (not args.expected_project or
                                 not args.confirmed_backup or
                                 not args.confirmed_no_automation):
        p.error("writes require exact --expected-project, --confirmed-backup "
                "and --confirmed-no-automation")
    if not EVENTS.is_file() or time.time() - EVENTS.stat().st_mtime > 3:
        p.error("Hammerspoon MIDI input heartbeat missing: restart the NK controller")
    scripts = Path(__file__).resolve().parent
    for filename in ("fairlight_mcu_continuous.py", "fairlight_mcu_bridge.py",
                     "scene2_continuous_clip_gain.py", "scene2_clip_gain_8rotary.py",
                     "scene2_soft_takeover.py", "scene2_live_pickup_readonly.py",
                     "scene2_audio_roundtrip_probe.py"):
        if not (scripts / filename).is_file():
            p.error("staged script missing: %s" % filename)
    for executable in (args.mcu_python, args.resolve_python):
        if not (Path(executable).is_file() and os.access(executable, os.X_OK)):
            p.error("Python executable unavailable: %s" % executable)
    print("SCENE2_COMBINED=START; duration=%s; mode=%s; "
          "one physical Korg MIDI owner; strip8 %s" %
          ("until Ctrl+C" if args.run_until_stopped else str(args.seconds)+"s",
           "AUTO_FOLLOW_PROJECT" if args.auto_run else
           "TEST_COPY_WRITE" if args.write_test_copy else
           "READ_ONLY",
           "ENABLED (CURRENT MCU BANK)" if args.auto_run and
           not args.disable_strip8 else "LOCKED"), flush=True)
    return supervise(commands(args, scripts))


if __name__ == "__main__":
    sys.exit(main())
