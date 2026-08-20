"""Small Demucs runner that only handles the PCM WAV produced by our pipeline.

Demucs' stock CLI shells out to ffprobe/ffmpeg even for WAV input. Loading and
saving the known PCM format directly keeps the app self-contained on Windows.
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np
import torch
from demucs.apply import apply_model
from demucs.audio import convert_audio
from demucs.pretrained import get_model


def load_pcm_wav(path: Path) -> tuple[torch.Tensor, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        sample_width = handle.getsampwidth()
        raw = handle.readframes(handle.getnframes())
    if sample_width != 2:
        raise ValueError("Expected a 16-bit PCM WAV file")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    samples = samples.reshape(-1, channels).T.copy()
    return torch.from_numpy(samples), sample_rate


def save_pcm_wav(path: Path, audio: torch.Tensor, sample_rate: int) -> None:
    audio = audio.detach().cpu().clamp(-1.0, 1.0)
    interleaved = audio.T.contiguous().numpy()
    pcm = np.rint(interleaved * 32767.0).astype("<i2").tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(audio.shape[0])
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)


def separate(
    mixture_path: Path,
    output_path: Path,
    model_name: str = "htdemucs",
    vocals_output_path: Path | None = None,
) -> None:
    model = get_model(model_name)
    model.cpu()
    model.eval()

    mixture, sample_rate = load_pcm_wav(mixture_path)
    mixture = convert_audio(
        mixture,
        sample_rate,
        model.samplerate,
        model.audio_channels,
    )
    reference = mixture.mean(0)
    mean = reference.mean()
    std = reference.std().clamp_min(1e-8)
    normalised = (mixture - mean) / std
    device = "cuda" if torch.cuda.is_available() else "cpu"

    with torch.inference_mode():
        sources = apply_model(
            model,
            normalised[None],
            device=device,
            shifts=1,
            split=True,
            overlap=0.25,
            progress=True,
            num_workers=0,
        )[0]
    sources = sources * std + mean

    instrumental = torch.zeros_like(sources[0])
    for index, name in enumerate(model.sources):
        if name != "vocals":
            instrumental += sources[index]
    save_pcm_wav(output_path, instrumental, model.samplerate)
    if vocals_output_path is not None:
        vocals_index = model.sources.index("vocals")
        save_pcm_wav(vocals_output_path, sources[vocals_index], model.samplerate)


def main() -> None:
    parser = argparse.ArgumentParser(description="Separate vocals with Demucs")
    parser.add_argument("mixture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="htdemucs")
    parser.add_argument("--vocals-output", type=Path)
    args = parser.parse_args()
    separate(
        args.mixture,
        args.output,
        args.model,
        vocals_output_path=args.vocals_output,
    )


if __name__ == "__main__":
    main()
