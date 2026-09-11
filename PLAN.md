# FIND-MISSING-PEP — Master One-Shot Build Plan & System Specification
## AI-Based Missing Person Detection & Real-Time CCTV Monitoring System

> **Contract Directive**: This document is the unified, self-contained implementation contract for **FIND-MISSING-PEP**. It strictly follows the [3-One-Shot-Build-Spec.md](file:///c:/SSD%20WINDOW/code/FIND%20-MISSING%20PEP/DOC/3-One-Shot-Build-Spec.md) architectural template — ordering configuration → schema → dependencies → runtime → AI domain logic → data layer → action layer → orchestration → API → UI → critical rules → ops.
> 
> **"Build this exactly. Do not skip anything. Do not simplify. Do not substitute libraries."** Every architectural mistake, mathematical timing paradox, and runtime blocker documented in [6-Architecture-Mistakes-and-Flaws.md](file:///c:/SSD%20WINDOW/code/FIND%20-MISSING%20PEP/DOC/6-Architecture-Mistakes-and-Flaws.md) and the codebase audit is definitively resolved herein.

---

## Table of Contents

| § | Section | Purpose |
|---|---|---|
| 0 | [Mission Statement](#0-mission-statement) | Plain language capabilities, flat pinned tech stack, build contract |
| 1 | [File Structure](#1-file-structure--complete-project-tree) | Literal directory tree with single-responsibility comments |
| 2 | [Environment / Secrets](#2-environment--secrets) | Comprehensive `.env` templates, precedence rules, `.gitignore` |
| 3 | [Data Schema](#3-data-schema) | Idempotent DDL for PostgreSQL & SQLite, RLS/access control postures |
| 4 | [Dependencies](#4-dependencies) | Pinned package specifications across backend, edge, web, mobile |
| 5 | [Containerization / Runtime](#5-containerization--runtime) | Debian 12 Dockerfile, model pre-warming, port ownership map |
| 6 | [Domain Config / AI Pipeline Architecture](#6-domain-config--ai-pipeline-architecture) | The core research novelty: SCRFD, landmark ByteTrack, ArcFace, FAISS, temporal verifier |
| 7 | [Data Access Layer](#7-data-access-layer--crud) | Single-query data functions grouped by entity, pagination & tombstone sync |
| 8 | [Action / Tool Layer](#8-action--tool-layer--services) | SSE manager (Redis + fallback), evidence ring buffer, offline sync queue |
| 9 | [Orchestration / Entrypoint](#9-orchestration--entrypoint) | Edge Agent multi-thread worker pipeline, backend lifespan, web app bootstrap |
| 10 | [API Layer](#10-api-layer--rest-contract) | REST endpoints, DTO models, atomic multipart uploads, static routes |
| 11 | [Frontend / UI Spec](#11-frontend--ui-spec) | Web App (React/Vite), Mobile App (Flutter), Edge Desktop (PySide6) |
| 12 | [Critical Architecture Rules — DO NOT DEVIATE](#12-critical-architecture-rules--do-not-deviate) | 26 WRONG vs CORRECT code pairs resolving all audited flaws |
| 13 | [Deployment](#13-deployment) | Step-by-step installation, Docker & native execution, success log output |
| 14 | [Known Gotchas Table](#14-known-gotchas-table) | Symptom → Root Cause → Fix operational reference |
| 15 | [Reference Data](#15-reference-data) | Status enums, biometric thresholds, model filenames, RTSP test links |
| 16 | [Cost / Ops Reference](#16-cost--ops-reference) | CPU/RAM hardware budget, bandwidth, storage metrics |
| 17 | [External API Integration Reference](#17-external-api-integration-reference) | Copy-paste code snippets for Firebase Auth, Leaflet, EventSource, ONVIF |
| 18 | [One-Time Setup Sequence](#18-one-time-setup-sequence) | Post-deployment checklist to bring the system to usable production state |

---

## 0. Mission Statement

### What the System Does
An installable, edge-native AI video surveillance and forensic platform that connects to existing CCTV infrastructure, continuously detects and tracks faces from live RTSP feeds, matches them against active missing-person reference galleries in sub-second time, temporally verifies matches across consecutive observations to eliminate false alarms, captures tamper-evident forensic media packages (face crops, full frames, short video clips), and dispatches instantaneous alerts to family members and operators via real-time Server-Sent Events (SSE) and mobile push notifications.

### Core Capabilities (Verbs)
1. **Ingests** live RTSP/ONVIF CCTV camera video feeds at native 15–25 FPS with non-blocking circular buffering.
2. **Detects** human faces using SCRFD (buffalo_l ONNX) on CPU with sub-30ms latency per sampled frame.
3. **Tracks** identities across space and time using a landmark-preserving ByteTrack Kalman filter, assigning persistent Track IDs.
4. **Extracts** 512-dimensional facial biometric representations using ArcFace (`w600k_r50.onnx`) normalized to unit hyperspheres.
5. **Indexes** active missing-person reference vectors into an in-memory FAISS `IndexFlatIP` search engine using atomic double-buffering.
6. **Verifies** candidate sightings temporally ($N=3$ observations within 5.0 seconds at cosine similarity $\ge 0.60$) before alerting.
7. **Captures** structured forensic evidence packages: 112×112 face crop, 1080p full frame snapshot, and 5-second circular video clip.
8. **Buffers** pending sightings locally in an offline SQLite queue when network connectivity drops, guaranteeing zero evidence loss.
9. **Broadcasts** real-time alerts to web dashboards and Flutter mobile apps via Redis Pub/Sub SSE with in-memory fallback.
10. **Reports** missing persons via atomic multipart HTTP submissions with on-device canvas image compression.
11. **Maps** chronological CCTV sighting breadcrumbs on an interactive Leaflet GPS timeline.
12. **Synchronizes** delta reference galleries between cloud and edge agents incrementally using tombstone tracking.

### Tech Stack
- **Edge Desktop GUI & Runtime**: Python 3.10–3.11, PySide6 6.6+, OpenCV 4.9+ (headless/native), ONNX Runtime 1.17+, FAISS-CPU 1.7.4, lapx 0.5.5, SQLite3 (WAL mode).
- **Backend API & Processing**: FastAPI 0.110+, Uvicorn 0.28+, SQLAlchemy 2.0+ (asyncio), AsyncPG 0.29+, PostgreSQL 16, Redis 7 (asyncio), Pydantic v2, Python-Jose / Cryptography (AES-GCM).
- **Web Application**: React 18.3+, TypeScript 5.5+, Vite 5.4+, TailwindCSS 3.4+, Lucide React, Leaflet 1.9+, Axios 1.6+, Firebase SDK v10.
- **Mobile Application**: Flutter 3.19+, Dart 3.3+, Flutter Riverpod 2.5+, GoRouter 13.2+, Dio 5.4+, Flutter Map 6.1+.
- **Inference Models**: InsightFace `buffalo_l` suite (`det_10g.onnx`, `w600k_r50.onnx`).

### Build Contract
> **"Build this exactly. Do not skip anything. Do not simplify. Do not substitute libraries."**
> This specification is authoritative. Do not replace `lapx` with `lap`. Do not replace async SQLAlchemy with synchronous drivers. Do not lower verification thresholds below 0.60. Do not omit the FAISS double-buffering pointer swap.

---

## 1. File Structure — Complete Project Tree

```
FIND-MISSING-PEP/
│
├── backend/                                    ← Central FastAPI Cloud/Server Platform
│   ├── alembic/                                ← Database migration environment
│   │   ├── env.py                              ← Async Alembic migration harness
│   │   ├── script.py.mako                      ← Migration script template
│   │   └── versions/                           ← Auto-generated migration versions
│   │       └── 0001_initial_schema.py          ← Core PostgreSQL DDL migration
│   ├── app/                                    ← Application package
│   │   ├── api/                                ← REST API routing layer
│   │   │   ├── __init__.py                     ← Router aggregator
│   │   │   ├── cameras.py                      ← Camera enrollment, pairing, and status endpoints
│   │   │   ├── deps.py                         ← Auth dependencies, Firebase verifier, mock token gate
│   │   │   ├── reports.py                      ← Missing person case management & photo upload
│   │   │   ├── sightings.py                    ← Edge sighting ingestion, evidence review, verification
│   │   │   ├── sse.py                          ← Server-Sent Events stream with token auth
│   │   │   ├── sync.py                         ← Incremental edge sync & tombstone package endpoints
│   │   │   └── users.py                        ← Authenticated user profile synchronization
│   │   ├── core/                               ← Core configurations and utilities
│   │   │   ├── __init__.py                     ← Package marker
│   │   │   ├── config.py                       ← Pydantic-Settings BaseSettings configuration
│   │   │   ├── database.py                     ← Async engine, sessionmaker, base declarative model
│   │   │   ├── logging.py                      ← Structured log formatter
│   │   │   └── security.py                     ← AES-GCM token encryption and key validation
│   │   ├── crud/                               ← Data Access Layer (Single query per function)
│   │   │   ├── __init__.py                     ← CRUD package marker
│   │   │   ├── camera.py                       ← Camera CRUD queries
│   │   │   ├── face_embedding.py               ← Biometric vector and tombstone queries
│   │   │   ├── missing_person.py               ← Case CRUD with DB-level status filtering
│   │   │   ├── photo.py                        ← Photo record mutations
│   │   │   ├── sighting.py                     ← Sighting timeline and audit mutations
│   │   │   └── user.py                         ← User profile queries
│   │   ├── models/                             ← SQLAlchemy Declarative ORM models
│   │   │   ├── __init__.py                     ← Central model exports for Alembic discovery
│   │   │   ├── base.py                         ← Base model with UUID and timestamp mixins
│   │   │   ├── camera.py                       ← Camera registry entity
│   │   │   ├── enums.py                        ← Authoritative string enum definitions
│   │   │   ├── face_embedding.py               ← 512-D embedding storage with soft-delete tombstones
│   │   │   ├── missing_person.py               ← Missing person case registry
│   │   │   ├── photo.py                        ← Reference photo metadata
│   │   │   ├── sighting.py                     ← Sighting events and forensic evidence paths
│   │   │   └── user.py                         ← User profile mapped to Firebase UID
│   │   ├── schemas/                            ← Pydantic validation and DTO schemas
│   │   │   ├── __init__.py                     ← Schema exports
│   │   │   ├── camera.py                       ← Camera request/response schemas
│   │   │   ├── common.py                       ← Pagination, error, and standard responses
│   │   │   ├── missing_person.py               ← Case creation and summary DTOs
│   │   │   ├── notification.py                 ← Sighting alert broadcast schemas
│   │   │   ├── photo.py                        ← Photo upload validation schemas
│   │   │   ├── sighting.py                     ← Sighting payload and evidence schemas
│   │   │   ├── sync.py                         ← Edge gallery sync package DTOs
│   │   │   └── user.py                         ← User registration and profile DTOs
│   │   ├── services/                           ← Action / Tool layer services
│   │   │   ├── __init__.py                     ← Service exports
│   │   │   ├── face_processor.py               ← Server-side SCRFD + ArcFace feature extractor
│   │   │   ├── fcm_service.py                  ← Firebase Cloud Messaging push dispatcher
│   │   │   ├── sse_manager.py                  ← Real-time SSE broker (Redis PubSub + in-memory fallback)
│   │   │   └── storage_service.py              ← Secure local disk filesystem asset manager
│   │   ├── utils/                              ← Utility modules
│   │   │   ├── __init__.py                     ← Utility exports
│   │   │   ├── crypto.py                       ← AES-256 GCM encryption helpers
│   │   │   └── geo.py                          ← Haversine distance and geofencing calculations
│   │   └── main.py                             ← FastAPI app factory, lifespan, CORS, static file mounts
│   ├── tests/                                  ← Backend pytest suite
│   │   ├── conftest.py                         ← Pytest async client fixtures and test DB
│   │   ├── test_auth.py                        ← Auth and token verification tests
│   │   ├── test_reports.py                     ← Report creation and pagination tests
│   │   ├── test_sightings.py                   ← Sighting ingestion and alert tests
│   │   └── test_sync.py                        ← Edge sync package and tombstone tests
│   ├── .env.example                            ← Backend environment variable blueprint
│   ├── alembic.ini                             ← Alembic configuration file
│   ├── Dockerfile                              ← Debian 12 multi-stage Docker build with pre-warmed models
│   ├── requirements.txt                        ← Pinned backend Python dependencies
│   └── start.sh                                ← Production container entrypoint script
│
├── edge_agent/                                 ← Desktop Edge CCTV Processing Application
│   ├── ai/                                     ← Edge AI Pipeline
│   │   ├── __init__.py                         ← AI package exports
│   │   ├── face_detector.py                    ← SCRFD ONNX inference engine (CPU optimized)
│   │   ├── face_recognizer.py                  ← ArcFace ONNX 512-D feature extraction engine
│   │   ├── temporal_verifier.py                ← Multi-frame temporal confirmation engine
│   │   ├── track_state.py                      ← Landmark-preserving track state data structures
│   │   ├── tracker.py                          ← Modernized ByteTrack with 8D Kalman filter (no np.float)
│   │   └── vector_search.py                    ← Double-buffered thread-safe FAISS search engine
│   ├── camera/                                 ← Video ingestion and camera discovery
│   │   ├── __init__.py                         ← Camera package exports
│   │   ├── circular_buffer.py                  ← 15 FPS pre/post match video ring buffer
│   │   ├── onvif_discovery.py                  ← WS-Discovery and ONVIF profile resolver
│   │   └── stream_manager.py                   ← Non-blocking multi-threaded RTSP capture worker
│   ├── network/                                ← Central backend communication client
│   │   ├── __init__.py                         ← Network exports
│   │   ├── api_client.py                       ← Authenticated HTTPX client with retries
│   │   ├── sse_listener.py                     ← SSE background event subscriber
│   │   └── sync_worker.py                      ← Periodic incremental embedding cache sync worker
│   ├── storage/                                ← Local persistence
│   │   ├── __init__.py                         ← Storage exports
│   │   ├── evidence_store.py                   ← Local disk storage for crops and snapshots
│   │   └── local_db.py                         ← Thread-safe SQLite store with WAL mode
│   ├── ui/                                     ← PySide6 (Qt) Desktop User Interface
│   │   ├── __init__.py                         ← UI exports
│   │   ├── alert_dialog.py                     ← Sighting match popup dialog with alarm chime
│   │   ├── camera_grid.py                      ← Responsive 1x1, 2x2 multi-camera live view widget
│   │   ├── main_window.py                      ← Primary desktop window, menu, status bar
│   │   └── theme.py                            ← Dark mode CSS styling and palettes
│   ├── utils/                                  ← Edge utility helpers
│   │   ├── __init__.py                         ← Utility exports
│   │   └── hardware.py                         ← CPU, RAM, and camera FPS diagnostic telemetry
│   ├── config.ini                              ← Local edge agent configuration file
│   ├── config.py                               ← Pydantic configuration loader
│   ├── main.py                                 ← PySide6 application bootstrap and orchestration
│   └── requirements.txt                        ← Pinned Edge Agent Python dependencies (Windows friendly)
│
├── web_app/                                    ← Modern Citizen & Operator Web Portal
│   ├── public/                                 ← Static assets, icons, sound effects
│   │   ├── alert_chime.mp3                     ← Sighting alert sound notification
│   │   └── favicon.ico                         ← Web app icon
│   ├── src/                                    ← Frontend React application
│   │   ├── components/                         ← Reusable UI component library
│   │   │   ├── common/                         ← Badges, modals, cards, buttons, spinners
│   │   │   ├── layout/                         ← Navigation bar, sidebar, breadcrumb header
│   │   │   ├── map/                            ← Interactive Leaflet GPS breadcrumb component
│   │   │   └── sighting/                       ← Side-by-side face inspection and audit controls
│   │   ├── context/                            ← Global state providers
│   │   │   ├── AuthContext.tsx                 ← Firebase auth state, dev mock tokens, profile sync
│   │   │   └── SseContext.tsx                  ← Live Server-Sent Events listener and toast alerts
│   │   ├── hooks/                              ← Custom React hooks
│   │   │   ├── useDebounce.ts                  ← Search query debounce hook
│   │   │   └── useImageCompressor.ts           ← HTML5 Canvas client-side photo compressor
│   │   ├── pages/                              ← Application route views
│   │   │   ├── CaseDetailsPage.tsx             ← Detailed missing person case portfolio
│   │   │   ├── DashboardPage.tsx               ← Global statistics and recent activity feed
│   │   │   ├── LoginPage.tsx                   ← Firebase and Dev Mock login screen
│   │   │   ├── MapTimelinePage.tsx             ← Interactive multi-camera geographic sighting trail
│   │   │   ├── ReportPersonPage.tsx            ← Atomic missing person report submission form
│   │   │   └── SightingsReviewPage.tsx         ← Forensic review queue with accept/reject triage
│   │   ├── services/                           ← Axios API client and DTO endpoints
│   │   │   ├── api.ts                          ← Axios instance with interceptors
│   │   │   ├── authService.ts                  ← Firebase and mock auth methods
│   │   │   ├── reportService.ts                ← Report and photo upload API calls
│   │   │   └── sightingService.ts              ← Sighting verification API calls
│   │   ├── types/                              ← TypeScript interfaces and enums
│   │   │   └── index.ts                        ← Full-stack shared type definitions
│   │   ├── App.tsx                             ← Root route configuration and route guards
│   │   ├── index.css                           ← TailwindCSS tokens and custom glassmorphism styles
│   │   └── main.tsx                            ← Application bootstrap entrypoint
│   ├── .env                                    ← Web app local environment variables
│   ├── Dockerfile                              ← Multi-stage Nginx production build
│   ├── nginx.conf                              ← SPA routing and proxy configuration
│   ├── package.json                            ← Pinned npm dependencies and scripts
│   ├── tsconfig.json                           ← Strict TypeScript configuration
│   └── vite.config.ts                          ← Vite bundler configuration and dev proxy
│
├── flutter_app/                                ← Mobile Citizen & Family Reporting App
│   ├── lib/                                    ← Dart source code
│   │   ├── core/                               ← Core themes, constants, network client
│   │   ├── models/                             ← Dart data models
│   │   ├── providers/                          ← Riverpod state management providers
│   │   ├── screens/                            ← Mobile UI screens (Hindi + English)
│   │   └── services/                           ← Mobile Dio client, auth, FCM notifications
│   ├── pubspec.yaml                            ← Flutter dependencies
│   └── README.md                               ← Flutter setup instructions
│
├── scripts/                                    ← Automation, seeding, and verification scripts
│   ├── download_models.py                      ← Standalone script to download InsightFace buffalo_l
│   ├── generate_synthetic_cctv.py              ← OpenCV synthetic RTSP test video generator
│   ├── seed_database.py                        ← Database populator with test cases and embeddings
│   └── verify_pipeline.py                      ← End-to-end integration test runner
│
├── docker-compose.yml                          ← Multi-container orchestration (Postgres, Redis, Backend, Web)
├── run_all.py                                  ← Multi-service local development runner
└── PLAN.md                                     ← This authoritative build plan document
```

---

## 2. Environment / Secrets

### 2.1 Settings Precedence Chain
```
Command Line Arguments > OS Environment Variables > Component .env File > Pydantic Defaults
```

### 2.2 Backend Environment Template (`backend/.env`)
```bash
# ── Server Runtime ──
DEBUG=True                                      # Set to False in production
SECRET_KEY=b4a9f3e1c2d5e7a8b0c3d2e1f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3 # 32-byte hex key for AES-256
API_V1_PREFIX=/api
HOST=0.0.0.0
PORT=8000
ALLOWED_HOSTS=*
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000

# ── PostgreSQL Database ──
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/find_missing_pep
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# ── Redis Pub/Sub & Caching ──
REDIS_URL=redis://localhost:6379/0

# ── Storage & Asset Uploads ──
UPLOAD_DIR=./uploads
MAX_PHOTO_SIZE_MB=10
ALLOWED_PHOTO_EXTENSIONS=.jpg,.jpeg,.png,.webp

# ── Firebase Authentication (Optional in DEBUG mode) ──
FIREBASE_CREDENTIALS_PATH=./firebase_credentials.json

# ── AI Model Parameters ──
AI_MODELS_DIR=./ai_models
INSIGHTFACE_DET_SIZE=640
FACE_DETECTION_THRESHOLD=0.50
```

### 2.3 Edge Agent Configuration (`edge_agent/config.ini`)
```ini
[server]
backend_url = http://localhost:8000
agent_token = edge_token_secret_key_12345
sync_interval_seconds = 60
heartbeat_interval_seconds = 30

[cameras]
; Format: local_id = rtsp_url, name, latitude, longitude
cam_01 = 0, Entrance North, 28.6139, 77.2090
cam_02 = test_cctv_feed.mp4, Hallway East, 28.6142, 77.2095

[ai]
det_size = 640
det_threshold = 0.50
track_thresh = 0.50
match_thresh = 0.80
frame_rate = 15
track_buffer = 30
candidate_cutoff = 0.50
temporal_threshold = 0.60
temporal_window_size = 3
temporal_max_timespan = 5.0
alert_cooldown_seconds = 300.0

[storage]
db_path = local_data.db
evidence_dir = ./evidence
max_storage_gb = 20
```

### 2.4 Web Application Environment (`web_app/.env`)
```bash
VITE_API_BASE_URL=http://localhost:8000/api
VITE_SSE_URL=http://localhost:8000/api/sse/events
VITE_ENABLE_MOCK_AUTH=true

# Firebase Web Client (Optional for dev mock)
VITE_FIREBASE_API_KEY=AIzaSyDummyKeyForDevelopment12345
VITE_FIREBASE_AUTH_DOMAIN=find-missing-pep.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=find-missing-pep
VITE_FIREBASE_STORAGE_BUCKET=find-missing-pep.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=1234567890
VITE_FIREBASE_APP_ID=1:1234567890:web:abcdef123456
```

### 2.5 Master `.gitignore`
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.env
.venv/
env/
venv/
.pytest_cache/

# Node / Web App
node_modules/
dist/
.vite/

# Desktop / Edge Agent
local_data.db
local_data.db-wal
local_data.db-shm
evidence/
uploads/
ai_models/

# OS / IDE
.DS_Store
Thumbs.db
.vscode/
.idea/
*.log
```

---

## 3. Data Schema

### 3.1 PostgreSQL Backend Schema (DDL — Idempotent)
```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users Table (Indexed on Firebase UID)
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firebase_uid    VARCHAR(128) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    phone_number    VARCHAR(32),
    role            VARCHAR(32) DEFAULT 'CITIZEN' NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid);

-- 2. Cameras Table
CREATE TABLE IF NOT EXISTS cameras (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    local_id        VARCHAR(64) UNIQUE NOT NULL,
    name            VARCHAR(255) NOT NULL,
    rtsp_url        TEXT NOT NULL,
    location_name   VARCHAR(255),
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    status          VARCHAR(32) DEFAULT 'OFFLINE' NOT NULL,
    last_heartbeat  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 3. Missing Persons Table
CREATE TABLE IF NOT EXISTS missing_persons (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    case_number         VARCHAR(64) UNIQUE NOT NULL,
    full_name           VARCHAR(255) NOT NULL,
    alias               VARCHAR(255),
    age                 INTEGER NOT NULL,
    gender              VARCHAR(32) NOT NULL,
    last_seen_date      TIMESTAMPTZ NOT NULL,
    last_seen_location  VARCHAR(255) NOT NULL,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    description         TEXT,
    identifying_features TEXT,
    contact_phone       VARCHAR(32) NOT NULL,
    status              VARCHAR(32) DEFAULT 'PROCESSING' NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_missing_persons_status ON missing_persons(status);
CREATE INDEX IF NOT EXISTS idx_missing_persons_user ON missing_persons(user_id);

-- 4. Photos Table
CREATE TABLE IF NOT EXISTS photos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id           UUID NOT NULL REFERENCES missing_persons(id) ON DELETE CASCADE,
    file_path           TEXT NOT NULL,
    is_primary          BOOLEAN DEFAULT FALSE NOT NULL,
    processing_status   VARCHAR(32) DEFAULT 'PENDING' NOT NULL,
    quality_score       DOUBLE PRECISION,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_photos_person ON photos(person_id);

-- 5. Face Embeddings Table (with Tombstones for Incremental Sync)
CREATE TABLE IF NOT EXISTS face_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id       UUID NOT NULL REFERENCES missing_persons(id) ON DELETE CASCADE,
    photo_id        UUID NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    embedding       BYTEA NOT NULL, -- 512 float32 binary blob (2048 bytes)
    is_active       BOOLEAN DEFAULT TRUE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_embeddings_person ON face_embeddings(person_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_sync ON face_embeddings(updated_at, is_active);

-- 6. Sightings Table (ON DELETE CASCADE to prevent FK trap)
CREATE TABLE IF NOT EXISTS sightings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id           UUID NOT NULL REFERENCES missing_persons(id) ON DELETE CASCADE,
    camera_id           UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    similarity_score    DOUBLE PRECISION NOT NULL,
    confidence_level    VARCHAR(32) DEFAULT 'POSSIBLE' NOT NULL,
    num_frames_matched  INTEGER DEFAULT 1 NOT NULL,
    face_crop_path      TEXT NOT NULL,
    full_frame_path     TEXT NOT NULL,
    video_clip_path     TEXT,
    sighting_time       TIMESTAMPTZ NOT NULL,
    status              VARCHAR(32) DEFAULT 'UNCONFIRMED' NOT NULL,
    operator_notes      TEXT,
    reviewed_at         TIMESTAMPTZ,
    reviewed_by         UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sightings_person ON sightings(person_id);
CREATE INDEX IF NOT EXISTS idx_sightings_camera ON sightings(camera_id);
CREATE INDEX IF NOT EXISTS idx_sightings_time ON sightings(sighting_time DESC);
```

### 3.2 Edge Agent SQLite Local Schema (Idempotent)
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- 1. Sync State Key-Value Table
CREATE TABLE IF NOT EXISTS sync_state (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- 2. Camera Identity Mappings (Local String -> Backend UUID)
CREATE TABLE IF NOT EXISTS camera_mappings (
    local_camera_id TEXT PRIMARY KEY,
    backend_uuid    TEXT NOT NULL,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- 3. Multi-Photo Cached Embeddings (Primary Key is ID, Indexed by Person)
CREATE TABLE IF NOT EXISTS cached_embeddings (
    id              TEXT PRIMARY KEY,
    person_id       TEXT NOT NULL,
    person_name     TEXT,
    embedding_data  BLOB NOT NULL,
    photo_url       TEXT,
    is_active       INTEGER DEFAULT 1 NOT NULL,
    synced_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cached_person ON cached_embeddings(person_id);
CREATE INDEX IF NOT EXISTS idx_cached_active ON cached_embeddings(is_active);

-- 4. Offline Durable Pending Sightings Queue
CREATE TABLE IF NOT EXISTS pending_sightings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id           TEXT NOT NULL,
    camera_id           TEXT NOT NULL,
    similarity_score    REAL NOT NULL,
    confidence_level    TEXT DEFAULT 'POSSIBLE',
    num_frames_matched  INTEGER DEFAULT 1,
    face_crop_path      TEXT NOT NULL,
    full_frame_path     TEXT NOT NULL,
    video_clip_path     TEXT,
    detected_at         TEXT NOT NULL,
    uploaded            INTEGER DEFAULT 0,
    retry_count         INTEGER DEFAULT 0,
    last_attempt_at     TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pending_upload ON pending_sightings(uploaded, retry_count);
```

---

## 4. Dependencies

### 4.1 Backend Requirements (`backend/requirements.txt`)
```text
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
sqlalchemy[asyncio]>=2.0.28
asyncpg>=0.29.0
alembic>=1.13.1
redis>=5.0.3
python-multipart>=0.0.9
pillow>=10.2.0
numpy>=1.26.0,<2.0.0
opencv-python-headless>=4.9.0.80
insightface>=0.7.3
onnxruntime>=1.17.1
firebase-admin>=6.5.0
cryptography>=42.0.5
python-jose[cryptography]>=3.3.0
httpx>=0.27.0
```

### 4.2 Edge Agent Requirements (`edge_agent/requirements.txt`)
```text
PySide6>=6.6.2
opencv-python>=4.9.0.80
numpy>=1.26.0,<2.0.0
onnxruntime>=1.17.1
insightface>=0.7.3
faiss-cpu>=1.7.4
scipy>=1.12.0
lapx>=0.5.5
httpx>=0.27.0
sseclient-py>=1.8.0
onvif-zeep>=0.2.12
wsdiscovery>=2.0.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
pillow>=10.2.0
psutil>=5.9.8
pytest>=8.1.1
pytest-asyncio>=0.23.5
```

### 4.3 Web Application (`web_app/package.json`)
```json
{
  "name": "find-missing-pep-web",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.6.8",
    "clsx": "^2.1.0",
    "firebase": "^10.9.0",
    "leaflet": "^1.9.4",
    "lucide-react": "^0.359.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.22.3",
    "tailwind-merge": "^2.2.2"
  },
  "devDependencies": {
    "@types/leaflet": "^1.9.8",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.3",
    "typescript": "^5.4.5",
    "vite": "^5.4.2"
  }
}
```

---

## 5. Containerization / Runtime

### 5.1 Backend Dockerfile (`backend/Dockerfile`)
```dockerfile
FROM python:3.11-slim

# Install system dependencies (Debian 12 Bookworm compatible: libgl1 + libglib2.0-0)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-warm and download InsightFace models into image during build
RUN mkdir -p /app/ai_models
RUN python -c "from insightface.app import FaceAnalysis; app = FaceAnalysis(name='buffalo_l', root='/app/ai_models', providers=['CPUExecutionProvider']); app.prepare(ctx_id=-1, det_size=(640, 640))"

# Copy source code
COPY . .
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]
```

### 5.2 Container Entrypoint (`backend/start.sh`)
```bash
#!/bin/bash
set -e

echo "=== FIND-MISSING-PEP Backend Starting ==="
echo "Host: ${HOST:-0.0.0.0}"
echo "Port: ${PORT:-8000}"
echo "Database URL: ${DATABASE_URL}"
echo "Redis URL: ${REDIS_URL}"
echo "Upload Directory: ${UPLOAD_DIR:-./uploads}"
echo "=========================================="

# Ensure upload directories exist
mkdir -p "${UPLOAD_DIR:-./uploads}/faces"
mkdir -p "${UPLOAD_DIR:-./uploads}/full_frames"
mkdir -p "${UPLOAD_DIR:-./uploads}/clips"

# Run database migrations
echo "Applying database migrations with Alembic..."
alembic upgrade head || echo "Warning: Alembic migration failed, continuing..."

# Start Uvicorn
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --workers 2
```

### 5.3 Port Ownership Map
| Service | Host Port | Container Port | Protocol | Purpose |
|---|---|---|---|---|
| PostgreSQL | 5432 | 5432 | TCP | Relational DB |
| Redis | 6379 | 6379 | TCP | Pub/Sub & Caching |
| Backend API | 8000 | 8000 | HTTP/SSE | REST & Event API |
| Web Application | 5173 | 80 / 5173 | HTTP | Frontend Portal |
| Edge Agent | N/A | N/A | Native Windows | PySide6 Desktop GUI |

---

## 6. Domain Config / AI Pipeline Architecture

The core research novelty relies on a five-stage computer vision pipeline designed to execute efficiently on standard multi-core CPUs without requiring dedicated GPUs:

```mermaid
flowchart LR
    A["RTSP Video Stream (15 FPS)"] --> B["Decoupled Sampler (5-10 FPS)"]
    B --> C["SCRFD Face Detection (det_10g.onnx)"]
    C --> D["ByteTrack + Landmark Kalman (STrack)"]
    D --> E{"Throttled Recognition? (Every 0.5s-1.0s)"}
    E -- No --> D
    E -- Yes --> F["ArcFace 512-D Embedding (w600k_r50.onnx)"]
    F --> G["FAISS IndexFlatIP Cosine Search"]
    G --> H["Candidate Dedup (Max Score per Person)"]
    H --> I["Temporal Verifier (N=3, Span=5.0s, Sim>=0.60)"]
    I --> J["Confirmed Match & Sighting Event"]
```

### 6.1 Architectural Resolution of the 5 Vision Paradoxes
1. **Decoupled Detection & Recognition**: Face detection and ByteTrack bounding box tracking execute at **10–15 FPS** to ensure small inter-frame displacements (<15px) and high IoU overlap (>0.7), preventing track loss. Expensive ArcFace vector inference is throttled to run at **1–2 FPS** per active track ID.
2. **Landmark-Carrying Track State**: `STrack` is extended to carry the 5 facial landmarks from the matched detection. When a track is predicted via Kalman filter without detection, landmark alignment is gracefully skipped rather than throwing an exception.
3. **Realistic Biometric Thresholds**: ArcFace produces inter-identity similarity scores between 0.35 and 0.48. Setting threshold at 0.42 causes an unbearable false alarm rate.
   - **Candidate Search Cutoff**: `0.50`
   - **Temporal Verification Threshold**: `0.60` (ensures FAR $\le 10^{-4}$)
   - **Low Confidence Flag**: `0.50–0.59` (Logged for manual review, no sound alarm)
4. **Pedestrian Transit Window**: Pedestrians traverse CCTV camera views within 2 to 5 seconds. Requiring 25 seconds for 5 observations is impossible. The temporal verifier requires:
   - **Window Size ($N$)**: `3` observations
   - **Max Time Span**: `5.0` seconds
   - **Mean Similarity**: $\ge 0.60$
   - **Alert Cooldown**: `300.0` seconds per `(track_id, person_id)`
5. **Single-Frame Candidate Deduplication**: When a missing person has multiple reference photos indexed in FAISS, search results are grouped by `person_id` taking `max(similarity)`. Only one observation per person is fed to the temporal verifier per frame.

---

## 7. Data Access Layer — CRUD

All database queries adhere to: single function = single query, fully async, strict typing.

### 7.1 Missing Person CRUD with DB-Level Filtering
```python
# backend/app/crud/missing_person.py
async def list_reports_by_user(
    db: AsyncSession,
    user_id: UUID,
    page: int = 1,
    per_page: int = 20,
    status_filter: Optional[str] = None,
) -> tuple[List[MissingPerson], int]:
    """Lists reports for a user with DB-level pagination and status filtering."""
    base_conditions = [MissingPerson.user_id == user_id]
    if status_filter:
        base_conditions.append(MissingPerson.status == status_filter)

    # 1. Total count query
    count_stmt = select(func.count(MissingPerson.id)).where(and_(*base_conditions))
    total_count = (await db.execute(count_stmt)).scalar() or 0

    # 2. Paginated results query
    offset = (page - 1) * per_page
    stmt = (
        select(MissingPerson)
        .where(and_(*base_conditions))
        .order_by(desc(MissingPerson.created_at))
        .offset(offset)
        .limit(per_page)
        .options(selectinload(MissingPerson.photos))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total_count
```

### 7.2 Incremental Sync with Soft-Delete Tombstones
```python
# backend/app/crud/face_embedding.py
async def get_sync_package(
    db: AsyncSession,
    since: Optional[datetime] = None,
) -> tuple[List[dict], List[str], datetime]:
    """Retrieves active embeddings added/updated since timestamp, plus deactivated IDs."""
    now = datetime.now(timezone.utc)
    
    # Active embeddings query
    active_stmt = select(FaceEmbedding, MissingPerson.full_name).join(
        MissingPerson, FaceEmbedding.person_id == MissingPerson.id
    ).where(
        FaceEmbedding.is_active.is_(True),
        MissingPerson.status == ReportStatus.ACTIVE.value,
    )
    if since:
        active_stmt = active_stmt.where(FaceEmbedding.updated_at >= since)
    
    active_rows = (await db.execute(active_stmt)).all()
    active_records = [
        {
            "id": str(emb.id),
            "person_id": str(emb.person_id),
            "person_name": name,
            "embedding": base64.b64encode(emb.embedding).decode("ascii"),
        }
        for emb, name in active_rows
    ]

    # Deactivated or closed person IDs query
    removed_ids: List[str] = []
    if since:
        tombstone_stmt = select(FaceEmbedding.id).where(
            or_(
                and_(FaceEmbedding.is_active.is_(False), FaceEmbedding.updated_at >= since),
                FaceEmbedding.person_id.in_(
                    select(MissingPerson.id).where(
                        MissingPerson.status.in_([ReportStatus.FOUND.value, ReportStatus.CLOSED.value]),
                        MissingPerson.updated_at >= since,
                    )
                )
            )
        )
        removed_ids = [str(r) for r in (await db.execute(tombstone_stmt)).scalars().all()]

    return active_records, removed_ids, now
```

---

## 8. Action / Tool Layer — Services

### 8.1 SSE Manager with Dual-Mode Pub/Sub (`backend/app/services/sse_manager.py`)
- In production with Redis: leverages `redis.asyncio.pubsub` across distributed worker instances.
- In local development without Redis: automatically falls back to in-memory `asyncio.Queue` listener sets with zero configuration changes.

### 8.2 Double-Buffered FAISS Index Pointer Swap (`edge_agent/ai/vector_search.py`)
- Prevents C++ segfaults (`SIGSEGV` / `0xC0000005`) during multi-threaded video stream reads.
- When `SyncWorker` updates the gallery, a new `IndexFlatIP` is constructed completely in memory, and the pointer is atomically swapped under a short mutex lock:
```python
new_index = faiss.IndexFlatIP(512)
new_index.add(embedding_matrix)
with self.lock:
    self.index = new_index
    self.person_ids = new_person_ids
```

### 8.3 Non-Blocking 15 FPS Circular Frame Buffer (`edge_agent/camera/circular_buffer.py`)
- Implements `collections.deque(maxlen=150)` holding consecutive JPEG-encoded or raw frames at native 15 FPS (10 seconds total).
- Upon confirmation from `TemporalVerifier`, dumps a 5-second video clip (`-2.5s` to `+2.5s` around match timestamp) to `./evidence/clips/`.

---

## 9. Orchestration / Entrypoint

### 9.1 Edge Agent Pipeline Architecture
The Edge Agent coordinates 4 concurrent thread classes using Qt signals and slots:
1. `CameraWorker` (1 per camera): Decodes RTSP, runs SCRFD detection and landmark-carrying ByteTrack at 15 FPS, throttles ArcFace recognition.
2. `SyncWorker` (Periodic): Contacts `GET /api/sync/embeddings`, updates SQLite, rebuilds and swaps FAISS pointer.
3. `UploadWorker` (Periodic / Event-driven): Flushes pending sightings from SQLite to `POST /api/sightings/` with exponential backoff.
4. `MainWindow` (UI Thread): Renders video frames with bounding boxes, emits audio alerts, displays forensic review dialog.

### 9.2 Backend Lifespan Management (`backend/app/main.py`)
- Enforces directory existence for uploads (`faces`, `full_frames`, `clips`).
- Validates `SECRET_KEY` length ($\ge 32$ bytes) and issues loud startup warnings in log if default development keys are active.
- Initializes Redis connection pool with graceful fallback.

---

## 10. API Layer — REST Contract

| Method | Endpoint | Auth | Purpose |
|---|---|:---:|---|
| `POST` | `/api/users/` | Bearer | Synchronize authenticated user profile from Firebase |
| `GET` | `/api/reports/` | Bearer | List user missing person reports with DB-level pagination |
| `POST` | `/api/reports/` | Bearer | Create case metadata and upload reference photos atomically |
| `GET` | `/api/reports/{id}` | Optional | Get full case details with reference photos and sightings |
| `PATCH`| `/api/reports/{id}/status`| Bearer | Update case status (`ACTIVE`, `FOUND`, `CLOSED`) |
| `POST` | `/api/sightings/` | Agent / Bearer | Submit verified sighting with face crop, snapshot, clip |
| `GET` | `/api/sightings/` | Bearer | List sightings for user's reports with triage status filter |
| `PATCH`| `/api/sightings/{id}/review` | Bearer | Review sighting (`CONFIRMED`, `REJECTED`) |
| `GET` | `/api/cameras/` | Bearer | List registered cameras with status |
| `POST` | `/api/cameras/register` | Agent Secret | Register or update camera stream mapping |
| `GET` | `/api/sync/embeddings` | Agent Secret | Fetch incremental gallery package with tombstones |
| `GET` | `/api/sse/events` | Query Token | Real-time SSE alert stream for web/mobile apps |
| `GET` | `/health` | None | Health and dependency check |

---

## 11. Frontend / UI Spec

### 11.1 Web Application (React + Vite + TailwindCSS)
- **Design Language**: Modern, high-density forensic dark-theme (`bg-slate-950`, `border-slate-800`, vibrant indigo/cyan accents).
- **Core Screens**:
  1. `DashboardPage`: Case counters, active cameras count, recent verified sightings marquee.
  2. `ReportPersonPage`: Multi-step case intake with drag-and-drop photo uploader, client-side Canvas auto-compression to $<1\text{MB}$, and instant face preview.
  3. `SightingsReviewPage`: Forensic split-screen viewer comparing camera face crop with reference photo, showing cosine similarity score, camera location, and timestamp.
  4. `MapTimelinePage`: Interactive Leaflet map plotting sequential sighting breadcrumbs with directional vectors and camera markers.
  5. `CaseDetailsPage`: Case history, associated evidence gallery, status toggle controls.

### 11.2 Edge Agent Desktop GUI (PySide6)
- **Multi-Camera Grid**: 1x1, 2x2 responsive layout displaying active RTSP video feeds with color-coded bounding boxes:
  - Green: Tracked person (no match).
  - Amber: Potential candidate ($0.50 \le \text{sim} < 0.60$).
  - Flashing Red: Confirmed temporal match ($\text{sim} \ge 0.60, N \ge 3$).
- **Alert Popup**: Non-blocking modal showing candidate side-by-side, playing audio chime (`alert_chime.wav`), and auto-dismissing after 15 seconds.

---

## 12. Critical Architecture Rules — DO NOT DEVIATE

> [!IMPORTANT]
> The following 26 rules address the exact bugs, runtime blockers, and mathematical paradoxes uncovered in the audit. Every rule is formatted as WRONG vs CORRECT.

### Rule 1: Debian 12 Dockerfile Graphic Libraries
```dockerfile
# ❌ WRONG: libgl1-mesa-glx was deleted in Debian 12 (Bookworm)
RUN apt-get update && apt-get install -y libgl1-mesa-glx

# ✅ CORRECT: Use libgl1 and libglib2.0-0
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*
```

### Rule 2: InsightFace Model Pre-Warming in Docker
```dockerfile
# ❌ WRONG: FaceAnalysis(...) only sets metadata; does not download weights
RUN python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', root='/app/ai_models')"

# ✅ CORRECT: Must call .prepare() to trigger ONNX weight downloads during build
RUN python -c "from insightface.app import FaceAnalysis; app = FaceAnalysis(name='buffalo_l', root='/app/ai_models', providers=['CPUExecutionProvider']); app.prepare(ctx_id=-1, det_size=(640, 640))"
```

### Rule 3: ByteTrack LAP Solver on Modern Windows
```text
# ❌ WRONG: lap has no wheels on Python 3.10+ and fails C++ compilation on Windows
lap>=0.4.0

# ✅ CORRECT: Use lapx which provides modern pre-built binary wheels
lapx>=0.5.5
```

### Rule 4: Kalman Filter vs Deprecated NumPy Float
```python
# ❌ WRONG: filterpy uses np.float, which throws AttributeError on numpy>=1.24
import filterpy.kalman
self.kf = filterpy.kalman.KalmanFilter(dim_x=8, dim_z=4)

# ✅ CORRECT: Vendor or use standard np.float32/float64 Kalman Filter
self._motion_mat = np.eye(8, 8, dtype=np.float32)
```

### Rule 5: Asynchronous Redis Client Import
```python
# ❌ WRONG: aioredis was sunset and conflicts with modern redis-py
import aioredis
redis = await aioredis.from_url(settings.REDIS_URL)

# ✅ CORRECT: Import directly from redis.asyncio
import redis.asyncio as redis
client = redis.from_url(settings.REDIS_URL, decode_responses=True)
```

### Rule 6: FAISS Vector Search Multi-Thread Concurrency
```python
# ❌ WRONG: Resetting FAISS in-place causes C++ segfault in camera threads
self.index.reset()
for pid, emb in data:
    self.index.add(emb)

# ✅ CORRECT: Double-buffering atomic pointer swap under threading.Lock
new_index = faiss.IndexFlatIP(512)
if len(embeddings) > 0:
    new_index.add(np.ascontiguousarray(embeddings, dtype=np.float32))
with self.lock:
    self.index = new_index
    self.person_ids = new_person_ids
```

### Rule 7: Stream Frame Rate vs ByteTrack Kalman Association
```python
# ❌ WRONG: 1 FPS causes IoU = 0.0 for walking pedestrians; tracks break every frame
stream.set_sample_fps(1.0)
tracks = tracker.update(detector.detect(frame))

# ✅ CORRECT: Track at 10-15 FPS, throttle ArcFace recognition to 1 FPS
if frame_idx % 1 == 0:  # 15 FPS
    tracks = tracker.update(detector.detect(frame))
for track in tracks:
    if time.time() - track.last_recog_time >= 0.5:
        embedding = recognizer.extract(frame, track.landmarks)
```

### Rule 8: Pedestrian Transit Speed vs Temporal Window
```python
# ❌ WRONG: Requiring 5 observations at 5-second intervals requires 25s continuous tracking
window_size = 5
interval = 5.0  # Total = 25 seconds (pedestrian crossed FOV in 3 seconds!)

# ✅ CORRECT: 3 observations within a 5.0-second rolling window
window_size = 3
max_time_span = 5.0
threshold = 0.60
```

### Rule 9: Biometric Match Thresholds
```python
# ❌ WRONG: 0.42 similarity generates hundreds of false alarms per hour
if score >= 0.42:
    trigger_alarm()

# ✅ CORRECT: 0.60 minimum cosine similarity for automated alert
if score >= 0.60:
    trigger_alarm()
elif score >= 0.50:
    log_candidate_for_manual_review()
```

### Rule 10: Single-Frame Multi-Candidate Deduplication
```python
# ❌ WRONG: Adding duplicate candidates from multiple reference photos in 1 frame
for pid, score in candidates:
    verifier.check_match(track.id, pid, score)  # Fills window in 1 frame!

# ✅ CORRECT: Group by person_id and take max score per frame
best_candidates = {}
for pid, score in candidates:
    if pid not in best_candidates or score > best_candidates[pid]:
        best_candidates[pid] = score
for pid, score in best_candidates.items():
    verifier.check_match(track.id, pid, score)
```

### Rule 11: SQLite Cached Embeddings Schema
```sql
-- ❌ WRONG: person_id as PK fails when a person has multiple photos
CREATE TABLE cached_embeddings (person_id TEXT PRIMARY KEY, ...);

-- ✅ CORRECT: UUID id as PK, index on person_id
CREATE TABLE IF NOT EXISTS cached_embeddings (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL,
    embedding_data BLOB NOT NULL,
    synced_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cached_person ON cached_embeddings(person_id);
```

### Rule 12: Incremental Sync Gallery Tombstones
```python
# ❌ WRONG: Only checking created_at misses marked-found or closed cases
stmt = select(FaceEmbedding).where(FaceEmbedding.created_at >= since)

# ✅ CORRECT: Query updated_at and compute removed_ids from tombstones
stmt = select(FaceEmbedding).where(FaceEmbedding.updated_at >= since)
removed_ids = await get_tombstone_ids(since)
```

### Rule 13: PostgreSQL Sighting Foreign Key Deletion Cascade
```sql
-- ❌ WRONG: Missing cascade raises foreign_key_violation when deleting person
person_id UUID NOT NULL REFERENCES missing_persons(id)

-- ✅ CORRECT: Specify ON DELETE CASCADE
person_id UUID NOT NULL REFERENCES missing_persons(id) ON DELETE CASCADE
```

### Rule 14: Camera Identity Resolution (String vs UUID)
```python
# ❌ WRONG: Sending local "CAM-01" fails foreign key validation against UUID
sighting_payload = {"camera_id": "CAM-01", ...}

# ✅ CORRECT: Resolve local camera string to backend UUID via local mapping table
backend_uuid = db.get_camera_uuid("CAM-01")
sighting_payload = {"camera_id": backend_uuid, ...}
```

### Rule 15: Static File Serving Mount
```python
# ❌ WRONG: Not mounting upload directory returns 404 for all image thumbnails
# (omitted static mount)

# ✅ CORRECT: Mount uploads directory in FastAPI
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
```

### Rule 16: Strict AES-256 Key Length Validation
```python
# ❌ WRONG: Silently padding short keys weakens encryption
key = raw_key.ljust(32, b'\0')[:32]

# ✅ CORRECT: Validate exact 32-byte requirement and raise error
if len(key_bytes) != 32:
    raise ValueError(f"AES-256 requires exactly 32 bytes, got {len(key_bytes)}")
```

### Rule 17: Mock Auth Token Gate Behind Environment
```python
# ❌ WRONG: Mock token bypass active in production
if token.startswith("test-"): return mock_user

# ✅ CORRECT: Restrict mock tokens strictly to DEBUG mode
if token.startswith("test-") or token.startswith("mock-"):
    if not settings.DEBUG:
        raise HTTPException(status_code=401, detail="Mock tokens forbidden in production")
    return mock_user
```

### Rule 18: CORS Configuration Security
```python
# ❌ WRONG: Wildcard origin with allow_credentials=True is invalid & insecure
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)

# ✅ CORRECT: Explicitly enumerate allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Rule 19: Database-Level Status Filtering for Pagination
```python
# ❌ WRONG: Filtering in Python after fetching limit breaks total count & pagination
items = await get_page(limit=20)
items = [i for i in items if i.status == status]  # Broken!

# ✅ CORRECT: Push filter directly into SQLAlchemy query
stmt = select(MissingPerson).where(MissingPerson.status == status).offset(offset).limit(limit)
```

### Rule 20: SSE Dependency Function Signature
```python
# ❌ WRONG: Calling get_current_user with missing parameters triggers TypeError
user = await get_current_user(auth_header=header, db=db)

# ✅ CORRECT: Provide all parameters matching function definition
user = await get_current_user(auth_header=header, x_firebase_token=None, db=db)
```

### Rule 21: User Registration Route Auth Guard
```python
# ❌ WRONG: Unauthenticated user creation allows creating arbitrary profiles
@router.post("/")
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)): ...

# ✅ CORRECT: Enforce authentication guard
@router.post("/")
async def register(
    data: UserCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
): ...
```

### Rule 22: Evidence Image Compression
```typescript
// ❌ WRONG: Uploading uncompressed 10MB camera frames over mobile networks
await upload(file);

// ✅ CORRECT: Compress client-side via Canvas to max 1280px & 0.8 JPEG quality
const compressedBlob = await compressImage(file, { maxWidth: 1280, quality: 0.8 });
await upload(compressedBlob);
```

### Rule 23: Startup Security Diagnostics
```python
# ❌ WRONG: Starting silently with insecure default secret key
# (no warnings emitted)

# ✅ CORRECT: Emit loud logger.warning if running with known default key
if settings.SECRET_KEY.startswith("b4a9f3e1c2d5e7"):
    logger.warning("SECURITY ALERT: Running with default SECRET_KEY! Change immediately in production.")
```

### Rule 24: Landmark Preservation in STrack
```python
# ❌ WRONG: Assuming STrack contains landmarks attribute by default
aligned = aligner.align(frame, track.landmarks)  # AttributeError!

# ✅ CORRECT: Safely check if current detection landmarks exist
if hasattr(track, "current_landmarks") and track.current_landmarks is not None:
    aligned = aligner.align(frame, track.current_landmarks)
```

### Rule 25: Video Ring Buffer Lifecycle
```python
# ❌ WRONG: Writing video clip from 1 FPS frames creates corrupt unplayable files
# (dumping 1 FPS frames into cv2.VideoWriter)

# ✅ CORRECT: Write continuous 15 FPS frames from circular buffer
writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 15, (w, h))
for f in circular_buffer:
    writer.write(f)
writer.release()
```

### Rule 26: Graceful SSE Local Fallback
```python
# ❌ WRONG: Crashing when Redis connection fails in development
await redis_client.ping()

# ✅ CORRECT: Catch ConnectionError and transparently switch to in-memory queue
try:
    await redis_client.ping()
except Exception:
    logger.warning("Redis unavailable. Operating in local in-memory pub/sub mode.")
    self._mode = "memory"
```

---

## 13. Deployment

### 13.1 Local Development Deployment (Option A: Native Python + Vite)

#### Step 1: Database and Cache (Docker)
```bash
docker run -d --name find-postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=find_missing_pep postgres:16-alpine
docker run -d --name find-redis -p 6379:6379 redis:7-alpine
```

#### Step 2: Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -c "from insightface.app import FaceAnalysis; app = FaceAnalysis(name='buffalo_l', root='../ai_models'); app.prepare(ctx_id=-1, det_size=(640, 640))"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

#### Step 3: Web App Setup
```bash
cd ../web_app
npm install
npm run dev
```

#### Step 4: Edge Agent Setup (Windows)
```bash
cd ../edge_agent
python -m venv venv_edge
venv_edge\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 13.2 Expected Startup Log Output
```text
INFO:     Initializing FIND-MISSING-PEP Backend Services...
INFO:     Verified upload directory structure at: ./uploads
INFO:     Connected to Redis Pub/Sub successfully.
INFO:     Loaded database connection pool (PostgreSQL 16)
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## 14. Known Gotchas Table

| Symptom | Root Cause | Fix |
|---|---|---|
| `docker build` fails with `Package libgl1-mesa-glx has no installation candidate` | Debian 12 removed `libgl1-mesa-glx` | Replace with `libgl1` and `libglib2.0-0` in Dockerfile. |
| `AttributeError: module 'numpy' has no attribute 'float'` | `numpy>=1.24` removed deprecated alias used by `filterpy` | Use vendored modernized Kalman Filter with `np.float32`. |
| `lap` fails to install on Windows with Visual C++ error | Abandoned package without modern binary wheels | Switch to `lapx>=0.5.5` in requirements. |
| Qt Desktop Edge Agent crashes abruptly without traceback | Concurrent read/write on FAISS index during camera search | Implement atomic double-buffering pointer swap with `threading.Lock`. |
| Zero sightings ever trigger for walking people | 1 FPS tracking broke Kalman filter + 25s window required | Track at 15 FPS, reduce temporal window to 3 observations in 5 seconds. |
| Hundreds of false alarms per hour on strangers | Similarity threshold set at 0.42 (too low for ArcFace) | Raise temporal verification threshold to 0.60. |
| Sighting upload fails with SQLite constraint error | `cached_embeddings` defined with `person_id` as PRIMARY KEY | Change PRIMARY KEY to `id` (UUID) and add index on `person_id`. |
| Deleted/Found persons continue alerting on edge | Incremental sync did not track deactivations | Add soft-delete tombstone tracking to sync endpoint. |
| Deleting a person fails with FK violation | Table `sightings` lacked `ON DELETE CASCADE` | Alter table to add `ON DELETE CASCADE`. |
| SSE notifications never arrive in local dev | SSE manager hung waiting for unavailable Redis | Add in-memory `asyncio.Queue` fallback. |

---

## 15. Reference Data

### 15.1 System Status Enums
```python
class ReportStatus(str, Enum):
    PROCESSING = "PROCESSING"
    ACTIVE = "ACTIVE"
    FOUND = "FOUND"
    CLOSED = "CLOSED"

class SightingStatus(str, Enum):
    UNCONFIRMED = "UNCONFIRMED"
    VERIFIED = "VERIFIED"
    FALSE_ALARM = "FALSE_ALARM"

class ConfidenceLevel(str, Enum):
    POSSIBLE = "POSSIBLE"
    CONFIRMED = "CONFIRMED"
```

### 15.2 Biometric Model Parameters
- **Detection Model**: `det_10g.onnx` (SCRFD, input: 640×640×3, output: 5 landmarks + bounding box).
- **Recognition Model**: `w600k_r50.onnx` (ArcFace ResNet-50, input: 112×112×3, output: 512-D float32 normalized vector).
- **Metric**: Cosine Similarity via FAISS Inner Product (`IndexFlatIP`).

---

## 16. Cost / Ops Reference

### Hardware Sizing (Standard Edge PC without GPU)
- **CPU**: Intel Core i5/i7 (8th Gen+) or AMD Ryzen 5/7 (6–8 cores).
- **RAM**: 16 GB DDR4.
- **Storage**: 500 GB NVMe SSD (accommodates 100,000+ cached embeddings and 30 days of sighting clips).
- **Camera Workload**: 1 to 4 concurrent 1080p RTSP streams at 15 FPS consumes $\approx 45\%\text{--}65\%$ CPU utilization.

---

## 17. External API Integration Reference

### 17.1 Firebase Token Verification (Backend)
```python
from firebase_admin import auth

def verify_firebase_jwt(token: str) -> dict:
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase Token: {exc}")
```

### 17.2 Leaflet Breadcrumb GPS Map (Web App)
```tsx
import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';

export const SightingMap = ({ sightings }) => {
  const positions = sightings.map(s => [s.latitude, s.longitude]);
  return (
    <MapContainer center={positions[0] || [28.6139, 77.2090]} zoom={14} className="h-96 w-full rounded-xl">
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {sightings.map(s => (
        <Marker key={s.id} position={[s.latitude, s.longitude]}>
          <Popup>{s.person_name} seen at {new Date(s.sighting_time).toLocaleTimeString()}</Popup>
        </Marker>
      ))}
      <Polyline positions={positions} color="#6366f1" dashArray="6, 8" />
    </MapContainer>
  );
};
```

---

## 18. One-Time Setup Sequence

1. **Initialize Git Repository and verify directory paths**:
   ```bash
   python -c "import os; os.makedirs('uploads/faces', exist_ok=True); os.makedirs('uploads/full_frames', exist_ok=True); os.makedirs('uploads/clips', exist_ok=True); os.makedirs('evidence/clips', exist_ok=True)"
   ```
2. **Download and Cache AI Models**:
   ```bash
   python scripts/download_models.py
   ```
3. **Execute Database Migrations**:
   ```bash
   cd backend && alembic upgrade head
   ```
4. **Seed System with Realistic Test Cases**:
   ```bash
   python scripts/seed_database.py
   ```
5. **Run Full Integration Test Suite**:
   ```bash
   pytest backend/tests/ -v
   pytest edge_agent/tests/ -v
   ```
6. **Launch End-to-End Simulation**:
   ```bash
   python run_all.py
   ```
