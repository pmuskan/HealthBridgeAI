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

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
REGION = os.getenv("GCP_REGION", "us-central1")
BQ_DATASET = os.getenv("BQ_DATASET", "healthbridge_analytics")
BQ_TABLE = os.getenv("BQ_TABLE", "query_logs")

try:
    vertexai.init(project=PROJECT_ID, location=REGION)
    corpora = list(rag.list_corpora())
except Exception as e:
    print(f"Non-critical: Failed to retrieve Vertex RAG corpus name in region {REGION}: {e}")
    corpora = []

if not corpora and REGION != "us-central1":
    print(f"No RAG corpora found in region {REGION}. Falling back to us-central1...")
    REGION = "us-central1"
    try:
        vertexai.init(project=PROJECT_ID, location=REGION)
        corpora = list(rag.list_corpora())
    except Exception as e:
        print(f"Non-critical: Failed to retrieve Vertex RAG corpus name in fallback region us-central1: {e}")
        corpora = []

CORPUS_NAME = corpora[0].name if corpora else "healthbridge-corpus"
client = genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)
bq_client = bigquery.Client(project=PROJECT_ID)

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
→ If the retrieved RAG documents do not contain enough details or are missing the necessary information, use your pre-trained LLM knowledge (brain search) to answer the query fully and accurately. In the 📚 Source section, state which official NHM guideline or training document typically covers this protocol, and append "(assisted by general clinical knowledge)" to the source name.

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
3. Never invent numbers or thresholds not in the documents (unless using general clinical knowledge fallback, in which case specify they are standard clinical guidelines).
4. Always mention referral criteria.
5. Always cite the source document (or expected source document if using general clinical knowledge).
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
            result = translate_client.translate(
                stripped,
                target_language=target_code
            )
            translated_lines.append(result["translatedText"])

        return '\n'.join(translated_lines)

    except Exception as e:
        print(f"Translation error: {e}")
        return text

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
        bigquery.SchemaField("user_id",     "STRING",    mode="NULLABLE"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    bq_client.create_table(table, exists_ok=True)
    print(f"BigQuery table ready: {BQ_DATASET}.{BQ_TABLE}")

    # Appending user_id column safely if the table existed already without it
    try:
        table_ref = bq_client.get_table(table_id)
        existing_schema = table_ref.schema
        if not any(field.name == "user_id" for field in existing_schema):
            new_schema = list(existing_schema)
            new_schema.append(bigquery.SchemaField("user_id", "STRING", mode="NULLABLE"))
            table_ref.schema = new_schema
            bq_client.update_table(table_ref, ["schema"])
            print("Appended user_id field to existing BigQuery table schema.")
    except Exception as e:
        print(f"Non-critical error updating schema: {e}")

def log_query(query_type: str, language: str, success: bool,
              response_ms: int, has_image: bool, user_id: str = None):
    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
    rows = [{
        "timestamp":   datetime.datetime.utcnow().isoformat(),
        "query_type":  query_type,
        "language":    language,
        "success":     success,
        "response_ms": response_ms,
        "has_image":   has_image,
        "user_id":     str(user_id) if user_id is not None else None,
    }]
    try:
        errors = bq_client.insert_rows_json(table_id, rows)
        if errors:
            print(f"BigQuery insert errors: {errors}")
    except Exception as e:
        print(f"BigQuery logging failed (non-critical): {e}")

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

def query_healthbridge(
    user_query: str,
    language: str = "English",
    chat_history: list = [],
    image_bytes: bytes = None,
    image_mime_type: str = None,
    user_id: str = None
) -> dict:

    start_time = datetime.datetime.utcnow()
    query_type = "error"

    try:
        if image_bytes:
            query_type = "medical_document"
        else:
            query_type = classify_query(user_query)

        query_text = user_query.strip() if user_query else "Analyze this medical document."

        lang_instruction = (
            f"\n\n[LANGUAGE: {language}] "
            f"Write your ENTIRE response in {language}. "
            f"Keep all emoji symbols exactly as they are."
        )

        enhanced_query = f"[QUERY TYPE: {query_type}]\n\nQuestion: {query_text}{lang_instruction}"

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

            # use Cloud Translation as fallback since Gemini handles these without RAG
            if language != "English" and query_type in ["greeting", "general_health"]:
                answer = translate_text(answer, language)

        else:
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

        if not answer or len(answer.strip()) < 20:
            answer = (
                "I don't have enough information on this in my documents. "
                "Please consult your ANM or PHC doctor directly, or call 104."
            )

        elapsed_ms = int((datetime.datetime.utcnow() - start_time).total_seconds() * 1000)
        log_query(
            query_type=query_type,
            language=language,
            success=True,
            response_ms=elapsed_ms,
            has_image=bool(image_bytes),
            user_id=user_id
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
            has_image=bool(image_bytes),
            user_id=user_id
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

def get_user_analytics(user_id: str) -> dict:
    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
    
    today = datetime.date.today()
    last_7_days = [today - datetime.timedelta(days=i) for i in range(6, -1, -1)]
    queries_per_day = {day.strftime("%Y-%m-%d"): 0 for day in last_7_days}
    
    default_stats = {
        "total_queries": 0,
        "success_rate": 0.0,
        "avg_response_ms": 0.0,
        "total_image_uploads": 0,
        "query_types": [],
        "languages": [],
        "queries_per_day": [{"date": day, "count": 0} for day in sorted(queries_per_day.keys())]
    }
    
    try:
        query = f"""
            SELECT timestamp, query_type, language, success, response_ms, has_image
            FROM `{table_id}`
            WHERE user_id = @user_id
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("user_id", "STRING", str(user_id))
            ]
        )
        
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()
        rows = [dict(row) for row in results]
    except Exception as e:
        print(f"Error querying BigQuery for user {user_id}: {e}")
        return default_stats

    if not rows:
        return default_stats

    total_queries = len(rows)
    success_count = sum(1 for r in rows if r["success"])
    success_rate = (success_count / total_queries * 100) if total_queries > 0 else 0.0
    
    response_times = [r["response_ms"] for r in rows if r["response_ms"] is not None]
    avg_response_ms = (sum(response_times) / len(response_times)) if response_times else 0.0
    
    total_image_uploads = sum(1 for r in rows if r["has_image"])
    
    query_type_counts = {}
    for r in rows:
        q_type = r["query_type"]
        if q_type:
            query_type_counts[q_type] = query_type_counts.get(q_type, 0) + 1
            
    language_counts = {}
    for r in rows:
        lang = r["language"]
        if lang:
            language_counts[lang] = language_counts.get(lang, 0) + 1
            
    for r in rows:
        ts = r["timestamp"]
        # BigQuery returns datetime objects for TIMESTAMP fields. If it's a string, we parse it.
        if isinstance(ts, str):
            try:
                dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
            except Exception:
                dt = None
        else:
            dt = ts.date() if hasattr(ts, "date") else None
            
        if dt:
            day_str = dt.strftime("%Y-%m-%d")
            if day_str in queries_per_day:
                queries_per_day[day_str] += 1
                
    queries_by_day_list = [{"date": day, "count": count} for day, count in sorted(queries_per_day.items())]
    
    return {
        "total_queries": total_queries,
        "success_rate": round(success_rate, 2),
        "avg_response_ms": round(avg_response_ms, 2),
        "total_image_uploads": total_image_uploads,
        "query_types": [{"query_type": k, "count": v} for k, v in query_type_counts.items()],
        "languages": [{"language": k, "count": v} for k, v in language_counts.items()],
        "queries_per_day": queries_by_day_list
    }

init_bigquery()

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