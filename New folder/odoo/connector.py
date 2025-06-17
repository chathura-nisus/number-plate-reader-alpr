import xmlrpc.client
import base64
import os
from datetime import datetime as dt
import threading


class OdooConnector:
    def __init__(self, url, db_name, db_user, db_password, logging_service):
        self.url = url
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.logger = logging_service
        self.uid = None
        self.models = None
        self.anpr_settings = {}
        self.lock = threading.Lock()
        self._connect()
        if self.uid:
            self.anpr_settings = self.get_anpr_settings()

    def _connect(self):
        try:
            common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common', allow_none=True, verbose=False)
            self.uid = common.authenticate(self.db_name, self.db_user, self.db_password, {})
            if not self.uid:
                self.logger.web_log(f"Odoo authentication failed for user '{self.db_user}'. Check credentials.",
                                    "error")
                return False
            self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object', allow_none=True, verbose=False)
            self.logger.web_log(f"Successfully connected to Odoo database '{self.db_name}'.", "info")
            return True
        except Exception as e:
            self.logger.web_log(f"Odoo connection error: {e}", "error")
            return False

    def get_anpr_settings(self):
        if not self.uid: return {}
        with self.lock:
            try:
                settings = self.models.execute_kw(
                    self.db_name, self.uid, self.db_password,
                    'res.config.settings', 'get_anpr_settings', []
                )
                if settings:
                    self.logger.web_log("Successfully fetched ANPR settings from Odoo.", "info")
                    return settings
                return {}
            except Exception as e:
                self.logger.web_log(f"Error fetching ANPR settings from Odoo: {e}", "error")
                return {}

    def get_camera_locations(self):
        """ Fetches the list of camera locations from Odoo for the dashboard. """
        if not self.uid:
            self.logger.web_log("Cannot get camera locations: Odoo is not connected (no UID).", "warn")
            return []
        try:
            self.logger.web_log("Attempting to fetch camera locations from Odoo...", "info")
            locations = self.models.execute_kw(
                self.db_name, self.uid, self.db_password,
                'anpr.camera.location', 'search_read', [[]],
                {'fields': ['id', 'name', 'source', 'description', 'state']}
            )
            self.logger.web_log(f"Successfully fetched {len(locations)} camera location(s) from Odoo.", "info")
            return locations
        except Exception as e:
            # detailed logging to expose the error.
            self.logger.web_log("=" * 60, "critical")
            self.logger.web_log("CRITICAL ERROR FETCHING CAMERA LOCATIONS FROM ODOO", "critical")
            self.logger.web_log(f"The XML-RPC call to 'search_read' on 'anpr.camera.location' failed.", "error")
            self.logger.web_log(f"This is why the camera controls are not appearing on the dashboard.", "error")
            self.logger.web_log(f"Exception details: {e}", "error", exc_info=True)
            self.logger.web_log("=" * 60, "critical")
            return []

    def get_running_cameras(self):
        if not self.uid: return []
        try:
            cameras = self.models.execute_kw(
                self.db_name, self.uid, self.db_password,
                'anpr.camera.location', 'search_read',
                [[['state', '=', 'running']]],
                {'fields': ['id', 'name', 'source', 'description']}
            )
            return cameras
        except Exception as e:
            self.logger.web_log(f"Error fetching running cameras from Odoo: {e}", "error")
            return []

    def update_camera_status(self, location_id, state, message=""):
        if not self.uid: return
        with self.lock:
            try:
                self.models.execute_kw(
                    self.db_name, self.uid, self.db_password,
                    'anpr.camera.location', 'write',
                    [[location_id], {'state': state, 'state_message': message}]
                )
            except Exception as e:
                self.logger.web_log(f"Error updating camera status in Odoo for location {location_id}: {e}", "error")

    def save_detection_log(self, data):
        if not self.uid:
            self.logger.web_log("Cannot save log to Odoo: not connected.", "error")
            return {'success': False, 'error': 'Not connected to Odoo'}
        with self.lock:
            try:
                payload = {
                    'license_plate': data['text'],
                    'detection_time': dt.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'confidence_score': data.get('confidence', 0.0),
                    'location_id': data.get('location_id'),
                    'camera_source_identifier': data.get('camera_source'),
                }

                plate_roi_path = data.get('plate_roi_filepath')
                if plate_roi_path and os.path.exists(plate_roi_path):
                    with open(plate_roi_path, 'rb') as f:
                        payload['captured_image'] = base64.b64encode(f.read()).decode('utf-8')

                full_frame_path = data.get('full_frame_filepath')
                if full_frame_path and os.path.exists(full_frame_path):
                    with open(full_frame_path, 'rb') as f:
                        payload['full_frame_image'] = base64.b64encode(f.read()).decode('utf-8')

                self.logger.web_log(f"Sending new detection log to Odoo for plate '{data['text']}'.", "info")
                log_id = self.models.execute_kw(
                    self.db_name, self.uid, self.db_password,
                    'anpr.detection.log', 'create', [payload]
                )

                if isinstance(log_id, int):
                    self.logger.web_log(f"Successfully created Odoo log with ID: {log_id}", "info")
                    return {'success': True, 'log_id': log_id}
                else:
                    self.logger.web_log(f"Failed to create Odoo log record. Odoo response: {log_id}", "error")
                    return {'success': False, 'error': 'Failed to create log record in Odoo.'}

            except xmlrpc.client.Fault as e:
                self.logger.web_log(f"Odoo XML-RPC Fault during save: {e.faultString}", "error")
                return {'success': False, 'error': e.faultString}
            except Exception as e:
                self.logger.web_log(f"General error saving to Odoo: {e}", "error", exc_info=True)
                return {'success': False, 'error': str(e)}
