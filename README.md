# 🪩 DISCO MAESTRO

> **Conduct your light show like an opera maestro — using nothing but your hands.**

Disco Maestro is a real-time AI-powered XR hand tracking system that lets you control music playback, stage lighting, and visual effects through live camera gesture recognition. It combines computer vision, audio engineering, and generative AI to turn your hands into a conductor's baton for an immersive disco experience.

---

## ✨ Features

- 🖐 **18 distinct hand gestures** — fists, peace signs, pinches, vulcan salutes, swipes, and more
- 🎵 **Live MP3 playback control** — volume, pan, BPM warp, bass/treble boost via hand position
- 💡 **9 dynamic lighting themes** — Rainbow, Fire, Ocean, Forest, Cosmic, Gold, Pink, Arctic, Void
- ⚡ **Strobe, beat-sync, and blackout effects** driven by gesture velocity and trajectory
- 🤖 **AI Maestro powered by Google Gemini API** — reads your gesture history and automatically suggests optimal lighting and effect combinations in real time
- 🌐 **Web Studio UI** — full browser-based mixer with spectrum analyzer, EQ, waveform display, and animated disco floor
- ☁️ **Google Cloud Run deployment** — web dashboard and AI layer hosted serverlessly

---

## 🗂 Project Structure

```
disco-maestro/
├── README.md
├── disco_maestro.html           # Web studio UI (mixer, spectrum, lighting controls)
├── disco_hand_controller_v2.py  # Main XR hand tracking script (run locally)
├── disco_hand_controller.py     # Original v1 script (basic gestures, no AI)
└── cloud/                       # Google Cloud Run deployment
    ├── Dockerfile
    ├── main.py                  # FastAPI server (AI endpoint + WebSocket)
    ├── requirements.txt
    └── static/
        └── disco_maestro.html
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10 (required for MediaPipe compatibility)
- Webcam
- Google Gemini API key

### 1. Create a Python 3.10 environment

```bash
conda create -n disco python=3.10 -y
conda activate disco
```

### 2. Install dependencies

```bash
pip install mediapipe>=0.10.30 opencv-python pygame numpy google-generativeai
```

### 3. Set your Gemini API key

```bash
export GEMINI_API_KEY="your-key-here"
```

Get a free key at [aistudio.google.com](https://aistudio.google.com).

### 4. Run the hand controller

```bash
python disco_hand_controller_v2.py /path/to/your/track.mp3
# or without music (camera only):
python disco_hand_controller_v2.py
```

### 5. Open the web studio

Open `disco_maestro.html` directly in your browser — no server needed for local use. Drop an MP3 into the upload zone and start mixing.

---

## 🖐 Gesture Reference

### Right Hand — Primary Conductor

| Gesture | Effect |
|---|---|
| ✋ Open hand | Full white lights / reset |
| 👊 Fist | Bass boost + fire red strobe |
| ☝️ Point (index) | Volume = hand height / BPM warp |
| ✌️ Peace | Ocean blue chill mode |
| 🤙 Call-me | Rainbow beat-sync |
| 🤌 Pinch | Brightness crossfade |
| 👍 Thumbs up | Gold flash + energy pump |
| 👎 Thumbs down | Fade out volume + dim |
| 🖖 Vulcan salute | Cosmic purple slow strobe |
| 🤞 Crossed fingers | Cycle to next color theme |
| 3 fingers | Medium strobe (6 Hz) |
| 4 fingers | Fast strobe burst (16 Hz) |
| 🔫 Point + thumb | Noir void mode |

### Left Hand — Color & Scene

| Gesture | Effect |
|---|---|
| ✋ Open hand | Rainbow flash burst |
| 👊 Fist | Fade to black |
| ✌️ Peace | Cosmic purple mode |
| 🤌 Pinch | Ocean ambient mode |

### Two-Hand Combos

| Gesture | Effect |
|---|---|
| 🙌 Both open hands | **FULL DISCO MODE** — rainbow + strobe 10Hz + beat sync |

### Swipe Gestures (right hand velocity)

| Swipe | Effect |
|---|---|
| → Right | Next color theme |
| ← Left | Previous color theme |
| ↑ Up | Strobe burst |
| ↓ Down | 1-second blackout |

### Positional Axes

| Axis | Control |
|---|---|
| Y (hand height) | Volume — top = max, bottom = min |
| X (hand left/right) | Stereo pan |
| Z (palm size) | Close = bass boost / far = treble boost |

---

## 🤖 AI Maestro (Google Gemini)

Every 8 seconds, Gemini reads your recent gesture sequence and current show state (color mode, strobe, brightness, energy level) and returns a JSON lighting update applied live to the scene.

**Example AI response:**
```json
{
  "color_mode": "cosmic",
  "strobe_hz": 3.0,
  "brightness": 0.85,
  "energy_level": 0.9,
  "flash": false,
  "beat_sync": true,
  "suggestion_text": "Detected rhythmic fist-peace pattern — shifting to cosmic purple with slow pulse to match conductor's mood."
}
```

Press **`A`** during the show to force an immediate AI analysis at any time.

The Gemini integration is in `disco_hand_controller_v2.py` under the `ai_worker()` function. To swap models or adjust the prompt, edit the `build_ai_prompt()` function.

---

## ☁️ Google Cloud Deployment

### Deploy web UI + AI backend to Cloud Run

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

# Deploy
gcloud run deploy disco-maestro \
  --source ./cloud \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY="your-key-here" \
  --memory 512Mi
```

