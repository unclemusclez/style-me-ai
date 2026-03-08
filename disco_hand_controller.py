"""
╔══════════════════════════════════════════════════════════════╗
║         🪩 DISCO MAESTRO — XR Hand Tracking Controller 🪩    ║
║                                                              ║
║  Control music & lighting like an opera conductor!           ║
║  Uses MediaPipe Hands + OpenCV for real-time gesture XR      ║
╚══════════════════════════════════════════════════════════════╝

INSTALL DEPENDENCIES:
    pip install mediapipe opencv-python pygame numpy

GESTURES REFERENCE:
    ✋ Open Hand (both)       → All lights WHITE / full brightness
    👊 Fist (right)          → BASS BOOST + red strobe
    👆 Index finger (right)  → Raise volume (point up = up, down = down)
    🤙 Pinch (right)         → Crossfade / mix
    ✌️  Peace (left)          → Blue ambient mode
    🖐 Five fingers spread    → Rainbow disco flash
    🤲 Both hands wave        → Beat sync mode
    🤌 Fingers pinched (left) → Fade to silence / dim lights
    ↕️  Right hand Y-axis      → Controls tempo / BPM warp
    ↔️  Right hand X-axis      → Pans stereo left/right

HAND HEIGHT MAP:
    Top 25% of frame   → High energy (strobe, max brightness)
    Mid 50% of frame   → Normal play
    Bottom 25%         → Low/soft ambient mode
"""

import cv2
import mediapipe as mp
import numpy as np
import pygame
import sys
import os
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

# ─── OSC / DMX output (optional) ─────────────────────────────────────────────
# Uncomment if you have a lighting board connected via OSC:
# from pythonosc.udp_client import SimpleUDPClient
# osc_client = SimpleUDPClient("127.0.0.1", 7700)

# ─── Config ──────────────────────────────────────────────────────────────────
CAMERA_INDEX       = 0
WINDOW_NAME        = "🪩 DISCO MAESTRO — Hand Controller"
FRAME_W, FRAME_H   = 1280, 720
MUSIC_PATH: str    = ""          # Will be set from CLI arg or GUI prompt
BPM_BASE           = 128        # Starting BPM assumption
MIN_VOL, MAX_VOL   = 0.0, 1.0


# ─── Gesture State ────────────────────────────────────────────────────────────
@dataclass
class DiscoState:
    volume: float         = 0.8
    brightness: float     = 1.0
    color_mode: str       = "rainbow"   # rainbow | red | blue | white | green
    strobe_hz: float      = 0.0         # 0 = off
    bass_boost: bool      = False
    pan: float            = 0.0         # -1.0 (L) to 1.0 (R)
    bpm_warp: float       = 1.0         # playback speed multiplier
    beat_sync: bool       = False
    ambient: bool         = False
    flash: bool           = False
    last_gesture: str     = "---"
    right_hand_pos: tuple = (0.5, 0.5)
    left_hand_pos: tuple  = (0.5, 0.5)
    overlay_color: tuple  = (255, 255, 255)


state = DiscoState()


# ─── Lighting Overlay Renderer ────────────────────────────────────────────────
COLOR_MAP = {
    "rainbow": None,   # computed per frame
    "red":     (30,  30,  200),
    "blue":    (200, 80,   30),
    "white":   (255, 255, 255),
    "green":   (30,  200,  60),
    "purple":  (180,  30, 200),
}

def hsv_color(hue_deg: float) -> tuple:
    """Convert hue (0-360) to BGR tuple."""
    h = hue_deg / 60.0
    i = int(h)
    f = h - i
    funcs = [
        lambda f: (0, f, 1),
        lambda f: (0, 1, 1-f),
        lambda f: (f, 1, 0),
        lambda f: (1, 1-f, 0),
        lambda f: (1, 0, f),
        lambda f: (1-f, 0, 1),
    ]
    r, g, b = funcs[i % 6](f)
    return (int(b*255), int(g*255), int(r*255))

_rainbow_hue = 0.0

def get_light_color() -> tuple:
    global _rainbow_hue
    if state.color_mode == "rainbow":
        _rainbow_hue = (_rainbow_hue + 2.0) % 360
        return hsv_color(_rainbow_hue)
    return COLOR_MAP.get(state.color_mode, (255, 255, 255))

def apply_lighting_overlay(frame: np.ndarray) -> np.ndarray:
    """Blend a colored lighting overlay onto the camera frame."""
    color = get_light_color()
    alpha = min(state.brightness * 0.45, 0.65)

    # Strobe effect
    if state.strobe_hz > 0:
        t = time.time()
        on = (t * state.strobe_hz % 1.0) < 0.5
        if not on:
            alpha = 0.0
            color = (0, 0, 0)

    overlay = np.full_like(frame, color, dtype=np.uint8)
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha * 0.5, 0, frame)

    # Flash burst
    if state.flash:
        white = np.full_like(frame, (255, 255, 255), dtype=np.uint8)
        cv2.addWeighted(white, 0.6, frame, 0.4, 0, frame)

    return frame


