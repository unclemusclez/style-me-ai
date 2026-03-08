"""
╔══════════════════════════════════════════════════════════════════════╗
║       🪩 DISCO MAESTRO v2 — AI-Powered XR Hand Tracking 🪩          ║
║                                                                      ║
║  Conduct your light show like an opera maestro!                      ║
║  • MediaPipe Hands (compatible with 0.10.30+)                        ║
║  • Anthropic Claude — reads your gesture sequence & mood             ║
║    to generate intelligent lighting/effect suggestions               ║
║  • 18 distinct hand gestures + velocity / trajectory tracking        ║
╚══════════════════════════════════════════════════════════════════════╝

INSTALL:
    pip install mediapipe>=0.10.30 opencv-python pygame numpy anthropic

SET YOUR API KEY (one-time):
    export ANTHROPIC_API_KEY="sk-ant-..."

RUN:
    python disco_hand_controller_v2.py /path/to/track.mp3
    python disco_hand_controller_v2.py          # camera-only / no music

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GESTURE MAP (18 gestures)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RIGHT HAND (primary conductor):
  ✋ Open hand          → Full white light  /  reset all
  👊 Fist               → Bass boost  +  red strobe
  ☝️  Point (index up)   → Volume = hand height  /  BPM warp
  ✌️  Peace              → Blue chill mode
  🤙 Call-me (🤙)       → Rainbow beat-sync
  🤌 Pinch              → Crossfade brightness
  👍 Thumbs-up          → Pump up energy (gold flash)
  👎 Thumbs-down        → Fade out / dim
  🖖 Vulcan salute      → Psychedelic color shift
  🤞 Crossed fingers    → Rapid color cycle
  THREE fingers (234)   → Strobe ON medium
  FOUR fingers (2345)   → Strobe ON fast

LEFT HAND (color / scene):
  ✋ Open hand          → Rainbow flash burst
  👊 Fist               → Fade to black / silence
  ✌️  Peace              → Purple cosmic mode
  🤌 Pinch              → Ocean blue ambient
  👋 Wave (motion)      → Confetti rainbow sweep
  🙌 Both open hands    → FULL DISCO EXPLOSION 🎉

POSITIONAL AXES (right hand):
  Y-axis  ↕  → Volume  (top=max, bottom=min)
  X-axis  ↔  → Stereo pan  (left=L, right=R)
  Z-depth 🔲 → Estimated by palm area: close=bass++, far=treble++

VELOCITY gestures:
  Fast swipe LEFT   → Previous color theme
  Fast swipe RIGHT  → Next color theme
  Fast swipe UP     → Strobe burst
  Fast swipe DOWN   → Blackout 1s

AI MAESTRO (Claude):
  Every ~8 seconds Claude reads your recent gesture history + current
  state and suggests the optimal lighting/effect update. The suggestion
  is applied automatically and shown on the HUD. Press 'A' to force-
  trigger an AI analysis at any time.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ── Compatibility shim for mediapipe 0.10.30+ ──────────────────────────────
import importlib, sys, types

def _get_mp_solutions():
    """
    MediaPipe >= 0.10.18 moved solutions under mediapipe.python.solutions.
    This shim works on all versions from 0.10.0 → 0.10.32+
    """
    import mediapipe as mp
    # Try the classic path first
    if hasattr(mp, "solutions"):
        return mp.solutions
    # New path
    try:
        from mediapipe.python import solutions as sol
        # Monkey-patch so the rest of the code can use mp.solutions
        mp.solutions = sol
        return sol
    except ImportError:
        pass
    # Final fallback: direct submodule import
    try:
        import mediapipe.python.solutions.hands          # noqa
        import mediapipe.python.solutions.drawing_utils  # noqa
        import mediapipe.python.solutions.drawing_styles # noqa
        sol_mod = types.SimpleNamespace(
            hands          = importlib.import_module("mediapipe.python.solutions.hands"),
            drawing_utils  = importlib.import_module("mediapipe.python.solutions.drawing_utils"),
            drawing_styles = importlib.import_module("mediapipe.python.solutions.drawing_styles"),
        )
        import mediapipe as mp
        mp.solutions = sol_mod
        return sol_mod
    except Exception as e:
        print(f"[FATAL] Cannot load mediapipe solutions: {e}")
        print("  Try:  pip install mediapipe==0.10.14  (Python 3.10)")
        sys.exit(1)

import mediapipe as _mp_raw
_solutions = _get_mp_solutions()
mp_hands_mod  = _solutions.hands
mp_draw_mod   = _solutions.drawing_utils
mp_styles_mod = _solutions.drawing_styles

# ── Standard imports ────────────────────────────────────────────────────────
import cv2
import numpy as np
import pygame
import os, math, time, threading, queue, json
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict

# ── Anthropic ───────────────────────────────────────────────────────────────
try:
    import anthropic
    ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    if not ANTHROPIC_KEY:
        print("[AI] ⚠️  ANTHROPIC_API_KEY not set. AI suggestions disabled.")
        print("       export ANTHROPIC_API_KEY='sk-ant-...'")
    AI_ENABLED = bool(ANTHROPIC_KEY)
    ai_client  = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if AI_ENABLED else None
except ImportError:
    print("[AI] anthropic package not installed. pip install anthropic")
    AI_ENABLED = False
    ai_client  = None

# ── Config ──────────────────────────────────────────────────────────────────
CAMERA_INDEX     = 0
WINDOW_NAME      = "DISCO MAESTRO v2  |  AI Conductor"
FRAME_W, FRAME_H = 1280, 720
MIN_VOL, MAX_VOL = 0.0, 1.0
AI_INTERVAL_SEC  = 8      # How often Claude analyses gestures (seconds)
GESTURE_HISTORY_LEN = 40  # Gesture log kept for AI context

# ── Color themes (BGR) ──────────────────────────────────────────────────────
THEMES = [
    ("rainbow",  None),
    ("fire",     (30,  60,  220)),
    ("ocean",    (200, 120,  20)),
    ("forest",   (40,  180,  40)),
    ("cosmic",   (200,  30, 160)),
    ("gold",     (20,  200, 230)),
    ("pink",     (180,  60, 255)),
    ("arctic",   (220, 200, 180)),
    ("void",     (20,   20,  20)),
]
_theme_idx = 0

def next_theme():
    global _theme_idx
    _theme_idx = (_theme_idx + 1) % len(THEMES)
    return THEMES[_theme_idx][0]

def prev_theme():
    global _theme_idx
    _theme_idx = (_theme_idx - 1) % len(THEMES)
    return THEMES[_theme_idx][0]

# ── State ────────────────────────────────────────────────────────────────────
@dataclass
class DiscoState:
    volume:          float = 0.8
    brightness:      float = 1.0
    color_mode:      str   = "rainbow"
    strobe_hz:       float = 0.0
    bass_boost:      bool  = False
    treble_boost:    bool  = False
    pan:             float = 0.0
    bpm_warp:        float = 1.0
    beat_sync:       bool  = False
    ambient:         bool  = False
    flash:           bool  = False
    blackout:        bool  = False
    energy_level:    float = 0.5    # 0–1 overall scene energy
    last_gesture:    str   = "---"
    ai_suggestion:   str   = "Waiting for AI..."
    right_hand_pos:  tuple = (0.5, 0.5)
    left_hand_pos:   tuple = (0.5, 0.5)
    right_velocity:  tuple = (0.0, 0.0)
    left_velocity:   tuple = (0.0, 0.0)
    palm_area_right: float = 0.0   # proxy for Z-depth

state = DiscoState()

# ── Gesture history for AI ────────────────────────────────────────────────────
gesture_log: deque = deque(maxlen=GESTURE_HISTORY_LEN)

# ── AI suggestion queue ───────────────────────────────────────────────────────
ai_queue: queue.Queue = queue.Queue(maxsize=2)

# ── Lighting ─────────────────────────────────────────────────────────────────
_rainbow_hue = 0.0

def hsv_bgr(hue: float) -> tuple:
    h = (hue % 360) / 60.0
    i = int(h) % 6
    f = h - int(h)
    lut = [
        (0, f, 1), (0, 1, 1-f), (f, 1, 0),
        (1, 1-f, 0), (1, 0, f), (1-f, 0, 1)
    ]
    r, g, b = lut[i]
    return (int(b*255), int(g*255), int(r*255))

def get_light_color() -> tuple:
    global _rainbow_hue
    if state.color_mode == "rainbow":
        speed = 1.5 + state.energy_level * 4.0
        _rainbow_hue = (_rainbow_hue + speed) % 360
        return hsv_bgr(_rainbow_hue)
    for name, bgr in THEMES:
        if name == state.color_mode and bgr is not None:
            return bgr
    return (255, 255, 255)

def apply_lighting_overlay(frame: np.ndarray) -> np.ndarray:
    if state.blackout:
        return np.zeros_like(frame)

    color = get_light_color()
    alpha = min(state.brightness * 0.5, 0.70)

    if state.strobe_hz > 0:
        on = (time.time() * state.strobe_hz % 1.0) < 0.5
        if not on:
            alpha, color = 0.0, (0, 0, 0)

    overlay = np.full_like(frame, color, dtype=np.uint8)
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha * 0.4, 0, frame)

    if state.flash:
        white = np.full_like(frame, (255, 255, 255), dtype=np.uint8)
        cv2.addWeighted(white, 0.55, frame, 0.45, 0, frame)

    # Energy pulse ring
    if state.energy_level > 0.7:
        cx, cy = FRAME_W // 2, FRAME_H // 2
        r = int(80 + state.energy_level * 200)
        cv2.circle(frame, (cx, cy), r,
                   tuple(int(c * state.energy_level) for c in color), 2, cv2.LINE_AA)

    return frame

# ── Geometry helpers ──────────────────────────────────────────────────────────
def fingers_up(lm_list) -> List[bool]:
    tips   = [4, 8, 12, 16, 20]
    joints = [3, 6, 10, 14, 18]
    up = [lm_list[tips[0]].x < lm_list[joints[0]].x]
    for i in range(1, 5):
        up.append(lm_list[tips[i]].y < lm_list[joints[i]].y)
    return up

def pinch_dist(lm_list) -> float:
    dx = lm_list[4].x - lm_list[8].x
    dy = lm_list[4].y - lm_list[8].y
    return math.sqrt(dx*dx + dy*dy)

def palm_area(lm_list) -> float:
    """Rough palm bounding box area as Z-depth proxy."""
    xs = [lm_list[i].x for i in [0,1,5,9,13,17]]
    ys = [lm_list[i].y for i in [0,1,5,9,13,17]]
    return (max(xs)-min(xs)) * (max(ys)-min(ys))

def wrist(lm_list) -> tuple:
    return (lm_list[0].x, lm_list[0].y)

def finger_angle(lm_list, tip, mid, base) -> float:
    """Angle at mid between base→mid→tip (degrees)."""
    def v(a, b): return (lm_list[b].x-lm_list[a].x, lm_list[b].y-lm_list[a].y)
    v1, v2 = v(mid, base), v(mid, tip)
    dot = v1[0]*v2[0] + v1[1]*v2[1]
    m1  = math.sqrt(v1[0]**2+v1[1]**2)+1e-6
    m2  = math.sqrt(v2[0]**2+v2[1]**2)+1e-6
    return math.degrees(math.acos(max(-1, min(1, dot/(m1*m2)))))

# ── Gesture classifier (18 gestures) ─────────────────────────────────────────
def classify_gesture(hand_lm) -> str:
    lm   = hand_lm.landmark
    up   = fingers_up(lm)
    pinch= pinch_dist(lm)
    n    = sum(up)

    thumb, idx, mid, ring, pinky = up

    # Exact finger combos
    if n == 0:                                        return "fist"
    if n == 5:                                        return "open_hand"
    if idx and not mid and not ring and not pinky:
        if thumb:                                     return "point_thumb"  # gun
        return "point"
    if idx and mid and not ring and not pinky:
        if thumb:                                     return "three_fingers"
        return "peace"
    if idx and mid and ring and not pinky:            return "three_fingers"
    if idx and mid and ring and pinky and not thumb:  return "four_fingers"
    if thumb and not idx and not mid and not ring and not pinky: return "thumbs_up"
    if not thumb and idx and not mid and not ring and pinky:     return "call_me"
    if thumb and idx and mid and not ring and not pinky:         return "ok_three"

    # Vulcan salute: idx+mid up, ring+pinky up, gap between
    if idx and mid and ring and pinky:
        gap = abs(lm[8].x - lm[12].x)
        if gap > 0.06:                                return "vulcan"

    if pinch < 0.04:                                  return "pinch"

    # Thumbs down: thumb pointing down (y high), others curled
    if thumb and lm[4].y > lm[3].y and n == 1:       return "thumbs_down"

    # Crossed fingers: idx over mid
    if idx and mid and lm[8].x > lm[12].x:           return "crossed"

    return "partial"

# ── Velocity / trajectory tracker ────────────────────────────────────────────
class VelocityTracker:
    def __init__(self, window=6):
        self.hist = deque(maxlen=window)
        self.t    = deque(maxlen=window)

    def update(self, pos: tuple) -> tuple:
        now = time.time()
        self.hist.append(pos)
        self.t.append(now)
        if len(self.hist) < 2:
            return (0.0, 0.0)
        dt = self.t[-1] - self.t[-2] + 1e-6
        vx = (self.hist[-1][0] - self.hist[-2][0]) / dt
        vy = (self.hist[-1][1] - self.hist[-2][1]) / dt
        return (vx, vy)

    def swipe(self, threshold=1.2) -> Optional[str]:
        """Detect fast swipe direction over recent history."""
        if len(self.hist) < 4:
            return None
        dx = self.hist[-1][0] - self.hist[0][0]
        dy = self.hist[-1][1] - self.hist[0][1]
        dt = self.t[-1]  - self.t[0]  + 1e-6
        spd = math.sqrt(dx*dx + dy*dy) / dt
        if spd < threshold:
            return None
        if abs(dx) > abs(dy):
            return "swipe_right" if dx > 0 else "swipe_left"
        else:
            return "swipe_down"  if dy > 0 else "swipe_up"

r_tracker = VelocityTracker()
l_tracker = VelocityTracker()

# ── Main gesture → state mapping ──────────────────────────────────────────────
_blackout_until = 0.0
_last_swipe_t   = 0.0

def update_state_from_gestures(result, frame_h, frame_w):
    global state, _blackout_until, _last_swipe_t

    # Clear flash each frame
    state.flash = False

    # Lift blackout
    if time.time() > _blackout_until:
        state.blackout = False

    if not result.multi_hand_landmarks:
        state.bass_boost   = False
        state.treble_boost = False
        state.strobe_hz    = 0.0
        return

    right_lm = left_lm = None
    right_g  = left_g  = None

    for idx, hand_info in enumerate(result.multi_handedness):
        label = hand_info.classification[0].label
        lm    = result.multi_hand_landmarks[idx]
        if label == "Right":
            right_lm = lm
            right_g  = classify_gesture(lm)
            state.right_hand_pos  = wrist(lm.landmark)
            state.right_velocity  = r_tracker.update(state.right_hand_pos)
            state.palm_area_right = palm_area(lm.landmark)
        else:
            left_lm = lm
            left_g  = classify_gesture(lm)
            state.left_hand_pos  = wrist(lm.landmark)
            state.left_velocity  = l_tracker.update(state.left_hand_pos)

    # ── Swipe detection (right hand) ───────────────────────────────────────
    swipe = r_tracker.swipe()
    now   = time.time()
    if swipe and (now - _last_swipe_t) > 0.5:
        _last_swipe_t = now
        if swipe == "swipe_right":
            state.color_mode   = next_theme()
            state.last_gesture = f"→ THEME: {state.color_mode.upper()}"
            gesture_log.append(f"swipe_right→{state.color_mode}")
        elif swipe == "swipe_left":
            state.color_mode   = prev_theme()
            state.last_gesture = f"← THEME: {state.color_mode.upper()}"
            gesture_log.append(f"swipe_left→{state.color_mode}")
        elif swipe == "swipe_up":
            state.strobe_hz    = 12.0
            state.flash        = True
            state.energy_level = min(1.0, state.energy_level + 0.3)
            state.last_gesture = "↑ STROBE BURST"
            gesture_log.append("swipe_up→strobe_burst")
        elif swipe == "swipe_down":
            state.blackout     = True
            _blackout_until    = now + 1.0
            state.last_gesture = "↓ BLACKOUT 1s"
            gesture_log.append("swipe_down→blackout")
        return

    # ── RIGHT HAND ─────────────────────────────────────────────────────────
    if right_lm:
        rx, ry = state.right_hand_pos
        state.volume = max(MIN_VOL, min(MAX_VOL, 1.0 - ry))
        state.pan    = (rx - 0.5) * 2.0
        # Palm area → bass (close) / treble (far)
        pa = state.palm_area_right
        state.bass_boost   = pa > 0.04
        state.treble_boost = pa < 0.01
        state.energy_level = min(1.0, pa * 12 + (1.0 - ry) * 0.5)

        g = right_g
        gesture_log.append(f"R:{g}")

        if g == "fist":
            state.color_mode   = "fire"
            state.strobe_hz    = 4.0
            state.last_gesture = "👊 BASS FIST"
        elif g == "open_hand":
            state.color_mode   = "arctic"
            state.strobe_hz    = 0.0
            state.brightness   = 1.0
            state.last_gesture = "✋ FULL WHITE"
        elif g == "point":
            state.bpm_warp     = max(0.5, min(2.0, 1.5 - ry))
            state.strobe_hz    = 0.0
            state.last_gesture = f"☝️ BPM ×{state.bpm_warp:.2f}"
        elif g == "peace":
            state.color_mode   = "ocean"
            state.strobe_hz    = 0.0
            state.ambient      = True
            state.last_gesture = "✌️ CHILL OCEAN"
        elif g == "call_me":
            state.color_mode   = "rainbow"
            state.beat_sync    = True
            state.last_gesture = "🤙 BEAT SYNC"
        elif g == "pinch":
            dist = pinch_dist(right_lm.landmark)
            state.brightness   = min(1.0, dist * 8)
            state.last_gesture = f"🤌 PINCH BRIGHT {state.brightness*100:.0f}%"
        elif g == "thumbs_up":
            state.energy_level = min(1.0, state.energy_level + 0.2)
            state.brightness   = 1.0
            state.flash        = True
            state.color_mode   = "gold"
            state.last_gesture = "👍 PUMP UP GOLD"
        elif g == "thumbs_down":
            state.energy_level = max(0.0, state.energy_level - 0.2)
            state.brightness   = max(0.1, state.brightness - 0.15)
            state.volume       = max(0.0, state.volume - 0.1)
            state.last_gesture = "👎 FADE OUT"
        elif g == "vulcan":
            state.color_mode   = "cosmic"
            state.strobe_hz    = 2.0
            state.last_gesture = "🖖 VULCAN COSMIC"
        elif g == "crossed":
            state.color_mode   = next_theme()
            state.last_gesture = "🤞 CYCLE THEME"
        elif g == "three_fingers":
            state.strobe_hz    = 6.0
            state.last_gesture = "3️⃣ STROBE MED"
        elif g == "four_fingers":
            state.strobe_hz    = 16.0
            state.flash        = True
            state.last_gesture = "4️⃣ STROBE FAST"
        elif g == "point_thumb":
            state.color_mode   = "void"
            state.strobe_hz    = 0.5
            state.last_gesture = "🔫 NOIR MODE"
    else:
        state.bass_boost   = False
        state.treble_boost = False
        state.strobe_hz    = 0.0

    # ── LEFT HAND ──────────────────────────────────────────────────────────
    if left_lm:
        g = left_g
        gesture_log.append(f"L:{g}")

        if g == "open_hand":
            state.color_mode   = "rainbow"
            state.flash        = True
            state.energy_level = 1.0
            state.last_gesture = "🖐 RAINBOW BURST"
        elif g == "fist":
            state.volume       = max(0.0, state.volume - 0.05)
            state.brightness   = max(0.05, state.brightness - 0.05)
            state.last_gesture = "👊 LEFT FADE"
        elif g == "peace":
            state.color_mode   = "cosmic"
            state.strobe_hz    = 1.5
            state.last_gesture = "✌️ COSMIC PURPLE"
        elif g == "pinch":
            state.color_mode   = "ocean"
            state.strobe_hz    = 0.0
            state.ambient      = True
            state.last_gesture = "🤌 OCEAN AMBIENT"

    # ── Both hands open → FULL DISCO ───────────────────────────────────────
    if right_lm and left_lm and right_g == "open_hand" and left_g == "open_hand":
        state.color_mode   = "rainbow"
        state.strobe_hz    = 10.0
        state.brightness   = 1.0
        state.flash        = True
        state.beat_sync    = True
        state.energy_level = 1.0
        state.last_gesture = "🎉 FULL DISCO MODE 🎉"
        gesture_log.append("both_open→FULL_DISCO")


# ── AI Maestro (Anthropic) ────────────────────────────────────────────────────
_last_ai_call = 0.0

def build_ai_prompt() -> str:
    recent = list(gesture_log)[-20:]
    return f"""You are the AI Maestro for a disco light show controller.

