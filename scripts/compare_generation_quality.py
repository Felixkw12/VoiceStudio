"""Offline fixed-seed OmniVoice comparison; never changes app defaults.

Run with the repository Python and an already-installed checkpoint. Outputs
are provenance-marked. DSP warnings are not a perceptual quality verdict.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--text', default='The morning sunlight filled the quiet room. Today, we begin a new adventure.')
    parser.add_argument('--seeds', nargs='+', type=int, default=[42, 123])
    parser.add_argument('--ref-audio')
    parser.add_argument('--ref-text')
    args = parser.parse_args()
    if bool(args.ref_audio) != bool(args.ref_text):
        parser.error('--ref-audio and --ref-text must be supplied together (no implicit ASR)')
    import torch
    import soundfile as sf
    from omnivoice.models.omnivoice import OmniVoice
    from services.model_manager import get_best_device
    from services.watermark import mark_synthetic
    from services.audio_quality import analyze_audio

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    device = get_best_device()
    model = OmniVoice.from_pretrained(args.checkpoint, device_map=device,
                                     dtype=torch.float16, load_asr=False, local_files_only=True)
    results = []
    for seed in args.seeds:
        for steps, denoise in [(16, True), (32, True), (32, False)]:
            torch.manual_seed(seed)
            start = time.monotonic()
            with torch.inference_mode():
                wave = model.generate(text=args.text, language='English', num_step=steps,
                                      guidance_scale=2.0, denoise=denoise,
                                      ref_audio=args.ref_audio, ref_text=args.ref_text,
                                      postprocess_output=True)[0]
            seconds = time.monotonic() - start
            wave = mark_synthetic(wave, model.sampling_rate, context='quality-comparison')
            path = output / f'seed-{seed}-steps-{steps}-denoise-{denoise}.wav'
            sf.write(path, wave.detach().cpu().float().numpy().squeeze(), model.sampling_rate,
                     subtype='FLOAT')
            result = dict(file=path.name, seed=seed, steps=steps, denoise=denoise,
                          generation_seconds=round(seconds, 2), device=str(device),
                          analysis=analyze_audio(path).model_dump())
            results.append(result)
            print(json.dumps(result), flush=True)
    (output / 'results.json').write_text(json.dumps({'checkpoint': args.checkpoint,
        'text': args.text, 'reference_used': bool(args.ref_audio),
        'results': results}, indent=2) + '\n')


if __name__ == '__main__':
    main()
