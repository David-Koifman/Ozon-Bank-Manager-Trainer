import { useState, useEffect, useRef } from 'react'
import './App.css'
import { 
  authenticatedFetch, 
  login, 
  register, 
  logout, 
  getToken, 
  getUser, 
  setUser 
} from './auth'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000/ws/call'

function App() {
  // Authentication state
  const [user, setUserState] = useState(getUser())
  const [isAuthenticated, setIsAuthenticated] = useState(!!getToken())
  const [authMode, setAuthMode] = useState('login') // 'login' or 'register'
  const [authEmail, setAuthEmail] = useState('')
  const [authName, setAuthName] = useState('')
  const [authRole, setAuthRole] = useState('manager')
  const [authLoading, setAuthLoading] = useState(false)
  const [view, setView] = useState('training') // 'training', 'my-sessions', 'statistics', 'coach-dashboard', 'session-detail'
  const [selectedSession, setSelectedSession] = useState(null)
  
  // Training session state
  const [sessionId, setSessionId] = useState(null)
  const [sessionInfo, setSessionInfo] = useState(null)
  const [callActive, setCallActive] = useState(false)
  const [callStatus, setCallStatus] = useState('idle')
  const [conversationHistory, setConversationHistory] = useState([])
  const [partialTranscription, setPartialTranscription] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [judgment, setJudgment] = useState(null)
  const [judging, setJudging] = useState(false)
  
  // Statistics state
  const [mySessions, setMySessions] = useState([])
  const [myStatistics, setMyStatistics] = useState(null)
  const [allSessions, setAllSessions] = useState([])
  const [usersStatistics, setUsersStatistics] = useState([])
  const [loadingStats, setLoadingStats] = useState(false)
  
  // Training parameters
  const [scenario, setScenario] = useState('free')
  const [speaker, setSpeaker] = useState('aidar')
  const [behaviorArchetype, setBehaviorArchetype] = useState('novice')
  const [difficultyLevel, setDifficultyLevel] = useState('1')
  
  // Check authentication on mount
  useEffect(() => {
    const checkAuth = async () => {
      if (getToken()) {
        try {
          const currentUser = await authenticatedFetch('/auth/me')
          setUserState(currentUser)
          setUser(currentUser)
          setIsAuthenticated(true)
        } catch (err) {
          logout()
          setIsAuthenticated(false)
          setUserState(null)
        }
      }
    }
    checkAuth()
  }, [])
  
  // Load statistics when view changes
  useEffect(() => {
    if (isAuthenticated && view === 'my-sessions') {
      loadMySessions()
      loadMyStatistics()
    } else if (isAuthenticated && view === 'statistics') {
      loadMySessions()
      loadMyStatistics()
    } else if (isAuthenticated && user?.role === 'coach' && view === 'coach-dashboard') {
      loadAllSessions()
      loadAllStatistics()
    }
  }, [view, isAuthenticated, user])

  // Refs for WebSocket and audio
  const wsRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const audioContextRef = useRef(null)
  const processorRef = useRef(null)
  const audioQueueRef = useRef([])
  const isPlayingRef = useRef(false)
  const playbackAudioContextRef = useRef(null)

  // Authentication handlers
  const handleLogin = async (e) => {
    e.preventDefault()
    setAuthLoading(true)
    setError(null)
    try {
      const response = await login(authEmail)
      setUserState(response.user)
      setIsAuthenticated(true)
      setView('training')
    } catch (err) {
      setError(`Login failed: ${err.message}`)
    } finally {
      setAuthLoading(false)
    }
  }
  
  const handleRegister = async (e) => {
    e.preventDefault()
    setAuthLoading(true)
    setError(null)
    try {
      const response = await register(authEmail, authName, authRole)
      setUserState(response.user)
      setIsAuthenticated(true)
      setView('training')
    } catch (err) {
      setError(`Registration failed: ${err.message}`)
    } finally {
      setAuthLoading(false)
    }
  }
  
  const handleLogout = () => {
    logout()
    setIsAuthenticated(false)
    setUserState(null)
    setView('training')
    setSessionId(null)
    setSessionInfo(null)
    setConversationHistory([])
    setJudgment(null)
  }
  
  // Statistics loading functions
  const loadMySessions = async () => {
    try {
      const data = await authenticatedFetch('/my-sessions')
      setMySessions(data.sessions || [])
    } catch (err) {
      setError(`Failed to load sessions: ${err.message}`)
    }
  }
  
  const loadMyStatistics = async () => {
    try {
      const data = await authenticatedFetch('/my-statistics')
      setMyStatistics(data)
    } catch (err) {
      setError(`Failed to load statistics: ${err.message}`)
    }
  }
  
  const loadAllSessions = async () => {
    setLoadingStats(true)
    try {
      const data = await authenticatedFetch('/coach/sessions')
      setAllSessions(data.sessions || [])
    } catch (err) {
      setError(`Failed to load all sessions: ${err.message}`)
    } finally {
      setLoadingStats(false)
    }
  }
  
  const loadAllStatistics = async () => {
    setLoadingStats(true)
    try {
      const data = await authenticatedFetch('/coach/statistics')
      setUsersStatistics(data.users_statistics || [])
    } catch (err) {
      setError(`Failed to load statistics: ${err.message}`)
    } finally {
      setLoadingStats(false)
    }
  }
  
  const toggleJudgment = (sessionId) => {
    setExpandedJudgments(prev => {
      const newSet = new Set(prev)
      if (newSet.has(sessionId)) {
        newSet.delete(sessionId)
      } else {
        newSet.add(sessionId)
      }
      return newSet
    })
  }
  
  // Helper function to get color from score (0-10, red to green)
  const getScoreColor = (score) => {
    // Clamp score between 0 and 10
    const clampedScore = Math.max(0, Math.min(10, score))
    const ratio = clampedScore / 10
    
    // Muted colors: red (#c62828) to green (#2e7d32)
    // Using muted/subdued colors as requested
    const red = { r: 198, g: 40, b: 40 }   // #c62828 - muted red
    const green = { r: 46, g: 125, b: 50 } // #2e7d32 - muted green
    
    // Interpolate between red and green
    const r = Math.round(red.r + (green.r - red.r) * ratio)
    const g = Math.round(red.g + (green.g - red.g) * ratio)
    const b = Math.round(red.b + (green.b - red.b) * ratio)
    
    return `rgb(${r}, ${g}, ${b})`
  }

  // Helper function to render score progression chart
  const renderScoreChart = (sessions) => {
    // Prepare chart data from sessions
    const sessionsWithScores = sessions
      .filter(s => s.judgment && s.judgment.total_score !== undefined && s.judgment.total_score !== null)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
      .map((s, index) => ({
        sessionNumber: index + 1,
        score: s.judgment.total_score,
        date: new Date(s.created_at)
      }))
    
    if (sessionsWithScores.length === 0) {
      return (
        <div className="chart-container">
          <h3>Score Progression</h3>
          <p className="no-data-message">No completed sessions with scores yet.</p>
        </div>
      )
    }
    
    // Chart dimensions
    const chartWidth = 800
    const chartHeight = 300
    const padding = { top: 20, right: 20, bottom: 40, left: 50 }
    const innerWidth = chartWidth - padding.left - padding.right
    const innerHeight = chartHeight - padding.top - padding.bottom
    
    // Calculate scales
    const maxScore = 10
    const minScore = 0
    const scoreRange = maxScore - minScore
    
    const xScale = (sessionNum) => 
      padding.left + ((sessionNum - 1) / (sessionsWithScores.length - 1 || 1)) * innerWidth
    
    const yScale = (score) => 
      padding.top + innerHeight - ((score - minScore) / scoreRange) * innerHeight
    
    // Generate path for line
    const pathData = sessionsWithScores.map((point, idx) => {
      const x = xScale(point.sessionNumber)
      const y = yScale(point.score)
      return idx === 0 ? `M ${x} ${y}` : `L ${x} ${y}`
    }).join(' ')
    
    // Generate points
    const points = sessionsWithScores.map(point => ({
      x: xScale(point.sessionNumber),
      y: yScale(point.score),
      score: point.score,
      sessionNumber: point.sessionNumber
    }))
    
    return (
      <div className="chart-container">
        <h3>Score Progression</h3>
        <div className="chart-wrapper">
          <svg width={chartWidth} height={chartHeight} className="score-chart">
            {/* Grid lines */}
            {[0, 2, 4, 6, 8, 10].map(score => {
              const y = yScale(score)
              return (
                <line
                  key={score}
                  x1={padding.left}
                  y1={y}
                  x2={chartWidth - padding.right}
                  y2={y}
                  stroke="#e5e5e5"
                  strokeWidth="1"
                />
              )
            })}
            
            {/* Y-axis labels */}
            {[0, 2, 4, 6, 8, 10].map(score => {
              const y = yScale(score)
              return (
                <text
                  key={score}
                  x={padding.left - 10}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="12"
                  fill="#666"
                >
                  {score}
                </text>
              )
            })}
            
            {/* X-axis labels */}
            {sessionsWithScores.map((point, idx) => {
              if (idx % Math.ceil(sessionsWithScores.length / 10) === 0 || idx === sessionsWithScores.length - 1) {
                const x = xScale(point.sessionNumber)
                return (
                  <text
                    key={idx}
                    x={x}
                    y={chartHeight - padding.bottom + 20}
                    textAnchor="middle"
                    fontSize="12"
                    fill="#666"
                  >
                    {point.sessionNumber}
                  </text>
                )
              }
              return null
            })}
            
            {/* Axes */}
            <line
              x1={padding.left}
              y1={padding.top}
              x2={padding.left}
              y2={chartHeight - padding.bottom}
              stroke="#1a1a1a"
              strokeWidth="2"
            />
            <line
              x1={padding.left}
              y1={chartHeight - padding.bottom}
              x2={chartWidth - padding.right}
              y2={chartHeight - padding.bottom}
              stroke="#1a1a1a"
              strokeWidth="2"
            />
            
            {/* Line */}
            <path
              d={pathData}
              fill="none"
              stroke="#1a1a1a"
              strokeWidth="2"
              className="score-line"
            />
            
            {/* Points */}
            {points.map((point, idx) => {
              const pointColor = getScoreColor(point.score)
              return (
                <circle
                  key={idx}
                  cx={point.x}
                  cy={point.y}
                  r="4"
                  fill={pointColor}
                  stroke="#1a1a1a"
                  strokeWidth="1"
                  className="score-point"
                />
              )
            })}
          </svg>
        </div>
        <div className="chart-legend">
          <div className="legend-item">
            <span className="legend-label">X-axis:</span>
            <span>Session Number</span>
          </div>
          <div className="legend-item">
            <span className="legend-label">Y-axis:</span>
            <span>Overall Score (0-10)</span>
          </div>
        </div>
      </div>
    )
  }

  // Component to render judgment details
  const renderJudgmentDetails = (judgment, inline = false) => {
    if (!judgment) return null
    
    const totalScore = judgment.total_score || 0
    const maxScore = 10.0
    const scoreRatio = totalScore / maxScore
    const overallQuality = scoreRatio >= 0.9 ? 'excellent' : 
                          scoreRatio >= 0.7 ? 'good' : 
                          scoreRatio >= 0.5 ? 'average' : 'poor'
    
    // Get color for overall score
    const overallScoreColor = getScoreColor(totalScore)
    
    const aspectScores = Object.entries(judgment.scores || {}).map(([criterion, value]) => {
      let scoreValue = 0
      if (criterion === 'politeness') {
        scoreValue = typeof value === 'number' ? value : 0
      } else {
        scoreValue = value ? 10 : 0
      }
      return {
        aspect: criterion.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
        score: scoreValue,
        passed: value === true || (criterion === 'politeness' && value > 0)
      }
    })
    
    const summaryParts = []
    if (judgment.feedback_positive && judgment.feedback_positive.length > 0) {
      summaryParts.push(`Strengths: ${judgment.feedback_positive.slice(0, 2).join(', ')}`)
    }
    if (judgment.feedback_improvement && judgment.feedback_improvement.length > 0) {
      summaryParts.push(`Areas for improvement: ${judgment.feedback_improvement.slice(0, 2).join(', ')}`)
    }
    const summary = summaryParts.join('. ') || 'Evaluation completed.'
    
    const wrapperClass = inline ? 'judgment-details' : 'judgment-section'
    const contentClass = inline ? '' : 'judgment-content'
    
    const renderHeading = (text) => {
      return inline ? <h4>{text}</h4> : <h3>{text}</h3>
    }
    
    return (
      <div className={wrapperClass}>
        {!inline && (
          <div className="judgment-header">
            <h2>Session Evaluation</h2>
          </div>
        )}
        <div className={contentClass}>
          {/* Overall Score */}
          <div className="judgment-card overall-score">
            <div className="score-display">
              <div className={`score-circle ${inline ? 'score-circle-inline' : ''}`} style={{
                '--score': totalScore,
                '--max-score': 10,
                '--score-color': overallScoreColor,
                borderColor: overallScoreColor
              }}>
                <span className="score-value" style={{ color: overallScoreColor }}>{totalScore.toFixed(1)}</span>
                <span className="score-max">/ 10</span>
              </div>
              <div className={`quality-badge quality-${overallQuality}`} style={{
                borderColor: overallScoreColor,
                color: overallScoreColor
              }}>
                      {overallQuality === 'excellent' && 'Excellent'}
                      {overallQuality === 'good' && 'Good'}
                      {overallQuality === 'average' && 'Average'}
                      {overallQuality === 'poor' && 'Poor'}
              </div>
            </div>
          </div>


          {/* Critical Errors */}
          {judgment.critical_errors && judgment.critical_errors.length > 0 && (
            <div className="judgment-card critical-errors">
              {renderHeading('Critical Errors')}
              <ul>
                {judgment.critical_errors.map((error, idx) => (
                  <li key={idx} className="error-item">{error}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Aspect Scores */}
          {aspectScores.length > 0 && (
            <div className="judgment-card">
              {renderHeading('Detailed Scores')}
              <div className="aspect-scores">
                {aspectScores.map((aspect, idx) => {
                  const aspectColor = getScoreColor(aspect.score)
                  return (
                    <div key={idx} className="aspect-item">
                      <div className="aspect-header">
                        <span className="aspect-name">{aspect.aspect}</span>
                        <span className="aspect-score" style={{ color: aspectColor }}>{aspect.score}/10</span>
                      </div>
                      <div className="score-bar">
                        <div 
                          className="score-fill" 
                          style={{ 
                            width: `${(aspect.score / 10) * 100}%`,
                            backgroundColor: aspectColor
                          }}
                        ></div>
                      </div>
                      <p className="aspect-comment">
                              {aspect.passed ? 'Passed' : 'Failed'}: {aspect.aspect}
                      </p>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Strengths */}
          {judgment.feedback_positive && judgment.feedback_positive.length > 0 && (
            <div className="judgment-card strengths">
              {renderHeading('Strengths')}
              <ul>
                {judgment.feedback_positive.map((strength, idx) => (
                  <li key={idx}>{strength}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Areas for Improvement */}
          {judgment.feedback_improvement && judgment.feedback_improvement.length > 0 && (
            <div className="judgment-card weaknesses">
              {renderHeading('Areas for Improvement')}
              <ul>
                {judgment.feedback_improvement.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Recommendations */}
          {judgment.recommendations && judgment.recommendations.length > 0 && (
            <div className="judgment-card recommendations">
              {renderHeading('Recommendations')}
              <ul>
                {judgment.recommendations.map((rec, idx) => (
                  <li key={idx}>{rec}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    )
  }
  
  // Start training session
  const startSession = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await authenticatedFetch('/start-training', {
        method: 'POST',
        body: JSON.stringify({
          scenario: scenario,
          speaker: speaker,
          behavior_archetype: behaviorArchetype,
          difficulty_level: difficultyLevel
        })
      })
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
      setJudging(true)
      setJudgment(null)
      try {
        const data = await authenticatedFetch('/end-training', {
          method: 'POST',
          body: JSON.stringify({ session_id: sessionId })
        })
        
        // Check if judgment is included in response
        if (data.judgment) {
          setJudgment(data.judgment)
        } else if (data.judgment_error) {
          setError(`Failed to get judgment: ${data.judgment_error}`)
        }
        
        // Refresh sessions list if on sessions view
        if (view === 'my-sessions') {
          loadMySessions()
          loadMyStatistics()
        }
      } catch (err) {
        console.error('Error ending session:', err)
        setError(`Failed to end session: ${err.message}`)
      } finally {
        setJudging(false)
      }
    }
  }
  
  // Reset session (after viewing judgment)
  const resetSession = () => {
    setSessionId(null)
    setSessionInfo(null)
    setConversationHistory([])
    setJudgment(null)
    setError(null)
  }

  // Start WebSocket call for streaming mode
  const startCall = async () => {
    if (!sessionId) {
      setError('Please start a training session first')
      return
    }

    // Check if getUserMedia is available
    let getUserMediaFunc = null
    
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      getUserMediaFunc = (constraints) => navigator.mediaDevices.getUserMedia(constraints)
    } else if (navigator.getUserMedia) {
      // Legacy API - wrap in Promise
      getUserMediaFunc = (constraints) => {
        return new Promise((resolve, reject) => {
          navigator.getUserMedia(constraints, resolve, reject)
        })
      }
    } else if (navigator.webkitGetUserMedia) {
      getUserMediaFunc = (constraints) => {
        return new Promise((resolve, reject) => {
          navigator.webkitGetUserMedia(constraints, resolve, reject)
        })
      }
    } else if (navigator.mozGetUserMedia) {
      getUserMediaFunc = (constraints) => {
        return new Promise((resolve, reject) => {
          navigator.mozGetUserMedia(constraints, resolve, reject)
        })
      }
    }
    
    if (!getUserMediaFunc) {
      setError('Microphone access is not available. Please ensure you are using HTTPS (or localhost) and a modern browser that supports microphone access.')
      return
    }

    try {
      // Request microphone access
      const stream = await getUserMediaFunc({ 
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

  // Navigate to session detail page
  const viewSessionDetail = (session) => {
    setSelectedSession(session)
    setView('session-detail')
  }
  
  // Navigate back to previous view
  const backToPreviousView = () => {
    setSelectedSession(null)
    // Determine which view to go back to based on user role
    if (user?.role === 'coach') {
      setView('coach-dashboard')
    } else {
      setView('my-sessions')
    }
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCall()
      endSession()
    }
  }, [])

  // Show login/register if not authenticated
  if (!isAuthenticated) {
    return (
      <div className="app">
        <div className="header">
          <h1>Operator Voice Trainer</h1>
          <p>Real-time voice training with AI</p>
        </div>
        <div className="auth-container">
          <div className="auth-card">
            <div className="auth-tabs">
              <button 
                className={authMode === 'login' ? 'active' : ''}
                onClick={() => setAuthMode('login')}
              >
                Login
              </button>
              <button 
                className={authMode === 'register' ? 'active' : ''}
                onClick={() => setAuthMode('register')}
              >
                Register
              </button>
            </div>
            
            {authMode === 'login' ? (
              <form onSubmit={handleLogin}>
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={authEmail}
                    onChange={(e) => setAuthEmail(e.target.value)}
                    required
                    placeholder="your@email.com"
                  />
                </div>
                <button type="submit" className="btn btn-primary" disabled={authLoading}>
                  {authLoading ? 'Logging in...' : 'Login'}
                </button>
              </form>
            ) : (
              <form onSubmit={handleRegister}>
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={authEmail}
                    onChange={(e) => setAuthEmail(e.target.value)}
                    required
                    placeholder="your@email.com"
                  />
                </div>
                <div className="form-group">
                  <label>Name</label>
                  <input
                    type="text"
                    value={authName}
                    onChange={(e) => setAuthName(e.target.value)}
                    required
                    placeholder="Your Name"
                  />
                </div>
                <div className="form-group">
                  <label>Role</label>
                  <select
                    value={authRole}
                    onChange={(e) => setAuthRole(e.target.value)}
                  >
                    <option value="manager">Manager</option>
                    <option value="coach">Coach</option>
                  </select>
                </div>
                <button type="submit" className="btn btn-primary" disabled={authLoading}>
                  {authLoading ? 'Registering...' : 'Register'}
                </button>
              </form>
            )}
            
            {error && <div className="error-message">{error}</div>}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <div className="header">
        <h1>Operator Voice Trainer</h1>
        <div className="header-right">
          <span className="user-info">
            {user?.name} ({user?.role})
          </span>
          <button className="btn btn-secondary" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </div>

      {/* Navigation */}
      <div className="nav-tabs">
        <button 
          className={view === 'training' ? 'active' : ''}
          onClick={() => setView('training')}
        >
          Training
        </button>
        <button 
          className={view === 'my-sessions' ? 'active' : ''}
          onClick={() => setView('my-sessions')}
        >
          My Sessions
        </button>
        <button 
          className={view === 'statistics' ? 'active' : ''}
          onClick={() => setView('statistics')}
        >
          My Statistics
        </button>
        {user?.role === 'coach' && (
          <button 
            className={view === 'coach-dashboard' ? 'active' : ''}
            onClick={() => setView('coach-dashboard')}
          >
            Coach Dashboard
          </button>
        )}
      </div>

      <div className="content">
        {/* My Sessions View */}
        {view === 'my-sessions' && (
          <div className="sessions-view">
            <h2>My Training Sessions</h2>
            {mySessions.length === 0 ? (
              <p>No sessions yet. Start a training session to see it here.</p>
            ) : (
              <div className="sessions-list">
                {mySessions.map((session) => (
                  <div 
                    key={session.id} 
                    className="session-card clickable"
                    onClick={() => viewSessionDetail(session)}
                  >
                    <div className="session-header">
                      <h3>Session {session.session_id.substring(0, 8)}...</h3>
                      <span className={`status-badge ${session.status}`}>
                        {session.status}
                      </span>
                    </div>
                    <div className="session-details">
                      <p><strong>Scenario:</strong> {session.scenario}</p>
                      <p><strong>Behavior:</strong> {session.behavior_archetype}</p>
                      <p><strong>Difficulty:</strong> {session.difficulty_level}</p>
                      <p><strong>Created:</strong> {new Date(session.created_at).toLocaleString()}</p>
                      {session.judgment && (
                        <div className="judgment-preview">
                          <strong>Score:</strong> {session.judgment.total_score || 'N/A'}
                          {session.judgment.critical_errors?.length > 0 && (
                            <span className="error-badge">
                              {session.judgment.critical_errors.length} errors
                            </span>
                          )}
                          <span className="view-details-link">View Full Details</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* My Statistics View */}
        {view === 'statistics' && (
          <div className="statistics-view">
            <h2>My Statistics</h2>
            {myStatistics ? (
              <>
                <div className="stats-grid">
                  <div className="stat-card">
                    <h3>Total Sessions</h3>
                    <p className="stat-value">{myStatistics.total_sessions}</p>
                  </div>
                  <div className="stat-card">
                    <h3>Completed</h3>
                    <p className="stat-value">{myStatistics.completed_sessions}</p>
                  </div>
                  <div className="stat-card">
                    <h3>Active</h3>
                    <p className="stat-value">{myStatistics.active_sessions}</p>
                  </div>
                  <div className="stat-card">
                    <h3>Average Score</h3>
                    <p className="stat-value">{myStatistics.average_score || 'N/A'}</p>
                  </div>
                </div>
                
                {/* Score Progression Chart */}
                {renderScoreChart(mySessions)}
              </>
            ) : (
              <p>Loading statistics...</p>
            )}
          </div>
        )}

        {/* Session Detail View */}
        {view === 'session-detail' && selectedSession && (
          <div className="session-detail-view">
            <div className="session-detail-header">
              <button className="btn btn-secondary" onClick={backToPreviousView}>
                ← Back to {user?.role === 'coach' ? 'Dashboard' : 'My Sessions'}
              </button>
              <h2>Session Details</h2>
            </div>
            
            <div className="session-detail-info">
              <div className="session-info-card">
                <h3>Session Information</h3>
                <div className="info-grid">
                  <div className="info-item">
                    <strong>Session ID:</strong> {selectedSession.session_id}
                  </div>
                  {selectedSession.user_name && (
                    <div className="info-item">
                      <strong>Manager:</strong> {selectedSession.user_name} ({selectedSession.user_email})
                    </div>
                  )}
                  <div className="info-item">
                    <strong>Scenario:</strong> {selectedSession.scenario}
                  </div>
                  <div className="info-item">
                    <strong>Behavior Archetype:</strong> {selectedSession.behavior_archetype}
                  </div>
                  <div className="info-item">
                    <strong>Difficulty Level:</strong> {selectedSession.difficulty_level}
                  </div>
                  <div className="info-item">
                    <strong>Status:</strong> 
                    <span className={`status-badge ${selectedSession.status}`}>
                      {selectedSession.status}
                    </span>
                  </div>
                  <div className="info-item">
                    <strong>Created:</strong> {new Date(selectedSession.created_at).toLocaleString()}
                  </div>
                  {selectedSession.ended_at && (
                    <div className="info-item">
                      <strong>Ended:</strong> {new Date(selectedSession.ended_at).toLocaleString()}
                    </div>
                  )}
                </div>
              </div>
              
              {selectedSession.judgment ? (
                <div className="session-judgment-full-page">
                  {renderJudgmentDetails(selectedSession.judgment, false)}
                </div>
              ) : (
                <div className="no-judgment">
                  <p>This session has not been evaluated yet.</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Coach Dashboard View */}
        {view === 'coach-dashboard' && user?.role === 'coach' && (
          <div className="coach-dashboard">
            <h2>Coach Dashboard</h2>
            
            {/* Per-User Statistics */}
            <div className="dashboard-section">
              <h3>Statistics by User</h3>
              {loadingStats ? (
                <p>Loading statistics...</p>
              ) : usersStatistics.length === 0 ? (
                <p>No users found.</p>
              ) : (
                <div className="users-statistics-list">
                  {usersStatistics.map((userStat) => {
                    // Filter sessions for this user
                    const userSessions = allSessions.filter(s => s.user_id === userStat.user.id)
                    
                    return (
                      <div key={userStat.user.id} className="user-statistics-card">
                        <div className="user-statistics-header">
                          <h4>{userStat.user.name}</h4>
                          <span className="user-email">{userStat.user.email}</span>
                          <span className={`role-badge ${userStat.user.role}`}>
                            {userStat.user.role}
                          </span>
                        </div>
                        <div className="user-stats-grid">
                          <div className="stat-card">
                            <h5>Total Sessions</h5>
                            <p className="stat-value">{userStat.statistics.total_sessions}</p>
                          </div>
                          <div className="stat-card">
                            <h5>Completed</h5>
                            <p className="stat-value">{userStat.statistics.completed_sessions}</p>
                          </div>
                          <div className="stat-card">
                            <h5>Active</h5>
                            <p className="stat-value">{userStat.statistics.active_sessions}</p>
                          </div>
                          <div className="stat-card">
                            <h5>Average Score</h5>
                            <p className="stat-value">{userStat.statistics.average_score || 'N/A'}</p>
                          </div>
                          <div className="stat-card">
                            <h5>Sessions with Scores</h5>
                            <p className="stat-value">{userStat.statistics.sessions_with_scores}</p>
                          </div>
                        </div>
                        {/* Score Progression Chart for this user */}
                        {renderScoreChart(userSessions)}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* All Sessions */}
            <div className="dashboard-section">
              <h3>All Training Sessions</h3>
              {loadingStats ? (
                <p>Loading sessions...</p>
              ) : allSessions.length === 0 ? (
                <p>No sessions found.</p>
              ) : (
                <div className="sessions-list">
                  {allSessions.map((session) => (
                    <div 
                      key={session.id} 
                      className="session-card clickable"
                      onClick={() => viewSessionDetail(session)}
                    >
                      <div className="session-header">
                        <h3>Session {session.session_id.substring(0, 8)}...</h3>
                        <span className={`status-badge ${session.status}`}>
                          {session.status}
                        </span>
                      </div>
                      <div className="session-details">
                        <p><strong>Manager:</strong> {session.user_name} ({session.user_email})</p>
                        <p><strong>Scenario:</strong> {session.scenario}</p>
                        <p><strong>Behavior:</strong> {session.behavior_archetype}</p>
                        <p><strong>Difficulty:</strong> {session.difficulty_level}</p>
                        <p><strong>Created:</strong> {new Date(session.created_at).toLocaleString()}</p>
                        {session.judgment && (
                          <div className="judgment-preview">
                            <strong>Score:</strong> {session.judgment.total_score || 'N/A'}
                            {session.judgment.critical_errors?.length > 0 && (
                              <span className="error-badge">
                                {session.judgment.critical_errors.length} errors
                              </span>
                            )}
                            <span className="view-details-link">View Full Details</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Training View */}
        {view === 'training' && (
          <>
        {/* Sidebar */}
        <div className="sidebar">
          <div className="session-info">
            <h3>Session Management</h3>
            {sessionId ? (
              <>
                <p>Session ID: <code>{sessionId.substring(0, 8)}...</code></p>
                <div className="session-controls">
                  {!judgment && (
                    <button className="btn btn-danger" onClick={endSession} disabled={judging}>
                      {judging ? 'Judging...' : 'End Session'}
                    </button>
                  )}
                  {judgment && (
                    <button className="btn btn-primary" onClick={resetSession}>
                      New Session
                    </button>
                  )}
                </div>
              </>
            ) : (
              <>
                <div className="training-params">
                  <div className="param-group">
                    <label htmlFor="scenario">Scenario / Product</label>
                    <select
                      id="scenario"
                      value={scenario}
                      onChange={(e) => setScenario(e.target.value)}
                    >
                      <option value="free">Свободная тема</option>
                      <option value="rko">РКО</option>
                      <option value="bank_card">Бизнес-карта</option>
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
                      <option value="skeptic">Скептик</option>
                      <option value="busy_owner">Занятой предприниматель</option>
                      <option value="friendly">Дружелюбный</option>
                    </select>
                  </div>

                  <div className="param-group">
                    <label htmlFor="difficulty">Difficulty Level</label>
                    <select
                      id="difficulty"
                      value={difficultyLevel}
                      onChange={(e) => setDifficultyLevel(e.target.value)}
                    >
                      <option value="1">1 — Лёгкий</option>
                      <option value="2">2 — Нормальный</option>
                      <option value="3">3 — Сложный</option>
                      <option value="4">4 — Очень сложный</option>
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
              <h2>Conversation</h2>
            </div>

            {/* Chat container */}
            <div className="chat-container">
              {conversationHistory.length === 0 && !partialTranscription ? (
                <div className="loading">
                  Start a conversation by clicking "Start Call" and speaking.
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
                  Start Call
                </button>
              ) : (
                <button className="btn btn-danger" onClick={stopCall}>
                  End Call
                </button>
              )}
              <div className={`status-indicator status-${callStatus}`}>
                Status: {callStatus}
              </div>
            </div>
          </div>
        )}

        {/* Judgment visualization */}
        {judgment && (() => {
          // Calculate overall quality from total_score
          const totalScore = judgment.total_score || 0
          const maxScore = 10.0
          const scoreRatio = totalScore / maxScore
          const overallQuality = scoreRatio >= 0.9 ? 'excellent' : 
                                scoreRatio >= 0.7 ? 'good' : 
                                scoreRatio >= 0.5 ? 'average' : 'poor'
          
          // Transform scores dict to aspect_scores array
          const aspectScores = Object.entries(judgment.scores || {}).map(([criterion, value]) => {
            let scoreValue = 0
            if (criterion === 'politeness') {
              scoreValue = typeof value === 'number' ? value : 0
            } else {
              scoreValue = value ? 10 : 0
            }
            return {
              aspect: criterion.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
              score: scoreValue,
              passed: value === true || (criterion === 'politeness' && value > 0)
            }
          })
          
          // Create summary from feedback
          const summaryParts = []
          if (judgment.feedback_positive && judgment.feedback_positive.length > 0) {
            summaryParts.push(`Strengths: ${judgment.feedback_positive.slice(0, 2).join(', ')}`)
          }
          if (judgment.feedback_improvement && judgment.feedback_improvement.length > 0) {
            summaryParts.push(`Areas for improvement: ${judgment.feedback_improvement.slice(0, 2).join(', ')}`)
          }
          const summary = summaryParts.join('. ') || 'Evaluation completed.'
          
          return (
            <div className="judgment-section">
              <div className="judgment-header">
                <h2>Session Evaluation</h2>
              </div>
              
              <div className="judgment-content">
                {/* Overall Score */}
                <div className="judgment-card overall-score">
                  <div className="score-display">
                    {(() => {
                      const overallScoreColor = getScoreColor(totalScore)
                      return (
                        <>
                          <div className="score-circle" style={{
                            '--score': totalScore,
                            '--max-score': 10,
                            '--score-color': overallScoreColor,
                            borderColor: overallScoreColor
                          }}>
                            <span className="score-value" style={{ color: overallScoreColor }}>{totalScore.toFixed(1)}</span>
                            <span className="score-max">/ 10</span>
                          </div>
                          <div className={`quality-badge quality-${overallQuality}`} style={{
                            borderColor: overallScoreColor,
                            color: overallScoreColor
                          }}>
                            {overallQuality === 'excellent' && 'Excellent'}
                            {overallQuality === 'good' && 'Good'}
                            {overallQuality === 'average' && 'Average'}
                            {overallQuality === 'poor' && 'Poor'}
                          </div>
                        </>
                      )
                    })()}
                  </div>
                </div>


                {/* Critical Errors */}
                {judgment.critical_errors && judgment.critical_errors.length > 0 && (
                  <div className="judgment-card critical-errors">
                    <h3>Critical Errors</h3>
                    <ul>
                      {judgment.critical_errors.map((error, idx) => (
                        <li key={idx} className="error-item">{error}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Aspect Scores */}
                {aspectScores.length > 0 && (
                  <div className="judgment-card">
                    <h3>Detailed Scores</h3>
                    <div className="aspect-scores">
                      {aspectScores.map((aspect, idx) => {
                        const aspectColor = getScoreColor(aspect.score)
                        return (
                          <div key={idx} className="aspect-item">
                            <div className="aspect-header">
                              <span className="aspect-name">{aspect.aspect}</span>
                              <span className="aspect-score" style={{ color: aspectColor }}>{aspect.score}/10</span>
                            </div>
                            <div className="score-bar">
                              <div 
                                className="score-fill" 
                                style={{ 
                                  width: `${(aspect.score / 10) * 100}%`,
                                  backgroundColor: aspectColor
                                }}
                              ></div>
                            </div>
                            <p className="aspect-comment">
                              {aspect.passed ? 'Passed' : 'Failed'}: {aspect.aspect}
                            </p>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

        {/* Strengths */}
        {judgment.feedback_positive && judgment.feedback_positive.length > 0 && (
          <div className="judgment-card strengths">
            <h3>Strengths</h3>
            <ul>
              {judgment.feedback_positive.map((strength, idx) => (
                <li key={idx}>{strength}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Areas for Improvement */}
        {judgment.feedback_improvement && judgment.feedback_improvement.length > 0 && (
          <div className="judgment-card weaknesses">
            <h3>Areas for Improvement</h3>
            <ul>
              {judgment.feedback_improvement.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Recommendations */}
        {judgment.recommendations && judgment.recommendations.length > 0 && (
          <div className="judgment-card recommendations">
            <h3>Recommendations</h3>
            <ul>
              {judgment.recommendations.map((rec, idx) => (
                <li key={idx}>{rec}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Additional Info */}
        <div className="judgment-card stats">
          <h3>Session Information</h3>
                  <div className="stats-grid">
                    <div className="stat-item">
                      <span className="stat-label">Scenario</span>
                      <span className="stat-value">{judgment.scenario_id || 'N/A'}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Model Used</span>
                      <span className="stat-value">{judgment.model_used || 'unknown'}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Backend</span>
                      <span className="stat-value">{judgment.judge_backend || 'unknown'}</span>
                    </div>
                    {judgment.client_profile && (
                      <div className="stat-item">
                        <span className="stat-label">Client Type</span>
                        <span className="stat-value">{judgment.client_profile.type || 'N/A'}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )
        })()}
          </>
        )}
      </div>
    </div>
  )
}

export default App


