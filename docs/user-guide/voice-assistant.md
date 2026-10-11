# Voice Assistant

`jarvis listen` turns OpenJarvis into a hands-free voice assistant. Say
**"Hey Jarvis"** (or clap twice) and talk. After each answer Jarvis keeps
listening for a follow-up, so one wake-up is a whole conversation. It returns
to standby after a pause or when you say goodbye ("tchau", "thanks", "that's
all").

```bash
uv sync --extra speech --extra voice     # microphone, speech-to-text, TTS, wake word
brew install espeak-ng                   # macOS: pronunciation for non-English voices
jarvis init --preset daily-ops-mac --force
jarvis listen
```

The preset sets Brazilian Portuguese; any config works, see below.

## How it works

| Stage | Runs | Notes |
|---|---|---|
| Wake word / claps | on-device | `hey_jarvis` model from [openWakeWord](https://github.com/dscripka/openWakeWord), bundled in the wheel: no download, no cloud |
| Speech-to-text | on-device | faster-whisper, language from `[speech] language` |
| Answer | your configured engine | e.g. `claude-haiku-5-5` through the cloud engine |
| Text-to-speech | on-device | Kokoro; long answers start speaking after the first sentence |

Only the transcribed text of your request goes to the model.

## What Jarvis can do by voice

`jarvis listen` runs the `orchestrator` agent with a short, fixed tool list
(change it with `--tools`):

| Tool | Examples |
|---|---|
| `mac_control` | "open Safari", "open github.com", "volume to 30", "mute", "next song" (Music or Spotify), "dark mode", "notify me: …" |
| `web_search` | "what happened in the news today?" |
| `digest_collect` | "what is on my calendar?", "any unread email?" (needs `jarvis connect gdrive`) |
| `think` | multi-step reasoning |

There is **no shell access** in this list. `mac_control` is a fixed set of
actions (open an app or an `http(s)` link, volume, mute, media keys, dark
mode, sleep the display, show a notification); it validates every parameter and
never builds a command from free text.

!!! warning "Text from the web and email is untrusted"
    Search results and emails reach the model, so a malicious page or message
    could try to steer Jarvis into using `mac_control`. The worst it can do is
    open an `http(s)` link or change the volume, so treat spoken requests that
    read untrusted content with the same care as clicking a link from it. Use
    `--tools` to drop `mac_control` if you do not want it.

## Settings

```toml
[speech]
language = "pt"            # transcription and replies; "" = auto-detect
tts_backend = "kokoro"
voice_id = "pm_alex"       # PT-BR male; "bm_george" = British (English)
wake = "both"              # "jarvis", "clap" or "both"
wake_threshold = 0.5       # lower = wakes more easily (and more false wakes)
follow_up_seconds = 8      # keep listening this long after an answer; 0 = one question per wake-up
```

Command-line flags override the config: `--wake`, `--sensitivity` (clap
loudness), `--agent`, `--tools`, `--once`.

## Troubleshooting

- **It does not wake on "Jarvis".** The model is trained on the English phrase
  "hey jarvis". Say the full phrase, or lower `wake_threshold` (try `0.3`).
- **It wakes by itself.** Raise `wake_threshold` (try `0.7`), or use
  `wake = "clap"`.
- **Claps are missed or too sensitive.** Tune `--sensitivity` (lower = more
  sensitive).
- **No microphone.** On macOS allow the microphone for your terminal (or the
  OpenJarvis app) in System Settings → Privacy & Security.
