#!/usr/bin/env python3
"""
Test script to verify Tesseract OCR installation
"""

import os
import platform
import pytesseract
from PIL import Image
import numpy as np


def test_tesseract_installation():
    print("Testing Tesseract OCR Installation")
    print("=" * 40)

    # Check system
    print(f"Operating System: {platform.system()}")

    # Try to get Tesseract version
    try:
        version = pytesseract.get_tesseract_version()
        print(f"✓ Tesseract version: {version}")
        return True
    except Exception as e:
        print(f"✗ Tesseract not found: {e}")

        # Try to find Tesseract manually on Windows
        if platform.system() == 'Windows':
            print("\nSearching for Tesseract installation...")
            possible_paths = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                r'C:\Users\%USERNAME%\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
            ]

            for path in possible_paths:
                expanded_path = os.path.expandvars(path)
                print(f"Checking: {expanded_path}")
                if os.path.exists(expanded_path):
                    print(f"✓ Found Tesseract at: {expanded_path}")
                    pytesseract.pytesseract.tesseract_cmd = expanded_path
                    try:
                        version = pytesseract.get_tesseract_version()
                        print(f"✓ Tesseract version: {version}")
                        return True
                    except:
                        print("✗ Found but couldn't execute")
                else:
                    print("✗ Not found at this location")

        return False


def test_ocr_functionality():
    print("\nTesting OCR functionality...")
    try:
        # Create a simple test image with text
        from PIL import Image, ImageDraw, ImageFont

        # Create a white image
        img = Image.new('RGB', (200, 50), color='white')
        draw = ImageDraw.Draw(img)

        # Add some text
        try:
            # Try to use a default font
            font = ImageFont.load_default()
        except:
            font = None

        draw.text((10, 15), "ABC-1234", fill='black', font=font)

        # Save temporarily
        img.save('test_image.png')

        # Test OCR
        text = pytesseract.image_to_string(img)
        print(f"OCR Result: '{text.strip()}'")

        # Clean up
        if os.path.exists('test_image.png'):
            os.remove('test_image.png')

        if 'ABC' in text or '1234' in text:
            print("✓ OCR functionality test passed")
            return True
        else:
            print("✗ OCR didn't recognize the test text properly")
            return False

    except Exception as e:
        print(f"✗ OCR test failed: {e}")
        return False


def provide_installation_help():
    print("\n" + "=" * 50)
    print("TESSERACT INSTALLATION HELP")
    print("=" * 50)

    if platform.system() == 'Windows':
        print("For Windows:")
        print("1. Go to: https://github.com/UB-Mannheim/tesseract/wiki")
        print("2. Download 'tesseract-ocr-w64-setup-5.3.x.exe'")
        print("3. Run installer as Administrator")
        print("4. Make sure to check 'Add to PATH' during installation")
        print("5. Restart your terminal/IDE after installation")

    elif platform.system() == 'Darwin':  # macOS
        print("For macOS:")
        print("brew install tesseract")

    elif platform.system() == 'Linux':
        print("For Ubuntu/Debian:")
        print("sudo apt update")
        print("sudo apt install tesseract-ocr")

        print("\nFor CentOS/RHEL:")
        print("sudo yum install tesseract")


if __name__ == "__main__":
    if test_tesseract_installation():
        if test_ocr_functionality():
            print("\n🎉 Tesseract is working correctly!")
            print("You can now run your license plate recognition system.")
        else:
            print("\n⚠️ Tesseract is installed but OCR test failed.")
    else:
        print("\n❌ Tesseract is not properly installed.")
        provide_installation_help()
