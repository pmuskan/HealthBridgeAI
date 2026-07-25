# HealthBridge AI

HealthBridge AI is a clinical decision support tool built for ASHA (Accredited Social Health Activist) workers in rural India. It gives them instant access to official National Health Mission guidelines in their own language, so they can make better decisions for the patients they serve.

## Why This Exists

ASHA workers are the backbone of rural healthcare in India. There are over a million of them, and each one looks after fifty to a hundred families in villages where the nearest doctor might be hours away. They are trained, motivated, and trusted by their communities, but they often have to make difficult calls without any real time guidance.

When a child shows signs of malnutrition, when a pregnant woman has swollen feet and a headache, when a family asks if they qualify for Ayushman Bharat, an ASHA worker needs a clear and reliable answer fast. Not a two hundred page PDF. Not a helpline that puts them on hold.

That is what HealthBridge AI is built to do.

## What It Does

ASHA workers can ask questions in plain language and get structured answers drawn directly from official NHM documents. Every answer tells them what to do right now, what to monitor, when to refer the patient, and which document the answer came from.

The tool handles five types of clinical questions out of the box: maternal health, child health, government scheme eligibility, drug protocols, and referral decisions. It also supports uploading photos of paper prescriptions or lab reports, so Gemini can extract and explain the contents in simple language without ever storing the image itself.

When a query touches on a genuine emergency, the app points the worker straight to a dedicated Emergency Action page, where she can find the nearest hospitals, call the national ambulance number, or reach the state health helpline in a single tap.

Responses are available in English, Tamil, Telugu, and Hindi, with consistent formatting and terminology across all four.

## Technical Stack

The backend runs on FastAPI and Python 3.11. The RAG pipeline uses Vertex AI RAG Engine with Gemini 2.5 Flash handling both text and image inputs. PostgreSQL manages user authentication and conversation history through a pooled connection layer. Anonymous query metadata is logged to BigQuery for usage analytics. The Places API powers the nearest hospital lookup on the Emergency Action page. The frontend is a React SPA served directly by the FastAPI server.

## Architecture

```
React Frontend (mobile responsive, collapsible navigation)
      |
FastAPI Server (rate limited, connection pooled)
      |
      +-- PostgreSQL (auth, chat history, session management)
      +-- Vertex AI RAG Engine (NHM document corpus)
      +-- Gemini 2.5 Flash (multimodal clinical reasoning)
      +-- Cloud Translation API (Tamil, Telugu, Hindi, batched per response)
      +-- Google Places API (nearest hospitals, Emergency Action page)
      +-- BigQuery (anonymous analytics logging)
```

## NHM Documents in the RAG Corpus

Every source document is an official Indian government health publication, freely available from NHM and MoHFW portals.

ASHA 2025 Training Module
Ayushman Bharat and PMJAY Guidelines
Janani Suraksha Yojana (JSY) Guidelines
Handbook for ASHA Facilitators
HBNC and HBYC Home Visit Handbook
Induction Training Module for ASHA Workers
Improving Knowledge and Skills of ASHAs in Child Health
National Immunization Schedule
Rastriya Bal Swaasthya Karyakram (RBSK)
Anemia Mukt Bharat Guidelines
Guidance Note on IV Iron Use in Pregnant Women
Operational Guidelines on Iron Treatment
HBP Clinical Guidelines
T3 Guidelines
CURRENT Medical Diagnosis and Treatment Reference
IMNCI Guidelines for Healthcare Providers
Community Health Workers Training Manual and Job Aids
NHM Maternal Health Guidelines, including the Safe Motherhood Booklet, the SUMAN framework, the MCP Card Guidebook, and the national guidelines on anemia, gestational diabetes, calcium supplementation, and high risk pregnancy management

The corpus is built and updated through a small import script in `scripts/import_nhm_maternal_health_docs.py`, which pulls documents directly from the official NHM guidelines page, uploads them to Cloud Storage, and bulk imports them into the RAG corpus in a single pass. This keeps the sourcing traceable and repeatable rather than relying on one time manual uploads.

## What Changed During the Prototype Refinement Phase

After making it to the Top 101 teams in the Google Cloud Gen AI Academy APAC Edition, Cohort 2 hackathon, the following improvements were made to the prototype.

**Patient data privacy.** Uploaded prescription and report images were previously written to disk and served through a public, unauthenticated folder. This has been rebuilt so images are processed entirely in memory, base64 encoded for that single response, and never persisted anywhere. Nothing about a patient's image survives beyond the request that used it.

