"""
Bulk-download NHM Maternal Health guideline PDFs and import them into
Vertex AI RAG corpus for HealthBridge AI
"""

import os
import re
import time
import requests
from pathlib import Path

import os
from dotenv import load_dotenv
load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
BUCKET_NAME = os.getenv("CORPUS_BUCKET")
GCS_FOLDER = "nhm-maternal-health-guidelines"
LOCATION = os.getenv("GCP_REGION", "us-central1")

CORPUS_NAME = os.getenv("GCP_CORPUS_NAME")
if not CORPUS_NAME:
    try:
        import vertexai
        from vertexai import rag
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        corpora = list(rag.list_corpora())
        
        if not corpora and LOCATION != "us-central1":
            print(f"No RAG corpora found in region {LOCATION}. Falling back to us-central1...")
            LOCATION = "us-central1"
            vertexai.init(project=PROJECT_ID, location=LOCATION)
            corpora = list(rag.list_corpora())
            
        if corpora:
            CORPUS_NAME = corpora[0].name
            print(f"Resolved RAG corpus: {CORPUS_NAME} in region {LOCATION}")
        else:
            CORPUS_NAME = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/healthbridge-corpus"
            print(f"No RAG corpus found. Defaulting to constructed name: {CORPUS_NAME}")
    except Exception as e:
        print(f"Failed to list corpora: {e}")
        CORPUS_NAME = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/healthbridge-corpus"

