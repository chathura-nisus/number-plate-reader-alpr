# anpr_flask_project/odoo/connector.py
import xmlrpc.client
import base64
import os
import mimetypes
from datetime import datetime as dt


class OdooConnector:
    def __init__(self, url, db_name, db_user, db_password, logging_service):
        self.url = url
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.logger = logging_service
        self.uid = None
        self.models = None
        self._connect()

    def _connect(self):
        try:
            common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common', allow_none=True, verbose=False)
            self.uid = common.authenticate(self.db_name, self.db_user, self.db_password, {})
            if not self.uid:
                self.logger.web_log(f"Odoo authentication failed for user '{self.db_user}'. Check credentials.",
                                    "error")
                self.models = None
                return False
            self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object', allow_none=True, verbose=False)
            # self.logger.web_log("Successfully connected and authenticated with Odoo.", "info") # Moved to test_connection
            return True
        except ConnectionRefusedError:
            self.logger.web_log(f"Odoo connection refused at {self.url}.", "error")
        except xmlrpc.client.Error as e:
            self.logger.web_log(f"Odoo XML-RPC Error during connect: {e}", "error")
        except Exception as e:
            self.logger.web_log(f"Unexpected error during Odoo connection setup: {e}", "error")
        self.uid = None
        self.models = None
        return False

    def test_connection(self):
        if self.uid and self.models:
            self.logger.web_log("Odoo connection test successful (already connected).", "info")
            return True
        if self._connect():
            self.logger.web_log("Odoo connection test successful (reconnected).", "info")
            return True
        self.logger.web_log("Odoo connection test failed.", "error")
        return False

    def get_camera_locations(self):
        """Fetches all camera locations from Odoo."""
        if not self.uid or not self.models:
            if not self._connect():
                self.logger.web_log("Cannot fetch camera locations: Odoo not connected/authenticated.", "error")
                return []
        try:
            location_ids = self.models.execute_kw(
                self.db_name, self.uid, self.db_password,
                'anpr.camera.location', 'search_read',
                [[]],  # No domain, fetch all
                {'fields': ['id', 'name', 'description'], 'order': 'name'}  # Specify fields and order
            )
            self.logger.web_log(f"Fetched {len(location_ids)} camera locations from Odoo.", "info")
            # location_ids will be a list of dictionaries, e.g., [{'id': 1, 'name': 'Main Gate'}, ...]
            return location_ids
        except xmlrpc.client.Fault as e:
            self.logger.web_log(f"Odoo XML-RPC Fault fetching camera locations: {e.faultString}", "error")
            return []
        except Exception as e:
            self.logger.web_log(f"Error fetching camera locations from Odoo: {e}", "error", exc_info=True)
            return []

    def save_detection_log(self, detection_data):
        if not self.uid or not self.models:
            if not self._connect():
                self.logger.web_log("Skipping Odoo save: Not connected/authenticated.", "error")
                return {'success': False, 'error': 'Odoo connection failed'}

        log_id = None
        try:
            dt_obj = detection_data.get('detection_time_obj', dt.now())
            log_vals = {
                'license_plate': detection_data['text'],
                'detection_time': dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
                'confidence_score': float(detection_data.get('score', 0.0)),
                'camera_source_identifier': detection_data.get('camera_source', 'Unknown'),
                'location': detection_data.get('location', 'Unknown'),
                # This should be the name from anpr.camera.location
                'image_filename': detection_data.get('plate_roi_filename', ''),
                'full_frame_filename': detection_data.get('full_frame_filename', ''),
            }
            log_id = self.models.execute_kw(
                self.db_name, self.uid, self.db_password,
                'anpr.detection.log', 'create', [log_vals]
            )
            if not isinstance(log_id, int):
                if isinstance(log_id, list) and len(log_id) > 0:
                    log_id = log_id[0]
                else:
                    raise ValueError(f"Odoo log creation failed, returned: {log_id}")

            self.logger.web_log(f"Created ANPR log in Odoo with ID: {log_id}", "info")

            update_payload = {}
            plate_fp = detection_data.get('plate_roi_filepath')
            plate_fn = detection_data.get('plate_roi_filename')
            if plate_fp and plate_fn and os.path.exists(plate_fp):
                try:
                    with open(plate_fp, 'rb') as f:
                        plate_b64 = base64.b64encode(f.read()).decode('utf-8')
                    mt, _ = mimetypes.guess_type(plate_fp)
                    p_mimetype = mt or ('image/jpeg' if plate_fn.lower().endswith(
                        ('.jpg', '.jpeg')) else 'image/png' if plate_fn.lower().endswith(
                        '.png') else 'application/octet-stream')
                    p_att_vals = {'name': plate_fn, 'datas': plate_b64, 'res_model': 'anpr.detection.log',
                                  'res_id': log_id, 'mimetype': p_mimetype}
                    plate_att_id = self.models.execute_kw(self.db_name, self.uid, self.db_password, 'ir.attachment',
                                                          'create', [p_att_vals])
                    if isinstance(plate_att_id, int):
                        update_payload['attachment_id'] = plate_att_id
                    elif isinstance(plate_att_id, list) and len(plate_att_id) > 0:
                        update_payload['attachment_id'] = plate_att_id[0]

                except Exception as e:
                    self.logger.web_log(f"Error attaching Plate ROI to Odoo (Log ID {log_id}): {e}", "error")

            ff_fp = detection_data.get('full_frame_filepath')
            ff_fn = detection_data.get('full_frame_filename')
            if ff_fp and ff_fn and os.path.exists(ff_fp):
                try:
                    with open(ff_fp, 'rb') as f:
                        ff_b64 = base64.b64encode(f.read()).decode('utf-8')
                    mt_ff, _ = mimetypes.guess_type(ff_fp)
                    ff_mimetype = mt_ff or ('image/jpeg' if ff_fn.lower().endswith(
                        ('.jpg', '.jpeg')) else 'image/png' if ff_fn.lower().endswith(
                        '.png') else 'application/octet-stream')
                    ff_att_vals = {'name': ff_fn, 'datas': ff_b64, 'res_model': 'anpr.detection.log', 'res_id': log_id,
                                   'mimetype': ff_mimetype}
                    ff_att_id = self.models.execute_kw(self.db_name, self.uid, self.db_password, 'ir.attachment',
                                                       'create', [ff_att_vals])
                    if isinstance(ff_att_id, int):
                        update_payload['full_frame_attachment_id'] = ff_att_id
                    elif isinstance(ff_att_id, list) and len(ff_att_id) > 0:
                        update_payload['full_frame_attachment_id'] = ff_att_id[0]
                except Exception as e:
                    self.logger.web_log(f"Error attaching Full Frame to Odoo (Log ID {log_id}): {e}", "error")

            if update_payload and log_id:
                self.models.execute_kw(self.db_name, self.uid, self.db_password, 'anpr.detection.log', 'write',
                                       [[log_id], update_payload])

            return {'success': True, 'log_id': log_id}

        except xmlrpc.client.Fault as e:
            self.logger.web_log(f"Odoo XML-RPC Fault during save: {e.faultString}", "error")
            return {'success': False, 'error': e.faultString}
        except Exception as e:
            self.logger.web_log(f"General error saving to Odoo: {e}", "error", exc_info=True)
            return {'success': False, 'error': str(e)}