Current show state:
- Color mode: {state.color_mode}
- Volume: {state.volume*100:.0f}%
- Brightness: {state.brightness*100:.0f}%
- Strobe: {state.strobe_hz} Hz
- Energy level: {state.energy_level:.2f}
- Bass boost: {state.bass_boost}
- Beat sync: {state.beat_sync}
- BPM warp: {state.bpm_warp:.2f}x

Recent gestures (last 20): {recent}

Based on the conductor's gesture pattern and current state, suggest the single best lighting/effect update to make the show more dramatic and cohesive. 

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "color_mode": "<one of: rainbow|fire|ocean|forest|cosmic|gold|pink|arctic|void>",
  "strobe_hz": <0-20 float>,
  "brightness": <0.1-1.0 float>,
  "energy_level": <0.0-1.0 float>,
  "flash": <true|false>,
  "beat_sync": <true|false>,
  "suggestion_text": "<20 word max human-readable description of what you're doing and why>"
}}"""

def ai_worker():
    """Background thread: calls Claude, pushes result to queue."""
    global _last_ai_call
    while True:
        time.sleep(0.5)
        now = time.time()
        if not AI_ENABLED:
            time.sleep(5)
            continue
        if (now - _last_ai_call) < AI_INTERVAL_SEC:
            continue
        _last_ai_call = now
        try:
            prompt = build_ai_prompt()
            resp = ai_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = resp.content[0].text.strip()
            # Strip markdown fences if present
            raw = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            if not ai_queue.full():
                ai_queue.put(data)
        except Exception as e:
            if not ai_queue.full():
                ai_queue.put({"suggestion_text": f"AI error: {str(e)[:60]}"})

def apply_ai_suggestion():
    """Apply latest AI suggestion from queue if available."""
    try:
        data = ai_queue.get_nowait()
        if "color_mode"    in data: state.color_mode   = data["color_mode"]
        if "strobe_hz"     in data: state.strobe_hz     = float(data["strobe_hz"])
        if "brightness"    in data: state.brightness    = float(data["brightness"])
        if "energy_level"  in data: state.energy_level  = float(data["energy_level"])
        if "flash"         in data: state.flash         = bool(data["flash"])
        if "beat_sync"     in data: state.beat_sync     = bool(data["beat_sync"])
        if "suggestion_text" in data:
            state.ai_suggestion = "🤖 " + data["suggestion_text"]
            print(f"\n[AI MAESTRO] {state.ai_suggestion}")
    except queue.Empty:
        pass


# ── Audio Engine ──────────────────────────────────────────────────────────────
class AudioEngine:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        self.loaded = False
        self._vol   = 0.8

    def load(self, path: str):
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self._vol)
            self.loaded = True
            print(f"[Audio] ✓ Loaded: {path}")
        except Exception as e:
            print(f"[Audio] ERROR: {e}")

    def play(self):
        if self.loaded: pygame.mixer.music.play(-1)

    def stop(self):
        pygame.mixer.music.stop()

    def update(self):
        if not self.loaded: return
        v = state.volume
        if abs(v - self._vol) > 0.005:
            self._vol = v
            pygame.mixer.music.set_volume(v)


# ── HUD ───────────────────────────────────────────────────────────────────────
_ai_text_lines: List[str] = []

def wrap_text(text: str, max_len: int = 42) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_len:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur: lines.append(cur)
    return lines

def draw_hud(frame: np.ndarray):
    h, w = frame.shape[:2]

    # ── Left panel ────────────────────────────────────────────────────────
    pw, ph = 430, 250
    roi = frame[16:16+ph, 16:16+pw]
    dark = np.zeros_like(roi)
    cv2.addWeighted(dark, 0.60, roi, 0.40, 0, roi)
    frame[16:16+ph, 16:16+pw] = roi
    cv2.rectangle(frame, (16, 16), (16+pw, 16+ph), (180, 60, 255), 1)

    def t(label, val, y, col=(180, 255, 180)):
        cv2.putText(frame, f"{label}: {val}", (30, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, col, 1, cv2.LINE_AA)

    cv2.putText(frame, "DISCO MAESTRO v2", (30, 42),
                cv2.FONT_HERSHEY_DUPLEX, 0.60, (255, 140, 255), 1, cv2.LINE_AA)

    t("GESTURE",    state.last_gesture,               66,  (255, 220, 80))
    t("VOL",        f"{state.volume*100:.0f}%  "
                    f"PAN {state.pan:+.2f}",           88,  (80, 255, 180))
    t("BRIGHT",     f"{state.brightness*100:.0f}%  "
                    f"ENERGY {state.energy_level:.2f}", 110, (80, 200, 255))
    t("THEME",      state.color_mode.upper(),          132, (255, 120, 200))
    t("STROBE",     f"{state.strobe_hz:.1f}Hz" if state.strobe_hz else "OFF",
                                                        154, (255, 60, 60))
    t("BPM WARP",   f"{state.bpm_warp:.2f}x  "
                    f"BASS {'ON' if state.bass_boost else 'off'}  "
                    f"TRB {'ON' if state.treble_boost else 'off'}", 176, (200,200,100))

    # AI suggestion
    ai_lines = wrap_text(state.ai_suggestion, 50)
    for i, line in enumerate(ai_lines[:2]):
        cv2.putText(frame, line, (30, 202 + i*18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 255, 255), 1, cv2.LINE_AA)

    # ── Volume bar ────────────────────────────────────────────────────────
    bw = int(state.volume * (w - 40))
    cv2.rectangle(frame, (20, h-36), (w-20, h-18), (30, 15, 50), -1)
    ec = state.energy_level
    bar_col = (int(50+ec*50), int(255-ec*180), int(200-ec*180))
    cv2.rectangle(frame, (20, h-36), (20+bw, h-18), bar_col, -1)
    cv2.putText(frame, "VOL", (22, h-21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180,180,180), 1)

    # ── Energy ring ───────────────────────────────────────────────────────
    r_vel = math.sqrt(state.right_velocity[0]**2 + state.right_velocity[1]**2)
    if r_vel > 0.3:
        rx = int(state.right_hand_pos[0] * w)
        ry = int(state.right_hand_pos[1] * h)
        cv2.circle(frame, (rx, ry), int(20 + r_vel * 40),
                   (255, 200, 60), 2, cv2.LINE_AA)

    # ── AI badge ──────────────────────────────────────────────────────────
    ai_col = (0, 255, 180) if AI_ENABLED else (80, 80, 80)
    cv2.putText(frame, "AI" if AI_ENABLED else "AI:OFF",
                (w-80, h-18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, ai_col, 1)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import sys, os
    music_path = ""
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        music_path = sys.argv[1]
    else:
        inp = input("🎵 MP3 path (or Enter to skip): ").strip().strip('"')
        if inp and os.path.exists(inp):
            music_path = inp
        elif inp:
            print("[WARN] File not found — running camera-only.")

    audio = AudioEngine()
    if music_path:
        audio.load(music_path)
        audio.play()

    # Start AI background thread
    if AI_ENABLED:
        t = threading.Thread(target=ai_worker, daemon=True)
        t.start()
        print("[AI] 🤖 Claude Maestro activated.")
    else:
        print("[AI] Running without Anthropic API.")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)

    print("\n🪩  Camera ready.  Conduct away!")
    print("   Q / ESC → quit  |  SPACE → pause/resume  |  A → force AI analysis\n")

    hands = mp_hands_mod.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.70,
        min_tracking_confidence=0.60,
    )

    paused = False

    while True:
        ret, frame = cap.read()
        if not ret: break

        frame  = cv2.flip(frame, 1)
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        update_state_from_gestures(result, FRAME_H, FRAME_W)
        apply_ai_suggestion()

        # Draw landmarks
        if result.multi_hand_landmarks:
            for hand_lm in result.multi_hand_landmarks:
                mp_draw_mod.draw_landmarks(
                    frame, hand_lm,
                    mp_hands_mod.HAND_CONNECTIONS,
                    mp_styles_mod.get_default_hand_landmarks_style(),
                    mp_styles_mod.get_default_hand_connections_style()
                )

        frame = apply_lighting_overlay(frame)
        draw_hud(frame)
        audio.update()

        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF

        if key in (ord('q'), 27):
            break
        elif key == ord(' '):
            if paused: pygame.mixer.music.unpause()
            else:      pygame.mixer.music.pause()
            paused = not paused
        elif key == ord('a') and AI_ENABLED:
            # Force immediate AI call
            global _last_ai_call
            _last_ai_call = 0.0
            print("[AI] Manual trigger...")

    hands.close()
    cap.release()
    cv2.destroyAllWindows()
    audio.stop()
    pygame.quit()
    print("\n🎤  Show's over. Thanks for conducting! 🪩")


if __name__ == "__main__":
    main()
