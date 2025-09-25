import json
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db, auth as firebase_auth

def init_firebase():
    load_dotenv()
    config_str = os.getenv('FIREBASE_CONFIG')
    if not config_str:
        raise ValueError("FIREBASE_CONFIG not set in .env")
    config = json.loads(config_str)
    cred = credentials.Certificate(config["serviceAccount"])
    # Check if Firebase app is already initialized
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            'databaseURL': config["databaseURL"]
        })
    return db, firebase_auth