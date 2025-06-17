import requests
import cv2
import base64
import config as app_config


class GeminiClient:
    def __init__(self, api_key, api_url, model_name, logging_service, config):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
        self.logger = logging_service
        self.config = config
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        self.prompt = """Perform an OCR (Optical Character Recognition) task on this image.
Your goal is to identify and extract the alphanumeric characters from the vehicle's license plate.
Follow these steps:
1. Carefully locate the rectangular license plate on the vehicle.
2. Read the characters on the plate from left to right.
3. Return *only* the sequence of characters from the license plate. Do not include any other text, descriptions, or explanations in your response.
If you cannot clearly read a license plate in the image, respond with the single phrase: 'Not Found'."""

    def read_plate(self, plate_roi_image):
        if not self.api_key or "YOUR_OPENROUTER_API_KEY_HERE" in self.api_key:
            self.logger.web_log("Gemini API key is not set. Cannot perform OCR.", "error")
            return ""

        try:
            # Encode the image (NumPy array) to Base64
            success, buffer = cv2.imencode('.jpg', plate_roi_image)
            if not success:
                self.logger.web_log("Failed to encode image for Gemini.", "error")
                return ""
            data_url = "data:image/jpeg;base64," + base64.b64encode(buffer).decode('utf-8')

            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.prompt},
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
                    }
                ]
            }

            response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=15)
            response.raise_for_status()

            result = response.json()
            if result.get('choices') and result['choices'][0].get('message'):
                plate_text = result['choices'][0]['message']['content'].strip()
                self.logger.web_log(f"Gemini OCR Result: '{plate_text}'", "info")

                if "Not Found" in plate_text or len(plate_text) < self.config.MIN_PLATE_TEXT_LENGTH:
                    return ""
                return plate_text
            else:
                self.logger.web_log("Gemini response was empty or malformed.", "warn")
                return ""

        except requests.exceptions.RequestException as e:
            self.logger.web_log(f"Gemini API request failed: {e}", "error")
            return ""
        except Exception as e:
            self.logger.web_log(f"An unexpected error occurred in Gemini client: {e}", "error", exc_info=True)
            return ""
