import cv2
import numpy as np
import base64
import time
import threading
import queue


class CameraWorker:
    def __init__(self, camera_info, anpr_processor, logging_service, config):
        self.camera_info = camera_info
        self.anpr_processor = anpr_processor
        self.logger = logging_service
        self.config = config

        self.video_capture = None
        self.latest_frame = None
        self.frame_queue = queue.Queue(maxsize=2)
        self.is_remote_stream = False

        self._is_running = False
        self.thread = None

    def _initialize_camera(self):
        source = self.camera_info.get('source')
        camera_id = self.camera_info.get('identifier')

        if str(source).lower() == 'remote_stream':
            self.is_remote_stream = True
            self.logger.web_log(f"Worker for '{camera_id}' initialized in REMOTE mode.", "info")
            return True

        # Try to convert to int if it's a digit (for local webcams 0, 1, etc.)
        if str(source).isdigit():
            source = int(source)
        elif str(source).lower() == 'local':  # Handle 'local' as a synonym for 0
            source = 0

        self.video_capture = cv2.VideoCapture(source)
        if self.video_capture.isOpened():
            self.logger.web_log(f"Worker for '{camera_id}' initialized hardware source: {source}", "info")
            return True
        else:
            self.logger.web_log(f"ERROR: Could not open camera source: {source}", "error")
            return False

    def is_running(self):
        """Public method to check the running state of the worker."""
        return self._is_running

    def push_remote_frame(self, image_data):
        try:
            # Non-blocking put, if queue is full, drop the frame
            self.frame_queue.put_nowait(image_data)
        except queue.Full:
            pass  # Ignore if the queue is full, just drop the frame

    def _processing_loop(self):
        camera_id = self.camera_info.get('identifier')

        while self._is_running:
            try:
                frame = None
                if self.is_remote_stream:
                    # For remote streams, block and wait for a frame to arrive
                    image_data_url = self.frame_queue.get(timeout=5)
                    if image_data_url is None:  # Shutdown signal
                        break
                    encoded_data = image_data_url.split(',')[1]
                    nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                else:
                    # For hardware cameras, read directly
                    ret, frame = self.video_capture.read()
                    if not ret:
                        self.logger.web_log(f"Lost connection to hardware camera '{camera_id}'. Stopping worker.",
                                            "warn")
                        break

                if frame is None:
                    continue

                # The core processing logic
                processed_frame = self.anpr_processor.process_detected_plates(frame.copy(), frame, self.camera_info)

                # Encode the processed frame to JPEG for streaming
                (flag, encodedImage) = cv2.imencode(".jpg", processed_frame)
                if flag:
                    self.latest_frame = encodedImage.tobytes()

            except queue.Empty:
                self.logger.web_log(f"No remote frame received for '{camera_id}' in 5s. Pausing.", "warn")
                self.latest_frame = None
                continue
            except Exception as e:
                self.logger.web_log(f"Error in processing loop for '{camera_id}': {e}", "error", exc_info=True)
                # Let's not break the loop for processing errors, just log and continue
                time.sleep(1)

            time.sleep(0.02)  # Small delay to yield CPU

    def start(self):
        if self._initialize_camera():
            self._is_running = True
            self.thread = threading.Thread(target=self._processing_loop, daemon=True)
            self.thread.start()
            self.logger.web_log(f"Camera worker thread started for '{self.camera_info.get('identifier')}'.", "info")

    def stop(self):
        self._is_running = False
        if self.thread:
            if self.is_remote_stream:
                # Send a shutdown signal to the queue
                self.frame_queue.put(None)
            self.thread.join(timeout=2)
        if self.video_capture and self.video_capture.isOpened():
            self.video_capture.release()
        self.logger.web_log(f"Worker for '{self.camera_info.get('identifier')}' has been stopped.", "info")