**Clinical response quality.** The system prompt was rewritten several times based on real test failures. It now requires a complete, actionable answer even when the RAG corpus has no matching document, rather than the model admitting it found nothing. A visible note appears whenever a response leans on general clinical knowledge instead of an official guideline, so the ASHA worker knows to double check with an ANM. Danger sign checklists that were previously repeated across two sections of a response now appear exactly once, which cut response length by roughly a third without dropping a single clinical detail.

**Formatting.** Responses were rendering with literal asterisks and uneven spacing on the frontend. This was traced to a mix of markdown not being parsed correctly and the model itself inserting blank lines between bullets. Both were fixed, one on the frontend with proper markdown rendering, and one in the prompt with explicit formatting rules and examples.

**Emergency Action page.** What started as a small side panel next to the chat is now its own dedicated page, reachable from the sidebar at any time, not only after a triggered response. It shows the nearest hospitals by distance and type, a tap to call the national ambulance number 108, the state health helpline 104, and a direct link to Google Maps for each hospital. Chat responses that warrant a referral now show a small alert instead of a large banner, keeping the conversation itself uncluttered.

**Security hardening.** CORS was locked down from an open wildcard to the app's actual origin. File uploads are now validated for type and size. Login and signup routes are rate limited using slowapi, along with the RAG chat endpoint and the hospital lookup endpoint, to prevent abuse and keep third party API costs predictable. Raw exception messages no longer leak to the client. All credentials, project identifiers, and API keys are loaded from environment variables, with no fallback values baked into the code.

**Performance.** Translation calls that were previously firing once per line now batch into a single call per response. Database access moved from opening and closing a new connection per query to a pooled connection reused across requests.

**Mobile responsiveness.** The app was originally built desktop first, and the sidebar, response cards, and Emergency Action page all needed rework to hold up on a phone. The sidebar now collapses into an overlay drawer with a proper close button. Touch targets were resized to at least 44 pixels. Input fields were adjusted to avoid the auto zoom that iOS Safari triggers on smaller text inputs. The ambulance number, helpline, and hospital search fields stack vertically below a 768 pixel breakpoint instead of being squeezed into a layout meant for a wider screen.

## Local Setup

You will need Python 3.10 or higher, Node.js 18 or higher, and a running PostgreSQL instance before you start.

Create a `.env` file in the root directory:

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

Set up the Python environment and install dependencies.

```bash
python -m venv venv
.\venv\Scripts\activate        # Windows
source venv/bin/activate       # macOS or Linux

pip install -r requirements.txt
```

Build the React frontend so FastAPI can serve it.

```bash
cd frontend
npm install
npm run build
cd ..
```

Start the server.

```bash
python server.py
```

Open `http://localhost:8000` in your browser.

## Deploying to Google Cloud Run

Build and push the Docker image to Artifact Registry.

```bash
gcloud artifacts repositories create healthbridge \
    --repository-format=docker \
    --location=asia-south1

gcloud builds submit \
    --tag asia-south1-docker.pkg.dev/YOUR_PROJECT_ID/healthbridge/app-server
```

Deploy to Cloud Run.

```bash
gcloud run deploy healthbridge-app \
  --image asia-south1-docker.pkg.dev/YOUR_PROJECT_ID/healthbridge/app-server \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --add-cloudsql-instances YOUR_PROJECT_ID:asia-south1:YOUR_INSTANCE_NAME \
  --update-env-vars "GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=asia-south1,DB_HOST=/cloudsql/YOUR_PROJECT_ID:asia-south1:YOUR_INSTANCE_NAME,DB_PORT=5432,DB_NAME=healthbridge,DB_USER=postgres,DB_PASSWORD=your_db_password"
```

The Cloud Run service account needs the following IAM roles.

roles/aiplatform.user
roles/bigquery.dataEditor
roles/cloudtranslate.user
roles/cloudsql.client

## Responsible AI

Every clinical answer cites the NHM source document it came from, or names the type of official guideline it would expect to draw from when general clinical knowledge fills a gap. The tool never diagnoses a new condition and never prescribes a new medication. Every clinical response ends with clear referral criteria so the ASHA worker always knows when to escalate to a PHC or ANM.

Patient images are processed strictly in memory and are never written to disk or stored in the database. Only anonymous metadata, such as query type, language, and response time, is logged to BigQuery for usage analytics. No personal health information touches persistent storage.

A disclaimer appears on every response reminding workers that this tool supports their judgment rather than replacing it. The national health helpline number 104 and the ambulance number 108 are both shown prominently throughout the app, not just within a single feature.

## Built By

Muskan P, Software Engineer based in Chennai, India.
Built for Google Cloud Gen AI Academy APAC Edition, Cohort 2.

## License

MIT License. See LICENSE file for details.
