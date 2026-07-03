# 🦅 Eagle Vision — Hyper-Local Retail Discovery Platform (Lamba)

> Connect consumers with physical inventory in nearby shops using **semantic text search**, **visual image search**, and **geospatial proximity ranking**.

This repository is organized as a unified workspace. It contains a containerized **FastAPI** backend with **PostGIS** and **Elasticsearch** (for AI vector search), and a **React Native (Expo)** mobile application.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    React Native (Expo)                          │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌──────────────┐ │
│  │  Search   │  │   Map    │  │  Product   │  │  Merchant    │ │
│  │  Screen   │  │  View    │  │  Detail    │  │  Dashboard   │ │
│  └─────┬─────┘  └─────┬────┘  └─────┬──────┘  └──────┬───────┘ │
│        └───────────────┴─────────────┴─────────────────┘        │
│                         HTTP / REST                             │
│  ───────────────────────────────┬───────────────────────────────  │
│                                 ▼ (Dynamic IP Resolution)       │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │                       FastAPI Backend                       │ │
│ │  ┌──────┐  ┌────────────┐  ┌────────────┐  ┌───────────────┐ │ │
│ │  │ Auth │  │   Search   │  │  Products  │  │    Shops      │ │ │
│ │  │ JWT  │  │ text/image │  │  CRUD+CSV  │  │    CRUD       │ │ │
│ │  └──────┘  └──────┬─────┘  └──────┬─────┘  └───────────────┘ │ │
│ │                   │               │                          │ │
│ │            ┌──────▼──────┐  ┌─────▼──────┐                   │ │
│ │            │    CLIP     │  │  Indexer   │                   │ │
│ │            │  Encoder    │  │  Service   │                   │ │
│ │            │ (512-d vec) │  │            │                   │ │
│ │            └──────┬──────┘  └─────┬──────┘                   │ │
│ └───────────────────┼───────────────┼──────────────────────────┘ │
└─────────────────────┼───────────────┼────────────────────────────┘
                      │               │
      ┌───────────────▼───┐    ┌──────▼──────────┐
      │  Elasticsearch    │    │  PostgreSQL     │
      │  kNN + geo_point  │    │  + PostGIS      │
      │  (embeddings)     │    │  (relational)   │
      └───────────────────┘    └─────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology | Description |
| :--- | :--- | :--- |
| **Mobile** | React Native + Expo (TypeScript) | Expo Router, Expo Camera, SecureStore, Native Maps |
| **Backend** | FastAPI (Python 3.11+) | Asynchronous routing, lifespan index initialization |
| **AI Model** | CLIP `clip-ViT-B-32` | Cross-modal text-and-image vector embedding generation |
| **Vector Search** | Elasticsearch 8.x | HNSW kNN search combined with strict geospatial pre-filtering |
| **Database** | PostgreSQL 16 + PostGIS 3.4 | Geolocation mapping, relational tables, async SQLAlchemy |
| **Orchestrator** | npm workspace & Docker Compose | Simplified dev workflow and isolated infrastructure |

---

## ⚡ Quick Start Guide (One-Command Launch)

The project has been organized with a **Root Orchestrator** to make running and testing the backend and frontend extremely simple. You do not need to install Python or set up PostgreSQL locally; everything is managed automatically.

### 📋 Prerequisites

