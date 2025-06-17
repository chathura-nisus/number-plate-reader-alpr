import cv2
import threading
import time
from .worker import CameraWorker
from anpr_core.processor import ANPRProcessor


class CameraManager:
    def __init__(self, logging_service, app_config, app_components):
        self.logger = logging_service
        self.config = app_config
        self.app_components = app_components
        self.workers = {}

    # NEW: Add this method to get the IDs of active workers
    def get_active_worker_ids(self):
        """Returns a list of camera IDs for all currently running workers."""
        return list(self.workers.keys())

    def autostart_cameras_from_odoo(self):
        """Queries Odoo for 'running' cameras and starts them."""
        self.logger.web_log("Checking Odoo for cameras to auto-start...", "info")
        odoo_connector = self.app_components.get("odoo_connector")
        if not odoo_connector:
            self.logger.web_log("Cannot autostart cameras: Odoo connector not available.", "error")
            return

        time.sleep(2)

        running_cameras = odoo_connector.get_running_cameras()
        if running_cameras:
            self.logger.web_log(
                f"Found {len(running_cameras)} camera(s) marked as 'running' in Odoo. Starting them now.", "info")
            for cam in running_cameras:
                cam_id = f"cam_{cam['id']}"
                source = cam['source']
                location_id = cam['id']
                location_name = cam['name']
                self.logger.web_log(f"Auto-starting camera: '{location_name}' (Source: {source})", "info")
                self.start_camera(cam_id, source, location_id, location_name)
        else:
            self.logger.web_log("No cameras in 'running' state found in Odoo. No cameras to autostart.", "info")

    def start_camera(self, camera_id, source, location_id, location_name=""):
        if camera_id in self.workers:
            self.logger.web_log(f"Camera '{camera_id}' is already running.", "warn")
            return

        thread = threading.Thread(
            target=self._start_worker_thread,
            args=(camera_id, source, location_id, location_name),
            daemon=True
        )
        thread.start()
        self.logger.web_log(f"Camera start command for '{camera_id}' received. Initializing in background.", "info")

    def _start_worker_thread(self, camera_id, source, location_id, location_name):
        odoo_connector = self.app_components.get("odoo_connector")
        try:
            anpr_settings = self.app_components.get("anpr_settings", {})
            ocr_engine_choice = anpr_settings.get('ocr_engine', 'easyocr')
            gemini_client = self.app_components.get("gemini_client")

            anpr_processor = ANPRProcessor(
                easyocr_reader=self.app_components["easyocr_reader"],
                plate_cascade=self.app_components["plate_cascade"],
                odoo_connector=odoo_connector,
                storage_handler=self.app_components["storage_handler"],
                logging_service=self.logger,
                app_config_obj=self.config,
                ocr_engine=ocr_engine_choice,
                gemini_client=gemini_client
            )

            camera_info = {'identifier': camera_id, 'source': source, 'location_id': location_id, 'name': location_name}

            if odoo_connector:
                odoo_connector.update_camera_status(location_id, 'starting', "Initializing camera...")

            worker = CameraWorker(camera_info, anpr_processor, self.logger, self.config)
            worker.start()

            if worker.is_running():
                self.workers[camera_id] = worker
                self.logger.web_log(f"Successfully started worker for '{camera_id}'.", "info")
                self.logger.emit_event('camera_started', {'identifier': camera_id, 'name': location_name})
                if odoo_connector:
                    odoo_connector.update_camera_status(location_id, 'running', "Stream is active.")
            else:
                raise RuntimeError("Worker thread failed to start or camera failed to open.")

        except Exception as e:
            self.logger.web_log(f"Failed to start camera worker for '{camera_id}': {e}", "error", exc_info=True)
            if odoo_connector:
                odoo_connector.update_camera_status(location_id, 'error', str(e))

    def stop_camera(self, camera_id):
        if camera_id in self.workers:
            location_id_to_update = self.workers[camera_id].camera_info.get('location_id')
            location_name = self.workers[camera_id].camera_info.get('name')

            self.workers[camera_id].stop()
            del self.workers[camera_id]
            self.logger.web_log(f"Successfully stopped and removed worker for '{camera_id}'.", "info")
            self.logger.emit_event('camera_stopped', {'identifier': camera_id, 'name': location_name})

            odoo_connector = self.app_components.get("odoo_connector")
            if odoo_connector and location_id_to_update:
                odoo_connector.update_camera_status(location_id_to_update, 'stopped',
                                                    "Camera stream stopped successfully.")
        else:
            self.logger.web_log(f"Could not stop camera '{camera_id}': not found.", "warn")

    def get_frame(self, camera_id):
        worker = self.workers.get(camera_id)
        return worker.latest_frame if worker else None

    def handle_remote_frame(self, stream_id, image_data):
        worker = self.workers.get(stream_id)
        if worker and worker.is_remote_stream:
            worker.push_remote_frame(image_data)

    def stop_all_cameras(self):
        self.logger.web_log("Stopping all active cameras...", "info")
        for cam_id in list(self.workers.keys()):
            self.stop_camera(cam_id)
