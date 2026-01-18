# Operator Voice Trainer

A real-time voice training system for call center operators with AI-powered evaluation and feedback.

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) OpenRouter API key for LLM services, or Ollama for local LLM

### Running All Services

1. **Create `.env` file** in the root directory (see example below)

2. **Start all services:**
   ```bash
   docker-compose up -d
   ```

3. **Access the application:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

4. **Stop all services:**
   ```bash
   docker-compose down
   ```

## 📋 Environment Variables

Create a `.env` file in the root directory:

### Using OpenRouter

```env
# LLM Provider
export LLM_PROVIDER=openrouter

# OpenRouter Configuration
export OPENROUTER_API_KEY=your_openrouter_api_key_here
export OPENROUTER_MODEL=openai/gpt-4o-mini
export OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```
Then in terminal
```bash
source .env
```


