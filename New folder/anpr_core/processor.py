import cv2
import time
import re
import os
import threading
from datetime import datetime as dt
from .helpers import (
    calculate_iou,
    score_ocr_result,
    enhance_plate_image_for_ocr
)


class ANPRProcessor:
    def __init__(self, easyocr_reader, plate_cascade, odoo_connector, storage_handler, logging_service,
                 app_config_obj, ocr_engine='easyocr', gemini_client=None):
        self.reader = easyocr_reader
        self.plate_cascade = plate_cascade
        self.odoo_connector = odoo_connector
        self.storage_handler = storage_handler
        self.logger = logging_service
        self.config = app_config_obj
        self.ocr_engine = ocr_engine
        self.gemini_client = gemini_client

        self.active_plate_candidates = []
        self.candidate_id_counter = 0
        self.last_saved_plate_text_globally = ""
        self.save_count = 0
        self.frame_counter = 0
        self.lock = threading.Lock()

    def recognize_plate_text_easyocr(self, processed_plate_roi):
        if processed_plate_roi is None or self.reader is None:
            return "", 0.0
        try:
            results = self.reader.readtext(processed_plate_roi, detail=1, paragraph=False)
            if not results:
                return "", 0.0

            best_result = max(results, key=lambda r: r[2])
            text, confidence = best_result[1], best_result[2]
            return text.upper().strip(), confidence
        except Exception as e:
            self.logger.web_log(f"EasyOCR Error: {e}", "error")
            return "", 0.0

    def process_detected_plates(self, display_frame, original_frame, current_camera_info):
        self.frame_counter += 1
        if self.config.ENABLE_FRAME_SKIPPING and self.frame_counter % (self.config.FRAME_SKIP_COUNT + 1) != 0:
            return display_frame

        img_gray = cv2.cvtColor(original_frame, cv2.COLOR_BGR2GRAY)
        plate_candidates = self.plate_cascade.detectMultiScale(img_gray, scaleFactor=1.1, minNeighbors=4,
                                                               minSize=(60, 20))

        with self.lock:
            current_matches = [False] * len(self.active_plate_candidates)

            for (x, y, w, h) in plate_candidates:
                plate_roi_original = original_frame[y:y + h, x:x + w]
                found_match = False
                for i, candidate in enumerate(self.active_plate_candidates):
                    if calculate_iou((x, y, w, h), candidate['bbox']) > self.config.IOU_THRESHOLD_FOR_MATCH:
                        found_match = True
                        current_matches[i] = True
                        candidate.update({
                            'bbox': (x, y, w, h),
                            'last_seen': time.time(),
                            'frames_seen': candidate['frames_seen'] + 1,
                            'plate_roi_to_save': plate_roi_original,
                            'full_frame_to_save': original_frame
                        })
                        break
                if not found_match:
                    self.candidate_id_counter += 1
                    new_candidate = {
                        'id': self.candidate_id_counter, 'bbox': (x, y, w, h), 'best_text': "", 'best_score': 0,
                        'confidence': 0.0, 'first_seen': time.time(), 'last_seen': time.time(),
                        'last_updated': time.time(), 'frames_seen': 1, 'saved': False,
                        'plate_roi_to_save': plate_roi_original, 'full_frame_to_save': original_frame
                    }
                    self.active_plate_candidates.append(new_candidate)
                    current_matches.append(True)

            for i, candidate in enumerate(self.active_plate_candidates):
                if candidate['frames_seen'] % (self.config.FRAME_SKIP_COUNT + 2) == 0:
                    processed_roi = enhance_plate_image_for_ocr(candidate['plate_roi_to_save'], self.config,
                                                                self.logger.web_log)
                    text, confidence = self.recognize_plate_text_easyocr(processed_roi)
                    score = score_ocr_result(text)
                    if score > candidate['best_score']:
                        candidate.update({'best_score': score, 'best_text': text, 'confidence': confidence,
                                          'last_updated': time.time()})

                if not candidate['saved'] and candidate['best_score'] > self.config.MIN_OCR_SCORE_TO_BUFFER and (
                        time.time() - candidate['last_updated']) > self.config.PLATE_SAVE_STABILIZATION_SECONDS:
                    if candidate['best_text'] != self.last_saved_plate_text_globally:
                        threading.Thread(target=self._save_candidate,
                                         args=(candidate.copy(), current_camera_info)).start()
                        candidate['saved'] = True

                (cx, cy, cw, ch) = candidate['bbox']
                cv2.rectangle(display_frame, (cx, cy), (cx + cw, cy + ch), (0, 255, 0), 2)
                label = f"{candidate.get('best_text', '')} (S:{candidate.get('best_score', 0)})"
                cv2.putText(display_frame, label, (cx, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            self.active_plate_candidates = [p for i, p in enumerate(self.active_plate_candidates) if (
                    time.time() - p['last_seen']) < self.config.PLATE_CANDIDATE_TIMEOUT_SECONDS]

        return display_frame

    def _save_candidate(self, candidate, current_camera_info):
        try:
            final_text = candidate['best_text']
            if self.ocr_engine == 'gemini' and self.gemini_client:
                self.logger.web_log(f"Performing final OCR with Gemini for candidate ID {candidate['id']}...", "info")
                gemini_text = self.gemini_client.read_plate(candidate['plate_roi_to_save'])
                if gemini_text:
                    self.logger.web_log(f"Gemini updated plate text from '{final_text}' to '{gemini_text}'.", "success")
                    final_text = gemini_text
                    candidate['confidence'] = 0.95

            saved_paths = self.storage_handler.save_detection_images(
                plate_roi=candidate.get('plate_roi_to_save'),
                full_frame=candidate.get('full_frame_to_save'),
                plate_text=final_text
            )

            if saved_paths and self.odoo_connector:
                self.logger.web_log(
                    f"SAVED Plate ROI (Stabilized): {saved_paths['plate_roi_filename']} - Text: {final_text}")
                odoo_data = {
                    'text': final_text,
                    'timestamp': dt.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'confidence': float(candidate.get('confidence', 0)),
                    'plate_roi_filepath': saved_paths.get('plate_roi_filepath'),
                    'full_frame_filepath': saved_paths.get('full_frame_filepath'),
                    'camera_source': current_camera_info['identifier'],
                    'location_id': current_camera_info['location_id']
                }

                self.odoo_connector.save_detection_log(odoo_data)

                self.logger.emit_event('new_plate_saved', {
                    'filename': saved_paths['plate_roi_filename'],
                    'text': final_text,
                    'score': candidate['best_score'],
                    'confidence': candidate.get('confidence', 0),
                    'location_id': current_camera_info['location_id']
                })
                with self.lock:
                    self.last_saved_plate_text_globally = final_text
                    self.save_count += 1
        except Exception as e:
            self.logger.web_log(f"Error in _save_candidate: {e}", "error", exc_info=True)
