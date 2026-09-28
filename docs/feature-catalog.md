# Features and engines

Engine availability depends on installed models, hardware, and configured providers.

The macOS menu-bar icon uses an 18-point image with a Retina representation in
both idle and recording states; Windows and Linux retain their existing tray sizing.

Settings → Models and the sidebar performance control share the same global pack
tier. Switching to an already-installed pack requires no download-space reserve.
Installing missing pack models still requires their estimated download size plus
10 GB of free-space headroom on the selected target.
Both controls verify that the pack's required models are installed before applying
it. Settings can preview an incomplete pack without changing the active tier;
while that panel stays open, successful installation activates the pack. Changing
the tier or target cancels that pending activation. Missing-pack and disk-space
warnings appear in red.
The sidebar shows one compact “Models required” hint with a Models link for an
incomplete pack, rather than a generic retry error and duplicate toast.

## Features

- **Voice Cloning**
- **Voice Design**
- **Saved voice prompt export** — Saved Voices → Export prompts saves one Markdown
  file with each profile's language, personality, style, and available reference
  transcript. It is text only; use Export persona when a cloned voice's reference
  audio must travel with it.
- **Video Dubbing**
- **Dictation Widget**
- **Vocal Isolation**
- **Speaker Diarization**
- **Batch Queue**
- **MCP Server**
- **AI Watermark**
- **Local-first**
- **GPU Auto-Detect**
- **Remote Model Downloads**
- **Extensible**

## Speech generation

- **VoiceStudio** (default, powered by k2-fsa/OmniVoice)
- omnivoice-subprocess — [Guide](engines/omnivoice-subprocess.md)
- CosyVoice 3 — [Guide](engines/cosyvoice.md)
- KittenTTS
- MLX-Audio
- VoxCPM2
- MOSS-TTS-Nano
- gpt-sovits
- sherpa-onnx
- **IndexTTS 2.5** ⚡ — [Guide](engines/indextts.md)
- omnivoice-gguf
- supertonic3
- **MOSS-TTS-v1.5** — [Guide](engines/moss-tts-v15.md)
- **dots.tts** — [Guide](engines/dots-tts.md)
- **Confucius4-TTS** — [Guide](engines/confucius4-tts.md)
- pockettts
- audiocpp — [Guide](engines/audio-cpp.md)

## Transcription

- **WhisperX** (default)
- Faster-Whisper
- MLX Whisper
- PyTorch Whisper
- Parakeet TDT
- Parakeet TDT v3 (MLX)
- Moonshine
- FunASR
- **sherpa-onnx** (live dictation)
- **OpenAI-compatible** ⚠️ configured server
