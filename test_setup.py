import os
from dotenv import load_dotenv
from google.cloud import storage

load_dotenv()

project_id = os.getenv("GCP_PROJECT_ID")
client = storage.Client(project=project_id)
buckets = list(client.list_buckets())

print("Connected to GCP project:", project_id)
print("Buckets found:")
for b in buckets:
    print("  -", b.name)
