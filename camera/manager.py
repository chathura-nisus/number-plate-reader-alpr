import cv2
import numpy as np
import time
import base64
import config


class CameraManager:
    def __init__(self, anpr_processor, logging_service, app_config):
        self.anpr_processor = anpr_processor  # To process frames
        self.logger = logging_service
        self.config = app_config

        self.video_capture = None
        self.current_camera_identifier = self.config.DEFAULT_CAMERA_IDENTIFIER
        self.current_camera_location = self.config.DEFAULT_CAMERA_LOCATION
        self.current_source_type = self.config.DEFAULT_SOURCE_TYPE

        self.phone_camera_frame = None
        self.last_phone_frame_time = 0
        self.is_generating_frames = False  # To control the frame generation loop

    def initialize_camera(self, source_param="local", camera_id="default_local", location_name="Main Gate"):
        previous_camera_id = self.current_camera_identifier
        self.current_camera_identifier = camera_id
        self.current_camera_location = location_name
        self.current_source_type = source_param

        if self.video_capture and source_param != "phone_stream":
            self.video_capture.release()
        self.video_capture = None

        self.logger.web_log(
            f"Attempting to initialize camera: {source_param} (ID: {camera_id}, Location: {location_name})")

        if source_param == "phone_stream":
            self.logger.web_log("Switched to phone stream mode. Waiting for frames via SocketIO.")
            return True

        actual_source_to_open = None
        if source_param and source_param.lower() != "local":
            actual_source_to_open = source_param
            if source_param.isdigit():
                actual_source_to_open = int(source_param)
        else:  # Try default camera indices for "local"
            for index in [0, 1, -1]:  # Common camera indices
                temp_cap = cv2.VideoCapture(index)
                if temp_cap.isOpened():
                    actual_source_to_open = index
                    temp_cap.release()
                    break
                temp_cap.release()
            if not isinstance(actual_source_to_open, int):
                self.logger.web_log(f"No local camera found for 'local' source for camera ID {camera_id}.", "warn")

        if actual_source_to_open is not None:
            self.video_capture = cv2.VideoCapture(actual_source_to_open)
            if self.video_capture.isOpened():
                self.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.FRAME_WIDTH)
                self.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.FRAME_HEIGHT)
                self.logger.web_log(
                    f"Camera '{camera_id}' at '{location_name}' opened successfully: {actual_source_to_open}")
                return True
            else:
                self.logger.web_log(f"Failed to open camera source: {actual_source_to_open} for ID '{camera_id}'",
                                    "error")
                self.video_capture = None
                self.current_camera_identifier = previous_camera_id  # Revert
                self.current_source_type = self.config.DEFAULT_SOURCE_TYPE  # Revert
                return False
        else:
            self.logger.web_log(f"No valid camera source determined for ID '{camera_id}' (param: {source_param}).",
                                "error")
            self.current_camera_identifier = previous_camera_id  # Revert
            self.current_source_type = self.config.DEFAULT_SOURCE_TYPE  # Revert
            return False

    def handle_phone_frame_stream(self, data):
        try:
            img_data_b64 = data['image_data'].split(',')[1]
            img_bytes = base64.b64decode(img_data_b64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            self.phone_camera_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            self.last_phone_frame_time = time.time()
        except Exception as e:
            self.logger.web_log(f"Phone Frame Error: {e}", "error")
            self.phone_camera_frame = None

    def _get_current_camera_info(self):
        return {
            "identifier": self.current_camera_identifier,
            "location": self.current_camera_location,
            "source_type": self.current_source_type
        }

    def generate_frames_for_web_stream(self):
        self.is_generating_frames = True
        frame_counter = 0

        if self.anpr_processor.plate_cascade is None or self.anpr_processor.plate_cascade.empty():
            self.logger.web_log("Haar Cascade not loaded for ANPR. Cannot generate frames.", "critical")
            error_img = np.zeros((self.config.FRAME_HEIGHT, self.config.FRAME_WIDTH, 3), dtype=np.uint8)
            cv2.putText(error_img, "Haar Cascade Error", (30, self.config.FRAME_HEIGHT // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        1, (0, 0, 255), 2)
            (f, e) = cv2.imencode(".jpg", error_img)
            if f: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + bytearray(e) + b'\r\n')
            self.is_generating_frames = False
            return

        while self.is_generating_frames:
            frame_counter += 1
            captured_frame = None
            status_message = None

            try:
                if self.current_source_type == "phone_stream":
                    if self.phone_camera_frame is not None and \
                            (time.time() - self.last_phone_frame_time < self.config.PHONE_STREAM_TIMEOUT_SECONDS):
                        captured_frame = self.phone_camera_frame.copy()
                    else:
                        status_message = "Waiting for Phone..." if self.phone_camera_frame is None else "Phone Stream Paused/Timeout"
                        time.sleep(0.2)  # Wait a bit for phone frame
                elif self.video_capture and self.video_capture.isOpened():
                    success, cap_frame = self.video_capture.read()
                    if success and cap_frame is not None:
                        captured_frame = cap_frame
                    else:
                        status_message = "Camera Read Error"
                        self.logger.web_log(f"Failed to grab frame from '{self.current_camera_identifier}'.", "warn")
                        time.sleep(0.5)  # Wait before retrying
                else:  # Fallback if source is unknown or camera became unavailable
                    status_message = "Camera Disconnected"
                    self.logger.web_log(
                        f"Source '{self.current_camera_identifier}' (type: {self.current_source_type}) not open in loop.",
                        "error")
                    self.is_generating_frames = False  # Stop generation
                    break

                if status_message:  # Display status if no frame
                    error_img = np.zeros((self.config.FRAME_HEIGHT, self.config.FRAME_WIDTH, 3), dtype=np.uint8)
                    cv2.putText(error_img, status_message, (30, self.config.FRAME_HEIGHT // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    (f, e) = cv2.imencode(".jpg", error_img)
                    if f: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + bytearray(e) + b'\r\n')
                    continue

                if captured_frame is None:
                    time.sleep(0.05)
                    continue

                # Make a copy for display modifications, ANPR works on original frame data
                display_frame = captured_frame.copy()

                # Process for ANPR
                # The ANPR processor will modify display_frame with detections and manage candidates
                current_cam_info = self._get_current_camera_info()
                processed_display_frame = self.anpr_processor.process_detected_plates(display_frame, captured_frame,
                                                                                      current_cam_info)

                (flag, encodedImage) = cv2.imencode(".jpg", processed_display_frame)
                if not flag:
                    self.logger.web_log("JPEG encoding failed.", "warn")
                    continue

                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')
                time.sleep(0.01)  # Control frame rate for web stream

            except Exception as e:  # Catch broad exceptions from the loop
                self.logger.web_log(f"Error in generate_frames_for_web_stream (Loop {frame_counter}): {e}", "error",
                                    exc_info=True)
                self.is_generating_frames = False  # Stop on critical error
                # Potentially yield an error frame
                error_img = np.zeros((self.config.FRAME_HEIGHT, self.config.FRAME_WIDTH, 3), dtype=np.uint8)
                cv2.putText(error_img, "Stream Error", (30, self.config.FRAME_HEIGHT // 2), cv2.FONT_HERSHEY_SIMPLEX, 1,
                            (0, 0, 255), 2)
                (f_err, e_err) = cv2.imencode(".jpg", error_img)
                if f_err: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + bytearray(e_err) + b'\r\n')
                break

        self.logger.web_log("Frame generation stopped.", "info")

    def stop_frame_generation(self):
        self.is_generating_frames = False
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None
        self.logger.web_log("Requested to stop frame generation.", "info")
