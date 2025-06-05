# anpr_flask_project/config.py
import os

# --- Application Root ---
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# --- Flask & SocketIO Configuration ---
FLASK_SECRET_KEY = 'your_secret_key_here_refactored_oop_v1'
FLASK_DEBUG = True
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5000

# --- ANPR Core Configuration ---
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
MIN_PLATE_AREA = 500
MIN_PLATE_TEXT_LENGTH = 3
CASCADE_FILE = os.path.join(APP_ROOT, "haarcascade_russian_plate_number.xml")  # Ensure this path is correct
OCR_LANGUAGES = ['en']
OCR_MIN_CONFIDENCE = 0.3

# --- NEW: Configuration for OCR Image Enhancement ---
# Set to True to enable the advanced image processing on the cropped plate before OCR
USE_PLATE_ENHANCEMENT_FOR_OCR = True
ENHANCE_OCR_MORPH_OPEN_KERNEL_SIZE = (2, 2)

# --- ANPR Optimization Parameters ---
IOU_THRESHOLD_FOR_MATCH = 0.3
MIN_OCR_SCORE_TO_BUFFER = 35
PLATE_CANDIDATE_TIMEOUT_SECONDS = 3.0
PLATE_SAVE_STABILIZATION_SECONDS = 0.75

# --- Odoo XML-RPC Configuration ---
ODOO_URL = "http://localhost:8018"
ODOO_DB_NAME = "odoo118"
ODOO_DB_USER = "admin"
ODOO_DB_PASSWORD = "admin"  # Consider using environment variables for sensitive data

# --- Storage & Logging Configuration ---
SAVE_DIR_NAME = "IMAGES_DETECTED"
SAVE_DIR = os.path.join(APP_ROOT, SAVE_DIR_NAME)
LOG_FILE_NAME = "detected_plates_log.csv"
LOG_FILE = os.path.join(APP_ROOT, LOG_FILE_NAME)  # Will be created in SAVE_DIR by StorageHandler

# --- Image Cleanup Configuration ---
IMAGE_CLEANUP_TARGET_HOUR = 22  # 10 PM
IMAGE_CLEANUP_CHECK_INTERVAL_SECONDS = 60 * 30  # Every 30 minutes
IMAGE_MAX_AGE_DAYS = 7

# --- Camera Defaults ---
DEFAULT_CAMERA_IDENTIFIER = "default_local"
DEFAULT_CAMERA_LOCATION = "Main Gate"
DEFAULT_SOURCE_TYPE = "local"
PHONE_STREAM_TIMEOUT_SECONDS = 5.0  # How long to wait for a phone frame before considering it stale
