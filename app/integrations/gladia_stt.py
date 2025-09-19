import os
import time
import mimetypes
import requests

UPLOAD_URL = "https://api.gladia.io/v2/upload"
PR_INIT_URL = "https://api.gladia.io/v2/pre-recorded"
PR_GET_URL = "https://api.gladia.io/v2/pre-recorded/{id}"

class GladiaError(RuntimeError):
    pass

def _headers():
    api = os.getenv("GLADIA_API_KEY")
    if not api:
        raise GladiaError("GLADIA_API_KEY not set")
    return {"x-gladia-key": api}

def _upload_local_file(path: str) -> str:
    mt = mimetypes.guess_type(path)[0] or "audio/wav"
    with open(path, "rb") as fh:
        files = {"audio": (os.path.basename(path), fh, mt)}
        r = requests.post(UPLOAD_URL, headers=_headers(), files=files, timeout=120)
    r.raise_for_status()
    js = r.json()
    audio_url = js.get("audio_url")
    if not audio_url:
        raise GladiaError(f"Upload response missing audio_url: {js}")
    return audio_url

def _init_pre_recorded(audio_url: str) -> str:
    payload = {
        "audio_url": audio_url,
        # keep it simple; you can add options (language_config, diarization, etc.)
    }
    r = requests.post(PR_INIT_URL, headers={**_headers(), "Content-Type": "application/json"}, json=payload, timeout=60)
    # per docs this returns 201 with {"id": "...", "result_url": "..."}
    if r.status_code not in (200, 201):
        raise GladiaError(f"Init failed: {r.status_code} {r.text}")
    js = r.json()
    job_id = js.get("id")
    if not job_id:
        raise GladiaError(f"Init response missing id: {js}")
    return job_id

def _get_result(job_id: str) -> dict:
    url = PR_GET_URL.format(id=job_id)
    r = requests.get(url, headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json()

def transcribe_audio(path_or_url: str, poll_interval=1.2, max_wait=60) -> str:
    """
    Transcribe local file or remote URL via Gladia pre-recorded API.
    Returns transcript text (or raises GladiaError).
    """
    # 1) if local path, upload to get audio_url
    if path_or_url.startswith(("http://", "https://")):
        audio_url = path_or_url
    else:
        audio_url = _upload_local_file(path_or_url)

    # 2) initiate job
    job_id = _init_pre_recorded(audio_url)

    # 3) poll for completion
    deadline = time.time() + max_wait
    status = "queued"
    last = None
    while time.time() < deadline:
        last = _get_result(job_id)
        status = last.get("status") or last.get("state") or status
        if status in ("completed", "success", "succeeded"):
            break
        if status in ("error", "failed", "canceled"):
            raise GladiaError(f"Transcription failed: {last}")
        time.sleep(poll_interval)

    if status not in ("completed", "success", "succeeded"):
        raise GladiaError(f"Timeout waiting for transcription (last status: {status})")

    # 4) parse transcript
    result = last.get("result") or {}
    tr = result.get("transcription") or {}
    text = tr.get("full_transcript")
    if not text:
        # fallback: join utterances
        utts = tr.get("utterances") or []
        if isinstance(utts, list):
            texts = [u.get("text") for u in utts if isinstance(u, dict) and u.get("text")]
            if texts:
                text = " ".join(texts)
    if not text:
        raise GladiaError(f"No transcript found in result: {last}")
    return text
