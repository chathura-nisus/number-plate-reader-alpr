import os

# --- Application Root ---
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# --- Flask & SocketIO Configuration --
FLASK_SECRET_KEY = '58f9e6266038f5a07ce6b88bf1ec5a74021a536190e49b824c976a7f1d1e6922'
JWT_SECRET_KEY = 'a9cb72c7c1c0536ba461c9ccd205cc81d6eccf8507159088d2b637c91f46971b'
FLASK_DEBUG = True
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 8080

# --- ANPR Core Configuration ---
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
MIN_PLATE_AREA = 500
MIN_PLATE_TEXT_LENGTH = 3
CASCADE_FILE = os.path.join(APP_ROOT, "haarcascade_russian_plate_number.xml")
OCR_LANGUAGES = ['en']
OCR_MIN_CONFIDENCE = 0.3

# --- Specialized Plate Processing ---
USE_SRI_LANKAN_PLATE_PROCESSING = True
DETECT_PROVINCIAL_CODES = True
PROVINCIAL_CODE_MIN_CONFIDENCE = 0.2
ENABLE_PLATE_COLOR_DETECTION = True
YELLOW_PLATE_CONTRAST_BOOST = 1.5
WHITE_PLATE_CONTRAST_BOOST = 1.2
ENABLE_PERSPECTIVE_CORRECTION = True
ENABLE_SRI_LANKAN_VALIDATION = True
MIN_VALIDATION_SCORE = 40

# --- OCR Enhancement Configuration ---
USE_PLATE_ENHANCEMENT_FOR_OCR = True
MULTI_SCALE_FACTORS = [1.0, 1.5, 2.0]
ENHANCE_OCR_MORPH_OPEN_KERNEL_SIZE = (3, 3)  # Kernel for morphological opening
ENHANCE_OCR_THRESHOLD_BLOCK_SIZE = 15  # Block size for adaptive thresholding
ENHANCE_OCR_THRESHOLD_C = 4  # Constant C for adaptive thresholding

# --- ANPR Optimization Parameters --
IOU_THRESHOLD_FOR_MATCH = 0.3
MIN_OCR_SCORE_TO_BUFFER = 35
PLATE_CANDIDATE_TIMEOUT_SECONDS = 3.0
PLATE_SAVE_STABILIZATION_SECONDS = 0.75

# --- Real-time Performance Optimization --
ENABLE_FRAME_SKIPPING = True
FRAME_SKIP_COUNT = 2  # Process every 3rd frame
ENABLE_MULTI_THREADING = True
MAX_THREADS = 4

# --- Odoo XML-RPC Configuration --
ODOO_URL = "http://localhost:8018"
ODOO_DB_NAME = "odoo118"
ODOO_DB_USER = "admin"
ODOO_DB_PASSWORD = "admin"

# --- Gemini API Configuration ---
GEMINI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_MODEL_NAME = "google/gemini-2.0-flash-exp:free"

# --- Storage & Logging Configuration --
SAVE_DIR_NAME = "IMAGES_DETECTED"
SAVE_DIR = os.path.join(APP_ROOT, SAVE_DIR_NAME)
LOG_FILE_NAME = "detected_plates_log.csv"
LOG_FILE = os.path.join(APP_ROOT, LOG_FILE_NAME)

# --- Image Cleanup Configuration --
IMAGE_CLEANUP_TARGET_HOUR = 22  # 10 PM
IMAGE_CLEANUP_CHECK_INTERVAL_SECONDS = 60 * 30  # Every 30 minutes
IMAGE_MAX_AGE_DAYS = 7
