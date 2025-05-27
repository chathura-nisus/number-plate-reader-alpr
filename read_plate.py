from flask import Flask, render_template, request, jsonify, send_from_directory
import cv2
import numpy as np
import easyocr
import base64
import io
from PIL import Image
import os
from datetime import datetime
import json

app = Flask(__name__)

# Create directories for uploads and logs
os.makedirs('uploads', exist_ok=True)
os.makedirs('logs', exist_ok=True)

# Initialize EasyOCR reader (load once for efficiency)
reader = easyocr.Reader(['en'])

# Store detection results
detection_log = []


def enhanced_image_processing(image):
    """Enhanced image processing for better plate detection"""
    # Resize for consistency
    image = cv2.resize(image, (800, 600))

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply multiple preprocessing techniques
    # 1. Bilateral filter to reduce noise while keeping edges
    filtered = cv2.bilateralFilter(gray, 11, 17, 17)

    # 2. Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(filtered)

    # 3. Morphological operations to close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)

    return image, morph


def detect_plate_region(processed_image, original_image):
    """Improved plate region detection with multiple methods"""
    height, width = processed_image.shape

    # Method 1: Original edge-based detection (more relaxed criteria)
    edges1 = cv2.Canny(processed_image, 50, 150)
    edges2 = cv2.Canny(processed_image, 30, 100)
    edges = cv2.bitwise_or(edges1, edges2)

    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:20]

    plate_candidates = []

    print(f"Found {len(contours)} contours to analyze")

    for i, contour in enumerate(contours):
        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)

        # Basic size filtering
        if w < 30 or h < 10:
            continue

        # Calculate metrics
        aspect_ratio = w / float(h)
        area = cv2.contourArea(contour)
        rect_area = w * h
        extent = area / rect_area if rect_area > 0 else 0

        # More relaxed license plate criteria
        if (1.5 < aspect_ratio < 8.0 and  # wider aspect ratio range
                area > 200 and  # much lower area threshold
                w > 30 and h > 10 and  # smaller minimum dimensions
                extent > 0.2 and  # lower extent threshold
                x > 5 and y > 5 and  # not at edges
                x + w < width - 5 and y + h < height - 5):
            plate_candidates.append({
                'region': (x, y, w, h),
                'area': area,
                'aspect_ratio': aspect_ratio,
                'extent': extent,
                'score': area * aspect_ratio * extent  # composite score
            })

            print(f"Candidate {i}: area={area}, aspect={aspect_ratio:.2f}, extent={extent:.2f}")

    # Method 2: Rectangle detection if no good candidates
    if len(plate_candidates) < 3:
        print("Trying rectangle detection method...")

        # Apply morphological operations
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morph = cv2.morphologyEx(processed_image, cv2.MORPH_CLOSE, kernel)

        # Different edge detection
        edges_alt = cv2.Canny(morph, 20, 80)

        # Find rectangles
        contours_alt, _ = cv2.findContours(edges_alt, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours_alt:
            # Approximate to polygon
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            if len(approx) >= 4:  # At least 4 corners (rectangle-like)
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / float(h)
                area = cv2.contourArea(contour)

                if (1.8 < aspect_ratio < 6.0 and area > 300 and w > 40 and h > 15):
                    plate_candidates.append({
                        'region': (x, y, w, h),
                        'area': area,
                        'aspect_ratio': aspect_ratio,
                        'extent': 0.7,  # assume good extent for rectangles
                        'score': area * aspect_ratio * 0.7
                    })

    # Method 3: Template matching for common plate sizes
    if len(plate_candidates) < 2:
        print("Trying template-based size detection...")

        # Common license plate dimensions (scaled to image)
        scale_factor = width / 800.0  # assuming 800px width standard

        common_sizes = [
            (int(120 * scale_factor), int(30 * scale_factor)),  # Standard plate
            (int(100 * scale_factor), int(25 * scale_factor)),  # Smaller plate
            (int(140 * scale_factor), int(35 * scale_factor)),  # Larger plate
        ]

        for template_w, template_h in common_sizes:
            if template_w < width and template_h < height:
                # Slide window across image
                for y in range(0, height - template_h, 20):
                    for x in range(0, width - template_w, 20):
                        roi = processed_image[y:y + template_h, x:x + template_w]

                        # Check if region has text-like properties
                        edges_roi = cv2.Canny(roi, 50, 150)
                        edge_density = np.sum(edges_roi > 0) / (template_w * template_h)

                        if 0.1 < edge_density < 0.4:  # Good edge density for text
                            plate_candidates.append({
                                'region': (x, y, template_w, template_h),
                                'area': template_w * template_h,
                                'aspect_ratio': template_w / template_h,
                                'extent': 0.6,
                                'score': edge_density * template_w * template_h
                            })

    print(f"Total candidates found: {len(plate_candidates)}")

    # Sort by composite score and return best candidates
    if plate_candidates:
        sorted_candidates = sorted(plate_candidates, key=lambda x: x['score'], reverse=True)
        print(f"Best candidate: {sorted_candidates[0]}")
        return sorted_candidates[0]['region']

    print("No suitable plate candidates found")
    return None


def perform_ocr(image_region):
    """Perform OCR with confidence filtering and multiple attempts"""
    # Try OCR on original region
    results = reader.readtext(image_region)
    detected_texts = []

    print(f"OCR found {len(results)} text regions")

    for detection in results:
        text = detection[1].strip()
        confidence = detection[2]

        print(f"OCR result: '{text}' (confidence: {confidence:.2f})")

        # More lenient filtering
        if confidence > 0.2 and len(text) >= 2:  # Lower confidence threshold
            # Clean up common OCR errors but preserve more text
            clean_text = text.replace(' ', '').replace('-', '').replace('.', '').replace('|', '1').replace('O', '0')

            # Accept alphanumeric or mostly alphanumeric
            alpha_ratio = sum(c.isalnum() for c in clean_text) / len(clean_text) if clean_text else 0

            if alpha_ratio > 0.6:  # At least 60% alphanumeric
                detected_texts.append({
                    'text': clean_text.upper(),
                    'confidence': confidence,
                    'original': text
                })

    # If no good results, try with image preprocessing
    if not detected_texts:
        print("No good OCR results, trying with image enhancement...")

        # Enhance contrast
        enhanced = cv2.convertScaleAbs(image_region, alpha=1.5, beta=30)

        # Try different preprocessing
        gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY) if len(enhanced.shape) == 3 else enhanced

        # Apply different thresholding methods
        _, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)

        for thresh_img in [thresh1, thresh2]:
            results = reader.readtext(thresh_img)
            for detection in results:
                text = detection[1].strip()
                confidence = detection[2]

                if confidence > 0.15 and len(text) >= 2:
                    clean_text = text.replace(' ', '').replace('-', '').replace('.', '')
                    alpha_ratio = sum(c.isalnum() for c in clean_text) / len(clean_text) if clean_text else 0

                    if alpha_ratio > 0.5:
                        detected_texts.append({
                            'text': clean_text.upper(),
                            'confidence': confidence * 0.8,  # Slightly reduce confidence for processed images
                            'original': text
                        })

    return detected_texts


