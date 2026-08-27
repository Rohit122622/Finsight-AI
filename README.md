# FinSentry AI

**Autonomous Multi-Agent Financial Research & Forensic SEC Analysis Platform**

FinSentry AI is a production-grade financial analysis platform engineered for automated document ingestion, multi-agent SEC Form 10-K/Q forensic analysis, derived math grounding, and citation-backed research assistant capabilities.

---

## Architecture Overview

```
FinSentry-AI/
├── backend/
│   ├── agents/          # Autonomous agents (Document, Extraction, RedFlag, Research, LiveAnalysis)
│   ├── api/             # FastAPI REST & WebSocket route handlers
│   ├── core/            # Configuration, logging, exception handlers, security
│   ├── crew/            # CrewAI task and tool orchestration
│   ├── database/        # Async MongoDB (Motor) & Redis connection management
│   ├── evaluation/      # RAG evaluation benchmarks, test datasets, and regression suite
│   ├── middleware/      # JWT auth, ownership validation, upload & login rate limiters
│   ├── models/          # MongoDB document models (Beanie/Pydantic)
│   ├── prompts/         # Structured financial prompt templates & system instructions
│   ├── schemas/         # Pydantic request/response & DTO validation models
│   ├── scripts/         # Verification and diagnostic scripts
│   ├── services/        # Business logic (RAG, OCR, Chunking, Embeddings, LLM Fallback, R2)
│   ├── tests/           # 730+ comprehensive automated tests across all phases
│   ├── utils/           # Math grounding, sanitization, validation helpers
│   └── workers/         # Celery background task processing
├── frontend/
│   ├── src/
│   │   ├── api/         # Axios API clients with auto token refresh
│   │   ├── components/  # Modern React components & financial charts
│   │   ├── context/     # React context providers (Theme, Auth)
│   │   ├── hooks/       # Custom React hooks & WebSocket integration
│   │   ├── layouts/     # Workstation application layout
│   │   ├── pages/       # Financial analysis workstation pages
│   │   ├── services/    # Frontend service layer
│   │   ├── store/       # Zustand reactive state stores
│   │   └── types/       # TypeScript interfaces and type definitions
│   └── public/          # Static assets and icons
├── docker/              # Multi-stage Dockerfiles & Docker Compose profiles
├── docs/                # System design specifications and architecture notes
└── scripts/             # Production deployment and maintenance scripts
```

---

## Core Capabilities

- **Document Ingestion & OCR Pipeline**: Text-density inspection, scanned PDF detection, OCR via PyMuPDF/EasyOCR, layout-aware section classification, and table extraction.
- **Multi-Agent Forensic Pipeline**: Coordinated `DocumentAgent` → `ExtractionAgent` → `RedFlagAgent` execution for anomaly detection, revenue recognition risks, and disclosure audits.
- **RAG & Research Agent**: Hybrid dense-sparse retrieval, reciprocal rank fusion (RRF), semantic query expansion, claim-level exact citations, and anti-hallucination verification.
- **Derived Financial Math Grounding**: Deterministic verification of calculated margins, ratios, variances, and YoY trends preventing numerical hallucinations.
- **LLM Fallback & Resilience**: Seamless multi-provider fallback (Groq LLaMA 3.3 70B, Google Gemini, OpenAI, Anthropic) with rate-limit circuit breaking.
- **Modern Workstation UI**: Fast, responsive React 19 + TypeScript + Vite + Tailwind CSS dark/light workstation with streaming WebSocket execution updates.

---

## Technology Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn, Celery, Motor (Async MongoDB), Redis, PyMuPDF, LangChain, CrewAI
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS, Zustand, Lucide Icons
- **Storage & Infrastructure**: Cloudflare R2 / S3 Object Storage, MongoDB Atlas, Redis 7
- **Deployment**: Multi-stage Docker, Nginx Reverse Proxy & Gateway, GitHub Actions CI/CD

---

## Quick Start (Development)

### Prerequisites
- Python 3.11+
- Node.js 20+
- MongoDB instance (local or Atlas)
- Redis instance (local or Docker)

### 1. Backend Setup
```bash
cd backend
cp .env.example .env
# Configure your MONGODB_URI, REDIS_HOST, GROQ_API_KEY / GOOGLE_API_KEY in .env

python -m venv venv
# Linux/macOS: source venv/bin/activate
# Windows: .\venv\Scripts\Activate.ps1

pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

### 2. Frontend Setup
```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

### 3. Run Test Suite
```bash
cd backend
python -m pytest tests/ -v
```

---

## Production Deployment (Docker Compose)

```bash
# Build and run all services (Gateway, Backend, Celery Worker, Redis, Frontend)
./scripts/deploy.sh --build

# View container logs
./scripts/deploy.sh --logs

# Stop services
./scripts/deploy.sh --down
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
