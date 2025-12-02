from typing import Dict, Any
import asyncio
import logging

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
        
        elif action == "audio_input":
            # Process audio through the pipeline (echo mode)
            audio_data = message.get("audio", "")
            logger.info(f"Orchestrator: Processing audio input (audio_data length: {len(audio_data)})")
            
            # Parallel processing: Session Manager and STT
            logger.info("Orchestrator: Getting session info from Session Manager")
            session_info = session_manager.get_session(session_id)
            
            logger.info("Orchestrator: Calling STT.transcribe()")
            stt_result = await stt.transcribe(audio_data)
            logger.info(f"Orchestrator: STT result: {stt_result[:50]}...")
            
            # Log STT transcription to database
            if database:
                await database.log_stt_transcription(session_id, stt_result)
            
            # Session Manager -> Context
            logger.info("Orchestrator: Getting context from Context component")
            context_data = context.get_context(session_id, session_info)
            logger.info(f"Orchestrator: Context retrieved (length: {len(context_data)})")
            
            # STT + Context -> LLM
            logger.info("Orchestrator: Calling LLM.generate_response()")
            llm_response = await llm.generate_response(
                user_input=stt_result,
                context=context_data
            )
            logger.info(f"Orchestrator: LLM response received: {llm_response[:50]}...")
            
            # Log LLM response to database
            if database:
                await database.log_llm_response(session_id, stt_result, llm_response)
            
            # LLM -> TTS
            # Get speaker from session info
            speaker = session_info.get("speaker", "aidar") if session_info else "aidar"
            logger.info(f"Orchestrator: Calling TTS.synthesize() with speaker '{speaker}'")
            audio_output = await tts.synthesize(llm_response, speaker=speaker)
            logger.info(f"Orchestrator: TTS output received (length: {len(audio_output)})")
            
            # Update context with the interaction
            logger.info("Orchestrator: Updating context with interaction")
            context.update_context(session_id, stt_result, llm_response)
            
            logger.info("Orchestrator: Returning audio_response")
            return {
                "type": "audio_response",
                "transcription": stt_result,
                "response_text": llm_response,
                "audio": audio_output,
                "session_id": session_id
            }
        
        elif action == "end_training":
            logger.info(f"Orchestrator: Ending training session {session_id}")
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

