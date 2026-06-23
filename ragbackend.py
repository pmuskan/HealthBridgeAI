import vertexai
from vertexai import rag
from google import genai
from google.genai import types
from google.cloud import translate_v2 as translate
from google.cloud import bigquery
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ──────────────────────────────────────────────
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
REGION = "us-central1"
BQ_DATASET = "healthbridge_analytics"
BQ_TABLE = "query_logs"

vertexai.init(project=PROJECT_ID, location=REGION)

# ── Get corpus name automatically ──────────────────────────────
corpora = list(rag.list_corpora())
CORPUS_NAME = corpora[0].name

# ── Gemini client ──────────────────────────────────────────────
client = genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)

# ── BigQuery client ────────────────────────────────────────────
bq_client = bigquery.Client(project=PROJECT_ID)

# ── RAG retrieval tool ─────────────────────────────────────────
rag_retrieval_tool = types.Tool(
    retrieval=types.Retrieval(
        vertex_rag_store=types.VertexRagStore(
            rag_corpora=[CORPUS_NAME],
            rag_retrieval_config=types.RagRetrievalConfig(
                top_k=5,
            ),
        )
    )
)

# ── System prompt ──────────────────────────────────────────────
SYSTEM_PROMPT = """
You are HealthBridge AI, a friendly and evidence-based clinical decision support
assistant designed for ASHA (Accredited Social Health Activist) workers in India.

========================
CRITICAL RULE — READ FIRST
========================
ALWAYS answer the EXACT current question.
Ignore all previous conversation context.
The [QUERY TYPE] tag tells you how to respond.
The [LANGUAGE] tag tells you which language to write your ENTIRE response in.
If the language is not English, write every word of your response in that language.
Keep all emoji symbols exactly as they are. Only translate the text content.

========================
RESPONSE LENGTH
========================
- Adapt length to the question. Simple question = short answer.
- Use bullet points. Short paragraphs only when needed.
- No filler phrases like "Great question!", "Sure!", "Of course!".
- Never stop mid-sentence. Always complete your response fully.
- Always put each bullet point on its own new line.
- Always put each section header on its own new line.

========================
QUERY TYPE HANDLING
========================

[QUERY TYPE: greeting]
→ Respond warmly and briefly. 1-3 sentences only.
→ Do NOT search NHM documents.
→ Example: "Hi! I am HealthBridge AI, here to help ASHA workers with NHM health guidelines. What can I help you with today?"

[QUERY TYPE: general_health]
→ Answer from your own training knowledge.
→ Explain the condition simply, basic steps, when to see a doctor.
→ Max 300 words.
→ End with: "For official NHM protocol, consult your ANM or nearest health center."
→ Do NOT use the structured clinical format below.

[QUERY TYPE: scheme_eligibility]
[QUERY TYPE: referral_decision]
[QUERY TYPE: drug_protocol]
[QUERY TYPE: child_health]
[QUERY TYPE: maternal_health]
→ Answer from retrieved NHM documents.
→ Use the structured format below.
→ NEVER hallucinate clinical facts.
→ If not in documents: "I don't have enough information on this. Please consult your ANM or PHC doctor."

[QUERY TYPE: medical_document]
→ Answer based on the uploaded image (prescription, diagnostic report, lab result, clinical record, etc.) and the user query text.
→ Carefully analyze the image. Extract names of medicines, dosage, instructions, lab findings, or diagnosis details.
→ Translate clinical terms into simple language that an ASHA worker can understand.
→ Map your response strictly to the structured response format below.
→ In the 🔍 Situation section, provide a concise summary of the document, including what type of document it is and the key findings, test values, or medications.

========================
CORE RULES — CLINICAL QUERIES
========================
1. Never diagnose new diseases (summarizing or explaining the doctor's diagnosis written in the uploaded document is allowed).
2. Never prescribe new medicines or dosages (explaining and listing the medications and dosages already prescribed by the doctor in the image is allowed, but do not suggest any new medications or alter the dosages).
3. Never invent numbers or thresholds not in the documents.
4. Always mention referral criteria.
5. Always cite the source document.
6. Simple language — ASHA workers are trained but not doctors.
7. Complete EVERY section. Never cut off mid-response.
8. Every section header must be on its own line. Every bullet must be on its own line.

========================
RESPONSE FORMAT — CLINICAL QUERIES ONLY
========================

🔍 Situation
[1 line — what the ASHA worker is dealing with]

✅ Immediate Actions
[bullet — action 1]
[bullet — action 2]
[bullet — action 3 if needed]

📋 Follow-up
[bullet — monitoring step]
[bullet — next steps]

🗣️ Counseling Points
[bullet — message for patient or family]
[bullet — preventive advice]

🚨 Refer Immediately If
[bullet — danger sign 1]
[bullet — danger sign 2]
[bullet — danger sign 3 if needed]

📚 Source
[Document name only]

⚠️ Disclaimer: Decision support only. Consult ANM or PHC doctor when in doubt. Emergency: Call 104.
"""

