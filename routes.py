# anpr_flask_project/routes.py
from flask import current_app, render_template, Response, request, send_from_directory
from flask_socketio import emit
import os
import time

# These will be set by app.py after initialization
camera_manager = None
storage_handler = None
logging_service = None
flask_app = None  # Renamed from app to avoid conflict with Flask's 'app' context
socketio_instance = None
app_config = None
odoo_connector = None  # Add odoo_connector to be initialized


def init_routes(app_instance_flask, sio_instance, cam_manager, store_handler, log_service, cfg,
                odoo_conn):  # Added odoo_conn
    global camera_manager, storage_handler, logging_service, flask_app, socketio_instance, app_config, odoo_connector
    flask_app = app_instance_flask
    socketio_instance = sio_instance
    camera_manager = cam_manager
    storage_handler = store_handler
    logging_service = log_service
    app_config = cfg
    odoo_connector = odoo_conn  # Initialize odoo_connector

    @flask_app.route('/')
    def index():
        locations = []
        if odoo_connector:
            locations = odoo_connector.get_camera_locations()  # Fetch locations
            # Ensure locations is a list of dicts with 'id' and 'name'
            # If Odoo returns {'id': X, 'name': 'Y', 'description': 'Z'}, it's fine.
        else:
            logging_service.web_log("Odoo connector not available for fetching locations.", "warn")

        # Provide a default if no locations are fetched or Odoo is down
        if not locations:
            locations = [
                {'id': 0, 'name': app_config.DEFAULT_CAMERA_LOCATION, 'description': 'Default (Odoo unavailable)'}]

        return render_template('index.html', camera_locations=locations)

    @flask_app.route('/video_feed')
    def video_feed_route():
        source_param = request.args.get('source', app_config.DEFAULT_SOURCE_TYPE)
        camera_id_req = request.args.get('id', app_config.DEFAULT_CAMERA_IDENTIFIER)
        # Location name now comes from the dropdown value, which is the 'name' field from Odoo
        location_name_req = request.args.get('location', app_config.DEFAULT_CAMERA_LOCATION)

        logging_service.web_log(
            f"Video feed requested. Source: {source_param}, ID: {camera_id_req}, Location: {location_name_req}",
            "debug")

        if camera_manager.is_generating_frames:
            camera_manager.stop_frame_generation()
            time.sleep(0.1)

        needs_reinit = False
        if camera_id_req != camera_manager.current_camera_identifier or \
                source_param != camera_manager.current_source_type or \
                location_name_req != camera_manager.current_camera_location:  # Check if location changed
            needs_reinit = True
        elif source_param != "phone_stream" and \
                (camera_manager.video_capture is None or not camera_manager.video_capture.isOpened()):
            needs_reinit = True

        if needs_reinit:
            logging_service.web_log(
                f"Video_feed route: Re-initializing camera to ID: '{camera_id_req}', Source: {source_param}, Location: {location_name_req}")
            if not camera_manager.initialize_camera(source_param, camera_id_req, location_name_req):
                logging_service.web_log(
                    f"Video_feed_route: initialize_camera failed for {camera_id_req}. Stream may show error.", "warn")

        return Response(camera_manager.generate_frames_for_web_stream(),
                        mimetype='multipart/x-mixed-replace; boundary=frame')

    @flask_app.route('/get_image/<path:filename>')
    def get_image(filename):
        save_dir_abs = storage_handler.get_save_directory()
        try:
            # logging_service.web_log(f"Serving image: {filename} from {save_dir_abs}", "debug") # Can be noisy
            return send_from_directory(save_dir_abs, filename)
        except FileNotFoundError:
            logging_service.web_log(f"Image not found: {filename} in {save_dir_abs}", "error")
            return "Image not found", 404
        except Exception as e:
            logging_service.web_log(f"Error serving image {filename}: {e}", "error")
            return "Error serving image", 500

    @socketio_instance.on('connect')
    def handle_connect():
        logging_service.web_log('Client connected to SocketIO.', "info")

    @socketio_instance.on('disconnect')
    def handle_disconnect():
        logging_service.web_log('Client disconnected from SocketIO.', "info")

    @socketio_instance.on('phone_frame_stream')
    def handle_phone_frame_socket(data):
        if camera_manager:
            camera_manager.handle_phone_frame_stream(data)
        else:
            logging_service.web_log("CameraManager not initialized, cannot handle phone frame.", "error")
