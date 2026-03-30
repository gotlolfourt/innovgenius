# 🏦 NexaBank — Intelligent Onboarding System (v2)

An AI-powered bank account onboarding platform with KYC verification, biometric checks, risk assessment, and an admin review portal — all in one full-stack application.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Default Credentials](#default-credentials)
- [API Reference](#api-reference)
- [Onboarding Flow](#onboarding-flow)
- [Risk Engine](#risk-engine)
- [AI Chat (ARIA)](#ai-chat-aria)
- [Admin Panel](#admin-panel)
- [Screenshots](#screenshots)

---

## Overview

NexaBank's onboarding system lets customers open a bank account entirely online via a guided KYC (Know Your Customer) flow. An AI assistant called **ARIA** guides users through each step, answers banking questions, and provides a conversational experience. Admins can review, approve, or reject applications through a dedicated dashboard.

---

## ✨ Features

### Customer-Facing
- **User Registration & Login** — Email/password authentication with session management
- **Demo / Guest Mode** — Try the platform without creating an account
- **Conversational AI Onboarding** — ARIA (powered by Claude) guides you through KYC naturally
- **Step-by-step KYC flow** — Name → DOB → Email → Phone → Document → Selfie → OTP
- **Document Upload** — Supports Aadhaar, PAN, and Passport (PNG, JPG, PDF)
- **OCR Extraction** — Automatically reads name, DOB, and ID number from uploaded documents
- **Selfie / Biometric Verification** — Face score computed for identity match
- **OTP Verification** — Confirms mobile/email contact details
- **Chat History** — Full conversation history is saved and restorable per session
- **Multiple Applications** — Users can track all their application sessions

### Admin-Facing
- **Secure Admin Login** — Role-based access (superadmin / reviewer)
- **Applications Dashboard** — Filter by status, risk level, or search by name/email
- **Application Detail View** — Full audit trail, documents, OCR results, chat transcript, biometrics
- **Manual Decisions** — Approve, Reject, Request More Info, or set Pending
- **AI Override Tracking** — Flags when admin decisions differ from AI recommendation
- **Stats Dashboard** — Total, approved, pending, escalated, high/medium/low risk counts
- **Audit Log** — Every action logged with timestamp, actor, and detail
- **Document & Selfie Viewer** — Secure access for admins only

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Database | SQLite (WAL mode) |
| AI Chat | Anthropic Claude API (`claude-opus-4-6`) |
| OCR | Tesseract (via `pytesseract` + `Pillow`) |
| Frontend | HTML, CSS, JavaScript, Bootstrap |
| Auth | Flask Sessions + SHA-256 password hashing |
| File Storage | Local filesystem (`/uploads/documents`, `/uploads/selfies`) |

---

## 📁 Project Structure

```
nexabank/
├── app.py                    # Main Flask application
├── instance/
│   └── nexabank.db           # SQLite database (auto-created)
├── uploads/
│   ├── documents/            # Uploaded KYC documents
│   └── selfies/              # Uploaded selfie photos
├── templates/
│   ├── index.html            # Customer onboarding UI
│   ├── user_login.html       # User login/register page
│   ├── admin_login.html      # Admin login page
│   └── admin.html            # Admin dashboard
└── static/                   # CSS, JS, assets
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- `pip`
- (Optional) Tesseract OCR for document text extraction
- (Optional) Anthropic API key for conversational AI

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-repo/nexabank-onboarding.git
cd nexabank-onboarding

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install flask pillow pytesseract

# 4. (Optional) Install Tesseract OCR
# Ubuntu/Debian:
sudo apt install tesseract-ocr
# macOS:
brew install tesseract
# Windows: Download installer from https://github.com/UB-Mannheim/tesseract/wiki

# 5. Run the application
python app.py
```

The app will be available at:

| URL | Description |
|---|---|
| `http://localhost:8000/login` | Customer Login / Register |
| `http://localhost:8000/` | Customer Onboarding App |
| `http://localhost:8000/admin-login` | Admin Login |
| `http://localhost:8000/admin` | Admin Dashboard |
| `http://localhost:8000/health` | Health Check |

---

## 🔐 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | No | Enables Claude AI conversational chat. Falls back to rule-based responses if not set. |

```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

---

## 🔑 Default Credentials

### Admin Accounts

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | Superadmin |
| `reviewer` | `reviewer123` | Reviewer |

### Demo Applications (Pre-seeded)

| ID | Name | Risk Level | Status |
|---|---|---|---|
| NXB-DEMO-001 | Rohan Mehta | Low | Approved |
| NXB-DEMO-002 | Priya Sharma | Medium | Pending |
| NXB-DEMO-003 | Anjali Gupta | High | Escalated |
| NXB-DEMO-004 | Vikram Singh | Low | Approved |
| NXB-DEMO-005 | Kavitha Nair | Medium | Pending |

---

## 📡 API Reference

### User Auth

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/user/register` | Register a new user |
| `POST` | `/api/user/login` | Login with email + password |
| `POST` | `/api/user/demo-login` | Guest / demo access |
| `POST` | `/api/user/logout` | Logout |
| `GET` | `/api/user/me` | Get current user info |
| `GET` | `/api/user/applications` | Get all applications for logged-in user |

### Onboarding

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/session/start` | Start a new KYC session |
| `POST` | `/api/session/resume` | Resume an existing session |
| `POST` | `/api/identity/submit` | Submit personal details (name, DOB, email, phone) |
| `POST` | `/api/documents/upload` | Upload an ID document |
| `POST` | `/api/biometric/selfie` | Upload selfie for face verification |
| `POST` | `/api/otp/store` | Store OTP hash |
| `POST` | `/api/otp/verify` | Verify OTP |
| `POST` | `/api/risk/evaluate` | Run risk assessment + determine account status |
| `GET` | `/api/account/summary/<app_id>` | Get full application summary |

### Chat

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat/message` | Send a chat message to ARIA |
| `GET` | `/api/chat/history/<app_id>` | Load full chat history |
| `GET` | `/api/chat/sessions` | Get all chat sessions for current user |

### Admin

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/admin/login` | Admin login |
| `POST` | `/api/admin/logout` | Admin logout |
| `GET` | `/api/admin/me` | Get logged-in admin info |
| `GET` | `/api/admin/stats` | Dashboard statistics |
| `GET` | `/api/admin/applications` | List all applications (filterable, paginated) |
| `GET` | `/api/admin/application/<app_id>` | Full application detail |
| `POST` | `/api/admin/decision` | Submit approval/rejection decision |
| `GET` | `/api/admin/audit` | Audit log |

---

## 🔄 Onboarding Flow

```
User Registers / Logs In / Uses Demo
          ↓
    Start KYC Session
          ↓
  Chat with ARIA (AI Assistant)
          ↓
  Step 1: Collect Full Name
  Step 2: Collect Date of Birth
  Step 3: Collect Email Address
  Step 4: Collect Mobile Number
          ↓
  Step 5: Upload ID Document (Aadhaar / PAN / Passport)
            → OCR extracts name, DOB, ID number
            → Tamper detection checks
          ↓
  Step 6: Upload Selfie
            → Biometric face score computed
          ↓
  Step 7: OTP Verification
          ↓
  Step 8: Risk Assessment
            → Score computed (0–100)
            → Level: Low / Medium / High
          ↓
  Result:
    Low Risk   → Auto Approved + Account Number Issued
    Medium Risk → Pending Admin Review
    High Risk  → Escalated for Investigation
```

---

## ⚠️ Risk Engine

The risk engine calculates a score from 0–100 based on multiple weighted factors:

| Factor | Deduction | Notes |
|---|---|---|
| OCR Confidence | 0 / -10 / -25 | High ≥ 75%, Moderate ≥ 50%, Low < 50% |
| Tamper Detection | -20 per flag | Flags from document analysis |
| Age Gate | 0 / -5 / -100 | Under 18 blocks entirely |
| Biometric Match | 0 / -10 / -30 / -15 | ≥90% strong, ≥75% acceptable, <75% poor, missing -15 |
| OTP Verification | 0 / -20 | Verified or not |
| Email Trust | 0 / -20 | Disposable email providers flagged |

**Risk Levels:**

| Score | Level | Outcome |
|---|---|---|
| 70–100 | Low | Auto-Approved |
| 45–69 | Medium | Pending Admin Review |
| 0–44 | High | Escalated |

---

## 🤖 AI Chat (ARIA)

ARIA is NexaBank's conversational onboarding assistant built on Claude (`claude-opus-4-6`).

**Capabilities:**
- Guides users through each KYC step naturally
- Answers general banking questions (eligibility, documents required, interest rates, fees, security, etc.)
- Remembers the full conversation context across the session
- Adapts tone to the user (formal/informal)
- Handles Hindi/mixed-language messages naturally
- Falls back to an intelligent rule-based engine if no API key is configured

**System Prompt Context includes:**
- Current application state (which step, what's been collected)
- All previous messages in the conversation
- Specific instructions on what NOT to ask (full Aadhaar number, passwords, etc.)

---

## 🖥 Admin Panel

The admin dashboard provides:

- **Stats cards** — Total applications, approved/pending/escalated/in-progress counts, average risk score, total users, documents, and chat messages
- **Application table** — Searchable, filterable by status and risk level, paginated
- **Application detail drawer** — Complete view with: personal info, documents + OCR data, selfie, biometric score, risk breakdown, chat transcript, audit log, and previous decisions
- **Decision panel** — Approve / Reject / Request More Info / Pending with notes
- **AI override flag** — Highlighted when admin decision differs from the AI recommendation
- **Document/selfie viewer** — Secure, admin-only media access

---

## 📝 Notes

- Selfie face scores are currently simulated with a random value (82–98%). Integration with a real face-matching service (e.g., AWS Rekognition) is recommended for production.
- OCR requires Tesseract to be installed. Without it, OCR data will be empty but the flow continues.
- The SQLite database uses WAL (Write-Ahead Logging) mode for better concurrent access handling.
- All file uploads are stored locally. For production, consider migrating to S3 or equivalent cloud storage.
- Passwords are hashed using SHA-256. For production, upgrade to `bcrypt` or `argon2`.

---

## 📄 License

This project is for educational/demonstration purposes.
