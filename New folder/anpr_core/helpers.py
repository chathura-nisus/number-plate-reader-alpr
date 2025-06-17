# anpr_flask_project/anpr_core/helpers.py
import cv2
import numpy as np
import re
import math


def calculate_iou(boxA, boxB):
    """
    Calculates the Intersection over Union (IoU) of two bounding boxes.
    """
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    if interArea == 0: return 0.0
    boxAArea = boxA[2] * boxA[3]
    boxBArea = boxB[2] * boxB[3]
    if boxAArea <= 0 or boxBArea <= 0: return 0.0
    return interArea / float(boxAArea + boxBArea - interArea)


def score_ocr_result(text):
    """
    Scores the quality of a recognized plate text based on length and character types.
    Enhanced for Sri Lankan license plates.
    """
    score = 0
    if not text or not isinstance(text, str): return 0
    
    # Clean the text for analysis
    clean_text = text.replace(" ", "").replace("-", "")
    text_len = len(clean_text)
    
    # Score based on text length (Sri Lankan plates typically have 6-8 characters)
    if 6 <= text_len <= 8:
        score += 35
    elif 5 <= text_len < 6 or 8 < text_len <= 9:
        score += 25
    elif 3 <= text_len < 5:
        score += 15
    elif text_len > 9:
        score += 10
    
    # Score based on alphanumeric ratio
    alnum_chars = sum(1 for char in clean_text if char.isalnum())
    if text_len > 0:
        alnum_ratio = alnum_chars / float(text_len)
        if alnum_ratio > 0.9:
            score += 30
        elif alnum_ratio > 0.8:
            score += 25
        elif alnum_ratio > 0.6:
            score += 10
    
    # Score based on digit count (Sri Lankan plates typically have 3-4 digits)
    num_digits = sum(1 for char in clean_text if char.isdigit())
    if 3 <= num_digits <= 4:
        score += 20
    elif num_digits >= 2:
        score += 15
    
    # Score based on letter count (Sri Lankan plates typically have 2-3 letters)
    num_letters = sum(1 for char in clean_text if char.isalpha())
    if 2 <= num_letters <= 3:
        score += 20
    elif num_letters >= 1:
        score += 10
    
    # Bonus for Sri Lankan plate format patterns
    if re.search(r'[A-Z]{2,3}[-\s]?[0-9]{3,4}', text):
        score += 25
    
    # Bonus for provincial code detection
    sri_lankan_provinces = ['WP', 'SP', 'CP', 'NP', 'EP', 'UP', 'NW', 'SG', 'NC']
    for province in sri_lankan_provinces:
        if province in text:
            score += 20
            break
    
    return score


def preprocess_for_easyocr(plate_roi, web_logger_func=None):
    """
    Performs simple scaling on the plate region for OCR. This is the fallback method.
    """
    if plate_roi is None or plate_roi.shape[0] == 0 or plate_roi.shape[1] == 0:
        return None
    scale_factor = 1.5
    h, w = plate_roi.shape[:2]
    if h * scale_factor < 400 and w * scale_factor < 800:
        try:
            return cv2.resize(plate_roi, (int(w * scale_factor), int(h * scale_factor)), interpolation=cv2.INTER_CUBIC)
        except Exception as e:
            if web_logger_func:
                web_logger_func(f"Resize Error in preprocess_for_easyocr: {e}", "error")
            return plate_roi
    return plate_roi


