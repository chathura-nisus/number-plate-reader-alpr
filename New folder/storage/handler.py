import os
import csv
import time
from datetime import datetime as dt, timedelta
import cv2
import re


class StorageHandler:
    def __init__(self, save_dir, log_file_path, image_max_age_days, cleanup_target_hour, cleanup_interval_sec,
                 logging_service, app_root):
        self.save_dir = save_dir
        self.log_file_path = os.path.join(self.save_dir, os.path.basename(log_file_path))
        self.image_max_age_days = image_max_age_days
        self.cleanup_target_hour = cleanup_target_hour
        self.cleanup_interval_sec = cleanup_interval_sec
        self.logger = logging_service
        self.app_root = app_root
        self.last_cleanup_day = -1
        self._ensure_directories_exist()

    def _ensure_directories_exist(self):
        if not os.path.exists(self.save_dir):
            try:
                os.makedirs(self.save_dir)
                self.logger.web_log(f"Created save directory: {self.save_dir}", "info")
            except OSError as e:
                self.logger.web_log(f"Error creating save directory {self.save_dir}: {e}", "critical")

    def get_save_directory(self):
        return self.save_dir

    def save_detection_images(self, plate_roi, full_frame, plate_text="UNKNOWN"):
        try:
            timestamp = dt.now()
            safe_plate_text = re.sub(r'[^A-Z0-9]', '', plate_text.upper())
            base_filename = f"plate_{safe_plate_text}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"

            plate_roi_filename = f"{base_filename}.jpg"
            plate_roi_filepath = os.path.join(self.save_dir, plate_roi_filename)
            cv2.imwrite(plate_roi_filepath, plate_roi)

            full_frame_filename = None
            full_frame_filepath = None
            if full_frame is not None:
                full_frame_filename = f"{base_filename}_full.jpg"
                full_frame_filepath = os.path.join(self.save_dir, full_frame_filename)
                cv2.imwrite(full_frame_filepath, full_frame)

            return {
                'plate_roi_filename': plate_roi_filename,
                'plate_roi_filepath': plate_roi_filepath,
                'full_frame_filename': full_frame_filename,
                'full_frame_filepath': full_frame_filepath
            }
        except Exception as e:
            self.logger.web_log(f"Error saving images: {e}", "error", exc_info=True)
            return None

    def run_cleanup_scheduler_at_specific_time(self):
        self.logger.web_log("Image cleanup scheduler (specific time) started.", "info")
        while True:
            now = dt.now()
            if now.hour == self.cleanup_target_hour and now.day != self.last_cleanup_day:
                self.cleanup_old_images()
            time.sleep(self.cleanup_interval_sec)

    def cleanup_old_images(self):
        if not os.path.isdir(self.save_dir):
            return

        self.logger.web_log(f"Cleanup: Starting daily cleanup of images older than {self.image_max_age_days} days...")
        cutoff = dt.now() - timedelta(days=self.image_max_age_days)
        deleted_count = 0
        checked_count = 0

        for filename in os.listdir(self.save_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                checked_count += 1
                file_path = os.path.join(self.save_dir, filename)
                try:
                    file_mod_time = dt.fromtimestamp(os.path.getmtime(file_path))
                    if file_mod_time < cutoff:
                        os.remove(file_path)
                        deleted_count += 1
                except Exception as e_file:
                    self.logger.web_log(f"Cleanup: Error processing file '{filename}': {e_file}", "error")

        self.logger.web_log(f"Cleanup: Finished. Checked {checked_count}, deleted {deleted_count} images.")
        self.last_cleanup_day = dt.now().day
