# --- Attempt to patch with eventlet FIRST ---
_eventlet_available = False
try:
    import eventlet

    eventlet.monkey_patch()
    _eventlet_available = True
    print("INFO: Eventlet monkey patching successfully applied.")
except ImportError:
    print("INFO: Eventlet not found. Server will use standard threading or Werkzeug's default capabilities.")
except RuntimeError as e:
    print(
        f"ERROR: Eventlet monkey_patch() failed: {e}. Server will use standard threading or Werkzeug's default capabilities.")
    _eventlet_available = False

import sys
import os
import threading
import time

# Ensure the project root is in the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app_setup import build_application
import routes

if __name__ == '__main__':
    app_components = build_application(eventlet_available_flag=_eventlet_available)

    if app_components is None:
        print("CRITICAL: Application setup failed. Exiting.")
        sys.exit(1)

    # Unpack components
    flask_app = app_components["app"]
    socketio_instance = app_components["socketio"]
    logging_service = app_components["logging_service"]
    camera_manager = app_components["camera_manager"]
    storage_handler = app_components["storage_handler"]
    odoo_connector = app_components["odoo_connector"]
    app_cfg = app_components["config"]
    gemini_client = app_components["gemini_client"]
    jwt_manager = app_components["jwt_manager"]

    # Initialize routes and pass necessary instances
    routes.init_routes(
        app_instance_flask=flask_app,
        sio_instance=socketio_instance,
        cam_manager=camera_manager,
        store_handler=storage_handler,
        log_service=logging_service,
        cfg=app_cfg,
        odoo_conn=odoo_connector,
    )
    logging_service.web_log("Routes initialized.", "info")

    # Start background threads
    if storage_handler:
        cleanup_thread = threading.Thread(target=storage_handler.run_cleanup_scheduler_at_specific_time, daemon=True)
        cleanup_thread.start()
        logging_service.web_log("Image cleanup scheduler thread started.", "info")

    # Start the camera autostart process in a background thread
    autostart_thread = threading.Thread(target=camera_manager.autostart_cameras_from_odoo, daemon=True)
    autostart_thread.start()

    start_message = f"Starting Flask-SocketIO server on http://{app_cfg.SERVER_HOST}:{app_cfg.SERVER_PORT} (Debug: {app_cfg.FLASK_DEBUG})"
    if _eventlet_available:
        logging_service.web_log(f"{start_message} with eventlet.", "info")
        socketio_instance.run(flask_app, host=app_cfg.SERVER_HOST, port=app_cfg.SERVER_PORT)
    else:
        logging_service.web_log(f"{start_message} with standard Werkzeug server.", "info")
        socketio_instance.run(flask_app, host=app_cfg.SERVER_HOST, port=app_cfg.SERVER_PORT, debug=app_cfg.FLASK_DEBUG,
                              allow_unsafe_werkzeug=True)

    camera_manager.stop_all_cameras()
    print("Server has shut down.")