def detect_plate_color(plate_img, web_logger_func=None):
    """
    Detects whether the license plate has a yellow or white background.
    Returns: "yellow", "white", or "unknown"
    """
    if plate_img is None or plate_img.size == 0:
        if web_logger_func: web_logger_func("detect_plate_color: Input plate_img is None.", "warn")
        return "unknown"
    
    try:
        # Convert to HSV color space for better color detection
        if len(plate_img.shape) == 3 and plate_img.shape[2] == 3:
            hsv_img = cv2.cvtColor(plate_img, cv2.COLOR_BGR2HSV)
        else:
            if web_logger_func: web_logger_func("detect_plate_color: Input is not a color image.", "warn")
            return "unknown"
        
        # Define color ranges for yellow and white in HSV
        yellow_lower = np.array([20, 100, 100])
        yellow_upper = np.array([40, 255, 255])
        
        white_lower = np.array([0, 0, 180])
        white_upper = np.array([180, 30, 255])
        
        # Create masks for yellow and white colors
        yellow_mask = cv2.inRange(hsv_img, yellow_lower, yellow_upper)
        white_mask = cv2.inRange(hsv_img, white_lower, white_upper)
        
        # Calculate percentage of yellow and white pixels
        total_pixels = plate_img.shape[0] * plate_img.shape[1]
        yellow_pixels = cv2.countNonZero(yellow_mask)
        white_pixels = cv2.countNonZero(white_mask)
        
        yellow_percentage = (yellow_pixels / total_pixels) * 100
        white_percentage = (white_pixels / total_pixels) * 100
        
        # Determine plate color based on percentages
        if yellow_percentage > 30 and yellow_percentage > white_percentage:
            return "yellow"
        elif white_percentage > 30 and white_percentage > yellow_percentage:
            return "white"
        else:
            return "unknown"
    
    except Exception as e:
        if web_logger_func: web_logger_func(f"Error in detect_plate_color: {e}", "error")
        return "unknown"


