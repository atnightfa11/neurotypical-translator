from flask import Flask, request, render_template, jsonify, send_from_directory
from openai import OpenAI, OpenAIError
from flask_talisman import Talisman
import os
from dotenv import load_dotenv
from PIL import Image
import pytesseract
import io
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
import re
import html
import imghdr
import hashlib

load_dotenv()

# Get Tesseract path from environment or use default paths
tesseract_paths = [
    os.getenv('TESSERACT_PATH'),
    '/usr/bin/tesseract',
    '/usr/local/bin/tesseract',
    '/opt/homebrew/bin/tesseract',
    'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
]

# Add error handling for Tesseract path
tesseract_found = False
for path in tesseract_paths:
    if path and os.path.exists(path):
        pytesseract.pytesseract.tesseract_cmd = path
        print(f"Using Tesseract at: {path}")
        tesseract_found = True
        break
else:
    print("Error: Tesseract not found in standard locations")

try:
    import subprocess
    result = subprocess.run([pytesseract.pytesseract.tesseract_cmd, '--version'], capture_output=True, text=True)
    print(f"Tesseract version: {result.stdout}")
except Exception as e:
    print(f"Failed to get Tesseract version: {str(e)}")

app = Flask(__name__, static_url_path='/static', static_folder='static')

# Initialize the client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Initialize cache
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

# Add security headers
Talisman(app, content_security_policy={
    'default-src': "'self'",
    'script-src': "'self' 'unsafe-inline' https://cdn.tailwindcss.com https://rsms.me https://plausible.io",
    'style-src': "'self' 'unsafe-inline' https://rsms.me",
    'img-src': "'self' data:",
    'font-src': "'self' https://rsms.me",
    'connect-src': "'self' https://plausible.io",
})

# Validate image uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE = 5 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_input(text):
    text = html.escape(text)
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
    text = ' '.join(text.split())
    return text

def validate_and_format_response(text):
    try:
        if not text or len(text.strip()) < 10:
            return None, "Response too short"
        def create_section(title, content):
            return f"""<div class="{title.lower()}">
                <h3>{title}</h3>
                <div class="{title.lower()}-content">
                    {content.strip()}
                </div>
            </div>"""
        if "Analysis:" in text and "Translation:" in text:
            parts = text.split("Translation:", 1)
            if len(parts) == 2:
                analysis = parts[0].replace('Analysis:', '').strip()
                translation = parts[1].strip()
                formatted = create_section("Analysis", analysis) + create_section("Translation", translation)
                return formatted, None
        else:
            formatted = create_section("Translation", text)
            return formatted, None
    except Exception as e:
        return None, str(e)

def build_prompt(input_text, mode, tone, explain_context):
    tone_prompts = {
        "neutral": "Use clear, straightforward language that sounds natural rather than robotic.",
        "formal": "Use professional language suitable for work or academic settings.",
        "casual": "Use relaxed, conversational language as if speaking with friends.",
        "empathetic": "Use language that shows understanding and acknowledges emotions."
    }
    tone_instruction = tone_prompts.get(tone, tone_prompts["neutral"])

    if mode == "nt-to-nd":
        if explain_context == "yes":
            prompt = (
                "Translate the following neurotypical phrase into clear, direct language. "
                "Identify any implied expectations and provide a direct command if needed. "
                f"Input: \"{input_text}\"\n\nTone: {tone_instruction}"
            )
        else:
            prompt = (
                "Translate this neurotypical statement into a clear, direct command. "
                f"Input: \"{input_text}\"\n\nTone: {tone_instruction}"
            )
    elif mode == "nd-to-nt":
        prompt = (
            "Translate this neurodivergent statement into neurotypical-friendly language. "
            f"Input: \"{input_text}\"\n\nTone: {tone_instruction}"
        )
    else:
        prompt = f"Translate: \"{input_text}\"\nTone: {tone_instruction}"
    return prompt

def validate_image(file):
    try:
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > MAX_FILE_SIZE:
            return False, "File too large (max 5MB)"
        if size == 0:
            return False, "Empty file uploaded"
        
        # Save the current position
        original_position = file.tell()
        
        try:
            image = Image.open(file)
            image.verify()
            # Check image dimensions
            if image.size[0] * image.size[1] > 25000000:  # 25MP limit
                return False, "Image dimensions too large"
            
            # Reset file position after verify()
            file.seek(original_position)
            
        except Exception as e:
            return False, f"Invalid image file: {e}"
        
        # Get file extension from original filename
        if not allowed_file(file.filename):
            return False, "Invalid image format. Please upload PNG or JPG files."
        
        return True, None
    except Exception as e:
        return False, f"Error validating image: {e}"

def generate_cache_key(input_text, translation_mode, tone, explain_context):
    if not input_text:
        return None
    text_hash = hashlib.sha256(input_text.encode()).hexdigest()
    return f"{text_hash}:{translation_mode}:{tone}:{explain_context}"

@app.route("/", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def index():
    if request.method == "POST":
        input_text = request.form.get("input_text")
        input_text = sanitize_input(input_text)
        translation_mode = request.form.get("mode")
        tone = request.form.get("tone", "neutral").lower()
        explain_context = request.form.get("explain_context", "no").lower()

        if not input_text:
            return jsonify({"error": "Please enter some text."})

        if len(input_text) > 1000:
            return jsonify({"error": "Text exceeds 1000 characters. Please shorten your message."})

        cache_key = generate_cache_key(input_text, translation_mode, tone, explain_context)
        cached_result = cache.get(cache_key)
        if cached_result:
            return jsonify({"result": cached_result})

        prompt = build_prompt(input_text, translation_mode, tone, explain_context)

        try:
            response = client.completions.create(
                model="gpt-3.5-turbo-instruct",
                prompt=prompt,
                max_tokens=300,
                temperature=0.7,
                presence_penalty=0.6
            )

            if not response.choices:
                raise ValueError("No response from OpenAI API")

            result = response.choices[0].text.strip()
            formatted_result, error = validate_and_format_response(result)

            if formatted_result:
                cache.set(cache_key, formatted_result, timeout=1800)
                return jsonify({"result": formatted_result})
            else:
                return jsonify({"error": error})
        except OpenAIError as e:
            print(f"OpenAI API error: {str(e)}")
            return jsonify({"error": "Translation service temporarily unavailable. Please try again later."})
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return jsonify({"error": "An unexpected error occurred. Please try again."})

    return render_template("index.html")

@app.route("/process-image", methods=["POST"])
def process_image():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"})
    
    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "No file selected"})
    
    is_valid, error = validate_image(file)
    if not is_valid:
        return jsonify({"error": error})
    
    try:
        image = Image.open(io.BytesIO(file.read()))
        text = pytesseract.image_to_string(image, lang='eng').strip()

        if not text:
            return jsonify({"error": "No text could be extracted from the image"})

        return jsonify({"text": text})

    except Exception as e:
        print(f"Error processing image: {str(e)}")
        return jsonify({"error": f"Error processing image: {str(e)}"})

@app.route("/static/social-preview.png")
def social_preview():
    return send_from_directory('static', 'social-preview.png')

@app.route("/apple-touch-icon.png")
@app.route("/apple-touch-icon-precomposed.png")
def apple_touch_icon():
    return send_from_directory('static', 'favicon.ico')

if __name__ == "__main__":
    app.run(debug=True)
    