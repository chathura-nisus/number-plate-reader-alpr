# anpr_flask_project/app_setup.py
import os
from flask import Flask
from flask_socketio import SocketIO
import cv2
import easyocr

import config as app_config
from utils.logging_service import LoggingService
from odoo.connector import OdooConnector
from storage.handler import StorageHandler
from anpr_core.processor import ANPRProcessor
from camera.manager import CameraManager

def build_application(eventlet_available_flag):
    """
    Creates the Flask app, SocketIO instance, and initializes all core services.
    Returns a dictionary containing the app, socketio, and all initialized services.
    Returns None if a critical initialization step fails.
    """
    # --- Initialize Flask App ---
    app = Flask(__name__)
    app.config['SECRET_KEY'] = app_config.FLASK_SECRET_KEY

    # --- Initialize SocketIO (conditionally on eventlet) ---
    socketio_instance = None
    if eventlet_available_flag:
        socketio_instance = SocketIO(app, async_mode='eventlet', logger=False, engineio_logger=False, ping_timeout=120, ping_interval=25)
        print("INFO: (app_setup) Flask-SocketIO initialized with async_mode='eventlet'.")
    else:
        socketio_instance = SocketIO(app, async_mode=None, logger=False, engineio_logger=False, ping_timeout=120, ping_interval=25)
        print("INFO: (app_setup) Flask-SocketIO initialized without eventlet (using default async_mode).")

    # 1. Logging Service
    logging_service = LoggingService(socketio_instance=socketio_instance)
    logging_service.web_log("Application setup starting...", "info")

    # 2. Load Haar Cascade
    logging_service.web_log("Initializing Haar Cascade...", "info")
    plate_cascade_path = app_config.CASCADE_FILE
    if not os.path.exists(plate_cascade_path):
        logging_service.web_log(f"Haar Cascade file not found: {plate_cascade_path}", "critical")
        return None
    plate_cascade = cv2.CascadeClassifier(plate_cascade_path)
    if plate_cascade.empty():
        logging_service.web_log(f"Could not load Haar Cascade from: {plate_cascade_path}", "critical")
        return None
    logging_service.web_log(f"Haar Cascade loaded from {plate_cascade_path}", "info")

    # 3. Load EasyOCR Reader
    logging_service.web_log("Initializing EasyOCR Reader...", "info")
    easyocr_reader = None
    try:
        easyocr_reader = easyocr.Reader(app_config.OCR_LANGUAGES, gpu=True)
        logging_service.web_log("EasyOCR reader initialized (attempted GPU; check console for PyTorch CPU fallback warnings if CUDA/MPS not found).", "info")
    except Exception as e_ocr:
        logging_service.web_log(f"EasyOCR initialization (gpu=True attempt) failed directly: {e_ocr}. Trying CPU explicitly.", "warn")
        try:
            easyocr_reader = easyocr.Reader(app_config.OCR_LANGUAGES, gpu=False)
            logging_service.web_log("EasyOCR initialized with explicit CPU support.", "info")
        except Exception as e_cpu:
            logging_service.web_log(f"EasyOCR CPU initialization failed: {e_cpu}", "critical")
            return None # Critical failure
    if easyocr_reader is None: # Should be caught if first try fails and second try also fails
        logging_service.web_log("EasyOCR reader could not be initialized.", "critical")
        return None


    # 4. Initialize Services/Managers
    logging_service.web_log("Initializing application services...", "info")

    odoo_connector = OdooConnector(
        url=app_config.ODOO_URL,
        db_name=app_config.ODOO_DB_NAME,
        db_user=app_config.ODOO_DB_USER,
        db_password=app_config.ODOO_DB_PASSWORD,
        logging_service=logging_service
    )
    if not odoo_connector.test_connection():
        logging_service.web_log("Odoo connection failed during setup. Data may not be saved to Odoo.", "warn")

    storage_handler = StorageHandler(
        save_dir=app_config.SAVE_DIR,
        log_file_path=app_config.LOG_FILE,
        image_max_age_days=app_config.IMAGE_MAX_AGE_DAYS,
        cleanup_target_hour=app_config.IMAGE_CLEANUP_TARGET_HOUR,
        cleanup_interval_sec=app_config.IMAGE_CLEANUP_CHECK_INTERVAL_SECONDS,
        logging_service=logging_service,
        app_root=app_config.APP_ROOT
    )

    anpr_processor = ANPRProcessor(
        easyocr_reader=easyocr_reader,
        plate_cascade=plate_cascade,
        odoo_connector=odoo_connector,
        storage_handler=storage_handler,
        logging_service=logging_service,
        app_config_obj=app_config
    )

    camera_manager = CameraManager(
        anpr_processor=anpr_processor,
        logging_service=logging_service,
        app_config=app_config
    )

    logging_service.web_log("All core services initialized.", "info")

    return {
        "app": app,
        "socketio": socketio_instance,
        "logging_service": logging_service,
        "odoo_connector": odoo_connector,
        "storage_handler": storage_handler,
        "anpr_processor": anpr_processor, # Though not directly used by app.py, useful if app.py needed it
        "camera_manager": camera_manager,
        "config": app_config # Pass config if needed by app.py or routes initialization
    }