# ── Translation helper (used only for greetings and general health) ──
translate_client = translate.Client()

LANGUAGE_CODES = {
    "English": "en",
    "Tamil": "ta",
    "Telugu": "te",
    "Hindi": "hi"
}

def translate_text(text: str, target_language: str) -> str:
    """Translate line by line to preserve structure."""
    if target_language == "English":
        return text

    target_code = LANGUAGE_CODES.get(target_language, "en")
    try:
        lines = text.split('\n')
        translated_lines = []

        for line in lines:
            stripped = line.strip()
            # Preserve empty lines
            if not stripped:
                translated_lines.append('')
                continue
            # Preserve very short lines and emoji-only lines
            if len(stripped) <= 2:
                translated_lines.append(stripped)
                continue
            # Translate the line
            result = translate_client.translate(
                stripped,
                target_language=target_code
            )
            translated_lines.append(result["translatedText"])

        return '\n'.join(translated_lines)

    except Exception as e:
        print(f"Translation error: {e}")
        return text

# ── BigQuery setup ─────────────────────────────────────────────
def init_bigquery():
    dataset_id = f"{PROJECT_ID}.{BQ_DATASET}"
    try:
        bq_client.get_dataset(dataset_id)
    except Exception:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = "US"
        bq_client.create_dataset(dataset, exists_ok=True)
        print(f"Created BigQuery dataset: {BQ_DATASET}")

    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
    schema = [
        bigquery.SchemaField("timestamp",   "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("query_type",  "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("language",    "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("success",     "BOOLEAN",   mode="REQUIRED"),
        bigquery.SchemaField("response_ms", "INTEGER",   mode="NULLABLE"),
        bigquery.SchemaField("has_image",   "BOOLEAN",   mode="REQUIRED"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    bq_client.create_table(table, exists_ok=True)
    print(f"BigQuery table ready: {BQ_DATASET}.{BQ_TABLE}")

def log_query(query_type: str, language: str, success: bool,
              response_ms: int, has_image: bool):
    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
    rows = [{
        "timestamp":   datetime.datetime.utcnow().isoformat(),
        "query_type":  query_type,
        "language":    language,
        "success":     success,
        "response_ms": response_ms,
        "has_image":   has_image,
    }]
    try:
        errors = bq_client.insert_rows_json(table_id, rows)
        if errors:
            print(f"BigQuery insert errors: {errors}")
    except Exception as e:
        print(f"BigQuery logging failed (non-critical): {e}")

# ── Query classifier ───────────────────────────────────────────
def classify_query(query: str) -> str:
    query_lower = query.lower().strip()

    greeting_words = ["hi", "hello", "hey", "how are you", "good morning",
                      "good evening", "good afternoon", "thanks", "thank you",
                      "who are you", "what are you", "your name", "what is your name"]
    if any(query_lower.startswith(w) for w in greeting_words) and len(query_lower.split()) < 8:
        return "greeting"

    if any(w in query_lower for w in ["scheme", "eligible", "eligibility", "benefit",
                                       "pmjay", "jsy", "ayushman", "yojana", "rashtriya"]):
        return "scheme_eligibility"

    if any(w in query_lower for w in ["refer", "referral", "emergency", "urgent",
                                       "hospital", "immediately", "danger sign"]):
        return "referral_decision"

    if any(w in query_lower for w in ["medicine", "drug", "dose", "dosage", "tablet",
                                       "injection", "supplement", "iron tablet", "folic"]):
        return "drug_protocol"

    if any(w in query_lower for w in ["child", "baby", "infant", "toddler", "newborn",
                                       "nutrition", "malnourish", "underweight", "immuniz",
                                       "vaccine", "vaccination", "rbsk"]):
        return "child_health"

    if any(w in query_lower for w in ["pregnant", "pregnancy", "mother", "delivery",
                                       "antenatal", "postnatal", "trimester", "labour",
                                       "breastfeed", "maternal", "anaemia", "anemia", "hbnc"]):
        return "maternal_health"

    return "general_health"


# ── Main query function ────────────────────────────────────────
def query_healthbridge(
    user_query: str,
    language: str = "English",
    chat_history: list = [],
    image_bytes: bytes = None,
    image_mime_type: str = None
) -> dict:

    start_time = datetime.datetime.utcnow()
    query_type = "error"

    try:
        # Classify
        if image_bytes:
            query_type = "medical_document"
        else:
            query_type = classify_query(user_query)

        query_text = user_query.strip() if user_query else "Analyze this medical document."

        # Add language instruction for non-English responses
        if language != "English":
            lang_instruction = (
                f"\n\n[LANGUAGE: {language}] "
                f"Write your ENTIRE response in {language}. "
                f"Keep all emoji symbols exactly as they are. "
                f"Only translate the text. "
                f"Each section header and each bullet point must be on its own separate line."
            )
        else:
            lang_instruction = ""

        enhanced_query = f"[QUERY TYPE: {query_type}]\n\nQuestion: {query_text}{lang_instruction}"

        # Greetings, general health, medical documents — no RAG
        if query_type in ["greeting", "general_health", "medical_document"]:
            contents = []
            if image_bytes and image_mime_type:
                contents.append(
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=image_mime_type
                    )
                )
            contents.append(enhanced_query)

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.5,
                    max_output_tokens=1024,
                ),
            )

            answer = response.text

            # For greetings and general health in non-English
            # use Cloud Translation as fallback since Gemini handles these without RAG
            if language != "English" and query_type in ["greeting", "general_health"]:
                answer = translate_text(answer, language)

        else:
            # Clinical queries — use RAG
            # Gemini responds directly in the target language — no post-translation needed
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=enhanced_query,
                config=types.GenerateContentConfig(
                    tools=[rag_retrieval_tool],
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                    max_output_tokens=4096,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=0
                    ),
                ),
            )

            answer = response.text
            # No translation needed — Gemini already responded in target language

        if not answer or len(answer.strip()) < 20:
            answer = (
                "I don't have enough information on this in my documents. "
                "Please consult your ANM or PHC doctor directly, or call 104."
            )

        # Log to BigQuery
        elapsed_ms = int((datetime.datetime.utcnow() - start_time).total_seconds() * 1000)
        log_query(
            query_type=query_type,
            language=language,
            success=True,
            response_ms=elapsed_ms,
            has_image=bool(image_bytes)
        )

        return {
            "success": True,
            "response": answer,
            "query_type": query_type,
            "language": language,
            "error": None
        }

    except Exception as e:
        elapsed_ms = int((datetime.datetime.utcnow() - start_time).total_seconds() * 1000)
        log_query(
            query_type=query_type,
            language=language,
            success=False,
            response_ms=elapsed_ms,
            has_image=bool(image_bytes)
        )
        return {
            "success": False,
            "response": (
                "I'm having trouble connecting right now. "
                "Please try again or consult your ANM directly."
            ),
            "query_type": "error",
            "language": language,
            "error": str(e)
        }


# ── Initialize BigQuery on module load ─────────────────────────
init_bigquery()


# ── Test ───────────────────────────────────────────────────────
if __name__ == "__main__":
    test_queries = [
        ("hi", "English"),
        ("I have PCOS, what should I do?", "English"),
        ("What should I check during a home visit for a pregnant woman in third trimester?", "English"),
        ("Who is eligible for Janani Suraksha Yojana?", "English"),
        ("When should I refer a child to PHC?", "Tamil"),
        ("What are danger signs in a child under 5?", "Telugu"),
        ("Pregnant woman has severe headache, what to do?", "Hindi"),
    ]

    for query, lang in test_queries:
        print(f"\nQuery: {query} [{lang}]")
        result = query_healthbridge(query, lang)
        print(f"Type:     {result['query_type']}")
        print(f"Response:\n{result['response']}")
        print("="*60)