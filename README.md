# 🎙️ AI Video Dubbing (Zero-Cost Serverless Architecture)

A robust, serverless AI application that automatically dubs videos into multiple languages while preserving background music and speaker identity.

![Status](https://img.shields.io/badge/Status-Production%20Ready-success)
![Modal](https://img.shields.io/badge/Deployed%20on-Modal-black)
![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-red)

## ✨ Features

- **🗣️ Voice Cloning (XTTS)**: Clones the speaker's voice for major languages (Hindi, English, Spanish, etc.).
- **🇮🇳 High-Quality Indian Voices**: Uses **Edge TTS** + **Gender Detection** for natural-sounding Kannada, Telugu, Malayalam, and Tamil dubbing.
- **🎵 Music Preservation**: Separates vocals from background music (`Demucs`), dubs the vocals, and mixes them back together.
- **⚡ GPU Accelerated**: Runs on NVIDIA A10G GPUs via Modal for fast processing (WhisperX Alignment & Diarization).
- **🔒 Secure & Scalable**:
  - **Rate Limiting**: Enforces 3 requests/day per user.
  - **Auto-Cleanup**: Automatically wipes temporary files to prevent storage exhaustion.
  - **Input Validation**: Sanitized Job IDs and URL checks.

## 🏗️ Architecture

1.  **Frontend**: Streamlit (Lightweight UI).
2.  **Backend**: Modal (Serverless GPU Functions).
3.  **Storage**: Cloudflare R2 (Video Hosting).
4.  **AI Pipeline**:
    *   `Demucs` (Source Separation)
    *   `WhisperX` (Transcription & Diarization)
    *   `Deep Translator` (Translation)
    *   `Coqui XTTS v2` / `Edge TTS` (Synthesis)
    *   `FFmpeg` (Mixing)

## 🚀 Setup & Installation

### 1. Prerequisites
- Python 3.10+
- [Modal](https://modal.com) Account
- Cloudflare R2 Bucket (or S3 compatible)

### 2. Environment Variables
Create a `.env` file in the root directory:

```ini
# Cloudflare R2 Credentials
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_ENDPOINT_URL=https://your_account_id.r2.cloudflarestorage.com
R2_BUCKET_NAME=your_bucket_name

# Modal Backend URL (After deployment)
MODAL_BACKEND_URL=https://your-modal-app-url.modal.run
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Deploy Backend (Modal)
```bash
cd build
modal deploy modal_backend.py
```
*Wait for the deployment to finish. Copy the `web function` URL and paste it into `.env` (MODAL_BACKEND_URL).*

### 5. Run Frontend
```bash
streamlit run build/app.py
```

## 📂 Project Structure

```
├── build/
│   ├── modal_backend.py   # The monolithic AI backend (Modal)
│   ├── app.py             # Streamlit frontend
├── .env                   # Secrets (NOT committed)
├── .gitignore             # Security rules
├── requirements.txt       # Python dependencies
└── README.md              # Docs
```

## 🛡️ Security

- **Inputs Sanitized**: `job_id` and `video_url` are validated to prevent traversal/SSRF.
- **Secrets Managed**: Uses environment variables and Modal Secrets.
- **Cleanup**: Ephemeral storage is wiped after every job.

---
*Created by Vishnu Karanth*