# ─── Gesture Recognition ─────────────────────────────────────────────────────
mp_hands  = mp.solutions.hands
mp_draw   = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles

def fingers_up(hand_landmarks) -> list:
    """Returns [thumb, index, middle, ring, pinky] booleans."""
    lm = hand_landmarks.landmark
    tips   = [4, 8, 12, 16, 20]
    joints = [3, 6, 10, 14, 18]
    up = []
    # Thumb: compare x
    up.append(lm[tips[0]].x < lm[joints[0]].x)
    # Others: compare y (smaller y = higher on screen)
    for i in range(1, 5):
        up.append(lm[tips[i]].y < lm[joints[i]].y)
    return up

def pinch_distance(hand_landmarks) -> float:
    """Distance between thumb tip and index tip (normalised 0-1)."""
    lm = hand_landmarks.landmark
    dx = lm[4].x - lm[8].x
    dy = lm[4].y - lm[8].y
    return math.sqrt(dx*dx + dy*dy)

def wrist_pos(hand_landmarks) -> tuple:
    lm = hand_landmarks.landmark
    return (lm[0].x, lm[0].y)

def classify_gesture(hand_lm, handedness_label: str) -> str:
    up = fingers_up(hand_lm)
    pinch = pinch_distance(hand_lm)
    n_up = sum(up)

    if n_up == 0:
        return "fist"
    if n_up == 5:
        return "open_hand"
    if up[1] and not up[2] and not up[3] and not up[4]:
        return "point"
    if up[1] and up[2] and not up[3] and not up[4]:
        return "peace"
    if pinch < 0.04:
        return "pinch"
    if up[0] and not up[1] and not up[2] and not up[3] and up[4]:
        return "call_me"
    return "partial"


def update_state_from_gestures(hands_result, frame_h: int, frame_w: int):
    """Main gesture → state mapping."""
    global state

    if not hands_result.multi_hand_landmarks:
        state.flash = False
        return

    right_lm = left_lm = None
    right_hand = left_hand = None

    for idx, hand_info in enumerate(hands_result.multi_handedness):
        label = hand_info.classification[0].label
        lm    = hands_result.multi_hand_landmarks[idx]
        if label == "Right":
            right_lm = lm
            right_hand = classify_gesture(lm, "Right")
            state.right_hand_pos = wrist_pos(lm)
        else:
            left_lm = lm
            left_hand = classify_gesture(lm, "Left")
            state.left_hand_pos = wrist_pos(lm)

    # ── RIGHT HAND controls: Volume, BPM warp, Pan, Bass ──────────────────
    if right_lm:
        rx, ry = state.right_hand_pos
        # Y position → volume (higher hand = more volume)
        state.volume = max(MIN_VOL, min(MAX_VOL, 1.0 - ry))
        # X position → stereo pan
        state.pan    = (rx - 0.5) * 2.0

        if right_hand == "fist":
            state.bass_boost  = True
            state.color_mode  = "red"
            state.strobe_hz   = 4.0
            state.last_gesture = "🥊 BASS FIST"
        elif right_hand == "open_hand":
            state.bass_boost  = False
            state.color_mode  = "white"
            state.strobe_hz   = 0.0
            state.brightness  = 1.0
            state.last_gesture = "✋ FULL WHITE"
        elif right_hand == "point":
            # Pointing → BPM warp by hand height
            state.bpm_warp    = max(0.5, min(2.0, 1.5 - ry))
            state.last_gesture = f"☝️ BPM WARP ×{state.bpm_warp:.2f}"
        elif right_hand == "pinch":
            state.last_gesture = "🤌 CROSSFADE"
            state.brightness   = pinch_distance(right_lm) * 10
        elif right_hand == "call_me":
            state.beat_sync   = True
            state.color_mode  = "rainbow"
            state.last_gesture = "🤙 BEAT SYNC"
    else:
        state.bass_boost = False
        state.strobe_hz  = 0.0

    # ── LEFT HAND controls: Color mode, Ambient, Flash ────────────────────
    if left_lm:
        lx, ly = state.left_hand_pos

        if left_hand == "peace":
            state.color_mode  = "blue"
            state.ambient     = True
            state.strobe_hz   = 0.0
            state.last_gesture = "✌️ BLUE AMBIENT"
        elif left_hand == "open_hand":
            state.color_mode  = "rainbow"
            state.flash       = True
            state.last_gesture = "🖐 RAINBOW FLASH"
        elif left_hand == "fist":
            state.volume      = max(0.0, state.volume - 0.05)
            state.brightness  = max(0.1, state.brightness - 0.05)
            state.last_gesture = "👊 DIM + FADE"
        elif left_hand == "pinch":
            state.color_mode  = "purple"
            state.last_gesture = "🤌 PURPLE MODE"
        else:
            state.flash = False
    else:
        state.flash = False

    # ── Both hands waving → full disco mode ───────────────────────────────
    if right_lm and left_lm:
        if right_hand == "open_hand" and left_hand == "open_hand":
            state.color_mode  = "rainbow"
            state.strobe_hz   = 8.0
            state.brightness  = 1.0
            state.flash       = True
            state.beat_sync   = True
            state.last_gesture = "🎉 FULL DISCO MODE 🎉"


