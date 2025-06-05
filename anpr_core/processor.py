# anpr_flask_project/anpr_core/processor.py
import cv2
import time
import re
import os
from datetime import datetime as dt
# MODIFIED IMPORT: Added enhance_plate_image_for_ocr
from .helpers import calculate_iou, score_ocr_result, preprocess_for_easyocr, enhance_plate_image_for_ocr


class ANPRProcessor:
    def __init__(self, easyocr_reader, plate_cascade, odoo_connector, storage_handler, logging_service,
                 app_config_obj):
        self.reader = easyocr_reader
        self.plate_cascade = plate_cascade
        self.odoo_connector = odoo_connector
        self.storage_handler = storage_handler
        self.logger = logging_service
        self.config = app_config_obj

        self.active_plate_candidates = []
        self.candidate_id_counter = 0
        self.last_saved_plate_text_globally = ""
        self.save_count = 0

    def recognize_plate_text_easyocr(self, processed_plate_roi):
        if processed_plate_roi is None or self.reader is None:
            return ""
        try:
            results = self.reader.readtext(processed_plate_roi, detail=1, paragraph=False, min_size=10)
            if results:
                plate_text_parts = [
                    "".join(filter(str.isalnum, text)).upper()
                    for (bbox, text, prob) in results
                    if prob >= self.config.OCR_MIN_CONFIDENCE and "".join(filter(str.isalnum, text))
                ]
                return " ".join(plate_text_parts)
            return ""
        except Exception as e:
            self.logger.web_log(f"EasyOCR Error: {e}", "error", exc_info=True)
            return ""

    def process_detected_plates(self, frame_for_display, original_frame, current_camera_info):
        img_gray = cv2.cvtColor(original_frame, cv2.COLOR_BGR2GRAY)

        number_plates = self.plate_cascade.detectMultiScale(
            img_gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 20)
        )

        current_time = time.time()
        detected_in_this_frame_ids = []

        for (x, y, w, h) in number_plates:
            current_bbox = (x, y, w, h)
            area = w * h
            aspect_ratio = w / float(h) if h > 0 else 0

            if not (area > self.config.MIN_PLATE_AREA and 1.5 < aspect_ratio < 6.0):
                continue

            plate_roi_original = original_frame[y:y + h, x:x + w]

            # --- MODIFIED: Use the new enhancement function based on config ---
            processed_roi_for_ocr = None
            if self.config.USE_PLATE_ENHANCEMENT_FOR_OCR:
                # Use the new advanced enhancement
                processed_roi_for_ocr = enhance_plate_image_for_ocr(
                    plate_roi_original, self.config, self.logger.web_log
                )
            else:
                # Fallback to the old, simple scaling method if enhancement is turned off
                processed_roi_for_ocr = preprocess_for_easyocr(
                    plate_roi_original, self.logger.web_log
                )
            # --- END MODIFICATION ---

            if processed_roi_for_ocr is None:
                self.logger.web_log("Plate ROI processing for OCR failed completely.", "warn")
                ocr_text = ""
            else:
                ocr_text = self.recognize_plate_text_easyocr(processed_roi_for_ocr)

            ocr_score = score_ocr_result(ocr_text)

            cv2.rectangle(frame_for_display, (x, y), (x + w, y + h), (255, 0, 255), 2)
            display_text = f"S:{ocr_score}" if not ocr_text else f"{ocr_text[:10]} S:{ocr_score}"
            cv2.putText(frame_for_display, display_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

            if not ocr_text or ocr_score < self.config.MIN_OCR_SCORE_TO_BUFFER or \
                    len(ocr_text.replace(" ", "").replace("-", "")) < self.config.MIN_PLATE_TEXT_LENGTH:
                continue

            # The rest of the candidate matching and creation logic remains the same
            matched_candidate_index = -1
            best_iou_for_match = 0
            for i_cand, cand in enumerate(self.active_plate_candidates):
                iou = calculate_iou(current_bbox, cand['bbox'])
                if iou > self.config.IOU_THRESHOLD_FOR_MATCH and iou > best_iou_for_match:
                    matched_candidate_index = i_cand
                    best_iou_for_match = iou

            if matched_candidate_index != -1:
                candidate = self.active_plate_candidates[matched_candidate_index]
                detected_in_this_frame_ids.append(candidate['id'])
                candidate['last_update_time'] = current_time
                candidate['bbox'] = current_bbox
                if ocr_score > candidate['best_score']:
                    candidate['best_text'] = ocr_text
                    candidate['best_score'] = ocr_score
                    candidate['best_roi'] = plate_roi_original.copy()
                    candidate['current_full_frame'] = original_frame.copy()
                    candidate['save_pending_time'] = current_time + self.config.PLATE_SAVE_STABILIZATION_SECONDS
            else:
                self.candidate_id_counter += 1
                new_candidate = {
                    'id': self.candidate_id_counter, 'bbox': current_bbox, 'best_text': ocr_text,
                    'best_score': ocr_score, 'best_roi': plate_roi_original.copy(),
                    'current_full_frame': original_frame.copy(),
                    'last_update_time': current_time,
                    'save_pending_time': current_time + self.config.PLATE_SAVE_STABILIZATION_SECONDS
                }
                self.active_plate_candidates.append(new_candidate)
                detected_in_this_frame_ids.append(new_candidate['id'])

        self._process_and_save_candidates(current_camera_info)

        for cand_draw in self.active_plate_candidates:
            if cand_draw['id'] in detected_in_this_frame_ids or \
                    (current_time - cand_draw['last_update_time'] < 0.5):
                (cx, cy, cw, ch) = cand_draw['bbox']
                status_color = (0, 255, 0) if cand_draw.get('save_pending_time') else (0, 165, 255)
                cv2.putText(frame_for_display,
                            f"ID:{cand_draw['id']} {cand_draw['best_text'][:10]}(S:{cand_draw['best_score']})",
                            (cx, cy + ch + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, status_color, 1)
        return frame_for_display

    def _process_and_save_candidates(self, current_camera_info):
        current_time = time.time()
        plates_to_remove_indices = []

        for i, candidate in enumerate(self.active_plate_candidates):
            action_reason = None
            save_this_candidate = False

            if candidate.get('save_pending_time') is not None and current_time >= candidate['save_pending_time']:
                if candidate['best_text'] and candidate['best_text'] != self.last_saved_plate_text_globally:
                    action_reason = "Stabilized"
                    save_this_candidate = True
                candidate['save_pending_time'] = None

            if current_time - candidate['last_update_time'] > self.config.PLATE_CANDIDATE_TIMEOUT_SECONDS:
                if i not in plates_to_remove_indices:
                    plates_to_remove_indices.append(i)
                if candidate.get('save_pending_time') is not None and \
                        candidate['best_text'] and \
                        candidate['best_text'] != self.last_saved_plate_text_globally and \
                        not save_this_candidate:
                    action_reason = "TimeoutSave"
                    save_this_candidate = True

            if save_this_candidate:
                timestamp_obj = dt.now()
                safe_plate_text = re.sub(r'[^A-Z0-9-]', '', candidate['best_text'].upper()) or "UNKNOWN"

                saved_paths = self.storage_handler.save_detection_images(
                    candidate['best_roi'],
                    candidate.get('current_full_frame'),
                    safe_plate_text,
                    timestamp_obj,
                    self.save_count
                )

                if saved_paths['plate_roi_filename']:
                    self.logger.web_log(
                        f"SAVED Plate ROI ({action_reason}): {saved_paths['plate_roi_filename']} - Text: {candidate['best_text']} (S:{candidate['best_score']})")

                    if saved_paths['full_frame_filename']:
                        self.logger.web_log(f"SAVED Full Frame: {saved_paths['full_frame_filename']}")

                    self.storage_handler.log_detected_plate_csv(
                        timestamp_obj,
                        saved_paths['plate_roi_filename'],
                        candidate['best_text']
                    )

                    odoo_data = {
                        'text': candidate['best_text'],
                        'score': float(candidate['best_score']),
                        'detection_time_obj': timestamp_obj,
                        'plate_roi_filename': saved_paths['plate_roi_filename'],
                        'plate_roi_filepath': saved_paths['plate_roi_filepath'],
                        'full_frame_filename': saved_paths['full_frame_filename'],
                        'full_frame_filepath': saved_paths['full_frame_filepath'],
                        'camera_source': current_camera_info['identifier'],
                        'location': current_camera_info['location']
                    }
                    self.odoo_connector.save_detection_log(odoo_data)

                    self.logger.emit_event('new_plate_saved', {
                        'filename': saved_paths['plate_roi_filename'],
                        'text': candidate['best_text'],
                        'score': candidate['best_score']
                    })
                    self.last_saved_plate_text_globally = candidate['best_text']
                    self.save_count += 1
                else:
                    self.logger.web_log(
                        f"Failed to save plate ROI for candidate {candidate['id']}, text: {candidate['best_text']}",
                        "error")

                if i not in plates_to_remove_indices:
                    plates_to_remove_indices.append(i)

            if current_time - candidate['last_update_time'] > self.config.PLATE_CANDIDATE_TIMEOUT_SECONDS and \
                    i not in plates_to_remove_indices:
                plates_to_remove_indices.append(i)

        for index in sorted(list(set(plates_to_remove_indices)), reverse=True):
            if 0 <= index < len(self.active_plate_candidates):
                del self.active_plate_candidates[index]
