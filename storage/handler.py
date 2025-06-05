# anpr_flask_project/storage/handler.py
import os
import csv
import time
from datetime import datetime as dt, timedelta, time as dt_time
import cv2
import re  # For sanitizing filename


class StorageHandler:
    def __init__(self, save_dir, log_file_path, image_max_age_days, cleanup_target_hour, cleanup_interval_sec,
                 logging_service, app_root):
        self.save_dir = save_dir
        self.log_file_path = os.path.join(self.save_dir,
                                          os.path.basename(log_file_path))  # Place log file inside SAVE_DIR
        self.image_max_age_days = image_max_age_days
        self.cleanup_target_hour = cleanup_target_hour
        self.cleanup_interval_sec = cleanup_interval_sec
        self.logger = logging_service
        self.app_root = app_root  # Needed for send_from_directory if SAVE_DIR is relative to app_root

        self.last_cleanup_day = -1
        self._ensure_directories_exist()

    def _ensure_directories_exist(self):
        if not os.path.exists(self.save_dir):
            try:
                os.makedirs(self.save_dir)
                self.logger.web_log(f"Created save directory: {self.save_dir}", "info")
            except OSError as e:
                self.logger.web_log(f"Could not create save directory {self.save_dir}: {e}", "critical")
                raise  # Critical error

    def get_save_directory(self):
        # Ensure it's an absolute path for send_from_directory
        if os.path.isabs(self.save_dir):
            return self.save_dir
        return os.path.join(self.app_root, self.save_dir)

    def save_detection_images(self, plate_roi, full_frame, plate_text_safe, timestamp_obj, save_count):
        timestamp_str_file = timestamp_obj.strftime("%Y%m%d_%H%M%S_%f")

        # Plate ROI
        plate_img_fname_base = f"plate_{plate_text_safe}_{timestamp_str_file}_{str(save_count).zfill(4)}"
        plate_img_fname_full = f"{plate_img_fname_base}.jpg"
        plate_fpath = os.path.join(self.save_dir, plate_img_fname_full)

        # Full Frame
        full_frame_fname_full = None
        full_frame_fpath = None
        if full_frame is not None:
            full_frame_fname_full = f"{plate_img_fname_base}_full.jpg"
            full_frame_fpath = os.path.join(self.save_dir, full_frame_fname_full)

        saved_paths = {
            'plate_roi_filename': None, 'plate_roi_filepath': None,
            'full_frame_filename': None, 'full_frame_filepath': None
        }

        try:
            cv2.imwrite(plate_fpath, plate_roi)
            saved_paths['plate_roi_filename'] = plate_img_fname_full
            saved_paths['plate_roi_filepath'] = plate_fpath
        except Exception as e:
            self.logger.web_log(f"Error saving plate ROI image {plate_fpath}: {e}", "error")

        if full_frame is not None and full_frame_fpath:
            try:
                cv2.imwrite(full_frame_fpath, full_frame)
                saved_paths['full_frame_filename'] = full_frame_fname_full
                saved_paths['full_frame_filepath'] = full_frame_fpath
            except Exception as e:
                self.logger.web_log(f"Error saving full frame image {full_frame_fpath}: {e}", "error")

        return saved_paths

    def log_detected_plate_csv(self, timestamp_obj, image_filename, plate_text):
        timestamp_str_log = timestamp_obj.strftime("%Y-%m-%d %H:%M:%S")
        file_exists = os.path.isfile(self.log_file_path)
        try:
            with open(self.log_file_path, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['Timestamp', 'ImageFilename', 'RecognizedText']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(
                    {'Timestamp': timestamp_str_log, 'ImageFilename': image_filename, 'RecognizedText': plate_text})
        except IOError as e:
            self.logger.web_log(f"CSV Log Error for {self.log_file_path}: {e}", "error")

    def cleanup_old_images(self):
        if not os.path.isdir(self.save_dir):
            self.logger.web_log(f"Cleanup: Save directory '{self.save_dir}' not found.", "warn")
            return

        self.logger.web_log(f"Cleanup: Checking images older than {self.image_max_age_days} days in '{self.save_dir}'.")
        now_ts = time.time()
        cutoff_ts = now_ts - (self.image_max_age_days * 24 * 3600)
        deleted_count = 0
        checked_count = 0

        try:
            for filename in os.listdir(self.save_dir):
                # Only target image files, not the CSV log or other files
                if not (filename.lower().endswith((".jpg", ".png", ".jpeg"))):
                    continue

                filepath = os.path.join(self.save_dir, filename)
                try:
                    if os.path.isfile(filepath):
                        checked_count += 1
                        if os.path.getmtime(filepath) < cutoff_ts:
                            os.remove(filepath)
                            deleted_count += 1
                            self.logger.web_log(f"Cleanup: Deleted '{filename}'.")
                except Exception as e_file:
                    self.logger.web_log(f"Cleanup: Error processing file '{filename}': {e_file}", "error")
        except Exception as e_list:
            self.logger.web_log(f"Cleanup: Error listing directory '{self.save_dir}': {e_list}", "error")
            return

        if deleted_count > 0 or checked_count > 0:
            self.logger.web_log(f"Cleanup: Finished. Checked {checked_count}, deleted {deleted_count} images.")
        else:
            self.logger.web_log(f"Cleanup: Finished. No old images found among {checked_count} checked files.")

        self.last_cleanup_day = dt.now().day  # Update last cleanup day

    def run_cleanup_scheduler_at_specific_time(self):
        self.logger.web_log("Image cleanup scheduler (specific time) started.", "info")
        while True:  # Loop indefinitely
            now = dt.now()
            # Run if target hour is met AND it's a new day since last cleanup
            if now.hour == self.cleanup_target_hour and now.day != self.last_cleanup_day:
                self.logger.web_log(
                    f"Cleanup: Target time ({self.cleanup_target_hour}:00) reached. Day {now.day}, last cleanup day was {self.last_cleanup_day}. Running cleanup.")
                self.cleanup_old_images()  # This will update self.last_cleanup_day

            # Sleep for the configured interval
            time.sleep(self.cleanup_interval_sec)
