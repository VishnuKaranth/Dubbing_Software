import modal
import os
import asyncio

# --------------------------------------------------
# 🔥 GLOBAL MODEL CACHE
# --------------------------------------------------
WHISPER_MODEL = None
ALIGN_MODEL = None
ALIGN_METADATA = None
DIARIZER = None
XTTS_MODEL = None

# --------------------------------------------------
# Image
# --------------------------------------------------
dubbing_image = (
    modal.Image.debian_slim()
    # System dependencies
    .apt_install(
        "git", "ffmpeg", "libsndfile1", "espeak-ng",
        "libavformat-dev", "libavcodec-dev",
        "libavdevice-dev", "libavutil-dev",
        "libswscale-dev", "libswresample-dev",
        "pkg-config"
    )
    # Python dependencies
    .pip_install(
        "numpy<2.0",
        "torch==2.1.2",
        "torchaudio==2.1.2",
        "transformers<4.46",
        "whisperx",
        "TTS",
        "demucs",
        "librosa",
        "soundfile",
        "ffmpeg-python",
        "deep-translator",
        "accelerate",
        "boto3",
        "fastapi",
        "edge-tts",
        "scipy"
    )
    .env({"COQUI_TOS_AGREED": "1"})
)

# --------------------------------------------------
# App / Volume / Secrets
# --------------------------------------------------
app = modal.App("voice-dubbing-backend-v3", image=dubbing_image)

volume = modal.Volume.from_name("dubbing-storage", create_if_missing=True)
rate_limiter = modal.Dict.from_name("rate-limit-db", create_if_missing=True)
hf_token = modal.Secret.from_name("huggingface-token")
r2_secret = modal.Secret.from_dotenv(path="../.env")

# Runtime Mount Path
MOUNT_PATH = "/data" 
BASE_DIR = f"{MOUNT_PATH}/dubbing"

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def check_daily_limit(client_id):
    """
    Enforces 3 generations per 24 hours per client_id.
    Returns True if allowed, False if blocked.
    """
    import time
    if not client_id or client_id == "anonymous":
        return True # or False to force ID? Let's allow for now or strict?
        # User wants to lock user.
    
    now = time.time()
    try:
        timestamps = rate_limiter.get(client_id, [])
    except KeyError:
        timestamps = []
        
    # Filter timestamps older than 24h (86400 seconds)
    valid_timestamps = [t for t in timestamps if now - t < 86400]
    
    if len(valid_timestamps) >= 3:
        print(f"Rate Limit Hit for {client_id}: {len(valid_timestamps)} uses today.")
        return False
        
    valid_timestamps.append(now)
    rate_limiter[client_id] = valid_timestamps
    print(f"Rate Limit Check: {client_id} has {len(valid_timestamps)}/3 uses.")
    return True

def detect_gender(audio_path):
    """
    Detects gender based on Pitch (F0) analysis using Librosa.
    Threshold: 165Hz (Midpoint between avg Male ~120Hz and Female ~210Hz)
    """
    print("Detecting gender from vocals...")
    import librosa
    import numpy as np
    try:
        # Load first 30 seconds only for speed
        y, sr = librosa.load(audio_path, sr=None, duration=30)
        # Extract Pitch (F0) using probabilistic YIN
        f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=50, fmax=400)
        # Calculate mean pitch of voiced segments
        mean_pitch = np.nanmean(f0)
        
        if np.isnan(mean_pitch):
             print("Pitch detection failed (NaN), defaulting to Male")
             return "Male"
             
        print(f"Detected Pitch: {mean_pitch:.2f} Hz")
        return "Female" if mean_pitch > 165 else "Male"
    except Exception as e:
        print(f"Gender detection error: {e}, defaulting to Male")
        return "Male"

async def generate_edge_tts(text, voice, out_file):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_file)

