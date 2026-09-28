# WittingMouse audio feedback — investigation and tasks

Date: 2026-09-28. Scope: investigate supplied artifacts and plan work; no app changes or public uploads.

## Measured evidence

The three WAVs downloaded together on September 28 were inspected locally with
`ffprobe` and FFmpeg `volumedetect`, `ebur128=peak=true`, and
`silencedetect=noise=-50dB:d=0.3`. All are mono, 24,000 Hz, uncompressed PCM.
Version-to-filename mapping was confirmed by the subsequently supplied Discord
screenshot: `4619c980.wav` is approximately OmniVoice 0.2.7 (reporter's estimate),
`3ff95c1d.wav` is VoiceStudio 0.5.3, and `voicestudio-43577f3a.wav` is 0.5.6.

| File | Encoding | Bytes | Duration | Loudness | True peak |
| --- | --- | ---: | ---: | ---: | ---: |
| `4619c980.wav` | 32-bit float | 733,520 | 7.64 s | -18.5 LUFS | -1.9 dBFS |
| `3ff95c1d.wav` | 16-bit integer | 363,404 | 7.57 s | -19.2 LUFS | -2.0 dBFS |
| `voicestudio-43577f3a.wav` | 16-bit integer | 371,084 | 7.73 s | -18.5 LUFS | -2.0 dBFS |

The approximately halved file size is explained by sample width (four bytes
versus two per sample), with small duration/header differences. This is not
evidence of a lossy codec. It does **not** establish the cause of perceived
sound degradation or rule out processing earlier in the pipeline.

Detected quiet spans: `4619c980` 4.956–5.275 s; `3ff95c1d` 4.947–5.411 s;
`voicestudio-43577f3a` 6.099–6.441 s. These short spans can be normal pauses,
not necessarily defects. The measurements show no full-scale output clipping;
they cannot exclude clipping before attenuation. No controlled reproduction or
listening verdict has been established, so no audio-quality root cause is claimed.

Repeat measurements (substitute each filename):

```sh
ffprobe -v error -show_streams -show_format /path/to/sample.wav
ffmpeg -hide_banner -i /path/to/sample.wav -af 'silencedetect=noise=-50dB:d=0.3,ebur128=peak=true' -f null -
```

## Priority 1 — isolate the reported 0.5.6 sound regression

- [x] Confirm which file is 0.2.7, 0.5.3, and 0.5.6 (0.2.7 remains the reporter's estimate).
- [ ] Obtain original text, reference WAV/transcript, engine/model revision,
  seed, generation settings, device, and enabled effects/export settings.
  Keep recordings local; obtain permission before committing or publishing them.
- [ ] Reproduce on 0.5.3 and 0.5.6 with matched inputs/settings/hardware and
  several seeds. Capture engine-native output and final export separately.
  Acceptance: a repeatable symptom, not merely different randomly generated speech.
- [ ] Compare matched-level playback and time-local loudness/spectral measurements;
  test export alone using the **same input waveform** in both versions. Separate
  model/generation differences from resampling, effects, and serialization.
- [ ] Once reproducible, narrow the responsible change and add a failing regression
  test at the actual processing seam; fix only the demonstrated cause.
  Do not switch all exports to float solely to make files larger.
- [ ] Validate the correction across macOS, Windows, and Linux, with an offline,
  empty model cache for model-free tests; document the supported export behavior.

## Priority 2 — local audio-quality warnings

Existing building blocks: `tests/probe/judges/audio.py` measures decoded audio,
silence and clipping for tests; `backend/core/audio_validation.py` validates
reference-file integrity. Neither alone constitutes the requested timeline warning UI.
Audiobook loudness controls already exist and should not be duplicated.

- [ ] Define advisory checks for empty output, sustained near-silence, clipping,
  and unusually quiet/loud regions relative to surrounding speech.
- [ ] Calibrate thresholds on natural pauses, whispers, expressive speech, and
  chapter breaks; distinguish intentional silence from suspect missing speech.
- [ ] Implement a bounded-memory, local-only analyzer returning warning type,
  start/end timestamps, severity, and measurements; no model download required.
  Share suitable DSP logic through production code, not imports from test modules.
- [ ] Show localized, seekable warnings in Electron playback/generation results;
  allow dismissal. Never silently normalize, regenerate, block export, or alter audio.
- [ ] Add synthetic fixtures for silence, volume jumps, clipping, non-finite samples,
  stereo/channel cancellation, valid quiet speech, and long files. Confirm identical
  warning behavior on all supported OSes and translations in all maintained locales.

## Priority 3 — engine compatibility

- [ ] Ask which engines and workflows WittingMouse actually wants; distinguish
  a missing engine from installation or generation failures in existing engines.
- [ ] Track existing concrete reports rather than duplicate them: #2371
  (IndexTTS ROCm installation), #2372 (RDNA2 crash), #2373 (ROCm latency), and
  #2374 (WebSocket engine-override sidecar lifecycle). Validate each independently;
  none is established as the cause of these WAV differences.
- [ ] Build an install → load → generate → reference clone (where supported) →
  cancel → unload smoke matrix for requested engines across supported platforms.
  Preserve already-installed model state and explicit download consent.
- [ ] Prioritize repairing existing promised capabilities, then evaluate requested
  additions for licensing, dependencies, hardware support, and local-first operation.

Open PRs checked during investigation: #2368 (MCP voice tools), #2338 (IME),
#2325 (LLM provider); none directly covers this audio regression or warning UI.
The implemented warning feature is tracked in GitHub issue #2375. Original
recordings remain local; the issue contains no recording or private transcript.

## Implemented and measured locally

- The latest Clone output now offers **Check audio**. It performs a read-only
  scan on the configured backend and shows dismissible, seekable advisory
  warnings. No uploads to third-party services, model downloads, automatic
  repair, or generation-default changes are introduced.
- Checks cover empty output, non-finite samples, possible clipping, silence
  lasting at least one second below -50 dBFS (or an entirely quiet clip), and active regions at least
  12 dB above/below the recording's median active level for 0.5 seconds.
  Natural expression can trigger a warning; absence of warnings is not a
  quality guarantee. A scan is limited to two hours and 100 warnings, visibly
  disclosed in the UI. Other playback surfaces are not yet integrated.
- Real-file backend/API tests and renderer interaction tests cover analysis,
  path confinement, seek/dismiss, failures, and limits. All 21 maintained
  renderer locales contain translated labels.
- All three supplied WAVs produced no warnings under these conservative
  thresholds; the previously measured short pauses are not flagged.

### Generation-quality experiment

`scripts/compare_generation_quality.py` runs cache-only, fixed-seed comparisons
using the production OmniVoice model, with outputs passed through
`mark_synthetic`. It does not reproduce the full `/generate` processing pipeline
or a previous release. Supply an already-installed local checkpoint and a new
output directory; optional `--ref-audio` requires matching `--ref-text`.

Measured on this Mac's MPS device with checkpoint
`c5fdb5ccb189668d56333f77ba2629f4cd7535f4`, seeds 42 and 123, guidance 2,
postprocessing enabled, no reference, and the script's default English text:

| Configuration | Seed 42 time | Seed 123 time | Duration per sample |
| --- | ---: | ---: | ---: |
| 16 steps, denoise on | 4.63 s | 4.29 s | 4.80 s |
| 32 steps, denoise on | 8.30 s | 8.26 s | 4.80 s |
| 32 steps, denoise off | 8.27 s | 8.27 s | 4.80 s |

All six samples had no analyzer warnings. The installed faster-whisper base
model (CPU/int8, beam size 5, English, offline) recovered all spoken words
correctly; only punctuation differed. This small experiment establishes no
intelligibility advantage for 32 steps and does not measure naturalness or
voice similarity. Listening evaluation remains necessary; no default changed.
Times are single observations, not a warmed statistical benchmark.

Artifacts are local at `/tmp/voicestudio-quality-comparison-20260928/`, including
six WAVs and `results.json`; they have not been uploaded or committed.

A separate real sidecar PCM round-trip of the supplied float WAV measured
75.92 dB signal-to-error ratio and maximum absolute sample error 0.00004977.
This quantifies that conversion only, not the end-to-end reported regression.

Still needed: original reference and settings,
matched-level blind listening, broader texts/languages/reference voices, and
the requested additional engine names. Existing engine issues remain separate
work; none has been marked resolved by this feature.

### Release-source comparison after the migration report

The reporter confirmed that the same saved voice sounds padded/reverberant in
Electron. The mapped 0.5.3 and 0.5.6 WAVs both use 16-bit PCM at 24 kHz, so their
encoding format does not explain that perceived difference.

`scripts/compare_release_clone.py` was run against isolated source trees at
tags v0.5.3 (`135ccd09`) and v0.5.6 (`3915a62c`). Both used the same installed
checkpoint above, MPS/float16, seed 42, 16 steps, guidance 2, denoise and
postprocessing enabled, and the repository's UK audiobook narrator sample
with its transcript. No reporter recording was used as a substitute reference.

The raw generated samples were byte-identical across the two source versions:

| Language supplied to model | Raw output SHA-256, identical in both releases |
| --- | --- |
| English | `43dbb2f0513c63514257b3614ed70cfdf2c9c108176316f7897ab6e67e6e299f` |
| Auto / None | `70c5edf9ff88907aa3cbfe38a8f3c66a9629898cd62196237918dfa2f6743f37` |

Each render contained 98,880 samples. This isolates model-source behavior;
it does not test both installers, all backend routes, different hardware,
or the reporter's original saved reference and environment.

One request difference is confirmed: the legacy default Auto picker omitted
`language`, letting the backend inherit a saved profile's language. Electron
sends explicit `Auto`, intentionally selecting language-agnostic synthesis.
The two language conditions above produce different waveforms even with the
same voice and seed. That is a candidate to test against the report, **not a
confirmed cause of reverberation**. Existing tests explicitly protect Auto's
current semantics; no silent reversal was made.

The audio DSP code is unchanged between these tags. The pinned pedalboard
dependency changed from 0.9.24 to 0.9.20. Running the default mastering and
broadcast effect chain on each of the three supplied WAVs under both dependency
versions yielded identical output hashes for each input on this Mac. This
comparison found no DSP dependency regression for those inputs.

The v0.5.6 English/Auto listening pair is under
`/tmp/voicestudio-clone-v056-20260928/`. The earlier v0.5.3 experiment files used
only the mastering pre-stage (before the harness was corrected to include the
full broadcast chain), so their final WAVs must not be used for a matched-DSP
listening comparison. The raw model hashes were captured before either stage
and remain directly comparable.

Next diagnostic: select the same explicit output language in both apps and
repeat with the same seed. If the degradation remains, obtain the saved voice's
original reference/transcript and both takes' generation settings plus engine,
model revision, OS/device and dependency versions. Output WAVs alone cannot
recover those inputs. No production sound-quality fix is claimed yet.
