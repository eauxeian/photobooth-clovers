import os
import json

# Get the environment variable
creds_raw = os.getenv("GOOGLE_CREDS")

if not creds_raw:
    print("❌ GOOGLE_CREDS not found in environment variables")
else:
    print("✅ GOOGLE_CREDS found")

    try:
        creds_json = json.loads(creds_raw)
        print("✅ Valid JSON")
        print("Service Account Email:", creds_json.get("client_email"))
        print("Project ID:", creds_json.get("project_id"))
    except Exception as e:
        print("❌ Failed to parse JSON:", e)