Your dashboard will be live at `https://disco-maestro-xxxx-uc.a.run.app`.

The local hand controller script connects to the Cloud Run `/ai-suggest` endpoint and `/ws` WebSocket for real-time state sync between your webcam and any browser viewing the dashboard.

### Cost estimate (Cloud Run free tier)

| Service | Monthly cost |
|---|---|
| Cloud Run (light traffic) | $0 (2M requests free) |
| Gemini API (~100 AI calls) | ~$0.01 |
| Cloud Storage (MP3s) | ~$0.02/GB |
| **Total** | **~$0.03/month** |

---

## ⌨️ Keyboard Shortcuts

| Key | Action |
|---|---|
| `SPACE` | Pause / resume music |
| `A` | Force AI Maestro analysis |
| `Q` / `ESC` | Quit |

---

## 🛠 Troubleshooting

**`module 'mediapipe' has no attribute 'solutions'`**
You're on Python 3.13. MediaPipe requires Python 3.10:
```bash
conda create -n disco python=3.10 -y && conda activate disco
pip install mediapipe>=0.10.30
```

**SDL duplicate library warnings on macOS**
Harmless — caused by Anaconda's pygame and cv2 each bundling their own SDL2. The app still runs correctly.

**Camera not detected**
Change `CAMERA_INDEX = 0` to `1` or `2` at the top of the script if you have multiple cameras.

**No sound**
Ensure pygame can access your audio output: `python -c "import pygame; pygame.mixer.init(); print('OK')"`.

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `mediapipe>=0.10.30` | Hand landmark detection |
| `opencv-python` | Camera capture + frame rendering |
| `pygame` | Audio playback |
| `numpy` | Frame processing / lighting math |
| `google-generativeai` | Gemini AI lighting suggestions |
| `fastapi` + `uvicorn` | Cloud Run API server |

---

## 🙏 Acknowledgements

- [MediaPipe](https://developers.google.com/mediapipe) by Google — hand tracking models
- [Google Gemini API](https://aistudio.google.com) — AI-powered lighting intelligence
- [Google Cloud Run](https://cloud.google.com/run) — serverless deployment
- [pygame](https://www.pygame.org) — audio engine

---

*Built with 🪩 and a lot of hand-waving.*
