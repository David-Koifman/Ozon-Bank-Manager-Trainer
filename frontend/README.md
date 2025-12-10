# Operator Voice Trainer - Frontend

Simple React frontend for the Operator Voice Trainer application.

## Features

- ✅ Real-time streaming mode with WebSocket
- ✅ Batch mode for recording and sending audio
- ✅ Clean, modern UI
- ✅ Web Audio API for microphone access
- ✅ Conversation history with audio playback

## Setup

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Environment Variables

Create a `.env` file:

```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_WS_BASE_URL=ws://localhost:8000/ws/call
```

## Usage

1. Start the backend services (backend, STT, TTS)
2. Start this frontend: `npm run dev`
3. Open http://localhost:3000
4. Click "Start Training Session"
5. Choose Batch or Streaming mode
6. Start conversing!

## Technologies

- React 18
- Vite
- Web Audio API
- WebSocket API

