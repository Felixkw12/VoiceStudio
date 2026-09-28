"""Compare installed-model cloning across isolated release source trees, offline.

The same interpreter/dependencies, reference, checkpoint and seed are held fixed.
This isolates source/request changes, not differences in packaged environments.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--transcript', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    root = Path(args.source).resolve()
    sys.path[:0] = [str(root), str(root / 'backend')]
    import torch
    import soundfile as sf
    from omnivoice.models.omnivoice import OmniVoice
    from services.model_manager import get_best_device
    from services.audio_dsp import apply_mastering, normalize_audio, apply_effects_chain, get_effect_chain
    from services.watermark import mark_synthetic

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    model = OmniVoice.from_pretrained(args.checkpoint, device_map=get_best_device(),
                                     dtype=torch.float16, load_asr=False, local_files_only=True)
    for language in ['English', None]:
        torch.manual_seed(42)
        wave = model.generate(
            text='The morning sunlight filled the quiet room. Today, we begin a new adventure.',
            ref_audio=args.reference, ref_text=args.transcript, language=language,
            num_step=16, guidance_scale=2.0, denoise=True, postprocess_output=True,
            t_shift=.1, position_temperature=5., class_temperature=0., layer_penalty_factor=5.,
        )[0]
        raw = wave.detach().cpu().float().numpy()
        digest = hashlib.sha256(raw.tobytes()).hexdigest()
        wave = apply_mastering(wave, sample_rate=model.sampling_rate)
        wave = apply_effects_chain(wave, model.sampling_rate, get_effect_chain('broadcast'))
        wave = normalize_audio(wave, target_dBFS=-2.)
        wave = mark_synthetic(wave, model.sampling_rate, context='release-clone-comparison')
        sf.write(output / f'{language or "Auto"}.wav', wave.detach().cpu().float().numpy().squeeze(),
                 model.sampling_rate, subtype='PCM_16')
        print(json.dumps({'source': root.name, 'language': language, 'raw_sha256': digest,
                          'samples': raw.size}), flush=True)


if __name__ == '__main__':
    main()
