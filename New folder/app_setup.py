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
from anpr_core.gemini_client import GeminiClient
from utils.auth import jwt_manager


def build_application(eventlet_available_flag):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = app_config.FLASK_SECRET_KEY
    socketio_instance = SocketIO(app, async_mode='eventlet' if eventlet_available_flag else None)
    logging_service = LoggingService(socketio_instance=socketio_instance)
    logging_service.web_log("Application setup starting...", "info")

    plate_cascade = cv2.CascadeClassifier(app_config.CASCADE_FILE)
    easyocr_reader = easyocr.Reader(app_config.OCR_LANGUAGES, gpu=False)

    logging_service.web_log("Initializing application services...", "info")
    odoo_connector = OdooConnector(
        url=app_config.ODOO_URL, db_name=app_config.ODOO_DB_NAME,
        db_user=app_config.ODOO_DB_USER, db_password=app_config.ODOO_DB_PASSWORD,
        logging_service=logging_service
    )

    anpr_settings = odoo_connector.get_anpr_settings()
    if not anpr_settings:
        logging_service.web_log("Could not fetch ANPR settings from Odoo. Shutting down.", "critical")
        return None

    jwt_manager.init_app(app, odoo_connector, logging_service)

    storage_handler = StorageHandler(
        save_dir=app_config.SAVE_DIR, log_file_path=app_config.LOG_FILE,
        image_max_age_days=app_config.IMAGE_MAX_AGE_DAYS,
        cleanup_target_hour=app_config.IMAGE_CLEANUP_TARGET_HOUR,
        cleanup_interval_sec=app_config.IMAGE_CLEANUP_CHECK_INTERVAL_SECONDS,
        logging_service=logging_service, app_root=app_config.APP_ROOT
    )

    # Pass the app_config object to the GeminiClient
    gemini_client = GeminiClient(
        api_key=anpr_settings.get('api_key'),
        api_url=app_config.GEMINI_API_URL,
        model_name=app_config.GEMINI_MODEL_NAME,
        logging_service=logging_service,
        config=app_config
    )

    app_components_for_workers = {
        "easyocr_reader": easyocr_reader,
        "plate_cascade": plate_cascade,
        "odoo_connector": odoo_connector,
        "storage_handler": storage_handler,
        "gemini_client": gemini_client,
        "anpr_settings": anpr_settings
    }

    camera_manager = CameraManager(
        logging_service=logging_service,
        app_config=app_config,
        app_components=app_components_for_workers
    )

    logging_service.web_log("All core services initialized.", "info")

    return {
        "app": app,
        "socketio": socketio_instance,
        "logging_service": logging_service,
        "camera_manager": camera_manager,
        "storage_handler": storage_handler,
        "odoo_connector": odoo_connector,
        "config": app_config,
        "gemini_client": gemini_client,
        "jwt_manager": jwt_manager
    }
