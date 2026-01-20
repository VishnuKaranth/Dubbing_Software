import streamlit as st
import requests
import time
import os
import yt_dlp
import boto3
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Constants ---
BACKEND_URL = os.environ.get("MODAL_BACKEND_URL")
if not BACKEND_URL:
    raise ValueError("MODAL_BACKEND_URL not found in .env file. Please set it before running.")

# R2 Configuration
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_ENDPOINT = os.getenv("R2_ENDPOINT_URL")
R2_BUCKET = os.getenv("R2_BUCKET_NAME")

st.set_page_config(
    page_title="AI Voice Dubbing Studio",
    page_icon="🎙️",
    layout="wide"
)

def get_r2_client():
    """Initialize R2 client"""
    return boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name='auto'
    )

def download_video_locally(youtube_url, progress_placeholder):
    progress_placeholder.info("⏳ Downloading video locally...")

    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)

    video_path = os.path.join(download_dir, "video.mp4")

    ydl_opts = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": video_path,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        },
        "quiet": False,
        "no_warnings": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])

        if not os.path.exists(video_path):
            raise Exception("Download failed")

        size = os.path.getsize(video_path)
        if size < 1024 * 100:
            raise Exception("Downloaded file too small")

        progress_placeholder.success(
            f"✅ Downloaded ({size / 1024 / 1024:.1f} MB)"
        )
        return video_path

    except Exception as e:
        progress_placeholder.error(f"❌ Download failed: {e}")
        return None

def upload_to_r2(video_path, job_id, progress_placeholder):
    """Upload video to Cloudflare R2"""
    progress_placeholder.info("⏳ Uploading to Cloudflare R2...")

    try:
        file_size = os.path.getsize(video_path)
        progress_placeholder.info(f"📦 File size: {file_size / 1024 / 1024:.1f} MB")

        # Initialize R2 client
        r2 = get_r2_client()

        # Upload file
        object_key = f"temp/{job_id}/video.mp4"
        
        with open(video_path, 'rb') as f:
            r2.upload_fileobj(
                f,
                R2_BUCKET,
                object_key,
                ExtraArgs={
                    'ContentType': 'video/mp4',
                    'Metadata': {
                        'job_id': job_id,
                        'upload_time': str(int(time.time()))
                    }
                }
            )

        # Generate presigned URL (valid for 24 hours)
        url = r2.generate_presigned_url(
            'get_object',
            Params={'Bucket': R2_BUCKET, 'Key': object_key},
            ExpiresIn=86400  # 24 hours
        )

        progress_placeholder.success("✅ Upload complete!")
        return url, object_key

    except Exception as e:
        progress_placeholder.error(f"❌ Upload error: {e}")
        return None, None

def main():
    if "client_id" not in st.session_state:
        st.session_state.client_id = str(uuid.uuid4())

    st.title("🎙️ AI Voice Dubbing Studio")
    st.markdown("""
    **Hybrid Architecture**  
    Local Download → R2 Storage → Modal GPU Processing → Dubbed Video  

    *Supports: English, Hindi, Kannada, Telugu, Tamil, Malayalam.*
    """)

    # Check R2 credentials
    if not all([R2_ACCESS_KEY, R2_SECRET_KEY, R2_ENDPOINT, R2_BUCKET]):
        st.error("❌ R2 credentials not configured. Please set up your .env file.")
        st.info("Copy .env.example to .env and fill in your Cloudflare R2 credentials.")
        return

    # Sidebar
    st.sidebar.header("Configuration")
    target_lang = st.sidebar.selectbox(
        "Target Language",
        options=["hi", "kn", "te", "ta", "ml", "mr", "en", "es", "fr"],
        format_func=lambda x: {
            "hi": "Hindi (हिंदी)",
            "kn": "Kannada (ಕನ್ನಡ)",
            "te": "Telugu (తెలుగు)",
            "ta": "Tamil (தமிழ்)",
            "ml": "Malayalam (മലയാളം)",
            "mr": "Marathi (मराठी)",
            "en": "English",
            "es": "Spanish",
            "fr": "French"
        }.get(x, x)
    )

    # Tabs for Input Source
    tab1, tab2 = st.tabs(["📺 YouTube URL", "📁 Upload File"])
    
    youtube_url = None
    uploaded_file = None
    
    with tab1:
        youtube_url = st.text_input(
            "YouTube Video URL",
            placeholder="https://www.youtube.com/watch?v=..."
        )

    with tab2:
        uploaded_file = st.file_uploader("Upload Video (MP4/MOV/AVI)", type=["mp4", "mov", "avi"])

    if st.button("🚀 Dub Video", type="primary"):
        status_container = st.empty()
        progress_bar = st.progress(0)

        job_id = f"job_{int(time.time())}"
        video_path = None

        # Step 1: Get Video (Download or Save Upload)
        progress_bar.progress(10)
        
        if uploaded_file is not None:
            # Handle Manual Upload
            status_container.info("Processing uploaded file...")
            download_dir = os.path.join(os.getcwd(), "downloads")
            os.makedirs(download_dir, exist_ok=True)
            video_path = os.path.join(download_dir, f"{job_id}.mp4")
            with open(video_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
        elif youtube_url:
            # Handle YouTube Download
            video_path = download_video_locally(youtube_url, status_container)
        else:
            st.warning("Please enter a YouTube URL or Upload a File.")
            return

        if not video_path:
            return

        # Step 2: Upload to R2
        progress_bar.progress(30)
        r2_url, object_key = upload_to_r2(video_path, job_id, status_container)
        if not r2_url:
            return

        # Step 3: Process on Modal
        progress_bar.progress(50)
        status_container.info(
            "⏳ Processing on Modal GPU (Diarization, Translation, Voice Cloning)..."
        )

        try:
            payload = {
                "video_url": r2_url,
                "target_lang": target_lang,
                "job_id": job_id,
                "client_id": st.session_state.client_id
            }

            start_time = time.time()
            response = requests.post(BACKEND_URL, json=payload, timeout=3600)

            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    progress_bar.progress(100)
                    status_container.success(
                        f"✅ Dubbing Complete! (Took {int(time.time() - start_time)}s)"
                    )
                    st.write("### 🎬 Result")
                    
                    if result.get("video_url"):
                        st.video(result["video_url"])
                        st.success(f"Dubbing complete! Video duration: {int(time.time() - start_time)}s")
                    else:
                        st.json(result)
                    
                    # Cleanup: Delete source video from R2
                    try:
                        r2 = get_r2_client()
                        r2.delete_object(Bucket=R2_BUCKET, Key=object_key)
                        st.info("🗑️ Temporary files cleaned up from R2")
                    except:
                        pass
                else:
                    status_container.error(f"❌ Backend Error: {result.get('message')}")
                    st.json(result)
            else:
                status_container.error(f"❌ HTTP Error: {response.status_code}")
                st.write(response.text)

        except requests.exceptions.Timeout:
            status_container.error("⚠️ Request Timed Out")
        except Exception as e:
            status_container.error(f"❌ Error: {e}")

        # Cleanup local file
        try:
            os.remove(video_path)
        except:
            pass


if __name__ == "__main__":
    main()
