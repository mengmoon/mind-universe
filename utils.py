import firebase_admin
from firebase_admin import credentials, auth, firestore
import os
from dotenv import load_dotenv
import json

def init_firebase():
    load_dotenv()
    firebase_config = os.getenv("FIREBASE_CONFIG")
    if not firebase_config:
        raise ValueError("FIREBASE_CONFIG not set in environment")
    if not firebase_admin.get_app(name="[DEFAULT]", default=True):
        try:
            # Parse JSON string directly
            cred = credentials.Certificate(json.loads(firebase_config))
            firebase_admin.initialize_app(cred, {
                'databaseURL': f'https://{json.loads(firebase_config)["project_id"]}.firebaseio.com'
            })
        except Exception as e:
            raise ValueError(f"Firebase initialization failed: {str(e)}")
    db = firestore.client()
    return db, auth