import streamlit as st
import os
from translator import VideoTranslator, TranslationResult

def initialize_translator():
    if 'translator' not in st.session_state:
        st.session_state.translator = VideoTranslator()
    return st.session_state.translator

def create_language_mapping():
    return {
        'hi': 'Hindi',
        'ta': 'Tamil',
        'te': 'Telugu',
        'ml': 'Malayalam',
        'kn': 'Kannada'
    }

def display_results(result: TranslationResult):
    if result.success:
        # Display transcribed and translated text
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Original Transcription")
            st.text_area("", result.original_text, height=200)
        with col2:
            st.subheader("Translated Text")
            st.text_area("", result.translated_text, height=200)

        # Video player
        st.subheader("Translated Video")
        video_file = open(result.output_video_path, 'rb')
        video_bytes = video_file.read()
        st.video(video_bytes)

        # Download buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            with open(result.output_video_path, 'rb') as f:
                st.download_button(
                    label="Download Translated Video",
                    data=f.read(),
                    file_name=f'{result.video_title}_translated.webm',
                    mime='video/webm'
                )
        with col2:
            with open(result.translated_text_path, 'rb') as f:
                st.download_button(
                    label="Download Translated Text",
                    data=f.read(),
                    file_name=f'{result.video_title}_translated.txt',
                    mime='text/plain'
                )
        with col3:
            with open(result.translated_audio_path, 'rb') as f:
                st.download_button(
                    label="Download Translated Audio",
                    data=f.read(),
                    file_name=f'{result.video_title}_translated.mp3',
                    mime='audio/mpeg'
                )
    else:
        st.error(f"Processing failed: {result.error_message}")

def main():
    st.set_page_config(
        page_title="YouTube Video Translator",
        page_icon="🎥",
        layout="wide"
    )

    # Initialize the translator
    translator = initialize_translator()

    # Main UI
    st.title("🎥 YouTube Video Translator")
    st.write("Translate YouTube videos to different languages with subtitle generation")

    # Sidebar for language selection
    st.sidebar.header("Settings")
    language_mapping = create_language_mapping()
    target_language = st.sidebar.selectbox(
        "Select Target Language",
        options=list(language_mapping.keys()),
        format_func=lambda x: language_mapping[x]
    )

    # Main interface
    youtube_url = st.text_input("Enter YouTube URL", key="youtube_url")

    if youtube_url:
        if not youtube_url.startswith(('https://www.youtube.com', 'https://youtu.be')):
            st.error("Please enter a valid YouTube URL")
            return

        if st.button("Process Video"):
            with st.spinner("Processing video..."):
                # Create progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()

                # Process States
                states = [
                    "Downloading video...",
                    "Transcribing audio...",
                    "Translating text...",
                    "Generating speech...",
                    "Creating final video..."
                ]

                # Update progress bar during processing
                for i, state in enumerate(states):
                    status_text.text(state)
                    progress_bar.progress((i + 1) * 20)

                # Process the video
                result = translator.process_video(youtube_url, target_language)
                
                if result.success:
                    progress_bar.progress(100)
                    status_text.text("Processing complete!")
                    st.success("Video processing completed successfully!")
                    
                    # Display results
                    display_results(result)
                else:
                    status_text.text("Processing failed!")
                    st.error(f"Error: {result.error_message}")

if __name__ == "__main__":
    main()