1. **Docker Desktop** installed and running on your computer.
2. **Node.js (v18+)** installed.
3. **Expo Go** app installed on your physical mobile device ([iOS App Store](https://apps.apple.com/app/expo-go/id984021595) or [Android Play Store](https://play.google.com/store/apps/details?id=host.exp.exponent)).

---

### 🚀 Running the Stack

Open your terminal in the project root (`c:\Users\alisa\Downloads\eagle_vision`) and follow these steps:

#### Step 1: Start Infrastructure & Backend API
Spin up PostgreSQL, PostGIS, Elasticsearch, and the FastAPI API server all at once in the background:
```bash
npm run backend:up
```

#### Step 2: Seed Sample Data
Once the containers are running and healthy (takes a few seconds on first boot to download CLIP), run the seeder:
```bash
npm run backend:seed
```
*This creates 22 sample merchants/markets around **As-Salt, Balqa, Jordan** (~32.04°N 35.73°E) and ~25 products per market (~550 MarketItems) with auto-generated CLIP/MiniLM embeddings in pgvector and Elasticsearch.*

#### Step 3: Run Mobile on Expo Go
Start the React Native app. This command **automatically detects your computer's local network IP** and configures the mobile client to point directly to your backend.
```bash
npm run mobile:start
```

---

## 📱 Testing on Expo Go

Testing a physical phone with a local backend server can be challenging due to networking constraints. Eagle Vision solves this with automated configuration.

### 📶 Method A: Local Wi-Fi Mode (Recommended & Fastest)

1. Make sure both your **computer** and your **mobile phone** are connected to the **same Wi-Fi network**.
2. Run the start command:
   ```bash
   npm run mobile:start
   ```
3. A large QR code will print in your terminal.
4. **Scan the QR Code**:
   - **Android**: Open the **Expo Go** app and tap "Scan QR Code".
   - **iOS**: Open your physical camera app, scan the code, and tap the link to open in **Expo Go**.
5. Your app will load, and it will dynamically fetch products and perform searches against your running Docker backend!

> [!WARNING]
> **Windows Firewall / Network Troubleshooting**
> If the app hangs on `Connecting...` or throws a network error:
> 1. Double check that your Wi-Fi network profile on Windows is set to **Private** (so devices on the network can discover your computer).
> 2. Ensure your computer's firewall allows incoming connections on port `8000` (FastAPI) and `8081` (Expo packager).

---

### 📡 Method B: Tunnel Mode (Zero-Config Fallback)

If your Wi-Fi router isolates devices (common on university, corporate, or public Wi-Fi), or if you are testing on mobile data, use **Tunnel Mode**:

1. Run the tunnel command:
   ```bash
   npm run mobile:tunnel
   ```
2. Expo will create a secure, public tunnel (via `ngrok`) for both the frontend bundle and the backend API connection.
3. Scan the QR code as usual. The connection will succeed regardless of what network your phone is on!

---

## 🧪 Testing the API directly

You can also test the containerized FastAPI endpoints directly from your computer using `curl` or by visiting the interactive docs at `http://localhost:8000/docs`.

### 1. Sign up a Customer
```bash
# Sign-up triggers a mock SMS/email verification code (printed in the API logs).
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test12345","user_type":"customer","full_name":"Test User"}'

# Verify with the 6-digit code from the API logs (replace <USER_ID> and <CODE>).
curl -X POST http://localhost:8000/api/v1/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"user_id":"<USER_ID>","verification_code":"<CODE>"}'

# Sign in to obtain a JWT.
curl -X POST http://localhost:8000/api/v1/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email_or_phone":"test@example.com","password":"test12345"}'
```

### 2. Semantic text search (around the seeded markets in As-Salt)
```bash
curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT_TOKEN>" \
  -d '{"query":"soothing herbal tea","latitude":32.0385,"longitude":35.7275,"filters":{"max_distance_km":5.0}}'
```

### 3. Nearby markets
```bash
curl -X GET "http://localhost:8000/api/v1/customer/near-markets?latitude=32.0385&longitude=35.7275&radius_km=5.0" \
  -H "Authorization: Bearer <YOUR_JWT_TOKEN>"
```

---

## 🧮 Hybrid Ranking Formula

Search results are dynamically ranked using a weighted combination of semantic relevance and geographic proximity:

$$\text{hybrid\_score} = 0.7 \times \text{cosine\_similarity} + 0.3 \times \left(1 - \frac{\text{distance\_km}}{\text{max\_radius\_km}}\right)$$

- **Semantic Score (70%)**: Cosine similarity between query embedding and product embedding (pgvector).
- **Proximity Score (30%)**: Normalized inverse distance to the shop.

> **Local shop search exception:** when the request includes `market_id` (a request scoped to a single shop), the geo-proximity term is meaningless, so the score collapses to **100% semantic** (`final_score = boosted_semantic_score`).

---

## 💡 Key Design Decisions

1. **CLIP for Cross-Modal Search**: Both text and images are encoded into the same 512-dimensional vector space, enabling a photo of green tea to match the text "organic matcha green tea".
2. **Elasticsearch over Dedicated Vector DB**: For MVP scale (<1M products), ES 8.x kNN with HNSW handles vector + geo + text filtering in a single query.
3. **Embeddings in pgvector (PostgreSQL)**: Product text & image embeddings live in PostgreSQL via `pgvector` (`GlobalItem.text_embedding` 384-d MiniLM, `image_embedding` 512-d CLIP). The hybrid query fuses cosine similarity, lexical ILIKE fallback, PostGIS geo-distance, and faceted filters in a single SQL statement. Elasticsearch is still kept in sync by the indexer service for auxiliary full-text/analytics, but the live customer-facing search reads pgvector.
4. **Pre-filtering Strategy**: The PostGIS `ST_DWithin` filter is applied in the same query as the vector ranking, so only items within the requested radius are scored.

---

## 📂 Project Structure

```
eagle_vision/
├── package.json         # Root workspace & orchestration scripts
├── scripts/
│   └── start-mobile.js  # Node.js IP detector & Expo launcher
├── docker-compose.yml   # Multi-container local infra configuration
├── backend/
│   ├── app/
│   │   ├── main.py      # FastAPI entry + lifespan (index initialization)
│   │   ├── config.py    # Pydantic Settings validation
│   │   ├── database.py  # Async SQLAlchemy connection
│   │   ├── es_client.py # Elasticsearch vector index management
│   │   ├── seed.py      # Sample data seeder
│   │   ├── models/      # SQLAlchemy ORM models (PostGIS/User/Product)
│   │   ├── schemas/     # Pydantic validation schemas
│   │   ├── api/         # FastAPI router endpoints (Auth/Search/Shops)
│   │   └── services/    # Business logic & CLIP embedding service
│   ├── requirements.txt
│   └── Dockerfile
└── mobile/
    ├── app/             # Expo Router screens (Auth, Customer, Merchant)
    ├── components/      # Reusable styled UI components
    ├── services/        # Central API Client (dynamic IP resolution)
    └── constants/       # Global styling theme system
```
