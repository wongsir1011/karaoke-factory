from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import torch

from karaoke_maker.demucs_runner import load_pcm_wav, save_pcm_wav


def test_pcm_wav_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "audio.wav"
    source = torch.tensor([[0.0, 0.25, -0.25], [0.5, -0.5, 0.0]])

    save_pcm_wav(path, source, 44_100)
    restored, sample_rate = load_pcm_wav(path)

    assert sample_rate == 44_100
    assert restored.shape == source.shape
    assert torch.allclose(restored, source, atol=1 / 32768)

    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 2
        assert handle.getsampwidth() == 2
