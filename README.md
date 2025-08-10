# Integrations Technical Assessment

A full-stack, production-ready template for integrating with third-party SaaS platforms (Airtable, Notion, HubSpot, and Redis-backed OAuth credential storage) using **FastAPI** (backend) and **React** (frontend).

---

## 🚀 Features

- **Modular OAuth2 Integration**: Easily add new providers (Airtable, Notion, HubSpot, etc.)
- **Secure Credential Storage**: Uses Redis with TTL for ephemeral token storage
- **Clean, Scalable Architecture**: Separation of concerns, type hints, docstrings, and error handling
- **Frontend-Backend Demo**: End-to-end OAuth flow with popup, token exchange, and data fetch

---

## 🗂️ Project Structure

```
integrations_technical_assessment/
│
├── backend/
│   ├── integrations/         # Integration logic (airtable.py, notion.py, hubspot.py, etc.)
|   |── tests/                # Unit tests
│   ├── utils/                # Utility modules (env.py)
│   ├── main.py               # FastAPI entrypoint
│   ├── redis_client.py       # Async Redis client
│   ├── requirements.txt
|   ├── .env.example
│   ├── README.md
│   ├── .gitignore
│   ├── Dockerfile
│   └── docker-compose.yml
│
└── frontend/
    ├── src/
    │   ├── integrations/     # React components for each integration
    │   ├── components/       # Shared UI components
    │   └── ...
    ├── public/
    └── package.json
```

---

## ⚡ Quickstart

### 1. Clone & Configure

```sh
git clone <repo-url>
cd integrations_technical_assessment
cp backend/.env.example backend/.env
# Fill in your .env with client IDs/secrets for each integration
```

### 2. Start the Backend

```sh
cd backend
# make a venv and work on that [preferred]
pip install -r requirements.txt
docker-compose up -d # for starting the redis-instance [ensure docker engine is running]
uvicorn main:app --reload
```

- Backend: [http://localhost:8000](http://localhost:8000)
- Redis: [localhost:6379](redis://localhost:6379)

### 3. Start the Frontend

```sh
cd ../frontend
npm install
npm run start
```

- Frontend: [http://localhost:3000](http://localhost:3000)

---

## 🔑 Environment Variables

Create a `.env` file in `backend/`:

```env
# Airtable
AIRTABLE_CLIENT_ID=your_airtable_client_id
AIRTABLE_CLIENT_SECRET=your_airtable_client_secret
AIRTABLE_REDIRECT_URI=http://localhost:8000/integrations/airtable/oauth2callback

# Notion
NOTION_CLIENT_ID=your_notion_client_id
NOTION_CLIENT_SECRET=your_notion_client_secret
NOTION_REDIRECT_URI=http://localhost:8000/integrations/notion/oauth2callback

# HubSpot
HUBSPOT_CLIENT_ID=your_hubspot_client_id
HUBSPOT_CLIENT_SECRET=your_hubspot_client_secret
HUBSPOT_REDIRECT_URI=http://localhost:8000/integrations/hubspot/oauth2callback

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
```

---

### Unit Testing Integrations

```sh
cd backend

# Run all tests
pytest backend/tests/

# Run specific test file
pytest backend/tests/test_hubspot.py
```

- Backend: [http://localhost:8000](http://localhost:8000)
- Redis: [localhost:6379](redis://localhost:6379)

---

## 🛠️ Integrations

### Airtable, Notion, HubSpot

- **OAuth2 Authorization**: Secure, popup-based flow
- **Token Exchange & Storage**: Tokens stored in Redis with expiry
- **Data Fetch**: Fetches sample data (e.g., Airtable bases, Notion pages, HubSpot contacts)
- **Extensible**: Add new integrations by following the pattern in `backend/integrations/`

---

## 🧑‍💻 Development

- **Backend**: FastAPI, async/await, type hints, docstrings, error handling
- **Frontend**: React, modular components, popup OAuth, clean UI

---

## 🛡️ Security & Production Notes

- **No secrets in code**: All credentials via `.env`
- **Redis TTL**: Tokens are ephemeral, not persisted long-term
- **Error Handling**: All external calls wrapped in try/except
- **Non-root Docker**: (Recommended) Add a non-root user in Dockerfile for extra security
- **Dependencies**: Regularly update dependencies and scan Docker images for vulnerabilities

---

## 📚 Documentation

- **OAuth Flow**: See `backend/integrations/airtable.py`, `notion.py`, `hubspot.py`
- **Frontend Flow**: See `frontend/src/integration-form.js`, `frontend/src/integrations/`
- **IntegrationItem**: Standardized data model for all integrations

---

## 📝 How to Add a New Integration

1. Create a new file in `backend/integrations/`
2. Implement OAuth endpoints and data fetch logic
3. Add UI in `frontend/src/integrations/`
4. Update dropdowns/forms in `frontend/src/integration-form.js`

---

## 🧩 Known Issues & Improvements

- HubSpot and Slack integrations are in progress
- Add more robust unit/integration tests
- Add healthchecks to Docker Compose
- Use a non-root user in Dockerfile for extra security

---

## 📹 Demo

See the included screen recording for a walkthrough of the OAuth flow and data fetch.

---

## © 2025 Srisailam Kakurala
