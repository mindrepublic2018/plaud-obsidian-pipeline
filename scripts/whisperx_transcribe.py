#!/usr/bin/env python3
"""
WhisperX 전사 + 화자분리(diarization) — 선택 기능 (로컬 화자분리 폴백 티어).
  사용: .venv-whisperx/bin/python scripts/whisperx_transcribe.py <audio>
  표준출력: "SPEAKER_00: ...\nSPEAKER_01: ..." (화자 라벨 + 문장)
  HF 토큰 해석 순서: config.env HF_TOKEN → 레포 루트 .hf_token 파일 (# 주석/빈 줄 무시)

이 스크립트만은 별도 venv(.venv-whisperx, Python 3.11 + whisperx)에서 실행된다 —
시스템 python3 로 실행하는 다른 스크립트들과 달리 서드파티 의존성이 필요하다.
셋업 방법은 README '로컬 화자분리 (WhisperX)' 절 참고. venv 가 없으면
process_inbox.py 가 이 티어를 건너뛰고 whisper.cpp 로 폴백한다.

전사는 faster-whisper(CPU/int8), diarization 은 pyannote(가능하면 MPS).
한국어는 word-align 모델 지원이 약해 segment(문장) 단위로 화자를 할당한다.
"""
import os
import re
import sys
import warnings

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# torchcodec 이 brew ffmpeg dylib 을 찾도록 (pyannote 4.x 오디오 디코딩 경고 회피)
os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load  # noqa: E402

CFG = load()


def err(*a):
    print(*a, file=sys.stderr)


def assign_speaker(seg, df):
    """문장(segment)의 시간 중점이 속하는 화자 구간을 찾아 화자 라벨 반환."""
    s, e = seg.get("start"), seg.get("end")
    if s is None or e is None or df is None or len(df) == 0:
        return None
    mid = (s + e) / 2.0
    hit = df[(df["start"] <= mid) & (df["end"] >= mid)]
    if len(hit):
        return hit.iloc[0]["speaker"]
    # 포함 구간이 없으면 겹침이 가장 큰 화자
    ov = (df["end"].clip(upper=e) - df["start"].clip(lower=s)).clip(lower=0)
    if len(ov) and ov.max() > 0:
        return df.loc[ov.idxmax(), "speaker"]
    return None


def read_token():
    tok = (CFG.get("HF_TOKEN") or "").strip()
    if tok:
        return tok
    path = CFG["HF_TOKEN_PATH"]
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith("#") or not ln:
                continue
            m = re.search(r"hf_[A-Za-z0-9]+", ln)
            if m:
                return m.group(0)
    return None


def main():
    if len(sys.argv) < 2:
        err("usage: whisperx_transcribe.py <audio>")
        sys.exit(2)
    # whisperx 가 자체 로거에 stdout 핸들러를 붙여(log_utils.setup_logging) INFO 로그가
    # 전사 출력(stdout)에 섞이는 문제 방지: 작업 중에는 stdout 을 stderr 로 돌려두고,
    # 최종 전사 결과만 real_stdout 으로 낸다.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    audio_path = sys.argv[1]
    lang = CFG.get("WHISPER_LANG") or "ko"
    token = read_token()
    if not token:
        err("HF 토큰 없음 — diarization 불가")
        sys.exit(3)

    import torch
    import whisperx
    from whisperx.diarize import DiarizationPipeline

    # 전사: ctranslate2 는 Mac 에서 CPU 만. int8_float32 = int8 보다 정확, float32 보다 빠름
    asr_device = "cpu"
    compute_type = "int8_float32"
    # diarization: MPS 가능하면 사용, 아니면 CPU
    diar_device = "mps" if torch.backends.mps.is_available() else "cpu"

    err(f"[whisperx] load_model large-v3 (asr={asr_device}/{compute_type})")
    model = whisperx.load_model("large-v3", asr_device, compute_type=compute_type,
                                language=lang)
    audio = whisperx.load_audio(audio_path)   # ffmpeg CLI 사용 (torchcodec 무관)
    err("[whisperx] transcribe…")
    result = model.transcribe(audio, batch_size=8, language=lang)

    err(f"[whisperx] diarize (device={diar_device})…")
    diar_df = None
    for dev in ([diar_device, "cpu"] if diar_device != "cpu" else ["cpu"]):
        try:
            diar = DiarizationPipeline(model_name="pyannote/speaker-diarization-community-1",
                                       token=token, device=dev)
            diar_df = diar(audio, min_speakers=1, max_speakers=6)
            err(f"[whisperx] diarization OK (device={dev}, rows={len(diar_df)})")
            break
        except Exception as e:
            err(f"[whisperx] diarization 실패(device={dev}): {e}")
            diar_df = None
    has_diar = diar_df is not None and len(diar_df) > 0
    if has_diar:
        for seg in result.get("segments", []):
            seg["speaker"] = assign_speaker(seg, diar_df)
        spks = sorted({s.get("speaker") for s in result["segments"] if s.get("speaker")})
        err(f"[whisperx] 감지된 화자 {len(spks)}명: {spks}")

    # 출력: 연속 동일 화자는 합쳐서 가독성 ↑
    lines, cur_spk, buf = [], None, []

    def flush():
        if buf:
            txt = " ".join(buf).strip()
            if txt:
                lines.append((cur_spk, txt))

    for seg in result.get("segments", []):
        spk = seg.get("speaker") if has_diar else None
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if spk != cur_spk:
            flush()
            buf = []
            cur_spk = spk
        buf.append(text)
    flush()

    out = []
    for spk, txt in lines:
        label = spk if spk else "화자?"
        out.append(f"{label}: {txt}")
    print("\n".join(out), file=real_stdout)


if __name__ == "__main__":
    main()
