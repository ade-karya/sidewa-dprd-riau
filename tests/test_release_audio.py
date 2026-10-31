"""Pengujian validasi rekaman audio untuk draf rilis otomatis."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import release_draft


def _write(tmp_path: Path, name: str, payload: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


def test_prepare_audio_mengenali_mp3_dari_magic_bytes(tmp_path):
    source = _write(tmp_path, "rapat.mp3", b"ID3" + b"\x00" * 64)
    prepared = release_draft.prepare_audio(source, "Rapat Paripurna DPRD Riau.mp3")

    assert prepared.mime == "audio/mpeg"
    assert prepared.filename.endswith(".mp3")
    assert prepared.size == 67
    assert prepared.path == source


def test_prepare_audio_mengganti_ekstensi_yang_tidak_sesuai(tmp_path):
    source = _write(tmp_path, "rekaman.bin", b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 32)
    prepared = release_draft.prepare_audio(source, "rekaman.wav")

    assert prepared.mime == "audio/wav"
    assert prepared.filename.endswith(".wav")


def test_prepare_audio_menolak_berkas_bukan_audio(tmp_path):
    source = _write(tmp_path, "catatan.txt", b"bukan audio" * 4)
    with pytest.raises(release_draft.ReleaseAudioError):
        release_draft.prepare_audio(source, "catatan.txt")


def test_prepare_audio_menolak_berkas_melebihi_batas(tmp_path):
    source = _write(tmp_path, "rapat.mp3", b"ID3" + b"\x00" * 64)
    with pytest.raises(release_draft.ReleaseAudioError):
        release_draft.prepare_audio(source, "rapat.mp3", max_bytes=10)


def test_prepare_audio_tanpa_batas_tambahan(tmp_path):
    source = _write(tmp_path, "rapat.mp3", b"ID3" + b"\x00" * 1024)

    assert release_draft.max_audio_bytes() == release_draft.GEMINI_MAX_FILE_BYTES
    prepared = release_draft.prepare_audio(source, "rapat.mp3")

    assert prepared.size == 1027