def log_detection(plate_text, confidence, image_path):
    """Log detection with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        'timestamp': timestamp,
        'plate_number': plate_text,
        'confidence': confidence,
        'image_path': image_path
    }

    detection_log.append(log_entry)

    # Save to file
    with open('logs/detections.json', 'w') as f:
        json.dump(detection_log, f, indent=2)

    print(f"[{timestamp}] Detected: {plate_text} (Confidence: {confidence:.2f})")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        # Get base64 image data from request
        data = request.get_json()
        image_data = data['image'].split(',')[1]  # Remove data:image/jpeg;base64, prefix

        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))

        # Convert PIL to OpenCV format
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # Save original image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"capture_{timestamp}.jpg"
        image_path = os.path.join('uploads', image_filename)
        cv2.imwrite(image_path, cv_image)

        # Process image
        original_image, processed_image = enhanced_image_processing(cv_image)

        # Detect plate region
        plate_region = detect_plate_region(processed_image, original_image)

        if plate_region:
            x, y, w, h = plate_region
            cropped_plate = original_image[y:y + h, x:x + w]

            print(f"Detected plate region: {w}x{h} at ({x},{y})")

            # Save cropped plate for debugging
            cropped_filename = f"cropped_{timestamp}.jpg"
            cropped_path = os.path.join('uploads', cropped_filename)
            cv2.imwrite(cropped_path, cropped_plate)

            # Perform OCR
            detected_texts = perform_ocr(cropped_plate)

            if detected_texts:
                # Get best result
                best_result = max(detected_texts, key=lambda x: x['confidence'])
                plate_text = best_result['text']
                confidence = best_result['confidence']

                # Log the detection
                log_detection(plate_text, confidence, image_path)

                # Draw rectangle on original image
                cv2.rectangle(original_image, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(original_image, f"{plate_text} ({confidence:.2f})",
                            (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                # Save processed image
                processed_filename = f"processed_{timestamp}.jpg"
                processed_path = os.path.join('uploads', processed_filename)
                cv2.imwrite(processed_path, original_image)

                return jsonify({
                    'success': True,
                    'plate_number': plate_text,
                    'confidence': round(confidence, 2),
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'processed_image': processed_filename,
                    'cropped_image': cropped_filename,
                    'debug_info': f"Detected {len(detected_texts)} text regions"
                })
            else:
                # Still save the detected region for debugging
                cropped_filename = f"cropped_no_text_{timestamp}.jpg"
                cropped_path = os.path.join('uploads', cropped_filename)
                cv2.imwrite(cropped_path, cropped_plate)

                return jsonify({
                    'success': False,
                    'error': 'No readable text found in detected plate region',
                    'debug_info': f'Plate region detected but OCR failed. Check cropped image.',
                    'cropped_image': cropped_filename
                })
        else:
            # Save debug image showing all contours
            debug_image = original_image.copy()
            edges = cv2.Canny(processed_image, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(debug_image, contours[:10], -1, (0, 255, 255), 2)

            debug_filename = f"debug_{timestamp}.jpg"
            debug_path = os.path.join('uploads', debug_filename)
            cv2.imwrite(debug_path, debug_image)

            return jsonify({
                'success': False,
                'error': 'No license plate detected in image',
                'debug_info': f'Found {len(contours)} contours but none matched plate criteria',
                'debug_image': debug_filename
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Processing error: {str(e)}'
        })


@app.route('/logs')
def get_logs():
    return jsonify(detection_log)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)


if __name__ == '__main__':
    # Get local IP address for mobile access
    import socket

    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    print(f"\n🚗 License Plate Detection Server Starting...")
    print(f"📱 Access from your mobile device at: http://{local_ip}:5000")
    print(f"💻 Local access: http://localhost:5000")
    print(f"📊 View detection logs at: http://{local_ip}:5000/logs")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5000, debug=True)
