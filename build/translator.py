import os
import subprocess
import whisper
from deep_translator import GoogleTranslator
from gtts import gTTS
import re
import textwrap
import imageio_ffmpeg as ffmpeg
from terms import terms_to_preserve
from dataclasses import dataclass
from typing import Optional, Dict
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('video_translator.log'),
        logging.StreamHandler()
    ]
)

@dataclass
class TranslationResult:
    video_title: str
    original_text: str
    translated_text: str
    output_video_path: str
    translated_text_path: str
    translated_audio_path: str
    success: bool
    error_message: Optional[str] = None

class VideoTranslator:
    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.ffmpeg_path = ffmpeg.get_ffmpeg_exe()
        
        # Define directories with absolute paths
        self.directories = {
            'input_audio': os.path.join(self.base_dir, 'input_audio'),
            'translated_audio': os.path.join(self.base_dir, 'T_audio'),
            'translated_text': os.path.join(self.base_dir, 'translated_text'),
            'video': os.path.join(self.base_dir, 'video'),
            'output_video': os.path.join(self.base_dir, 'output_video')
        }
        self._create_directories()
        logging.info(f"Initialized VideoTranslator with base directory: {self.base_dir}")

    def _create_directories(self):
        for dir_name, dir_path in self.directories.items():
            try:
                os.makedirs(dir_path, exist_ok=True)
                logging.info(f"Created/verified directory: {dir_path}")
            except Exception as e:
                logging.error(f"Failed to create directory {dir_path}: {str(e)}")
                raise

    def _verify_file_exists(self, file_path: str, description: str) -> bool:
        if not os.path.exists(file_path):
            logging.error(f"{description} not found at: {file_path}")
            return False
        logging.info(f"{description} found at: {file_path}")
        return True

    def _sanitize_filename(self, filename: str) -> str:
        # Remove or replace invalid characters
        filename = re.sub(r'[\\/*?:"<>|]', '', filename)
        # Replace spaces with underscores
        filename = re.sub(r'\s+', '_', filename)
        return filename

    def get_video_title(self, youtube_url: str) -> str:
        try:
            result = subprocess.run(
                ['yt-dlp', '--get-title', youtube_url],
                capture_output=True,
                text=True,
                check=True
            )
            title = result.stdout.strip()
            sanitized_title = self._sanitize_filename(title)
            logging.info(f"Retrieved video title: {sanitized_title}")
            return sanitized_title
        except Exception as e:
            logging.error(f"Failed to get video title: {str(e)}")
            return "untitled_video"

    def download_audio_and_video(self, youtube_url: str, audio_filename: str, video_filename: str) -> bool:
        try:
            logging.info(f"Downloading from URL: {youtube_url}")
            logging.info(f"Audio output path: {audio_filename}")
            logging.info(f"Video output path: {video_filename}")

            # Download audio
            audio_command = [
                'yt-dlp',
                '--extract-audio',
                '--audio-format', 'mp3',
                youtube_url,
                '-o', audio_filename
            ]
            
            # Download video
            video_command = [
                'yt-dlp',
                youtube_url,
                '-o', video_filename
            ]

            # Execute commands
            subprocess.run(audio_command, check=True, capture_output=True, text=True)
            subprocess.run(video_command, check=True, capture_output=True, text=True)

            # Verify files were created
            audio_exists = self._verify_file_exists(audio_filename, "Audio file")
            video_exists = self._verify_file_exists(video_filename, "Video file")

            return audio_exists and video_exists

        except subprocess.CalledProcessError as e:
            logging.error(f"Download failed with error: {e.stderr}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error during download: {str(e)}")
            return False

    def transcribe_audio(self, file_path: str) -> str:
        try:
            if not self._verify_file_exists(file_path, "Audio file for transcription"):
                raise FileNotFoundError(f"Audio file not found: {file_path}")

            logging.info(f"Loading Whisper model...")
            model = whisper.load_model("base")
            
            logging.info(f"Transcribing audio: {file_path}")
            result = model.transcribe(file_path)
            
            logging.info("Transcription completed successfully")
            return result['text']

        except Exception as e:
            logging.error(f"Transcription failed: {str(e)}")
            raise

    def translate_text(self, text: str, language: str, terms: list) -> str:
        try:
            logging.info(f"Translating text to {language}")
            text_with_placeholders, placeholders = self._replace_with_placeholders(text, terms, language)
            text_chunks = textwrap.wrap(text_with_placeholders, width=5000, break_long_words=False, replace_whitespace=False)
            
            translated_chunks = []
            for i, chunk in enumerate(text_chunks):
                logging.info(f"Translating chunk {i+1}/{len(text_chunks)}")
                translation_chunk = GoogleTranslator(source='auto', target=language).translate(chunk)
                translated_chunks.append(translation_chunk)

            translated_text = " ".join(translated_chunks)
            for placeholder, original_term in placeholders.items():
                translated_text = re.sub(placeholder, original_term, translated_text, flags=re.IGNORECASE)

            logging.info("Translation completed successfully")
            return translated_text

        except Exception as e:
            logging.error(f"Translation failed: {str(e)}")
            raise

    def _replace_with_placeholders(self, text: str, terms: list, lang: str) -> tuple:
        placeholders = {}
        modified_text = text
        for i, term in enumerate(terms):
            if lang in ['hi', 'ta', 'ml']:
                placeholder = f"_term{i}_"
            elif lang == 'te':
                placeholder = f"___term{i}___"
            else:
                placeholder = f"__term{i}__"
            pattern = rf'\b{term}\b'
            modified_text = re.sub(pattern, placeholder, modified_text, flags=re.IGNORECASE)
            placeholders[placeholder] = term
        return modified_text, placeholders

    def text_to_speech(self, text: str, lang: str, audio_filename: str) -> bool:
        try:
            logging.info(f"Generating speech in {lang}")
            tts = gTTS(text=text, lang=lang)
            tts.save(audio_filename)
            logging.info(f"Speech generated successfully: {audio_filename}")
            return True
        except Exception as e:
            logging.error(f"Text-to-speech failed: {str(e)}")
            return False

    def get_duration(self, file_path: str) -> Optional[float]:
        try:
            result = subprocess.run(
                [self.ffmpeg_path, '-i', file_path],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True
            )
            for line in result.stderr.split('\n'):
                if "Duration" in line:
                    time_str = line.split("Duration: ")[1].split(",")[0]
                    h, m, s = map(float, time_str.split(':'))
                    duration = h * 3600 + m * 60 + s
                    logging.info(f"Duration of {file_path}: {duration} seconds")
                    return duration
            return None
        except Exception as e:
            logging.error(f"Failed to get duration: {str(e)}")
            return None

    def adjust_audio_speed(self, audio_path: str, speed_factor: float, output_audio_path: str) -> bool:
        try:
            logging.info(f"Adjusting audio speed by factor: {speed_factor}")
            subprocess.run([
                self.ffmpeg_path, '-i', audio_path,
                '-filter:a', f"atempo={speed_factor}",
                '-vn', output_audio_path
            ], check=True)
            logging.info("Audio speed adjusted successfully")
            return True
        except Exception as e:
            logging.error(f"Failed to adjust audio speed: {str(e)}")
            return False

    def replace_audio_in_video(self, video_path: str, audio_path: str, output_video_path: str) -> bool:
        try:
            logging.info("Replacing audio in video")
            subprocess.run([
                self.ffmpeg_path, '-i', video_path,
                '-i', audio_path,
                '-c:v', 'copy',
                '-map', '0:v:0',
                '-map', '1:a:0',
                output_video_path
            ], check=True)
            logging.info("Audio replaced successfully")
            return True
        except Exception as e:
            logging.error(f"Failed to replace audio: {str(e)}")
            return False

    def process_video(self, youtube_url: str, target_language: str) -> TranslationResult:
        try:
            # Get video title
            video_title = self.get_video_title(youtube_url)
            logging.info(f"Processing video: {video_title}")
            
            # Setup file paths
            audio_filename = os.path.join(self.directories['input_audio'], f'{video_title}.mp3')
            video_filename = os.path.join(self.directories['video'], f'{video_title}.webm')
            translated_audio_path = os.path.join(self.directories['translated_audio'], f'{video_title}_{target_language}.mp3')
            adjusted_audio_path = os.path.join(self.directories['translated_audio'], f'{video_title}_{target_language}_adjusted.mp3')
            output_video_path = os.path.join(self.directories['output_video'], f'{video_title}_{target_language}.webm')
            translated_text_path = os.path.join(self.directories['translated_text'], f'{video_title}_{target_language}.txt')

            # Download video and audio
            if not self.download_audio_and_video(youtube_url, audio_filename, video_filename):
                return TranslationResult(video_title, "", "", "", "", "", False, "Failed to download video")

            # Transcribe audio
            transcribed_text = self.transcribe_audio(audio_filename)

            # Translate text
            translated_text = self.translate_text(transcribed_text, target_language, terms_to_preserve)

            # Save translated text
            with open(translated_text_path, 'w', encoding='utf-8') as f:
                f.write(translated_text)

            # Generate speech from translated text
            if not self.text_to_speech(translated_text, target_language, translated_audio_path):
                return TranslationResult(video_title, transcribed_text, translated_text, "", translated_text_path, "", False, "Failed to generate speech")

            # Process audio and video
            video_duration = self.get_duration(video_filename)
            audio_duration = self.get_duration(translated_audio_path)
            
            if not video_duration or not audio_duration:
                return TranslationResult(video_title, transcribed_text, translated_text, "", translated_text_path, translated_audio_path, False, "Failed to get media durations")

            speed_factor = audio_duration / video_duration

            if not self.adjust_audio_speed(translated_audio_path, speed_factor, adjusted_audio_path):
                return TranslationResult(video_title, transcribed_text, translated_text, "", translated_text_path, translated_audio_path, False, "Failed to adjust audio speed")

            if not self.replace_audio_in_video(video_filename, adjusted_audio_path, output_video_path):
                return TranslationResult(video_title, transcribed_text, translated_text, "", translated_text_path, adjusted_audio_path, False, "Failed to create final video")

            return TranslationResult(
                video_title=video_title,
                original_text=transcribed_text,
                translated_text=translated_text,
                output_video_path=output_video_path,
                translated_text_path=translated_text_path,
                translated_audio_path=adjusted_audio_path,
                success=True
            )

        except Exception as e:
            error_msg = f"Error processing video: {str(e)}"
            logging.error(error_msg)
            return TranslationResult("", "", "", "", "", "", False, error_msg)