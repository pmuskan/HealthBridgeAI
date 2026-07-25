# HealthBridge AI

HealthBridge AI is a clinical decision support tool built for ASHA (Accredited Social Health Activist) workers in rural India. It gives them instant access to official National Health Mission guidelines in their own language, so they can make better decisions for the patients they serve.

---

## Why This Exists

ASHA workers are the backbone of rural healthcare in India. There are over a million of them, and they each look after 50 to 100 families in villages where the nearest doctor might be hours away. They are trained, motivated, and trusted by their communities but they often have to make difficult calls without any real-time guidance.

When a child shows signs of malnutrition, when a pregnant woman has swollen feet and a headache, when a family asks if they qualify for Ayushman Bharat — an ASHA worker needs a clear, reliable answer fast. Not a 200-page PDF. Not a helpline that puts them on hold.

That is what HealthBridge AI is built to do.

---

## What It Does

ASHA workers can ask questions in plain language and get structured answers drawn directly from official NHM documents. Every answer tells them what to do right now, what to monitor, when to refer the patient, and which document the answer came from.

The tool handles five types of questions out of the box — maternal health, child health, government scheme eligibility, drug protocols, and referral decisions. It also supports uploading photos of paper prescriptions or lab reports so Gemini can extract and explain the contents in simple language.

Responses are available in English, Tamil, Telugu, and Hindi.

---

## Technical Stack

The backend is built with FastAPI and Python 3.11. The RAG pipeline runs on Vertex AI RAG Engine with Gemini 2.5 Flash handling both text and image inputs. PostgreSQL manages user authentication and conversation history. Anonymous query metadata is logged to BigQuery for usage analytics. The frontend is a React SPA served directly by the FastAPI server.

---

## Architecture

```
React Frontend
      |
FastAPI Server  ──  PostgreSQL (auth and chat history)
      |
      ├── Vertex AI RAG Engine (NHM document corpus)
      ├── Gemini 2.5 Flash (multimodal responses)
      ├── Cloud Translation API (Tamil, Telugu, Hindi)
      └── BigQuery (anonymous analytics logging)
```

---

## NHM Documents in the RAG Corpus

All source documents are official Indian government health publications freely available from NHM and MoHFW portals.

- ASHA 2025 Training Module
- Ayushman Bharat and PMJAY Guidelines
- Janani Suraksha Yojana (JSY) Guidelines
- Handbook for ASHA Facilitators
- HBNC and HBYC Home Visit Handbook
- Induction Training Module for ASHA Workers
- Improving Knowledge and Skills of ASHAs in Child Health
- National Immunization Schedule
- Rastriya Bal Swaasthya Karyakram (RBSK)
- Anemia Mukt Bharat Guidelines
- Guidance Note on IV Iron Use in Pregnant Women
- Operational Guidelines on Iron Treatment
- HBP Clinical Guidelines
- T3 Guidelines
- CURRENT Medical Diagnosis and Treatment Reference

---

## Local Setup

You need Python 3.10 or higher, Node.js 18 or higher, and PostgreSQL running locally before you start.

Create a `.env` file in the root directory with the following variables:

```
GCP_PROJECT_ID=your-gcp-project-id
GCP_REGION=us-central1
CORPUS_BUCKET=your-bucket-name
DB_HOST=localhost
DB_PORT=5432
DB_NAME=healthbridge
DB_USER=postgres
DB_PASSWORD=your_db_password
GOOGLE_PLACES_API_KEY=your_google_places_api_key
```

Set up the Python environment and install dependencies:

```bash
python -m venv venv
.\venv\Scripts\activate        # Windows
source venv/bin/activate       # macOS or Linux

pip install -r requirements.txt
```

Build the React frontend so FastAPI can serve it:

```bash
cd frontend
npm install
npm run build
cd ..
```

Start the server:

```bash
python server.py
```

Open `http://localhost:8000` in your browser.

---

## Deploying to Google Cloud Run

Build and push the Docker image to Artifact Registry:

```bash
gcloud artifacts repositories create healthbridge \
    --repository-format=docker \
    --location=asia-south1

gcloud builds submit \
    --tag asia-south1-docker.pkg.dev/YOUR_PROJECT_ID/healthbridge/app-server
```

Deploy to Cloud Run:

```bash
gcloud run deploy healthbridge-app \
  --image asia-south1-docker.pkg.dev/YOUR_PROJECT_ID/healthbridge/app-server \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --add-cloudsql-instances YOUR_PROJECT_ID:asia-south1:YOUR_INSTANCE_NAME \
  --update-env-vars "GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=asia-south1,DB_HOST=/cloudsql/YOUR_PROJECT_ID:asia-south1:YOUR_INSTANCE_NAME,DB_PORT=5432,DB_NAME=healthbridge,DB_USER=postgres,DB_PASSWORD=your_db_password"
```

Make sure the Cloud Run service account has these IAM roles assigned:
- roles/aiplatform.user
- roles/bigquery.dataEditor
- roles/cloudtranslate.user
- roles/cloudsql.client

---

## Key Optimizations & Enhancements

- **Mobile Responsiveness Overhaul:** Converted the static left sidebar into a collapsible overlay drawer using GPU-accelerated transition animations, added an overlay closing (`X`) button, scaled touch targets to a minimum of `44px` height, and configured input fields to bypass iOS Safari auto-zoom issues. Stacked hotline and search fields dynamically on screens under `768px`.
- **Clinical Query Quality & Formatting:** Updated backend generation prompts to eliminate redundant checklists between `✅ Immediate Actions` (now actions only) and `🚨 Refer Immediately If` (danger signs only) to keep answers clean and clinically complete.
- **API Rate Limiting Enforcement:** Added request throttling via `slowapi` to protect key backend entry points (`/api/chats/.../messages`, `/api/geocode`, `/api/nearby-hospitals`) from abuse and control third-party billing costs.
- **Environment Isolation:** Cleaned all fallback credentials and domain origins from the code, loading origins and databases dynamically from environment parameters.

---

## Responsible AI

Every clinical answer cites the NHM source document it came from. The tool never diagnoses diseases, never prescribes medication, and always ends with referral criteria so the ASHA worker knows when to escalate to a PHC or ANM.

Patient images are processed strictly in-memory and are never written to local disk or database storage. Only anonymous metadata (like query type, language, and response time) is logged to BigQuery for usage analytics. No personal health information ever touches the database.

A disclaimer appears on every response reminding workers that this tool supports their judgment, not replaces it. The national health helpline number 104 is shown prominently throughout the app.

---

## Built By

Muskan P — Software Engineer based in Chennai, India.
Built for Google Builders APAC 2026.

---

## License

MIT License. See LICENSE file for details.