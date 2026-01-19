# 🎥 YouTube Video Dubbing Tool

A specialized automated dubbing pipeline designed to translate and dub educational or technical YouTube videos into multiple Indian languages. This tool preserves technical terminology while translating the context, making it ideal for computer science and engineering tutorials.

---

## 📖 Project Overview

This application automates the complex process of video dubbing. It takes a YouTube URL as input, transcribes the audio, translates the content while intelligently preserving technical jargon (like *stack*, *queue*, *algorithm*), generates voice-overs, and synchronizes the new audio with the original video.

---

## ✨ Key Features

* **Automated Pipeline**
  Seamlessly handles downloading, transcription, translation, and dubbing.

* **Language Support**
  Translates content into:

  * Hindi
  * Tamil
  * Telugu
  * Malayalam
  * Kannada

* **Technical Term Preservation**
  Uses a custom dictionary to ensure technical terms (e.g., *binary tree*, *hash map*) remain in English for clarity.

* **Audio-Video Synchronization**
  Automatically adjusts the speed of the translated audio to match the original video duration.

* **Interactive UI**
  Built with Streamlit for an easy-to-use web interface.

* **Downloadable Assets**
  Users can download:

  * Final dubbed video
  * Translated transcript
  * Generated audio file

---

## 🛠️ Tech Stack

| Component        | Technology                             |
| ---------------- | -------------------------------------- |
| Language         | Python 3.10                            |
| Frontend         | Streamlit                              |
| Transcription    | OpenAI Whisper                         |
| Translation      | Deep Translator (Google Translate API) |
| Text-to-Speech   | gTTS (Google Text-to-Speech)           |
| Media Processing | FFmpeg, imageio-ffmpeg, yt-dlp         |

---

## 📂 Project Structure

```bash
├── build/
│   ├── app.py              # Main Streamlit application entry point
│   ├── translator.py       # Core logic (Download → Transcribe → Translate → Sync)
│   └── terms.py            # Dictionary of technical terms to preserve
├── requirements.txt        # Python dependencies
├── runtime.txt             # Runtime configuration
└── LICENSE                 # MIT License
```

---

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd Dubbing_Software
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate it:

**Windows**

```bash
venv\Scripts\activate
```

**macOS / Linux**

```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> ⚠️ This project uses `openai-whisper`, which requires **FFmpeg** to be installed on your system.

---

## 💻 Usage

### Run the Application

```bash
streamlit run build/app.py
```

### Using the Interface

1. Select your target language from the sidebar (e.g., Hindi, Tamil).

2. Paste a valid YouTube URL into the input field.

3. Click **Process Video**.

4. Wait for the pipeline to finish:

   * Downloading Video
   * Transcribing Audio
   * Translating Text
   * Generating Speech
   * Creating Final Video

5. View & Download:

   * Watch original vs translated text side-by-side
   * Preview the dubbed video directly in the browser
   * Download the artifacts (Video, Audio, Text) for offline use

---

## ⚙️ How It Works (Pipeline)

1. **Ingestion**
   Uses `yt-dlp` to download the video and extract audio from the provided URL.

2. **Transcription**
   OpenAI Whisper converts the audio track into text with high accuracy.

3. **Smart Translation**

   * Technical keywords are identified using `terms.py`
   * Keywords are replaced with placeholders
   * Remaining text is translated via Google Translator
   * Keywords are re-inserted to maintain technical accuracy

4. **Voice Generation**
   `gTTS` converts the translated text into speech in the target language.

5. **Synchronization**

   * Generated audio duration is compared with the original video
   * FFmpeg dynamically adjusts audio speed to ensure perfect sync

6. **Merging**
   The new audio track is overlaid onto the original video.

---

## 📄 License

This project is licensed under the **MIT License** — see the `LICENSE` file for details.

---

## 👨‍💻 Developed By

**[Your Name]**
Final Year Project
