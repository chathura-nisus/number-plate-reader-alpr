# anpr_flask_project/anpr_core/helpers.py
import cv2
import numpy as np  # <-- IMPORTANT: Import NumPy
import config  # Import your app's config


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
    """
    score = 0
    if not text or not isinstance(text, str): return 0
    text_len = len(text.replace(" ", "").replace("-", ""))
    if 5 <= text_len <= 9:
        score += 30
    elif 3 <= text_len < 5:
        score += 15
    elif text_len > 9:
        score += 10
    alnum_chars = sum(1 for char in text if char.isalnum())
    if text_len > 0:
        alnum_ratio = alnum_chars / float(text_len)
        if alnum_ratio > 0.8:
            score += 25
        elif alnum_ratio > 0.6:
            score += 10
    num_digits = sum(1 for char in text if char.isdigit())
    if num_digits >= 2: score += 15
    if num_digits >= 4: score += 10
    num_letters = sum(1 for char in text if char.isalpha())
    if num_letters >= 1: score += 10
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


# --- NEWLY ADDED FUNCTION ---
def enhance_plate_image_for_ocr(plate_img, app_config, web_logger_func=None):
    """
    Enhances the cropped license plate image for better OCR results.
    This involves converting to grayscale, binarizing, and cleaning noise.
    """
    if plate_img is None or plate_img.size == 0:
        if web_logger_func: web_logger_func("enhance_plate_image_for_ocr: Input plate_img is None.", "warn")
        return None

    # 1. Convert to grayscale if it's a color image
    if len(plate_img.shape) == 3 and plate_img.shape[2] == 3:
        plate_gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    elif len(plate_img.shape) == 2:
        plate_gray = plate_img.copy()  # Already grayscale
    else:
        if web_logger_func: web_logger_func(f"enhance_plate_image_for_ocr: Invalid image shape {plate_img.shape}.",
                                            "error")
        return None

    # 2. Binarization using Otsu's method. This automatically finds the best threshold.
    # THRESH_BINARY_INV makes the plate characters (which are usually darker) white (255).
    try:
        _, plate_binary = cv2.threshold(plate_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    except cv2.error as e:
        if web_logger_func: web_logger_func(f"Otsu thresholding failed: {e}. Returning original grayscale.", "warn")
        # If Otsu fails (e.g., on a flat color image), fallback to the original simple scaling.
        return preprocess_for_easyocr(plate_img, web_logger_func)

    # 3. Morphological Opening to remove small noise (dots and specs) from the binary image.
    kernel_size = app_config.ENHANCE_OCR_MORPH_OPEN_KERNEL_SIZE
    kernel = np.ones(kernel_size, np.uint8)  # This requires NumPy (np)
    plate_binary_opened = cv2.morphologyEx(plate_binary, cv2.MORPH_OPEN, kernel)

    # 4. Invert the image so characters become black (0) on a white background (255).
    # This is a common format that OCR engines perform well on.
    enhanced_plate = 255 - plate_binary_opened

    return enhanced_plate
