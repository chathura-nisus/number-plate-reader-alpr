from flask import render_template, Response, request, jsonify, send_from_directory
import time
from utils.auth import jwt_manager

# Globals that will be initialized
camera_manager = None
storage_handler = None
logging_service = None
flask_app = None
socketio_instance = None
app_config = None
odoo_connector = None


def init_routes(app_instance_flask, sio_instance, cam_manager, store_handler, log_service, cfg, odoo_conn):
    global camera_manager, storage_handler, logging_service, flask_app, socketio_instance, app_config, odoo_connector
    flask_app = app_instance_flask
    socketio_instance = sio_instance
    camera_manager = cam_manager
    storage_handler = store_handler
    logging_service = log_service
    app_config = cfg
    odoo_connector = odoo_conn

    # MODIFIED: This route now fetches active cameras to display the correct state on the dashboard
    @flask_app.route('/')
    def index():
        locations = odoo_connector.get_camera_locations() if odoo_connector else []
        active_cameras = camera_manager.get_active_worker_ids() if camera_manager else []
        return render_template('index.html', locations=locations, active_cameras=active_cameras, title="ANPR Dashboard")

    @flask_app.route('/streamer')
    def streamer():
        return render_template('streamer.html')

    @flask_app.route('/get_image/<path:filename>')
    def get_image(filename):
        """Route to serve captured images to the frontend."""
        save_dir_abs = storage_handler.get_save_directory()
        try:
            return send_from_directory(save_dir_abs, filename)
        except FileNotFoundError:
            return "Image not found", 404

    @flask_app.route('/video_feed/<camera_id>')
    def video_feed(camera_id):
        def generate():
            while True:
                # Check if the camera is still supposed to be running
                if camera_id not in camera_manager.get_active_worker_ids():
                    break
                frame = camera_manager.get_frame(camera_id)
                if frame is not None:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                time.sleep(0.04)  # 25 FPS

        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    @flask_app.route('/api/start_camera', methods=['POST'])
    @jwt_manager.jwt_required
    def start_camera_api():
        data = request.json
        location_id = data.get('location_id')
        cam_id = f"cam_{location_id}"
        source = data.get('source')
        name = data.get('name')

        if not all([location_id, source, name]):
            return jsonify({'status': 'error', 'message': 'Missing camera ID, source, or name'}), 400

        camera_manager.start_camera(cam_id, source, location_id, name)
        return jsonify({'status': 'success', 'message': f'Camera {cam_id} start command received.'})

    @flask_app.route('/api/stop_camera', methods=['POST'])
    @jwt_manager.jwt_required
    def stop_camera_api():
        data = request.json
        cam_id = data.get('id')
        if not cam_id:
            return jsonify({'status': 'error', 'message': 'Missing camera ID'}), 400

        camera_manager.stop_camera(cam_id)
        return jsonify({'status': 'success', 'message': f'Camera {cam_id} stopped.'})

    @socketio_instance.on('connect')
    def handle_connect():
        logging_service.web_log('Client connected to SocketIO.', "info")

    @socketio_instance.on('disconnect')
    def handle_disconnect():
        logging_service.web_log('Client disconnected from SocketIO.', "info")

    @socketio_instance.on('remote_camera_stream')
    def handle_remote_stream(data):
        stream_id = data.get('stream_id')
        image_data = data.get('image_data')
        if stream_id and image_data:
            camera_manager.handle_remote_frame(stream_id, image_data)