# ─── Audio Engine ─────────────────────────────────────────────────────────────
class AudioEngine:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        self.music_loaded = False
        self._vol = 0.8

    def load(self, path: str):
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self._vol)
            self.music_loaded = True
            print(f"[Audio] Loaded: {path}")
        except Exception as e:
            print(f"[Audio] ERROR loading {path}: {e}")

    def play(self):
        if self.music_loaded:
            pygame.mixer.music.play(-1)

    def stop(self):
        pygame.mixer.music.stop()

    def update(self):
        if not self.music_loaded:
            return
        # Volume
        new_vol = state.volume
        if abs(new_vol - self._vol) > 0.01:
            self._vol = new_vol
            pygame.mixer.music.set_volume(new_vol)


# ─── HUD Overlay ─────────────────────────────────────────────────────────────
def draw_hud(frame: np.ndarray):
    h, w = frame.shape[:2]

    # Dark glass panel
    panel = frame[20:210, 20:420].copy()
    black_bg = np.zeros_like(panel)
    cv2.addWeighted(black_bg, 0.55, panel, 0.45, 0, panel)
    frame[20:210, 20:420] = panel

    # Neon border
    cv2.rectangle(frame, (20, 20), (420, 210), (200, 80, 255), 1)
    cv2.rectangle(frame, (21, 21), (419, 209), (100, 40, 130), 1)

    def txt(label, val, y, color=(200, 255, 200)):
        cv2.putText(frame, f"{label}: {val}", (34, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 1, cv2.LINE_AA)

    cv2.putText(frame, "🪩 DISCO MAESTRO", (34, 48),
                cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 160, 255), 1, cv2.LINE_AA)

    txt("GESTURE",    state.last_gesture,           72,  (255, 220, 100))
    txt("VOLUME",     f"{state.volume*100:.0f}%",   96,  (100, 255, 180))
    txt("BRIGHTNESS", f"{state.brightness*100:.0f}%", 118, (100, 200, 255))
    txt("COLOR MODE", state.color_mode.upper(),      140, (255, 130, 200))
    txt("STROBE",     f"{state.strobe_hz:.1f} Hz" if state.strobe_hz else "OFF",
                                                      162, (255, 80,  80 ))
    txt("PAN",        f"{state.pan:+.2f}",           184, (180, 255, 100))

    # VU meter bar
    bar_w = int(state.volume * 380)
    cv2.rectangle(frame, (20, h-40), (400, h-20), (40, 20, 60), -1)
    grad_color = (
        int(100 + state.volume * 155),
        int(255 - state.volume * 100),
        int(200 - state.volume * 150)
    )
    cv2.rectangle(frame, (20, h-40), (20 + bar_w, h-20), grad_color, -1)
    cv2.putText(frame, "VOLUME", (22, h-24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)


# ─── Main Loop ────────────────────────────────────────────────────────────────
def main():
    global MUSIC_PATH

    # Resolve music path from CLI
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        MUSIC_PATH = sys.argv[1]
    else:
        MUSIC_PATH = input("🎵 Enter path to your MP3 file: ").strip().strip('"')
        if not os.path.exists(MUSIC_PATH):
            print("[ERROR] File not found. Run without music (camera only).")
            MUSIC_PATH = ""

    audio = AudioEngine()
    if MUSIC_PATH:
        audio.load(MUSIC_PATH)
        audio.play()

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)

    print("\n[DISCO MAESTRO] 🪩 Camera active. Use hand gestures to conduct!")
    print("   Press Q to quit | SPACE to pause/resume music\n")

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.72,
        min_tracking_confidence=0.60,
    )

    paused = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)  # Mirror for natural conductor feel
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        # Update gesture state
        update_state_from_gestures(result, FRAME_H, FRAME_W)

        # Draw hand landmarks
        if result.multi_hand_landmarks:
            for hand_lm in result.multi_hand_landmarks:
                mp_draw.draw_landmarks(
                    frame, hand_lm, mp_hands.HAND_CONNECTIONS,
                    mp_styles.get_default_hand_landmarks_style(),
                    mp_styles.get_default_hand_connections_style()
                )

        # Apply lighting overlay
        frame = apply_lighting_overlay(frame)

        # HUD
        draw_hud(frame)

        # Audio engine tick
        audio.update()

        cv2.imshow(WINDOW_NAME, frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break
        elif key == ord(' '):
            if paused:
                pygame.mixer.music.unpause()
            else:
                pygame.mixer.music.pause()
            paused = not paused

    hands.close()
    cap.release()
    cv2.destroyAllWindows()
    audio.stop()
    pygame.quit()
    print("\n[DISCO MAESTRO] 🎤 Show's over. Thanks for conducting! 🪩")


if __name__ == "__main__":
    main()
