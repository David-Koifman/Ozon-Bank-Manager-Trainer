import streamlit as st
import requests
import base64
import io
import os
from datetime import datetime
from audio_recorder_streamlit import audio_recorder
from pydub import AudioSegment
from pydub.playback import play
import tempfile

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api")

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "is_recording" not in st.session_state:
    st.session_state.is_recording = False
if "recorded_audio" not in st.session_state:
    st.session_state.recorded_audio = None
if "backend_audio" not in st.session_state:
    st.session_state.backend_audio = None
if "transcription" not in st.session_state:
    st.session_state.transcription = None
if "response_text" not in st.session_state:
    st.session_state.response_text = None
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []

st.set_page_config(
    page_title="Operator Voice Trainer",
    page_icon="🎤",
    layout="wide"
)

# Add custom CSS for messenger-style chat
st.markdown("""
    <style>
    .chat-container {
        max-height: 600px;
        overflow-y: auto;
        padding: 20px;
        background-color: #f0f2f6;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .message {
        display: flex;
        margin-bottom: 15px;
        animation: fadeIn 0.3s;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .message-user {
        justify-content: flex-end;
    }
    .message-assistant {
        justify-content: flex-start;
    }
    .message-bubble {
        max-width: 70%;
        padding: 12px 16px;
        border-radius: 18px;
        word-wrap: break-word;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    .message-user .message-bubble {
        background-color: #007bff;
        color: white;
        border-bottom-right-radius: 4px;
    }
    .message-assistant .message-bubble {
        background-color: white;
        color: #333;
        border-bottom-left-radius: 4px;
    }
    .message-time {
        font-size: 0.75rem;
        color: #666;
        margin-top: 4px;
        padding: 0 4px;
    }
    .message-user .message-time {
        text-align: right;
    }
    .message-assistant .message-time {
        text-align: left;
    }
    .audio-player-container {
        margin-top: 8px;
        padding: 8px;
        background-color: rgba(0,0,0,0.05);
        border-radius: 8px;
    }
    .stButton>button {
        border-radius: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎤 Operator Voice Trainer")

# Info banner about localhost access for microphone
st.info("ℹ️ **Note:** For microphone access to work, please access this app via `http://localhost:8501` (not via IP address)")

st.markdown("---")

# Sidebar for session management
with st.sidebar:
    st.header("Session Management")
    
    if st.session_state.session_id:
        st.success(f"Session Active")
        st.info(f"Session ID: `{st.session_state.session_id[:8]}...`")
        
        if st.button("End Training Session", type="secondary", use_container_width=True):
            try:
                response = requests.post(
                    f"{API_BASE_URL}/end-training",
                    json={"session_id": st.session_state.session_id},
                    timeout=600,
                )
                if response.status_code == 200:
                    st.session_state.session_id = None
                    st.session_state.recorded_audio = None
                    st.session_state.backend_audio = None
                    st.session_state.transcription = None
                    st.session_state.response_text = None
                    st.session_state.conversation_history = []
                    st.success("Session ended successfully!")
                    st.rerun()
                else:
                    st.error(f"Error ending session: {response.text}")
            except Exception as e:
                st.error(f"Error: {str(e)}")
    else:
        st.info("No active session")
        
        scenario = st.selectbox(
            "Select Scenario",
            options=["default", "customer_service", "technical_support", "sales"],
            help="Choose a training scenario"
        )
        
        if st.button("Start Training Session", type="primary", use_container_width=True):
            try:
                response = requests.post(
                    f"{API_BASE_URL}/start-training",
                    json={"scenario": scenario},
                    timeout=30
                )
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.session_id = data.get("session_id")
                    st.session_state.conversation_history = []
                    st.success("Training session started!")
                    st.rerun()
                else:
                    st.error(f"Error starting session: {response.text}")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# Helper function to render message using Streamlit components
def render_message_streamlit(message_type, text, timestamp, audio_bytes=None, message_id=None):
    """Render a single message in messenger style using Streamlit"""
    time_str = timestamp.strftime("%H:%M") if isinstance(timestamp, datetime) else str(timestamp)
    
    if message_type == "user":
        icon = "👤"
        bubble_color = "#007bff"
        text_color = "white"
    else:
        icon = "🤖"
        bubble_color = "#ffffff"
        text_color = "#333333"
    
    # Create columns for alignment
    if message_type == "user":
        col1, col2 = st.columns([2, 1])
        with col2:
            st.markdown(f"""
                <div style="
                    background-color: {bubble_color};
                    color: {text_color};
                    padding: 12px 16px;
                    border-radius: 18px;
                    border-bottom-right-radius: 4px;
                    margin-bottom: 10px;
                    box-shadow: 0 1px 2px rgba(0,0,0,0.1);
                    word-wrap: break-word;
                ">
                    <strong>{icon}</strong> {text}
                    <div style="font-size: 0.7rem; margin-top: 6px; opacity: 0.8;">{time_str}</div>
                </div>
            """, unsafe_allow_html=True)
    else:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"""
                <div style="
                    background-color: {bubble_color};
                    color: {text_color};
                    padding: 12px 16px;
                    border-radius: 18px;
                    border-bottom-left-radius: 4px;
                    margin-bottom: 10px;
                    box-shadow: 0 1px 2px rgba(0,0,0,0.1);
                    word-wrap: break-word;
                ">
                    <strong>{icon}</strong> {text}
                    <div style="font-size: 0.7rem; margin-top: 6px; opacity: 0.7;">{time_str}</div>
                </div>
            """, unsafe_allow_html=True)
            # Add audio player if available
            if audio_bytes and message_id is not None:
                # Store audio in session state with unique key
                audio_key = f"audio_{message_id}"
                if audio_key not in st.session_state:
                    st.session_state[audio_key] = audio_bytes
                st.audio(st.session_state[audio_key], format="audio/wav")

# Main content area
if not st.session_state.session_id:
    st.info("Use the sidebar on the left to start a new training session.")
else:
    # Dialog section - Messenger style
    st.header("💬 Conversation")
    
    # Display conversation history
    if st.session_state.conversation_history:
        # Create a scrollable container with background
        chat_container = st.container()
        with chat_container:
            st.markdown("""
                <div style="
                    padding: 20px;
                    background-color: #f0f2f6;
                    border-radius: 10px;
                    margin-bottom: 20px;
                ">
            """, unsafe_allow_html=True)
            
            for idx, msg in enumerate(st.session_state.conversation_history):
                render_message_streamlit(
                    msg["type"],
                    msg["text"],
                    msg["timestamp"],
                    msg.get("audio_bytes"),
                    message_id=idx
                )
            
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("💡 Start a conversation by recording and sending your voice message.")
    
    st.markdown("---")
    
    # Recording section
    st.header("🎙️ Audio Recording")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Record Your Voice")
        
        # Audio recorder component
        audio_bytes = audio_recorder(
            text="Click to record",
            recording_color="#e74c3c",
            neutral_color="#6c757d",
            icon_name="microphone",
            icon_size="2x",
            pause_threshold=3.0
        )
        
        if audio_bytes:
            st.session_state.recorded_audio = audio_bytes
            st.audio(audio_bytes, format="audio/wav")
            st.success("✅ Audio recorded successfully!")
    
    with col2:
        st.subheader("Recording Status")
        if st.session_state.recorded_audio:
            st.success("✅ Audio Ready")
            audio_size = len(st.session_state.recorded_audio)
            st.metric("Audio Size", f"{audio_size / 1024:.2f} KB")
        else:
            st.info("No audio recorded yet")
    
    st.markdown("---")
    
    # Send audio section
    st.header("📤 Send Audio to Backend")
    
    if st.session_state.recorded_audio:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("🚀 Send Audio", type="primary", use_container_width=True):
                with st.spinner("Processing audio..."):
                    try:
                        # Validate audio data
                        if not st.session_state.recorded_audio:
                            st.error("No audio data to send. Please record audio first.")
                            st.stop()
                        
                        if not st.session_state.session_id:
                            st.error("No active session. Please start a training session first.")
                            st.stop()
                        
                        # Validate audio size (at least 1KB, max 10MB)
                        audio_size = len(st.session_state.recorded_audio)
                        if audio_size < 1024:
                            st.error("Audio file is too small. Please record longer audio.")
                            st.stop()
                        if audio_size > 10 * 1024 * 1024:
                            st.error("Audio file is too large (max 10MB). Please record shorter audio.")
                            st.stop()
                        
                        # Convert audio to base64
                        try:
                            audio_base64 = base64.b64encode(st.session_state.recorded_audio).decode('utf-8')
                        except Exception as e:
                            st.error(f"Error encoding audio: {str(e)}")
                            st.stop()
                        
                        # Send to backend
                        try:
                            response = requests.post(
                                f"{API_BASE_URL}/audio-input",
                                json={
                                    "audio": audio_base64,
                                    "session_id": st.session_state.session_id
                                },
                                timeout=600  # Longer timeout for processing
                            )
                        except requests.exceptions.Timeout:
                            st.error("Request timed out. The audio processing is taking too long.")
                            st.stop()
                        except requests.exceptions.ConnectionError:
                            st.error(f"Connection error. Cannot reach backend at {API_BASE_URL}")
                            st.stop()
                        
                        # Check response status
                        if response.status_code == 200:
                            try:
                                data = response.json()
                            except ValueError:
                                st.error("Invalid JSON response from backend")
                                st.stop()
                            
                            # Validate response structure
                            if not isinstance(data, dict):
                                st.error("Invalid response format from backend")
                                st.stop()
                            
                            # Store response data
                            transcription = data.get("transcription", "")
                            response_text = data.get("response_text", "")
                            backend_audio_base64 = data.get("audio", "")
                            
                            # Store in session state for backward compatibility
                            st.session_state.transcription = transcription
                            st.session_state.response_text = response_text
                            
                            # Decode backend audio if present
                            backend_audio_bytes = None
                            if backend_audio_base64:
                                try:
                                    backend_audio_bytes = base64.b64decode(backend_audio_base64)
                                    if len(backend_audio_bytes) > 0:
                                        st.session_state.backend_audio = backend_audio_bytes
                                    else:
                                        st.warning("Received empty audio response from backend")
                                        backend_audio_bytes = None
                                except Exception as e:
                                    st.warning(f"Could not decode audio response: {str(e)}")
                                    backend_audio_bytes = None
                            
                            # Add messages to conversation history
                            current_time = datetime.now()
                            
                            # Add user message (transcription)
                            if transcription:
                                st.session_state.conversation_history.append({
                                    "type": "user",
                                    "text": transcription,
                                    "timestamp": current_time,
                                    "audio_bytes": None
                                })
                            
                            # Add assistant message (response text and audio)
                            if response_text:
                                st.session_state.conversation_history.append({
                                    "type": "assistant",
                                    "text": response_text,
                                    "timestamp": current_time,
                                    "audio_bytes": backend_audio_bytes
                                })
                            
                            st.success("✅ Audio processed successfully!")
                            st.rerun()
                        else:
                            # Try to get error message from response
                            try:
                                error_data = response.json()
                                error_msg = error_data.get("detail", error_data.get("message", response.text))
                            except:
                                error_msg = response.text
                            st.error(f"Error processing audio (Status {response.status_code}): {error_msg}")
                    except Exception as e:
                        st.error(f"Unexpected error: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
        
        with col2:
            if st.button("🔄 Clear Recording", use_container_width=True):
                st.session_state.recorded_audio = None
                st.rerun()
    else:
        st.info("Please record audio first before sending to backend.")
    
    st.markdown("---")
    
    # Optional: Show detailed response section (collapsible)
    with st.expander("📋 View Detailed Response", expanded=False):
        if st.session_state.transcription or st.session_state.response_text:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📝 Transcription")
                if st.session_state.transcription:
                    st.info(st.session_state.transcription)
                else:
                    st.warning("No transcription available")
            
            with col2:
                st.subheader("💬 LLM Response")
                if st.session_state.response_text:
                    st.info(st.session_state.response_text)
                else:
                    st.warning("No response text available")
        
        if st.session_state.backend_audio:
            st.subheader("🎵 Audio Response")
            st.audio(st.session_state.backend_audio, format="audio/wav")
            
            # Download button
            audio_download = st.download_button(
                label="📥 Download Audio Response",
                data=st.session_state.backend_audio,
                file_name="backend_response.wav",
                mime="audio/wav",
                use_container_width=True
            )
        else:
            st.info("No audio response available yet. Send audio to backend to receive a response.")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #6c757d;'>
        <small>Operator Voice Trainer - Powered by Streamlit</small>
    </div>
    """,
    unsafe_allow_html=True
)