# --------------------------------------------------
# MAIN GPU PIPELINE
# --------------------------------------------------
@app.function(
    gpu="A10",
    volumes={MOUNT_PATH: volume},
    secrets=[hf_token, r2_secret],
    timeout=3600
)
@modal.fastapi_endpoint(method="POST")
def dub_video(item: dict):
    # -------------------- RUNTIME CONFIG --------------------
    os.environ["HF_HOME"] = f"{MOUNT_PATH}/models/hf"
    os.environ["TORCH_HOME"] = f"{MOUNT_PATH}/models/torch"
    os.environ["TTS_HOME"] = f"{MOUNT_PATH}/models/tts"
    os.environ["XDG_CACHE_HOME"] = f"{MOUNT_PATH}/cache"
    os.environ["COQUI_TOS_AGREED"] = "1"

    # Runtime imports to ensure availability
    import subprocess
    import ffmpeg
    import soundfile as sf
    import whisperx
    from TTS.api import TTS
    from deep_translator import GoogleTranslator
    from botocore.config import Config
    import librosa
    import edge_tts
    import asyncio
    import torch
    import numpy as np
    import shutil
    import re

    global WHISPER_MODEL, ALIGN_MODEL, ALIGN_METADATA, DIARIZER, XTTS_MODEL

    job_id = item["job_id"]
    video_url = item["video_url"]
    target_lang = item.get("target_lang", "hi")
    client_id = item.get("client_id", "unknown_user")
    
    # ------------------ SECURITY CHECKS ------------------
    import re
    # 1. Path Traversal Prevention
    # Allow alphanumeric, underscore, hyphen only. No illegal chars.
    if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
        print(f"[{job_id}] SECURITY BLOCK: Invalid job_id format.")
        return {"status": "error", "message": "Invalid job_id format. Security Block."}
        
    # 2. SSRF Prevention (Basic)
    # Ensure scheme is http or https.
    if not video_url.startswith(("http://", "https://")):
        print(f"[{job_id}] SECURITY BLOCK: Invalid URL scheme.")
        return {"status": "error", "message": "Invalid URL scheme."}
    # -----------------------------------------------------
    
    print(f"[{job_id}] Starting V3 Pipeline (EdgeTTS + GenderDetect)... User: {client_id}")

    # Rate Limit Check
    if not check_daily_limit(client_id):
        print(f"[{job_id}] BLOCKED by Rate Limit.")
        return {"status": "error", "message": "Daily limit reached (3/3). Please try again in 24 hours."}

    # Setup directories
    job_dir = f"{BASE_DIR}/{job_id}"
    os.makedirs(job_dir, exist_ok=True)

    video_path = f"{job_dir}/video.mp4"
    audio_path = f"{job_dir}/audio.wav"
    dubbed_audio = f"{job_dir}/dubbed.wav"
    final_video = f"{job_dir}/final_dubbed.mp4"

    # 1. DOWNLOAD VIDEO
    print(f"[{job_id}] Downloading video...")
    import requests
    r = requests.get(video_url, stream=True, timeout=600)
    r.raise_for_status()
    with open(video_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)

    # 2. EXTRACT AUDIO
    print(f"[{job_id}] Extracting audio...")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "44100", "-ac", "2",
        audio_path
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. DEMUCS
    print(f"[{job_id}] Separating vocals...")
    demucs_out = f"{job_dir}/separated"
    subprocess.run([
        "demucs", "--two-stems=vocals", "-n", "htdemucs", "--segment", "7",
        "-o", demucs_out, audio_path
    ], check=True)

    vocals, bg = None, None
    for root, _, files in os.walk(demucs_out):
        if "vocals.wav" in files:
            vocals = os.path.join(root, "vocals.wav")
            bg = os.path.join(root, "no_vocals.wav")
            break

    if not vocals:
        shutil.rmtree(job_dir, ignore_errors=True)
        return {"status": "error", "message": "Demucs failed"}

    # 4. WHISPERX
    print(f"[{job_id}] Transcribing...")
    if WHISPER_MODEL is None:
        print("Loading WhisperX model...")
        WHISPER_MODEL = whisperx.load_model("medium", device="cuda", compute_type="float16")
    
    audio_wav = whisperx.load_audio(vocals)
    result = WHISPER_MODEL.transcribe(audio_wav, batch_size=8, chunk_size=30)
    lang = result["language"]
    print(f"[{job_id}] Detected language: {lang}")

    if ALIGN_MODEL is None:
        ALIGN_MODEL, ALIGN_METADATA = whisperx.load_align_model(lang, device="cuda")
    result = whisperx.align(result["segments"], ALIGN_MODEL, ALIGN_METADATA, audio_wav, device="cuda")

    if DIARIZER is None:
        DIARIZER = whisperx.DiarizationPipeline(use_auth_token=os.environ["HF_TOKEN"], device="cuda")
    diar = DIARIZER(audio_wav)
    result = whisperx.assign_word_speakers(diar, result)

    # 5. TRANSLATION
    print(f"[{job_id}] Translating to {target_lang}...")
    translator = GoogleTranslator(source="auto", target=target_lang)
    for seg in result["segments"]:
        try:
            seg["translated_text"] = translator.translate(seg["text"])
        except:
            seg["translated_text"] = seg["text"]

    # 6. SYNTHESIS (XTTS vs EDGE TTS)
    xtts_langs = ["en","es","fr","de","it","pt","pl","tr","ru","nl","cs","ar","zh","ja","ko","hi"]
    combined = []

    if target_lang in xtts_langs:
        # XTTS CLONING
        print(f"[{job_id}] Using XTTS (Cloning) for {target_lang}")
        if XTTS_MODEL is None:
            print("Loading XTTS model...")
            XTTS_MODEL = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
        
        for seg in result["segments"]:
            if not seg.get("translated_text"): continue
            try:
                wav = XTTS_MODEL.tts(text=seg["translated_text"], speaker_wav=vocals, language=target_lang)
                combined.extend(wav)
            except Exception as e:
                print(f"XTTS error: {e}")
        
        sf.write(dubbed_audio, combined, 24000)

    else:
        # EDGE TTS (High Quality Fallback)
        print(f"[{job_id}] Using Microsoft Edge TTS for {target_lang}")
        
        # Detect Gender
        gender = detect_gender(vocals)
        print(f"[{job_id}] Selected Voice Gender: {gender}")

        # Edge TTS Voice Mapping
        edge_voices = {
            "kn": {"Male": "kn-IN-GaganNeural", "Female": "kn-IN-SapnaNeural"},
            "te": {"Male": "te-IN-MohanNeural", "Female": "te-IN-ShrutiNeural"},
            "ta": {"Male": "ta-IN-ValluvarNeural", "Female": "ta-IN-PallaviNeural"},
            "ml": {"Male": "ml-IN-MidhunNeural", "Female": "ml-IN-SobhanaNeural"},
            "mr": {"Male": "mr-IN-ManoharNeural", "Female": "mr-IN-AarohiNeural"},
            "gu": {"Male": "gu-IN-NiranjanNeural", "Female": "gu-IN-DhwaniNeural"},
            "bn": {"Male": "bn-BD-PradeepNeural", "Female": "bn-BD-NabanitaNeural"}, # Or IN variants
            "ur": {"Male": "ur-PK-UzairNeural", "Female": "ur-PK-UzmaNeural"}
        }
        
        # Default to English if unknown, but hopefully logic covers it
        lang_voices = edge_voices.get(target_lang, {"Male": "en-US-ChristopherNeural", "Female": "en-US-JennyNeural"})
        selected_voice = lang_voices.get(gender, lang_voices["Male"])
        print(f"[{job_id}] Voice: {selected_voice}")

        for i, seg in enumerate(result["segments"]):
            if not seg.get("translated_text"): continue
            try:
                temp_seg_file = f"{job_dir}/temp_{i}.mp3"
                # Run Async Edge TTS
                asyncio.run(generate_edge_tts(seg["translated_text"], selected_voice, temp_seg_file))
                
                # Read back with Librosa (resample to 24000 to match XTTS baseline logic for mixing)
                seg_wav, _ = librosa.load(temp_seg_file, sr=24000)
                combined.extend(seg_wav)
                
                # Cleanup
                if os.path.exists(temp_seg_file):
                    os.remove(temp_seg_file)
            except Exception as e:
                print(f"EdgeTTS error: {e}")

        sf.write(dubbed_audio, combined, 24000)

    # 7. MIXING
    print(f"[{job_id}] Mixing...")
    try:
        v_stream = ffmpeg.input(video_path).video
        a_stream = ffmpeg.input(dubbed_audio)
        bg_stream = ffmpeg.input(bg).filter("volume", 0.5) # Background music volume
        mixed = ffmpeg.filter([a_stream, bg_stream], "amix", inputs=2, duration="first")
        ffmpeg.output(v_stream, mixed, final_video, vcodec="copy", acodec="aac").run(overwrite_output=True)
    except ffmpeg.Error as e:
        print(f"FFmpeg Error: {e.stderr.decode() if e.stderr else str(e)}")
        shutil.rmtree(job_dir, ignore_errors=True)
        return {"status": "error", "message": "Mixing failed"}

    # 8. UPLOAD
    print(f"[{job_id}] Uploading...")
    import boto3
    r2 = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT_URL"],
                      aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                      region_name="auto", config=Config(signature_version="s3v4"))
    
    key = f"dubbed/{job_id}.mp4"
    r2.upload_file(final_video, os.environ["R2_BUCKET_NAME"], key)
    url = r2.generate_presigned_url("get_object", Params={"Bucket": os.environ["R2_BUCKET_NAME"], "Key": key}, ExpiresIn=3600)
    
    print(f"[{job_id}] Done! URL: {url}")
    shutil.rmtree(job_dir, ignore_errors=True)
    return {"status": "success", "video_url": url}
