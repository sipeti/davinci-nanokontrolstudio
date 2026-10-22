#!/usr/bin/env python3
"""Read-only DaVinci Resolve 21 status for the nanoKONTROL Studio.

Uses only official Resolve scripting getters; never modifies project/timeline.
Requires Resolve Studio > Preferences > System > General > External scripting: Local.
Run with Resolve 21.1's bundled ResolvePython interpreter.
"""
import json
import sys


def emit(data, code=0):
    print(json.dumps(data, ensure_ascii=True, separators=(",", ":")))
    return code


def snapshot(script_api):
    resolve = script_api.scriptapp("Resolve")
    if resolve is None:
        return {"ok": False, "error": "not_connected"}
    page = resolve.GetCurrentPage()
    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject() if manager else None
    timeline = project.GetCurrentTimeline() if project else None
    return {
        "ok": True,
        "page": str(page).lower() if page else None,
        "project": project.GetName() if project else None,
        "timeline": timeline.GetName() if timeline else None,
        "timecode": timeline.GetCurrentTimecode() if timeline else None,
    }


def main():
    try:
        import DaVinciResolveScript
    except ImportError:
        return emit({"ok": False, "error": "resolve_module_missing"}, 2)
    try:
        data = snapshot(DaVinciResolveScript)
    except Exception as exc:
        # Don't expose internal paths or project values in an error message.
        return emit({"ok": False, "error": "api_exception",
                     "exception_type": type(exc).__name__}, 3)
    return emit(data, 0 if data.get("ok") else 4)


if __name__ == "__main__":
    sys.exit(main())
