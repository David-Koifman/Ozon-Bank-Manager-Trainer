import { useState, useEffect, useRef } from 'react'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000/ws/call'

function App() {
  const [sessionId, setSessionId] = useState(null)
  const [sessionInfo, setSessionInfo] = useState(null)
  const [callActive, setCallActive] = useState(false)
  const [callStatus, setCallStatus] = useState('idle')
  const [conversationHistory, setConversationHistory] = useState([])
  const [partialTranscription, setPartialTranscription] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  
  // Training parameters
  const [scenario, setScenario] = useState('default')
  const [speaker, setSpeaker] = useState('aidar')
  const [behaviorArchetype, setBehaviorArchetype] = useState('novice')
  const [difficultyLevel, setDifficultyLevel] = useState('1')

  // Refs for WebSocket and audio
  const wsRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const audioContextRef = useRef(null)
  const processorRef = useRef(null)
  const audioQueueRef = useRef([])
  const isPlayingRef = useRef(false)
  const playbackAudioContextRef = useRef(null)

  // Start training session
  const startSession = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/start-training`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: scenario,
          speaker: speaker,
          behavior_archetype: behaviorArchetype,
          difficulty_level: difficultyLevel
        })
      })
      const data = await response.json()
      setSessionId(data.session_id)
      setSessionInfo(data)
      setConversationHistory([])
    } catch (err) {
      setError(`Failed to start session: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  // End training session
  const endSession = async () => {
    if (callActive) {
      stopCall()
    }
    if (sessionId) {
      try {
        await fetch(`${API_BASE_URL}/end-training`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId })
        })
      } catch (err) {
        console.error('Error ending session:', err)
      }
    }
    setSessionId(null)
    setSessionInfo(null)
    setConversationHistory([])
  }

  // Start WebSocket call for streaming mode
  const startCall = async () => {
    if (!sessionId) {
      setError('Please start a training session first')
      return
    }

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      })
      mediaStreamRef.current = stream

      // Create WebSocket connection
      const ws = new WebSocket(`${WS_BASE_URL}/${sessionId}`)
      wsRef.current = ws

      // Set up audio processing
      const audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000
      })
      audioContextRef.current = audioContext

      const source = audioContext.createMediaStreamSource(stream)
      // Use buffer size that matches VAD frame size: 30ms at 16kHz = 480 samples = 960 bytes (16-bit)
      // ScriptProcessor buffer size must be power of 2, so use 512 samples
      // But we need to send exactly 480 samples (960 bytes) to match VAD frame size
      const processor = audioContext.createScriptProcessor(512, 1, 1)
      processorRef.current = processor
      
      // Buffer to accumulate samples to exactly 480 (30ms frame)
      let sampleBuffer = new Float32Array(0)

      // Store callActive state in closure
      let isActive = false

      // Set up WebSocket handlers BEFORE starting audio
      ws.onopen = () => {
        console.log('WebSocket connection opened successfully')
        isActive = true
        setCallActive(true)
        setCallStatus('listening')
        setError(null)
        
        // Start audio processing AFTER WebSocket is confirmed open
        let chunkCount = 0
        let sampleBuffer = new Float32Array(0)
        const FRAME_SIZE_SAMPLES = 480 // 30ms at 16kHz = 480 samples = 960 bytes
        
        processor.onaudioprocess = (e) => {
          if (ws.readyState === WebSocket.OPEN && isActive) {
            const inputData = e.inputBuffer.getChannelData(0)
            
            // Accumulate samples to exactly 480 samples (30ms frame)
            const newBuffer = new Float32Array(sampleBuffer.length + inputData.length)
            newBuffer.set(sampleBuffer)
            newBuffer.set(inputData, sampleBuffer.length)
            sampleBuffer = newBuffer
            
            // Process complete frames (480 samples each)
            while (sampleBuffer.length >= FRAME_SIZE_SAMPLES) {
              // Extract exactly 480 samples
              const frame = sampleBuffer.slice(0, FRAME_SIZE_SAMPLES)
              sampleBuffer = sampleBuffer.slice(FRAME_SIZE_SAMPLES)
              
              // Convert Float32Array to Int16Array (PCM 16-bit)
              const int16Data = new Int16Array(FRAME_SIZE_SAMPLES)
              for (let i = 0; i < FRAME_SIZE_SAMPLES; i++) {
                int16Data[i] = Math.max(-32768, Math.min(32767, frame[i] * 32768))
              }
              
              // Convert to base64
              const bytes = new Uint8Array(int16Data.buffer)
              // Use Array.from to avoid "Maximum call stack size exceeded"
              const binary = Array.from(bytes, byte => String.fromCharCode(byte)).join('')
              const base64 = btoa(binary)
              
              chunkCount++
              if (chunkCount % 50 === 0) { // Log every 50 chunks to avoid spam
                console.log(`Sent ${chunkCount} audio chunks to backend, WebSocket state: ${ws.readyState}`)
              }
              
              // Send frame (exactly 960 bytes = 480 samples * 2 bytes)
              if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                  type: 'audio_chunk',
                  data: base64
                }))
              } else {
                console.warn(`WebSocket not open, state: ${ws.readyState}`)
              }
            }
          }
        }

        source.connect(processor)
        processor.connect(audioContext.destination)
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          console.log('Received WebSocket message:', message.type)
          handleWebSocketMessage(message)
        } catch (err) {
          console.error('Error parsing WebSocket message:', err, event.data)
        }
      }

      ws.onerror = (err) => {
        console.error('WebSocket error:', err)
        setError('WebSocket connection error')
      }

      ws.onclose = () => {
        console.log('WebSocket connection closed')
        isActive = false
        setCallActive(false)
        setCallStatus('idle')
        stopAudioCapture()
      }

    } catch (err) {
      setError(`Failed to start call: ${err.message}`)
      console.error('Error starting call:', err)
    }
  }

  // Stop WebSocket call
  const stopCall = () => {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: 'end_call' }))
      wsRef.current.close()
      wsRef.current = null
    }
    stopAudioCapture()
    // Clear audio queue and stop playback
    audioQueueRef.current = []
    if (playbackAudioContextRef.current) {
      playbackAudioContextRef.current.close()
      playbackAudioContextRef.current = null
    }
    isPlayingRef.current = false
    setCallActive(false)
    setCallStatus('idle')
  }

  // Stop audio capture
  const stopAudioCapture = () => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop())
      mediaStreamRef.current = null
    }
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
  }

  // Play audio automatically (like video conferencing)
  const playAudioChunk = async (audioBase64) => {
    try {
      // Create audio context for playback if not exists
      if (!playbackAudioContextRef.current) {
        playbackAudioContextRef.current = new (window.AudioContext || window.webkitAudioContext)()
      }
      const audioContext = playbackAudioContextRef.current

      // Decode base64 audio
      const audioData = Uint8Array.from(atob(audioBase64), c => c.charCodeAt(0))
      const audioBuffer = await audioContext.decodeAudioData(audioData.buffer)

      // Create buffer source and play
      const source = audioContext.createBufferSource()
      source.buffer = audioBuffer
      source.connect(audioContext.destination)
      
      source.onended = () => {
        // Play next audio in queue
        if (audioQueueRef.current.length > 0) {
          const nextAudio = audioQueueRef.current.shift()
          playAudioChunk(nextAudio)
        } else {
          isPlayingRef.current = false
        }
      }

      source.start(0)
      isPlayingRef.current = true
    } catch (err) {
      console.error('Error playing audio:', err)
      // If error, try next in queue
      if (audioQueueRef.current.length > 0) {
        const nextAudio = audioQueueRef.current.shift()
        playAudioChunk(nextAudio)
      } else {
        isPlayingRef.current = false
      }
    }
  }

  // Handle WebSocket messages
  const handleWebSocketMessage = (message) => {
    switch (message.type) {
      case 'connected':
        setCallStatus('listening')
        break
      case 'status':
        setCallStatus(message.status)
        break
      case 'partial_transcription':
        // Update partial transcription (for real-time display)
        setPartialTranscription(message.text)
        break
      case 'transcription':
        // Final transcription received - add to conversation and clear partial
        addMessage('user', message.text)
        setPartialTranscription('')
        break
      case 'audio_chunk':
        addMessage('assistant', message.text || '', message.data)
        // Auto-play audio chunk
        if (message.data) {
          if (isPlayingRef.current) {
            // Queue if already playing
            audioQueueRef.current.push(message.data)
          } else {
            // Play immediately
            playAudioChunk(message.data)
          }
        }
        break
      case 'response_complete':
        setCallStatus('listening') // Ready for next input
        break
      case 'error':
        setError(message.message)
        break
    }
  }

  // Add message to conversation
  const addMessage = (type, text, audioBase64 = null) => {
    const message = {
      type,
      text,
      audioBase64,
      timestamp: new Date()
    }
    setConversationHistory(prev => [...prev, message])
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCall()
      endSession()
    }
  }, [])

  return (
    <div className="app">
      <div className="header">
        <h1>🎤 Operator Voice Trainer</h1>
        <p>Real-time voice training with AI</p>
      </div>

      <div className="content">
        {/* Sidebar */}
        <div className="sidebar">
          <div className="session-info">
            <h3>Session Management</h3>
            {sessionId ? (
              <>
                <p>Session ID: <code>{sessionId.substring(0, 8)}...</code></p>
                <div className="session-controls">
                  <button className="btn btn-danger" onClick={endSession}>
                    End Session
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="training-params">
                  <div className="param-group">
                    <label htmlFor="scenario">Scenario</label>
                    <select
                      id="scenario"
                      value={scenario}
                      onChange={(e) => setScenario(e.target.value)}
                    >
                      <option value="default">Default</option>
                      <option value="customer_service">Customer Service</option>
                      <option value="technical_support">Technical Support</option>
                      <option value="sales">Sales</option>
                    </select>
                  </div>

                  <div className="param-group">
                    <label htmlFor="speaker">Speaker Voice</label>
                    <select
                      id="speaker"
                      value={speaker}
                      onChange={(e) => setSpeaker(e.target.value)}
                    >
                      <option value="aidar">Aidar</option>
                      <option value="baya">Baya</option>
                      <option value="kseniya">Kseniya</option>
                      <option value="xenia">Xenia</option>
                      <option value="eugene">Eugene</option>
                    </select>
                  </div>

                  <div className="param-group">
                    <label htmlFor="behavior">Client Behavior Archetype</label>
                    <select
                      id="behavior"
                      value={behaviorArchetype}
                      onChange={(e) => setBehaviorArchetype(e.target.value)}
                    >
                      <option value="novice">Новичок</option>
                      <option value="silent">Молчун</option>
                      <option value="expert">Эксперт</option>
                      <option value="complainer">Жалобщик</option>
                    </select>
                  </div>

                  <div className="param-group">
                    <label htmlFor="difficulty">Difficulty Level</label>
                    <select
                      id="difficulty"
                      value={difficultyLevel}
                      onChange={(e) => setDifficultyLevel(e.target.value)}
                    >
                      <option value="1">Базовый (1)</option>
                      <option value="2">Стандартный (2)</option>
                      <option value="3">Продвинутый (3)</option>
                      <option value="4">Экспертный (4)</option>
                    </select>
                  </div>
                </div>

                <div className="session-controls">
                  <button className="btn btn-primary" onClick={startSession} disabled={loading}>
                    {loading ? 'Starting...' : 'Start Training Session'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Error display */}
        {error && (
          <div className="error">
            {error}
          </div>
        )}

        {/* Conversation section */}
        {sessionId && (
          <div className="conversation-section">
            <div className="conversation-header">
              <h2>💬 Conversation</h2>
            </div>

            {/* Chat container */}
            <div className="chat-container">
              {conversationHistory.length === 0 && !partialTranscription ? (
                <div className="loading">
                  💡 Start a conversation by clicking "Start Call" and speaking.
                </div>
              ) : (
                <>
                  {conversationHistory.map((msg, idx) => (
                    <div key={idx} className={`message ${msg.type}`}>
                      <div>
                        <div className="message-bubble">
                          {msg.text}
                        </div>
                        <div className="message-time">
                          {msg.timestamp.toLocaleTimeString()}
                        </div>
                      </div>
                    </div>
                  ))}
                  {/* Display partial transcription in real-time */}
                  {partialTranscription && (
                    <div className="message user">
                      <div>
                        <div className="message-bubble partial-transcription">
                          {partialTranscription}
                        </div>
                        <div className="message-time">
                          Speaking...
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Audio controls */}
            <div className="audio-controls">
              {!callActive ? (
                <button className="btn btn-primary" onClick={startCall}>
                  📞 Start Call
                </button>
              ) : (
                <button className="btn btn-danger" onClick={stopCall}>
                  📴 End Call
                </button>
              )}
              <div className={`status-indicator status-${callStatus}`}>
                Status: {callStatus}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default App