def enhance_plate_image_for_ocr(plate_img, app_config, web_logger_func=None):
    """
    Enhances the cropped license plate image for better OCR results.
    Uses different processing techniques based on plate color.
    """
    if plate_img is None or plate_img.size == 0:
        if web_logger_func: web_logger_func("enhance_plate_image_for_ocr: Input plate_img is None.", "warn")
        return None
    
    # Detect plate color
    plate_color = detect_plate_color(plate_img, web_logger_func)
    if web_logger_func: web_logger_func(f"Detected plate color: {plate_color}", "info")
    
    # 1. Convert to grayscale if it's a color image
    if len(plate_img.shape) == 3 and plate_img.shape[2] == 3:
        plate_gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    elif len(plate_img.shape) == 2:
        plate_gray = plate_img.copy()  # Already grayscale
    else:
        if web_logger_func: web_logger_func(f"enhance_plate_image_for_ocr: Invalid image shape {plate_img.shape}.", "error")
        return None
    
    # 2. Apply different preprocessing based on plate color
    if plate_color == "yellow":
        # For yellow plates: Use adaptive thresholding with higher contrast
        try:
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            plate_gray = clahe.apply(plate_gray)
            
            # Apply adaptive thresholding
            plate_binary = cv2.adaptiveThreshold(
                plate_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 11, 2
            )
        except cv2.error as e:
            if web_logger_func: web_logger_func(f"Yellow plate processing failed: {e}. Trying Otsu.", "warn")
            _, plate_binary = cv2.threshold(plate_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    elif plate_color == "white":
        # For white plates: Use Otsu's thresholding with noise reduction
        try:
            # Apply bilateral filter to reduce noise while preserving edges
            plate_gray = cv2.bilateralFilter(plate_gray, 11, 17, 17)
            
            # Apply Otsu's thresholding
            _, plate_binary = cv2.threshold(plate_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        except cv2.error as e:
            if web_logger_func: web_logger_func(f"White plate processing failed: {e}. Using adaptive threshold.", "warn")
            plate_binary = cv2.adaptiveThreshold(
                plate_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 11, 2
            )
    
    else:  # Unknown color or fallback
        # Try both methods and choose the one with more defined edges
        try:
            # Method 1: Otsu's thresholding
            _, otsu_binary = cv2.threshold(plate_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Method 2: Adaptive thresholding
            adaptive_binary = cv2.adaptiveThreshold(
                plate_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # Choose the method with more defined edges
            otsu_edges = cv2.Canny(otsu_binary, 100, 200)
            adaptive_edges = cv2.Canny(adaptive_binary, 100, 200)
            
            if cv2.countNonZero(otsu_edges) > cv2.countNonZero(adaptive_edges):
                plate_binary = otsu_binary
            else:
                plate_binary = adaptive_binary
                
        except cv2.error as e:
            if web_logger_func: web_logger_func(f"Fallback processing failed: {e}. Using simple scaling.", "warn")
            return preprocess_for_easyocr(plate_img, web_logger_func)
    
    # 3. Morphological operations to clean up the binary image
    kernel_size = app_config.ENHANCE_OCR_MORPH_OPEN_KERNEL_SIZE
    kernel = np.ones(kernel_size, np.uint8)
    
    # Opening to remove small noise
    plate_binary_opened = cv2.morphologyEx(plate_binary, cv2.MORPH_OPEN, kernel)
    
    # Closing to fill small holes in characters
    plate_binary_closed = cv2.morphologyEx(plate_binary_opened, cv2.MORPH_CLOSE, kernel)
    
    # 4. Invert the image so characters become black (0) on white background (255)
    enhanced_plate = 255 - plate_binary_closed
    
    return enhanced_plate


def extract_provincial_code(plate_img, web_logger_func=None):
    """
    Extracts and recognizes the provincial code from a Sri Lankan license plate.
    Returns the extracted provincial code region for specialized OCR.
    """
    if plate_img is None or plate_img.size == 0:
        if web_logger_func: web_logger_func("extract_provincial_code: Input plate_img is None.", "warn")
        return None
    
    try:
        # Convert to grayscale if needed
        if len(plate_img.shape) == 3 and plate_img.shape[2] == 3:
            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = plate_img.copy()
        
        # Get plate dimensions
        height, width = gray.shape[:2]
        
        # Provincial codes are typically in the top/bottom left corner
        # Extract the left portion of the plate (approximately 25% of width)
        left_portion_width = int(width * 0.25)
        
        # Try both top and bottom left regions
        top_left_region = gray[0:int(height * 0.33), 0:left_portion_width]
        bottom_left_region = gray[int(height * 0.67):height, 0:left_portion_width]
        
        # Resize the regions for better OCR (provincial codes are small)
        scale_factor = 2.0
        top_left_resized = cv2.resize(top_left_region, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
        bottom_left_resized = cv2.resize(bottom_left_region, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
        
        # Apply adaptive thresholding to both regions
        top_left_binary = cv2.adaptiveThreshold(
            top_left_resized, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        bottom_left_binary = cv2.adaptiveThreshold(
            bottom_left_resized, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # Invert for OCR
        top_left_ocr = 255 - top_left_binary
        bottom_left_ocr = 255 - bottom_left_binary
        
        # Return both regions for OCR
        return {
            'top_left': top_left_ocr,
            'bottom_left': bottom_left_ocr
        }
        
    except Exception as e:
        if web_logger_func: web_logger_func(f"Error in extract_provincial_code: {e}", "error")
        return None


def validate_sri_lankan_plate(text):
    """
    Validates if the recognized text matches Sri Lankan license plate formats.
    Returns a tuple of (is_valid, corrected_text, confidence_adjustment)
    """
    if not text or not isinstance(text, str):
        return False, text, 0
    
    # Clean the text
    clean_text = text.replace(" ", "").upper()
    
    # List of Sri Lankan provincial codes
    provincial_codes = ['WP', 'SP', 'CP', 'NP', 'EP', 'UP', 'NW', 'SG', 'NC']
    
    # Common OCR errors and corrections for Sri Lankan plates
    ocr_corrections = {
        '0': 'O', 'O': '0',  # Depending on context
        '1': 'I', 'I': '1',  # Depending on context
        '8': 'B', 'B': '8',  # Depending on context
        '5': 'S', 'S': '5',  # Depending on context
        '2': 'Z', 'Z': '2',  # Depending on context
        '6': 'G', 'G': '6',  # Depending on context
    }
    
    # Check for provincial code at the beginning
    has_province_code = False
    detected_province = None
    
    for code in provincial_codes:
        if clean_text.startswith(code):
            has_province_code = True
            detected_province = code
            break
    
    # Modern format pattern: [Province Code] [2-3 Letters] [3-4 Numbers]
    modern_pattern = r'^([A-Z]{2})[A-Z]{1,3}[-]?[0-9]{3,4}$'
    
    # Older format pattern: [2-3 Letters]-[3-4 Numbers]
    older_pattern = r'^[A-Z]{1,3}[-]?[0-9]{3,4}$'
    
    # Check if text matches any pattern
    is_modern_format = re.match(modern_pattern, clean_text) is not None
    is_older_format = re.match(older_pattern, clean_text) is not None
    
    # Apply corrections if needed
    corrected_text = clean_text
    confidence_adjustment = 0
    
    if is_modern_format:
        # Text already matches modern format
        confidence_adjustment = 20
    elif is_older_format:
        # Text matches older format
        confidence_adjustment = 15
    elif has_province_code:
        # Has province code but doesn't match pattern fully
        # Try to correct common OCR errors
        remaining_text = clean_text[len(detected_province):]
        
        # Apply corrections to the remaining text
        corrected_remaining = remaining_text
        for char, correction in ocr_corrections.items():
            # Only correct digits in the last part of the text
            if char.isdigit():
                # Find position of first digit
                digit_pos = -1
                for i, c in enumerate(corrected_remaining):
                    if c.isdigit():
                        digit_pos = i
                        break
                
                if digit_pos >= 0:
                    # Only replace characters after the first digit
                    before_digits = corrected_remaining[:digit_pos]
                    after_digits = corrected_remaining[digit_pos:]
                    after_digits = after_digits.replace(correction, char)
                    corrected_remaining = before_digits + after_digits
            else:
                # For letters, only correct in the first part
                letter_part_end = len(corrected_remaining)
                for i, c in enumerate(corrected_remaining):
                    if c.isdigit():
                        letter_part_end = i
                        break
                
                if letter_part_end > 0:
                    before_letters = corrected_remaining[:letter_part_end]
                    after_letters = corrected_remaining[letter_part_end:]
                    before_letters = before_letters.replace(char, correction)
                    corrected_remaining = before_letters + after_letters
        
        corrected_text = detected_province + corrected_remaining
        
        # Check if corrected text matches any pattern
        is_corrected_modern = re.match(modern_pattern, corrected_text) is not None
        is_corrected_older = re.match(older_pattern, corrected_text) is not None
        
        if is_corrected_modern:
            confidence_adjustment = 15
        elif is_corrected_older:
            confidence_adjustment = 10
        else:
            confidence_adjustment = 5
    else:
        # No province code detected, check if it's an older format
        # Try to correct common OCR errors
        corrected_text = clean_text
        for char, correction in ocr_corrections.items():
            if char.isdigit():
                # Find position of first digit
                digit_pos = -1
                for i, c in enumerate(corrected_text):
                    if c.isdigit():
                        digit_pos = i
                        break
                
                if digit_pos >= 0:
                    # Only replace characters after the first digit
                    before_digits = corrected_text[:digit_pos]
                    after_digits = corrected_text[digit_pos:]
                    after_digits = after_digits.replace(correction, char)
                    corrected_text = before_digits + after_digits
            else:
                # For letters, only correct in the first part
                letter_part_end = len(corrected_text)
                for i, c in enumerate(corrected_text):
                    if c.isdigit():
                        letter_part_end = i
                        break
                
                if letter_part_end > 0:
                    before_letters = corrected_text[:letter_part_end]
                    after_letters = corrected_text[letter_part_end:]
                    before_letters = before_letters.replace(char, correction)
                    corrected_text = before_letters + after_letters
        
        # Check if corrected text matches older format
        is_corrected_older = re.match(older_pattern, corrected_text) is not None
        
        if is_corrected_older:
            confidence_adjustment = 10
        else:
            # Try adding a dash if missing
            for i in range(1, len(corrected_text) - 1):
                if corrected_text[i].isalpha() and corrected_text[i+1].isdigit():
                    corrected_with_dash = corrected_text[:i+1] + '-' + corrected_text[i+1:]
                    if re.match(older_pattern, corrected_with_dash):
                        corrected_text = corrected_with_dash
                        confidence_adjustment = 5
                        break
    
    # Final validation
    is_valid = re.match(modern_pattern, corrected_text) is not None or re.match(older_pattern, corrected_text) is not None
    
    return is_valid, corrected_text, confidence_adjustment


def detect_plate_with_color_filtering(img_gray, original_frame, web_logger_func=None):
    """
    Enhanced plate detection using color filtering for yellow and white plates.
    Returns a list of detected plate regions with their color information.
    """
    if img_gray is None or original_frame is None:
        if web_logger_func: web_logger_func("detect_plate_with_color_filtering: Input images are None.", "warn")
        return []
    
    try:
        # Convert original frame to HSV for color filtering
        hsv_frame = cv2.cvtColor(original_frame, cv2.COLOR_BGR2HSV)
        
        # Define color ranges for yellow and white in HSV
        yellow_lower = np.array([20, 100, 100])
        yellow_upper = np.array([40, 255, 255])
        
        white_lower = np.array([0, 0, 180])
        white_upper = np.array([180, 30, 255])
        
        # Create masks for yellow and white colors
        yellow_mask = cv2.inRange(hsv_frame, yellow_lower, yellow_upper)
        white_mask = cv2.inRange(hsv_frame, white_lower, white_upper)
        
        # Combine masks for all potential plate colors
        combined_mask = cv2.bitwise_or(yellow_mask, white_mask)
        
        # Apply morphological operations to clean up the mask
        kernel = np.ones((5, 5), np.uint8)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)
        
        # Find contours in the combined mask
        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter contours based on size and aspect ratio
        plate_candidates = []
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / float(h) if h > 0 else 0
            area = w * h
            
            # Sri Lankan plates typically have aspect ratios between 2.0 and 5.0
            if 1.5 < aspect_ratio < 6.0 and area > 1000:
                # Determine the color of this candidate
                roi_yellow = yellow_mask[y:y+h, x:x+w]
                roi_white = white_mask[y:y+h, x:x+w]
                
                yellow_pixels = cv2.countNonZero(roi_yellow)
                white_pixels = cv2.countNonZero(roi_white)
                
                # Determine dominant color
                if yellow_pixels > white_pixels and yellow_pixels > (w * h * 0.3):
                    color = "yellow"
                elif white_pixels > yellow_pixels and white_pixels > (w * h * 0.3):
                    color = "white"
                else:
                    color = "unknown"
                
                plate_candidates.append({
                    'bbox': (x, y, w, h),
                    'color': color,
                    'area': area,
                    'aspect_ratio': aspect_ratio
                })
        
        # Also run the traditional cascade detector
        cascade_plates = []
        try:
            # Use the Haar Cascade to detect plates
            cascade_plates = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_russian_plate_number.xml').detectMultiScale(
                img_gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(60, 20)
            )
        except Exception as e:
            if web_logger_func: web_logger_func(f"Haar Cascade detection failed: {e}", "warn")
        
        # Add cascade detections to candidates
        for (x, y, w, h) in cascade_plates:
            aspect_ratio = w / float(h) if h > 0 else 0
            area = w * h
            
            if 1.5 < aspect_ratio < 6.0 and area > 1000:
                # Determine color
                roi_hsv = hsv_frame[y:y+h, x:x+w]
                roi_yellow = cv2.inRange(roi_hsv, yellow_lower, yellow_upper)
                roi_white = cv2.inRange(roi_hsv, white_lower, white_upper)
                
                yellow_pixels = cv2.countNonZero(roi_yellow)
                white_pixels = cv2.countNonZero(roi_white)
                
                if yellow_pixels > white_pixels and yellow_pixels > (w * h * 0.3):
                    color = "yellow"
                elif white_pixels > yellow_pixels and white_pixels > (w * h * 0.3):
                    color = "white"
                else:
                    color = "unknown"
                
                # Check if this detection overlaps with existing candidates
                is_duplicate = False
                for candidate in plate_candidates:
                    if calculate_iou((x, y, w, h), candidate['bbox']) > 0.5:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    plate_candidates.append({
                        'bbox': (x, y, w, h),
                        'color': color,
                        'area': area,
                        'aspect_ratio': aspect_ratio
                    })
        
        return plate_candidates
        
    except Exception as e:
        if web_logger_func: web_logger_func(f"Error in detect_plate_with_color_filtering: {e}", "error")
        return []


def perspective_transform_plate(plate_img, web_logger_func=None):
    """
    Applies perspective transformation to correct skewed license plates.
    """
    if plate_img is None or plate_img.size == 0:
        if web_logger_func: web_logger_func("perspective_transform_plate: Input plate_img is None.", "warn")
        return None
    
    try:
        # Convert to grayscale if needed
        if len(plate_img.shape) == 3 and plate_img.shape[2] == 3:
            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = plate_img.copy()
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Apply Canny edge detection
        edges = cv2.Canny(blurred, 50, 150)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return plate_img  # Return original if no contours found
        
        # Find the largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Approximate the contour to a polygon
        epsilon = 0.02 * cv2.arcLength(largest_contour, True)
        approx = cv2.approxPolyDP(largest_contour, epsilon, True)
        
        # If we have a quadrilateral (4 points), apply perspective transform
        if len(approx) == 4:
            # Sort the points to get them in the correct order
            pts = np.array([point[0] for point in approx], dtype=np.float32)
            
            # Order points: top-left, top-right, bottom-right, bottom-left
            rect = np.zeros((4, 2), dtype=np.float32)
            
            # Sum of coordinates
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]  # Top-left has smallest sum
            rect[2] = pts[np.argmax(s)]  # Bottom-right has largest sum
            
            # Difference of coordinates
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]  # Top-right has smallest difference
            rect[3] = pts[np.argmax(diff)]  # Bottom-left has largest difference
            
            # Get width and height of the plate
            width_a = np.sqrt(((rect[2][0] - rect[3][0]) ** 2) + ((rect[2][1] - rect[3][1]) ** 2))
            width_b = np.sqrt(((rect[1][0] - rect[0][0]) ** 2) + ((rect[1][1] - rect[0][1]) ** 2))
            max_width = max(int(width_a), int(width_b))
            
            height_a = np.sqrt(((rect[1][0] - rect[2][0]) ** 2) + ((rect[1][1] - rect[2][1]) ** 2))
            height_b = np.sqrt(((rect[0][0] - rect[3][0]) ** 2) + ((rect[0][1] - rect[3][1]) ** 2))
            max_height = max(int(height_a), int(height_b))
            
            # Define destination points for the transform
            dst = np.array([
                [0, 0],
                [max_width - 1, 0],
                [max_width - 1, max_height - 1],
                [0, max_height - 1]
            ], dtype=np.float32)
            
            # Calculate perspective transform matrix
            M = cv2.getPerspectiveTransform(rect, dst)
            
            # Apply perspective transform
            warped = cv2.warpPerspective(plate_img, M, (max_width, max_height))
            
            return warped
        
        return plate_img  # Return original if not a quadrilateral
        
    except Exception as e:
        if web_logger_func: web_logger_func(f"Error in perspective_transform_plate: {e}", "error")
        return plate_img  # Return original on error

