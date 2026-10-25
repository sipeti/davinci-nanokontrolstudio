"""Pure, write-free Scene 2 clip-gain pickup logic.

No Resolve imports, SetProperties, MIDI callback or I/O in this module.
A future integration must supply an authoritative fresh snapshot for each
physical event, prove clip automation is safe, and separately perform a
revalidated setter/verification before calling confirm().
"""

from dataclasses import dataclass
import math


# Absolute CC13..20 in Korg Scene 2 (incoming zero-based MIDI channel 1).
SCENE2_CHANNEL = 1
FIRST_KNOB_CC = 13
LAST_KNOB_CC = 20
EPSILON_DB = 0.055
PICKUP_WINDOW_DB = 0.55



@dataclass(frozen=True)
class Decision:
    state: str
    strip: int = 0
    proposed_db: float = None
    reason: str = ""


def gain_for_cc(value):
    """Absolute rotary: left -100dB, centre CC64 0dB, right +30dB.

    Piecewise linear audio taper has smaller steps around 0dB without
    changing the hardware scene or requiring calibration.
    """
    if type(value) is not int or not 0 <= value <= 127:
        raise ValueError("MIDI value must be a CC integer in 0..127")
    if value <= 16:
        gain = -100.0 + 64.0 * value / 16.0
    elif value <= 40:
        gain = -36.0 + (value - 16)
    elif value <= 64:
        gain = -12.0 + 0.5 * (value - 40)
    elif value <= 108:
        gain = 12.0 * (value - 64) / 44.0
    else:
        gain = 12.0 + 18.0 * (value - 108) / 19.0
    return round(gain, 3)


def _valid_identity(identity, strip):
    """Require (project UID, timeline UID, track, clip UID, start, end)."""
    return (
        isinstance(identity, tuple) and len(identity) == 6
        and all(value is not None and value != "" for value in identity)
        and all(isinstance(identity[index], str) for index in (0, 1, 3))
        and type(identity[2]) is int and identity[2] == strip
        and all(type(identity[index]) in (int, float) and
                math.isfinite(identity[index]) for index in (4, 5))
        and identity[4] < identity[5]
    )


def _valid_db(db):
    return type(db) in (float, int) and math.isfinite(db) and -100 <= db <= 30


class SoftTakeover:
    """Independent, fail-closed pickup for eight Scene 2 rotary knobs.

    feed() returns an untrusted WRITE_INTENT, never a performed write. The
    caller MUST verify project, timeline, item, playhead, automation state
    and fresh dB once again immediately before SetProperties; then verify
    setter/readback and call confirm(). Any failure must call reject().
    """

    def __init__(self):
        self._strips = {}

    def reset(self):
        """Required on scene change, project/timeline switch and reconnect."""
        self._strips.clear()

    def reject(self, strip):
        self._strips.pop(strip, None)

    def state(self, strip):
        return self._strips.get(strip, {}).get("state", "DISABLED")

    def feed(self, channel, cc, value, identity=None, observed_db=None,
             authority_ok=False, track_offset=0):
        """Process exactly one incoming CC event and a FRESH gain snapshot."""
        if type(channel) is not int or channel != SCENE2_CHANNEL:
            # No scene-change event is guaranteed by hardware; invalidate on
            # every observed different input scene (and explicitly on switch).
            self.reset()
            return Decision("DISABLED", reason="outside Scene 2")
        if type(cc) is not int or not FIRST_KNOB_CC <= cc <= LAST_KNOB_CC:
            return Decision("IGNORED", reason="not a Scene 2 knob")
        if type(track_offset) is not int or track_offset not in (0, 8):
            return Decision("DISABLED", reason="invalid MCU track bank")
        strip = cc - FIRST_KNOB_CC + 1 + track_offset
        if type(value) is not int or not 0 <= value <= 127:
            self.reject(strip)
            return Decision("DISABLED", strip, reason="invalid MIDI CC value")
        if (authority_ok is not True or
                not _valid_identity(identity, strip) or
                not _valid_db(observed_db)):
            self.reject(strip)
            return Decision("DISABLED", strip, reason="missing trusted snapshot")
        current = self._strips.get(strip)
        if current is None or current["identity"] != identity or abs(
                current["expected_db"] - observed_db) > EPSILON_DB:
            # New clip or an external edit MUST rearm, never reuse position.
            self._strips[strip] = {
                "identity": identity, "expected_db": observed_db,
                "state": "PICKUP_PENDING", "last_cc": value,
            }
            return Decision("PICKUP_PENDING", strip,
                            reason="new target or out-of-band gain")
        if current["state"] == "AWAIT_ACK":
            # No second intent until the previous setter result is verified.
            self.reject(strip)
            return Decision("DISABLED", strip, reason="unacknowledged intent")

        previous_cc = current["last_cc"]
        current["last_cc"] = value
        if current["state"] == "PICKUP_PENDING":
            before_db, after_db = gain_for_cc(previous_cc), gain_for_cc(value)
            near_target = abs(after_db - observed_db) <= PICKUP_WINDOW_DB
            # Absolute rotary input may skip the exact pickup point.
            # A real crossing proves pickup, whatever the movement speed.
            # If the last sample overshot, that last CC is the requested
            # clip gain: commit it without waiting for another physical tick.
            crossed = (previous_cc != value and
                       min(before_db, after_db) <= observed_db <=
                       max(before_db, after_db))
            if previous_cc != value and (near_target or crossed):
                if crossed and not near_target and abs(
                        after_db - observed_db) > EPSILON_DB:
                    current["state"] = "AWAIT_ACK"
                    current["wanted_db"] = after_db
                    return Decision("WRITE_INTENT", strip, after_db,
                                    "physical pickup crossing; last CC")
                current["state"] = "ENGAGED"
                return Decision("ENGAGED", strip, reason="pickup; no write")
            return Decision("PICKUP_PENDING", strip, reason="waiting for pickup")

        if previous_cc == value:
            return Decision("ENGAGED", strip, reason="no physical movement")
        wanted_db = gain_for_cc(value)
        # After pickup, every changed physical absolute CC is intentional.
        # The caller still checks the real clip and verifies the write.
        if abs(wanted_db - observed_db) <= EPSILON_DB:
            return Decision("ENGAGED", strip, reason="no gain change")
        current["state"] = "AWAIT_ACK"
        current["wanted_db"] = wanted_db
        return Decision("WRITE_INTENT", strip, wanted_db,
                        "needs fresh context check, setter and readback")

    def confirm(self, strip, identity, verified_db, setter_succeeded):
        """Accept only an explicitly verified WRITE_INTENT on same item."""
        current = self._strips.get(strip)
        if (current is None or current["state"] != "AWAIT_ACK" or
                current["identity"] != identity or setter_succeeded is not True
                or not _valid_db(verified_db) or abs(
                    verified_db - current["wanted_db"]) > EPSILON_DB):
            self.reject(strip)
            return False
        current["expected_db"] = verified_db
        current["state"] = "ENGAGED"
        current.pop("wanted_db", None)
        return True
