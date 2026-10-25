#!/usr/bin/env python3
"""Single-command, finite Scene 2 bench: MCU mixer + Resolve clip gain.

Both workers tail the SAME Hammerspoon event file. Hammerspoon alone owns
physical Korg MIDI. This launcher opens no MIDI device and modifies no
Scene 1 / Hammerspoon configuration. No production auto-start.
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


def parser():
    p = argparse.ArgumentParser(description="Finite combined Scene 2 hardware bench")
    p.add_argument("--seconds", type=int, default=90)
    p.add_argument("--run-until-stopped", action="store_true",
                   help="explicit Ctrl+C mode (test copy only for writes)")
    p.add_argument("--write-test-copy", action="store_true",
                   help="Allow both MCU mixer and per-clip gain writes in disposable project")
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
    if args.write_test_copy:
        mcu += ["--enable-output", "--consent", MCU_CONSENT]
        clip += ["--write-test-copy", "--expected-project", args.expected_project,
                 "--confirmed-no-automation", "--consent", CLIP_CONSENT]
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
    if args.run_until_stopped:
        if args.seconds != 90:
            p.error("--run-until-stopped cannot be combined with --seconds")
        args.seconds = 0
    elif not 5 <= args.seconds <= 180:
        p.error("--seconds must be 5..180 (bounded MCU bench)")
    if args.max_clip_writes is None:
        args.max_clip_writes = (0 if args.run_until_stopped and
                               args.write_test_copy else 12)
    if not (1 <= args.max_clip_writes <= 256 or
            args.max_clip_writes == 0 and args.run_until_stopped
            and args.write_test_copy):
        p.error("clip writes: 1..256, or 0 only for a continuous test copy")
    if args.write_test_copy and (not args.expected_project or
                                 not args.confirmed_backup or
                                 not args.confirmed_no_automation):
        p.error("writes require exact --expected-project, --confirmed-backup "
                "and --confirmed-no-automation")
    if not EVENTS.is_file() or time.time() - EVENTS.stat().st_mtime > 3:
        p.error("Hammerspoon heartbeat absent: NK JOG > Scene 2 MIDI bridge: BE")
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
          "one physical Korg MIDI owner; strip8 LOCKED" %
          ("until Ctrl+C" if args.run_until_stopped else str(args.seconds)+"s",
           "TEST_COPY_WRITE" if args.write_test_copy
           else "READ_ONLY"), flush=True)
    return supervise(commands(args, scripts))


if __name__ == "__main__":
    sys.exit(main())
