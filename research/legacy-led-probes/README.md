# Archived / superseded LED hardware probes

This folder preserves the original Script/Tests artifacts from Draft PR #11 for historical reference only. The probes use exploratory mappings, not necessarily the currently accepted physical Scene 2 SOLO CC map (which skips CC32). They are NOT installed or run by product CI. They may open a direct Korg MIDI input when run; never launch them alongside the installed Hammerspoon controller.

The supported implementation is the single Hammerspoon hardware listener plus the Scene 2 MCU / IAC bridge described in docs/INSTALL.md and docs/USER_GUIDE.md. The Scene 1 rearm field note from Draft PR #12 was also archived; its software behavior and regressions are included in this release.
