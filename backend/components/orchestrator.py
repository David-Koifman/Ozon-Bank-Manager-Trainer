from typing import Dict, Any
import asyncio
import logging
import time
from fastapi import WebSocket
from components.utils import extract_complete_sentences
from components.dialogue_prompts import clean_reply

logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrates the flow between different components"""
    
    async def process(
        self,
        message: Dict[str, Any],
        session_id: str,
        session_manager,
        context,
        stt,
        llm,
        tts,
        database=None
    ) -> Dict[str, Any]:
        """
        Main orchestration logic following the architecture:
        1. Orchestrator -> Session Manager (parallel with STT)
        2. Orchestrator -> STT (parallel with Session Manager)
        3. Session Manager -> Context
        4. STT -> LLM
        5. Context -> LLM
        6. LLM -> TTS
        7. TTS -> Frontend
        """
        
        action = message.get("action", "")
        logger.info(f"Orchestrator: Processing action '{action}' for session {session_id}")
        
        # Handle different actions
        if action == "start_training":
            scenario = message.get("scenario", "default")
            speaker = message.get("speaker", "aidar")
            behavior_archetype = message.get("behavior_archetype", "novice")
            difficulty_level = message.get("difficulty_level", "1")
            logger.info(f"Orchestrator: Starting training session with scenario '{scenario}', speaker '{speaker}', behavior '{behavior_archetype}', difficulty '{difficulty_level}'")
            # Initialize session
            session_manager.start_session(session_id, scenario, speaker, behavior_archetype, difficulty_level)
            logger.info(f"Orchestrator: Session {session_id} started")
            return {
                "type": "session_started",
                "session_id": session_id,
                "message": "Training session started"
            }
        
        elif action == "end_training":
            logger.info(f"Orchestrator: Ending training session {session_id}")
            
            # Get all pending data from session
            pending_data = session_manager.get_pending_data(session_id)
            stt_transcriptions = pending_data["stt_transcriptions"]
            llm_responses = pending_data["llm_responses"]
            
            # Write all data to database
            if database and (stt_transcriptions or llm_responses):
                db_start = time.time()
                try:
                    await database.batch_log_session_data(
                        session_id=session_id,
                        stt_transcriptions=stt_transcriptions,
                        llm_responses=llm_responses
                    )
                    db_time = time.time() - db_start
                    logger.info(f"Orchestrator: Wrote {len(stt_transcriptions)} STT and {len(llm_responses)} LLM records to database in {db_time:.3f}s")
                except Exception as e:
                    logger.error(f"Orchestrator: Error writing session data to database: {e}", exc_info=True)
            
            # Clear pending data
            session_manager.clear_pending_data(session_id)
            
            # End session and clear context
            session_manager.end_session(session_id)
            context.clear_context(session_id)
            return {
                "type": "session_ended",
                "session_id": session_id,
                "message": "Training session ended"
            }
        
        else:
            logger.warning(f"Orchestrator: Unknown action '{action}'")
            return {
                "type": "error",
                "message": f"Unknown action: {action}"
            }
    
    async def process_streaming(
        self,
        websocket: WebSocket,
        session_id: str,
        session_info: dict,
        audio_base64: str = None,
        transcription: str = None,
        speaker: str = None,
        stt=None,
        llm=None,
        tts=None,
        context=None,
        session_manager=None,
        database=None
    ):
        """
        Process a complete user utterance in streaming mode: 
        STT -> LLM (streaming) -> TTS (streaming) -> Stream to client.
        
        Args:
            websocket: WebSocket connection
            session_id: Session ID
            session_info: Session information
            audio_base64: Base64 encoded audio (optional, if transcription is provided)
            transcription: Pre-transcribed text (optional, if provided, skips STT step)
            speaker: TTS speaker voice
            stt: STT client
            llm: LLM client
            tts: TTS client
            context: Context manager
            session_manager: Session manager (to store data for batch write)
            database: Database client
        """
        overall_start = time.time()
        try:
            # 1. Transcribe with STT (or use provided transcription)
            stt_start = time.time()
            stt_time = 0.0  # Initialize STT time
            
            if transcription is not None:
                # Use provided transcription (from streaming STT)
                logger.info("Orchestrator: Using provided transcription (streaming STT)")
                stt_time = 0.0  # No STT processing time (already done in streaming)
            elif audio_base64 is not None and stt is not None:
                # Transcribe with STT (non-streaming mode)
                logger.info("Orchestrator: Transcribing audio...")
                transcription = await stt.transcribe(audio_base64)
                stt_time = time.time() - stt_start
                logger.info(f"Orchestrator: Transcription: {transcription} (STT time: {stt_time:.3f}s)")
            else:
                raise ValueError("Either transcription or audio_base64 must be provided")
            
            # Store STT transcription in session (for batch database write on end_training)
            session_manager.add_stt_transcription(session_id, transcription)
            
            # Note: Transcription is already sent to client in WebSocket handler
            # (for streaming STT) or here (for non-streaming STT)
            # So we don't send it again to avoid duplicates
            
            # 2. Get context
            context_start = time.time()
            context_data = context.get_context(session_id, session_info)
            context_time = time.time() - context_start
            logger.info(f"Orchestrator: Context retrieved (time: {context_time:.3f}s)")
            
            # 3. Generate LLM response (streaming)
            llm_start = time.time()
            logger.info("Orchestrator: Generating LLM response (streaming)...")
            await websocket.send_json({
                "type": "status",
                "status": "responding",
                "message": "AI is responding..."
            })
            
            # Collect full response for context update
            raw_response = ""
            sentence_buffer = ""
            processed_sentences = set()
            tts_total_time = 0.0
            tts_count = 0
            extract_sentence_time_total = 0
            
            async for text_chunk in llm.generate_response_stream(
                user_input=transcription,
                context=context_data
            ):
                raw_response += text_chunk
                sentence_buffer += text_chunk
                
                # Check if we have complete sentences
                extract_sentence_start = time.time()
                complete_sentences, remaining = extract_complete_sentences(sentence_buffer)
                extract_sentence_time = time.time() - extract_sentence_start
                extract_sentence_time_total += extract_sentence_time
                
                # Process complete sentences
                for sentence in complete_sentences:
                    if sentence and sentence not in processed_sentences:
                        # Synthesize and send audio for this sentence
                        try:
                            tts_start = time.time()
                            audio_base64_chunk = await tts.synthesize(
                                text=sentence,
                                speaker=speaker
                            )
                            tts_time = time.time() - tts_start
                            tts_total_time += tts_time
                            tts_count += 1
                            
                            # Send audio chunk to client
                            await websocket.send_json({
                                "type": "audio_chunk",
                                "data": audio_base64_chunk,
                                "text": sentence  # Optional: include text for UI
                            })
                            
                            processed_sentences.add(sentence)
                            logger.debug(f"Orchestrator: Sent audio chunk for sentence: {sentence[:50]}... (TTS time: {tts_time:.3f}s)")
                        except Exception as e:
                            logger.error(f"Orchestrator: Error synthesizing sentence '{sentence}': {e}", exc_info=True)
                
                # Update buffer with remaining text
                sentence_buffer = remaining
            
            llm_time = time.time() - llm_start
            
            # Process remaining sentence buffer (final incomplete sentence)
            if sentence_buffer.strip():
                if sentence_buffer.strip() not in processed_sentences:
                    try:
                        tts_start = time.time()
                        audio_base64_chunk = await tts.synthesize(
                            text=sentence_buffer.strip(),
                            speaker=speaker
                        )
                        tts_time = time.time() - tts_start
                        tts_total_time += tts_time
                        tts_count += 1
                        await websocket.send_json({
                            "type": "audio_chunk",
                            "data": audio_base64_chunk,
                            "text": sentence_buffer.strip()
                        })
                    except Exception as e:
                        logger.error(f"Orchestrator: Error synthesizing final sentence: {e}", exc_info=True)
            
            # Clean the full response using dialogue_prompts.clean_reply
            clean_start = time.time()
            full_response = clean_reply(raw_response)
            clean_time = time.time() - clean_start
            logger.info(f"Orchestrator: Cleaned response (raw length: {len(raw_response)}, cleaned length: {len(full_response)}, clean time: {clean_time:.3f}s)")
            
            # Store LLM response in session (for batch database write on end_training)
            session_manager.add_llm_response(session_id, transcription, full_response)
            
            # 5. Update context
            context_update_start = time.time()
            context.update_context(session_id, transcription, full_response)
            context_update_time = time.time() - context_update_start
            logger.info(f"Orchestrator: Context updated (time: {context_update_time:.3f}s)")
            
            # 6. Send completion
            await websocket.send_json({
                "type": "response_complete",
                "transcription": transcription,
                "response_text": full_response
            })
            
            overall_time = time.time() - overall_start
            logger.info(
                f"Orchestrator: Utterance processing complete - "
                f"STT: {stt_time:.3f}s, "
                f"Context: {context_time:.3f}s, "
                f"LLM: {llm_time:.3f}s, "
                f"TTS: {tts_total_time:.3f}s ({tts_count} chunks, avg: {tts_total_time/tts_count if tts_count > 0 else 0:.3f}s), "
                f"Clean: {clean_time:.3f}s, "
                f"Context Update: {context_update_time:.3f}s, "
                f"Total: {overall_time:.3f}s, "
                f"Extraction sentences: {extract_sentence_time_total:.3f}s"
            )
        
        except Exception as e:
            overall_time = time.time() - overall_start
            logger.error(f"Orchestrator: Error processing utterance (failed after {overall_time:.3f}s): {e}", exc_info=True)
            try:
                # Check if WebSocket is still connected before sending error
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Error processing utterance: {str(e)}"
                    })
                except (RuntimeError, ConnectionError) as ws_error:
                    logger.warning(f"Orchestrator: Could not send error message to client (WebSocket disconnected): {ws_error}")
            except Exception as send_error:
                logger.warning(f"Orchestrator: Error sending error message to client: {send_error}")