DOWNLOAD_DIR = Path("./nhm_downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# All PDF documents scraped from the NHM Maternal Health Guidelines page:
DOCUMENTS = {
    "Suman_Roadmap_2030.pdf": "https://nhm.gov.in/pdf/2026/Guidelines- MH/Suman-Roadmap-Updated-2030-11.pdf",
    "Guidance_Note_Optimizing_Postnatal_Care.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/Guidance_Note_on_optimizing_post_natal_care.pdf",
    "Maternal_Health_Guidance_Booklet_CHOs_English.pdf": "https://nhm.gov.in/New_Update-2022-23/MH/GUIDELINES- MH/CHO_Booklet_ Maternal_Health-English.pdf",
    "SOP_HIV_Syphilis_Screening_Pregnant_Women.pdf": "https://nhm.gov.in/New_Updates_2018/NHM_Components/RMNCHA/MH/Guidelines/Final%20HIV%20syphilis%20screening%20SOP%20signed%20for%20dissemination.pdf",
    "SUMAN_Guideline_2020.pdf": "https://nhm.gov.in/New_Updates_2018/NHM_Components/RMNCHA/MH/Guidelines/SUMAN%20Guideline%202020%20Web%20Version.pdf",
    "ASHA_Handbook_for_Abortions.pdf": "https://nhm.gov.in/New_Updates_2018/NHM_Components/RMNCHA/MH/Guidelines/ASHA_handbook_for_abortions.pdf",
    "Guidelines_on_Midwifery_Services_India.pdf": "https://nhm.gov.in/New_Updates_2018/NHM_Components/RMNCHA/MH/Guidelines/Guidelines_on_Midwifery_Services_in_India.pdf",
    "LaQshya_Quality_Improvement_Resource_Material.pdf": "https://nhm.gov.in/New_Updates_2018/NHM_Components/RMNCHA/MH/Guidelines/LaQshya_Quality_Improvement_Cycles_Resource_Material.pdf",
    "Technical_Operational_Guidelines_Gestational_Diabetes.pdf": "http://nhm.gov.in/New_Updates_2018/NHM_Components/RMNCH_MH_Guidelines/Gestational-Diabetes-Mellitus.pdf",
    "Operational_Guidelines_Obstetric_HDU_ICU.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/Operational_Guidelines_for_Obstetric_ICUs_and_HDUs.pdf",
    "Guidelines_Maternal_Death_Surveillance_Response.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/Guideline_for_MDSR.pdf",
    "PMSMA_Operational_Framework.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/PMSMA_Operational_Framework.pdf",
    "Labor_Room_Guideline.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/Labor_Room%20Guideline.pdf",
    "National_Guidelines_Calcium_Supplementation.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/National_Guidelines_for_Calcium_Supplementation_During_Pregnancy_and_Lactation.pdf",
    "National_Guidelines_Gestational_Diabetes_Management.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/National_Guidelines_for_Diagnosis_&_Management_of_Gestational_Diabetes_Mellitus.pdf",
    "National_Guidelines_Hypothyroidism_Screening.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/National_Guidelines_for_Screening_of_Hypothyroidism_during_Pregnancy.pdf",
    "National_Guidelines_Deworming_Pregnancy.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/National_Guidelines_for_Deworming_in_Pregnancy.pdf",
    "Screening_Syphilis_Pregnancy.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/Syphilis_Doc_Low-res_5th_Jan.pdf",
    "Maternal_Death_Review_User_Manual.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/MDR_User_Manual-1_V2n.pdf",
    "Maternal_Newborn_Health_Toolkit.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/MNH_Toolkit_23_11_2013.pdf",
    "Guidelines_for_JSSK.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/guidelines_for_jssk.pdf",
    "Maternal_Death_Review_Guidebook.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/maternal_death_review_guidebook.pdf",
    "MCP_Card.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/mcp_card1.pdf",
    "SBA_Guidelines_Skilled_Attendance_Birth.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/sba_guidelines_for_skilled_attendance_at_birth.pdf",
    "SBA_Handbook_ANM_LHV_SN.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/sba_handbook_for_anm_lhv_sn.pdf",
    "My_Safe_Motherhood_Booklet_English.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/my_safe_motherhood_booklet_english.pdf",
    "Village_Health_Nutrition_Days.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/vhnd_guidelines.pdf",
    "JSY_Guidelines.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/ijsy_guidelines_2006.pdf",
    "24hrs_PHCs_Guidelines.pdf": "http://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/guidelines_for_operationalising_24_hours_functioning_phcs.pdf",
    "MCP_Guide_Book.pdf": "https://nhm.gov.in/New_Updates_2018/NHM_Components/Immunization/Guildelines_for_immunization/MCP_Guide_Book.pdf",
}


def sanitize_filename(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]', '_', name)


def download_all():
    print(f"Downloading {len(DOCUMENTS)} documents...\n")
    downloaded = []
    failed = []

    headers = {"User-Agent": "Mozilla/5.0 (compatible; HealthBridgeAI-Importer/1.0)"}

    for filename, url in DOCUMENTS.items():
        dest = DOWNLOAD_DIR / sanitize_filename(filename)
        try:
            resp = requests.get(url, headers=headers, timeout=60, stream=True)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            size_mb = dest.stat().st_size / (1024 * 1024)

            # Vertex AI RAG default parser limit for PDFs is 50MB
            if size_mb > 50:
                print(f"  SKIPPED (over 50MB limit, {size_mb:.1f}MB): {filename}")
                failed.append((filename, f"{size_mb:.1f}MB exceeds 50MB RAG limit"))
                dest.unlink()
                continue

            print(f"  OK ({size_mb:.1f}MB): {filename}")
            downloaded.append(dest)
            time.sleep(0.5)  # be polite to the government server
        except Exception as e:
            print(f"  FAILED: {filename} -> {e}")
            failed.append((filename, str(e)))

    print(f"\nDownloaded {len(downloaded)}/{len(DOCUMENTS)} files successfully.")
    if failed:
        print(f"\n{len(failed)} files failed or were skipped:")
        for name, reason in failed:
            print(f"  - {name}: {reason}")
        print("\nFor oversized files: split them (see earlier PDF-splitting approach)")
        print("or use the Document AI layout parser corpus setting instead (20MB limit, 500 pages).")

    return downloaded


def upload_to_gcs(files):
    from google.cloud import storage

    print(f"\nUploading {len(files)} files to gs://{BUCKET_NAME}/{GCS_FOLDER}/ ...")
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(BUCKET_NAME)

    for f in files:
        blob_path = f"{GCS_FOLDER}/{f.name}"
        blob = bucket.blob(blob_path)
        blob.upload_from_filename(str(f))
        print(f"  Uploaded: {blob_path}")

    gcs_path = f"gs://{BUCKET_NAME}/{GCS_FOLDER}"
    print(f"\nAll files uploaded to {gcs_path}")
    return gcs_path


def import_to_rag_corpus(gcs_path):
    from vertexai import rag
    import vertexai

    print(f"\nImporting from {gcs_path} into RAG corpus...")
    vertexai.init(project=PROJECT_ID, location=LOCATION)

    response = rag.import_files(
        corpus_name=CORPUS_NAME,
        paths=[gcs_path],
        transformation_config=rag.TransformationConfig(
            rag.ChunkingConfig(chunk_size=1024, chunk_overlap=256)
        ),
        max_embedding_requests_per_min=900,
    )
    print(f"\nDone. Imported {response.imported_rag_files_count} files into the corpus.")


if __name__ == "__main__":
    files = download_all()
    if not files:
        print("No files downloaded successfully — aborting.")
        exit(1)

    gcs_path = upload_to_gcs(files)
    import_to_rag_corpus(gcs_path)