"""A published dub must contain every requested spoken segment, without early clipping."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
import torch
import soundfile as sf

from schemas.requests import DubRequest


@pytest.fixture
def render_dub(monkeypatch, tmp_path):
    import api.routers.dub_generate as dg
    job = {'duration': 4.0, 'dubbed_tracks': {}, 'segments': [], 'seg_wav_kind_by_lang': {'en': 'natural'}}
    path = tmp_path / 'job'
    path.mkdir()
    events = []
    generated = []
    async def resolve():
        return 'omnivoice', SimpleNamespace(target='local', remote=False), backend
    def generate(**kwargs):
        generated.append(kwargs)
        return output[0]()
    backend = SimpleNamespace(sample_rate=24000, generate=generate, applies_own_mastering=True)
    output = [lambda: torch.ones(1, 24000) * .1]
    class Tasks:
        def is_cancelled(self, *_): return False
        async def add_task(self, tid, kind, func, *args):
            async for event in func(*args):
                if event.startswith('data: '): events.append(json.loads(event[6:]))
    monkeypatch.setattr(dg, '_resolve_dub_execution', resolve)
    monkeypatch.setattr(dg, '_get_job', lambda _: job)
    monkeypatch.setattr(dg, '_save_job', lambda *_: None)
    monkeypatch.setattr(dg, 'DUB_DIR', str(tmp_path))
    monkeypatch.setattr(dg, 'dub_seg_path', lambda _, sid: str(path / f'seg_{sid}.wav'))
    monkeypatch.setattr(dg, 'task_manager', Tasks())
    monkeypatch.setattr(dg, 'rvc_is_enabled', lambda: False)
    monkeypatch.setattr(dg, 'mark_synthetic', lambda a, *args, **kw: a)
    monkeypatch.setattr(dg, 'get_effect_chain', lambda _: None)
    monkeypatch.setattr(dg, 'normalize_audio', lambda a, **kw: a)
    def run(**kwargs):
        body = dict(segments=[dict(start=0, end=1, text='hello')], segment_ids=['a'], language_code='en', num_step=4)
        body.update(kwargs)
        asyncio.run(dg.dub_generate('job', DubRequest(**body)))
        return events
    return SimpleNamespace(run=run, output=output, job=job, path=path, generated=generated)


def test_failed_segment_does_not_publish_complete_track(render_dub):
    def fail(): raise RuntimeError('engine failed')
    render_dub.output[0] = fail
    events = render_dub.run()
    assert any(e['type'] == 'error' for e in events)
    assert not any(e['type'] == 'done' for e in events)
    assert not render_dub.job['dubbed_tracks']


def test_missing_partial_cache_is_regenerated(render_dub):
    events = render_dub.run(regen_only=[])
    assert render_dub.generated
    assert (render_dub.path / 'seg_en_a.wav').exists()
    assert any(e['type'] == 'done' for e in events)


@pytest.mark.parametrize("rvc_enabled", [False, True])
def test_strict_slot_keeps_full_cache_and_fits_the_tail(render_dub, monkeypatch, rvc_enabled):
    import api.routers.dub_generate as dg
    render_dub.output[0] = lambda: torch.cat((torch.ones(1, 24000)*.1, torch.ones(1, 24000)*.3), dim=-1)
    monkeypatch.setattr(dg, "rvc_is_enabled", lambda: rvc_enabled)
    monkeypatch.setattr(dg, "apply_rvc", lambda _: None)
    calls=[]
    async def stretch(wav, target, sr):
        calls.append((wav.shape[-1], target, float(wav[0,-1])))
        return torch.nn.functional.interpolate(wav.unsqueeze(0),size=target,mode='linear').squeeze(0)
    monkeypatch.setattr(dg, '_pitch_preserving_stretch', stretch)
    events=render_dub.run(timing_strategy='strict_slot')
    assert any(e['type']=='done' for e in events)
    assert sf.info(render_dub.path/'seg_en_a.wav').duration == 2
    assert calls and calls[0][0] == 48000 and calls[0][1] == 24000
    assert calls[0][2] == pytest.approx(.3, abs=1e-4)


def test_concise_overrun_does_not_publish_truncated_track(render_dub):
    render_dub.output[0] = lambda: torch.ones(1, 48000)*.1
    events=render_dub.run()
    assert any(e['type']=='error' for e in events)
    assert not any(e['type']=='done' for e in events)
    assert not render_dub.job['dubbed_tracks']


def test_silent_engine_output_is_not_a_successful_segment(render_dub):
    render_dub.output[0] = lambda: torch.zeros(1, 24000)
    events = render_dub.run()
    assert any(e['type'] == 'error' for e in events)
    assert not render_dub.job['dubbed_tracks']


def test_camera_cut_uses_word_times_instead_of_character_ratio():
    from services.segmentation import Segment, _apply_scene_cuts
    words = [
        {'text': 'A very long early phrase', 'start': 0, 'end': 1.8},
        {'text': 'Short later phrase', 'start': 4.0, 'end': 6.0},
    ]
    segment = Segment(start=0, end=6, text='A very long early phrase Short later phrase', extra={'words': words})
    pieces = _apply_scene_cuts([segment], [4.0])
    assert len(pieces) == 2
    assert pieces[0].end == 1.8
    assert pieces[1].start == 4
    assert pieces[0].extra['words'] == words[:1]
    assert pieces[1].text == 'Short later phrase'


def test_camera_cut_inside_a_word_does_not_reassign_speech():
    from services.segmentation import Segment, _apply_scene_cuts
    words = [
        {'text': 'A lengthy opening phrase', 'start': 0, 'end': 4},
        {'text': 'And the closing phrase', 'start': 4.5, 'end': 7},
    ]
    segment = Segment(start=0, end=7, text='A lengthy opening phrase And the closing phrase', extra={'words': words})
    assert _apply_scene_cuts([segment], [3]) == [segment]


def test_failed_regeneration_preserves_previous_track(render_dub):
    previous = render_dub.path / 'dubbed_en.wav'
    previous.write_bytes(b'previous successful output')
    render_dub.job['dubbed_tracks']['en'] = {'path': str(previous)}
    def fail(): raise RuntimeError('failure')
    render_dub.output[0] = fail
    render_dub.run()
    assert previous.read_bytes() == b'previous successful output'
    assert render_dub.job['dubbed_tracks']['en']['path'] == str(previous)


@pytest.mark.parametrize("segment_ids", [["duplicate", "duplicate"], ["seg_1"]])
def test_conflicting_regeneration_preserves_saved_audio_and_text(render_dub, monkeypatch, segment_ids):
    from api.routers import dub_generate as dg
    from fastapi import HTTPException

    previous = render_dub.path / 'dubbed_en.wav'
    sf.write(previous, [.2] * 24000, 24000)
    previous_bytes = previous.read_bytes()
    render_dub.job.update({
        'segments': [{'id': 'a', 'start': 0, 'end': 1, 'text': 'saved first'},
                     {'id': 'b', 'start': 1, 'end': 2, 'text': 'saved second'}],
        'segments_i18n': {'en': {'a': 'saved first', 'b': 'saved second'}},
        'dubbed_tracks': {'en': {'path': str(previous)}},
    })
    saved = copy.deepcopy(render_dub.job)
    persisted = render_dub.path / 'job.json'
    persisted.write_text(json.dumps(saved))
    monkeypatch.setattr(dg, '_save_job', lambda _, job: persisted.write_text(json.dumps(job)))
    async def forbidden_resolution():
        pytest.fail('Conflicting identities must be rejected before loading a backend')
    monkeypatch.setattr(dg, '_resolve_dub_execution', forbidden_resolution)

    with pytest.raises(HTTPException) as error:
        render_dub.run(segments=[dict(start=0, end=1, text='replacement first'),
                                 dict(start=1, end=2, text='replacement second')],
                       segment_ids=segment_ids)
    assert error.value.status_code == 409
    assert error.value.detail['code'] == 'dub_segment_identity_conflict'
    assert previous.read_bytes() == previous_bytes
    assert json.loads(persisted.read_text()) == saved
    assert render_dub.job == saved
    assert not render_dub.generated


def test_partial_ids_render_without_reusing_a_saved_segment(render_dub):
    render_dub.job['segments'] = [
        {'id': 'a', 'start': 0, 'end': 1, 'text': 'original a'},
        {'id': 'b', 'start': 1, 'end': 2, 'text': 'original b'},
    ]
    events = render_dub.run(segments=[dict(start=0, end=1, text='translated b'),
                                      dict(start=1, end=2, text='new segment')],
                            segment_ids=['b'])
    assert any(e['type'] == 'done' for e in events)
    assert [row['id'] for row in render_dub.job['segments']] == ['b', 'seg_1']
    assert render_dub.job['segments_i18n']['en'] == {'b': 'translated b', 'seg_1': 'new segment'}
    assert sf.info(render_dub.path / 'dubbed_en.wav').frames > 0


def test_explicit_later_id_keeps_saved_metadata_after_render(render_dub):
    render_dub.job['segments'] = [
        {'id': 'a', 'start': 0, 'end': 1, 'text': 'original a', 'speaker_id': 'speaker-a'},
        {'id': 'b', 'start': 1, 'end': 2, 'text': 'original b', 'speaker_id': 'speaker-b'},
    ]
    events = render_dub.run(segments=[dict(start=0, end=1, text='new x'),
                                      dict(start=1, end=2, text='translated a')],
                            segment_ids=['x', 'a'])
    assert any(e['type'] == 'done' for e in events)
    rows = render_dub.job['segments']
    assert [row['id'] for row in rows] == ['x', 'a']
    assert 'speaker_id' not in rows[0]
    assert rows[0]['text_original'] == ''
    assert rows[1]['speaker_id'] == 'speaker-a'
    assert rows[1]['text_original'] == 'original a'
    assert render_dub.job['segments_i18n']['en'] == {'x': 'new x', 'a': 'translated a'}
    assert sf.info(render_dub.path / 'dubbed_en.wav').frames > 0


def test_timing_trims_edge_silence_but_keeps_internal_pauses():
    from services.audio_dsp import trim_speech_padding
    wav = torch.cat((torch.zeros(1, 1000), torch.ones(1, 200)*.1,
                     torch.zeros(1, 200), torch.ones(1, 200)*.1, torch.zeros(1,1000)), dim=-1)
    result = trim_speech_padding(wav, 1000)
    assert result.shape[-1] == 700
    assert torch.equal(result[..., 250:450], torch.zeros(1,200))


def test_identity_change_during_render_preserves_previous_publication(render_dub, monkeypatch):
    from api.routers import dub_generate as dg

    previous = render_dub.path / 'dubbed_en.wav'
    previous.write_bytes(b'previous complete track')
    render_dub.job.update({
        'segments': [{'id': 'a', 'start': 0, 'end': 1, 'text': 'saved first'},
                     {'id': 'b', 'start': 1, 'end': 2, 'text': 'saved second'}],
        'segments_i18n': {'en': {'a': 'saved first', 'b': 'saved second'}},
        'seg_hashes': {'a': 'saved hash'},
        'seg_hashes_by_lang': {'en': {'a': 'saved hash'}},
        'dubbed_tracks': {'en': {'path': str(previous)}},
    })
    cached = [render_dub.path / f'seg_en_seg_{i}.wav' for i in range(2)]
    for cache in cached:
        sf.write(cache, [.2] * 24000, 24000)
    cached_bytes = [cache.read_bytes() for cache in cached]
    saved = copy.deepcopy(render_dub.job)
    persisted = render_dub.path / 'job.json'
    persisted.write_text(json.dumps(saved))
    monkeypatch.setattr(dg, '_save_job', lambda _, job: persisted.write_text(json.dumps(job)))

    def change_identity():
        render_dub.job['segments'][0]['id'] = 'duplicate'
        render_dub.job['segments'][1]['id'] = 'duplicate'
        return torch.ones(1, 24000) * .1
    render_dub.output[0] = change_identity
    events = render_dub.run(segments=[dict(start=0, end=1, text='replacement first'),
                                      dict(start=1, end=2, text='replacement second')],
                            segment_ids=[])
    assert any(e['type'] == 'error' and e.get('error_code') == 'dub_segment_identity_conflict'
               for e in events)
    assert not any(e['type'] == 'done' for e in events)
    assert [cache.read_bytes() for cache in cached] == cached_bytes
    assert not list(render_dub.path.glob('.render-*'))
    assert previous.read_bytes() == b'previous complete track'
    assert json.loads(persisted.read_text()) == saved
    for key in ('seg_hashes', 'seg_hashes_by_lang', 'segments_i18n', 'dubbed_tracks'):
        assert render_dub.job[key] == saved[key]


def test_subtitle_import_during_assembly_keeps_edits_and_previous_track(render_dub, monkeypatch):
    import io
    from fastapi import UploadFile
    from api.routers import dub_core, dub_generate as dg

    previous = render_dub.path / 'dubbed_en.wav'
    previous.write_bytes(b'previous complete track')
    render_dub.job.update({
        'segments': [{'id': 'a', 'start': 0, 'end': 1, 'text': 'saved text'}],
        'seg_order': ['a'],
        'seg_hashes': {'a': 'saved hash'},
        'seg_hashes_by_lang': {'en': {'a': 'saved hash'}},
        'dubbed_tracks': {'en': {'path': str(previous)}},
    })
    saved_hashes = copy.deepcopy(render_dub.job['seg_hashes_by_lang'])
    persisted = render_dub.path / 'job.json'
    def persist(_, job):
        persisted.write_text(json.dumps(job))
    persist('job', render_dub.job)
    monkeypatch.setattr(dg, '_save_job', persist)
    monkeypatch.setattr(dub_core, '_save_job', persist)
    monkeypatch.setattr(dub_core, '_get_job', lambda _: render_dub.job)
    imported = []
    async def stretch(wav, target, sr):
        result = await dub_core.dub_import_srt('job', UploadFile(
            filename='corrected.srt',
            file=io.BytesIO(b'1\n00:00:00,000 --> 00:00:01,000\nCorrected subtitle\n'),
        ))
        imported.extend(copy.deepcopy(result['segments']))
        return torch.nn.functional.interpolate(wav.unsqueeze(0), size=target, mode='linear').squeeze(0)
    monkeypatch.setattr(dg, '_pitch_preserving_stretch', stretch)
    render_dub.output[0] = lambda: torch.ones(1, 48000) * .1
    events = render_dub.run(timing_strategy='strict_slot')
    assert imported
    assert any(e['type'] == 'error' and e.get('error_code') == 'dub_source_changed' for e in events)
    assert not any(e['type'] == 'done' for e in events)
    assert render_dub.job['segments'] == imported
    assert render_dub.job['seg_hashes_by_lang'] == saved_hashes
    assert previous.read_bytes() == b'previous complete track'
    assert json.loads(persisted.read_text()) == render_dub.job


def test_empty_dub_request_rejected_before_backend_resolution(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers import dub_generate as dg

    async def forbidden():
        pytest.fail('Empty requests must not load the synthesis backend')
    monkeypatch.setattr(dg, '_resolve_dub_execution', forbidden)
    monkeypatch.setattr(dg, '_get_job', lambda _: {'segments': []})
    app = FastAPI()
    app.include_router(dg.router)
    with TestClient(app) as client:
        response = client.post('/dub/generate/job', json={'segments': []})
    assert response.status_code == 422
    assert any(error['loc'] == ['body', 'segments'] for error in response.json()['detail'])


@pytest.mark.parametrize('failure', ['install', 'persist'])
def test_failed_publication_restores_track_and_segment_cache(render_dub, monkeypatch, failure):
    from api.routers import dub_generate as dg

    previous = render_dub.path / 'dubbed_en.wav'
    previous.write_bytes(b'previous complete track')
    cache = render_dub.path / 'seg_en_a.wav'
    sf.write(cache, [.2] * 24000, 24000)
    cache_bytes = cache.read_bytes()
    render_dub.job['dubbed_tracks']['en'] = {'path': str(previous)}
    render_dub.job['segments'] = [{'id': 'a', 'start': 0, 'end': 1, 'text': 'old speech',
                                   'qc_flagged': True, 'qc_recognized': 'old speech'}]
    original = copy.deepcopy(render_dub.job)
    if failure == 'install':
        replace = dg.os.replace
        def fail_track_install(source, destination):
            if str(destination) == str(previous):
                raise OSError('injected track installation failure')
            return replace(source, destination)
        monkeypatch.setattr(dg.os, 'replace', fail_track_install)
    else:
        def fail_save(*_):
            raise OSError('injected persistence failure')
        monkeypatch.setattr(dg, '_save_job', fail_save)
    events = render_dub.run()
    assert any(e['type'] == 'error' for e in events)
    assert not any(e['type'] == 'done' for e in events)
    assert previous.read_bytes() == b'previous complete track'
    assert cache.read_bytes() == cache_bytes
    assert render_dub.job == original
    assert not list(render_dub.path.glob('.render-*'))


def test_cancelled_render_discards_staged_cache(render_dub, monkeypatch):
    from api.routers import dub_generate as dg

    cache = render_dub.path / 'seg_en_a.wav'
    sf.write(cache, [.2] * 24000, 24000)
    cache_bytes = cache.read_bytes()
    calls = []
    def cancelled(_):
        calls.append(True)
        return len(calls) >= 3  # after the first segment, before the second
    monkeypatch.setattr(dg.task_manager, 'is_cancelled', cancelled)
    events = render_dub.run(segments=[dict(start=0, end=1, text='first'),
                                      dict(start=1, end=2, text='second')], segment_ids=['a', 'b'])
    assert any(e['type'] == 'cancelled' for e in events)
    assert cache.read_bytes() == cache_bytes
    assert not (render_dub.path / 'seg_en_b.wav').exists()
    assert not list(render_dub.path.glob('.render-*'))


def test_qc_annotations_during_assembly_do_not_discard_render(render_dub, monkeypatch):
    from api.routers import dub_generate as dg

    render_dub.job['segments'] = [{'id': 'a', 'start': 0, 'end': 1, 'text': 'original'}]
    async def stretch(wav, target, sr):
        render_dub.job['segments'][0].update(qc_drift=0.2, qc_flagged=True,
                                            qc_recognized='measured speech',
                                            qc_measured_start=0.1, qc_measured_end=0.9)
        return torch.nn.functional.interpolate(wav.unsqueeze(0), size=target, mode='linear').squeeze(0)
    monkeypatch.setattr(dg, '_pitch_preserving_stretch', stretch)
    render_dub.output[0] = lambda: torch.ones(1, 48000) * .1
    events = render_dub.run(timing_strategy='strict_slot')
    assert any(e['type'] == 'done' for e in events)
    assert not any(e.get('error_code') == 'dub_source_changed' for e in events)
    assert not any(key.startswith('qc_') for key in render_dub.job['segments'][0])
    assert render_dub.job['segments'][0]['text'] == 'hello'
