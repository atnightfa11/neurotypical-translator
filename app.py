import os
import logging
import subprocess
import re
import html
import hashlib
import io

# Third-party imports
from flask import Flask, request, render_template, jsonify, send_from_directory, abort
from openai import OpenAI, OpenAIError
from flask_talisman import Talisman
from dotenv import load_dotenv
from PIL import Image
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
import werkzeug.datastructures

# Configure logging
log = logging.getLogger(__name__)
log_level = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

# Initialize Flask app right away
app = Flask(__name__, static_url_path='/static', static_folder='static')

@app.before_request
def block_suspicious_files():
    blocked = ['.env', '.git', '.DS_Store', 'sitemap.xml.gz']
    if any(x in request.path for x in blocked):
        return abort(404)

# Feature flags object for clear indication of available features
app_features = {
    "text_translation": True,  # Core feature - always available
    "image_processing": False  # Will be set to True if Tesseract is available
}

# Try to import pytesseract but handle its absence gracefully
tesseract_available = False
try:
    import pytesseract
    # Get Tesseract path from environment or use default paths
    tesseract_paths = [
        os.getenv('TESSERACT_PATH'),
        '/usr/bin/tesseract',
        '/usr/local/bin/tesseract',
        '/opt/homebrew/bin/tesseract',
        'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
    ]

    # Check if Tesseract is installed
    tesseract_found = False
    for path in tesseract_paths:
        if path and os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            log.info(f"Using Tesseract at: {path}")
            tesseract_found = True
            break

    if not tesseract_found:
        # Try system default
        try:
            result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True)
            log.info(f"Found system Tesseract: {result.stdout}")
            tesseract_found = True
            tesseract_available = True
            app_features["image_processing"] = True
        except Exception as e:
            log.warning(f"Tesseract not available: {str(e)}")
            tesseract_available = False
    else:
        tesseract_available = True
        app_features["image_processing"] = True
except ImportError:
    log.warning("pytesseract module not available")
    tesseract_available = False

# Initialize the client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day", "20 per hour"],
    storage_uri="memory://"
)

# Initialize cache with timeout
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 1800,
    'CACHE_THRESHOLD': 1000  # Limit cache size
})

# Add security headers
Talisman(app, content_security_policy={
    'default-src': "'self'",
    'script-src': "'self' https://cdn.tailwindcss.com https://rsms.me https://plausible.io",
    'style-src': "'self' 'unsafe-inline' https://rsms.me",
    'img-src': "'self' data:",
    'font-src': "'self' https://rsms.me",
    'connect-src': "'self' https://plausible.io",
    'frame-ancestors': "'none'",  # Prevent clickjacking
    'form-action': "'self'",
})

# Validate image uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE = 5 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_input(text):
    if not isinstance(text, str):
        return ''
    text = html.escape(text)
    text = re.sub(r'<[^>]*>', '', text, flags=re.DOTALL)  # Remove all HTML tags
    text = ' '.join(text.split())
    return text[:1000]  # Enforce length limit

def validate_and_format_response(text):
    try:
        if not text or len(text.strip()) < 10:
            return None, "The response was too short. Please try again with a different input."
        # Sanitize the response
        text = html.escape(text)
        # Add line breaks for readability
        text = text.replace('\n\n', '<br><br>')
        def create_section(title, content):
            return f"""<div class="{title.lower()}" role="region" aria-label="{title}">
                <h3>{title}</h3>
                <div class="{title.lower()}-content" tabindex="0">
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
        return None, "There was a problem formatting the response. This is not your fault. Please try again."

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
                "Remove ambiguity and explicitly state any hidden expectations. "
                f"Input: \"{input_text}\"\n\nTone: {tone_instruction}"
            )
        else:
            prompt = (
                "Translate this neurotypical statement into a clear, direct command. "
                "Remove ambiguity and explicitly state any hidden expectations. "
                f"Input: \"{input_text}\"\n\nTone: {tone_instruction}"
            )
    elif mode == "nd-to-nt":
        prompt = (
            "Translate this neurodivergent statement into neurotypical-friendly language. "
            "Add appropriate social niceties while preserving the original meaning. "
            f"Input: \"{input_text}\"\n\nTone: {tone_instruction}"
        )
    else:
        prompt = f"Translate: \"{input_text}\"\nTone: {tone_instruction}"
    return prompt

def validate_image(file):
    # Skip this function if Tesseract is not available
    if not tesseract_available:
        return False, "Image processing is currently not available. You can still use text translation."
        
    try:
        if not file or not isinstance(file, werkzeug.datastructures.FileStorage):
            return False, "The file upload didn't work. Please try again or use text input instead."
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > MAX_FILE_SIZE:
            return False, "The image is too large (max 5MB). Please use a smaller image or type your text."
        if size == 0:
            return False, "The file appears to be empty. Please select a valid image file."
        
        # Create a copy of the file in memory
        file_bytes = file.read()
        file.seek(0)
        
        try:
            image = Image.open(io.BytesIO(file_bytes))
            image.verify()
            
            # Additional image validation
            if image.format.upper() not in ['JPEG', 'PNG']:
                return False, "Please use a JPEG or PNG image format."
            
            if image.size[0] * image.size[1] > 25000000:  # 25MP limit
                return False, "The image dimensions are too large. Please use a smaller image."
            
        except Exception as e:
            return False, f"The image file couldn't be processed: {e}. Try a different image."
        
        # Get file extension from original filename
        if not allowed_file(file.filename):
            return False, "Only PNG and JPG files are accepted. Please select a different file."
        
        # Add content type validation
        content_type = file.content_type.lower()
        if content_type not in ['image/jpeg', 'image/png']:
            return False, "The file type isn't supported. Please use a JPEG or PNG image."
        
        return True, None
    except Exception as e:
        return False, f"There was a problem with the image: {e}. Try using text input instead."

def generate_cache_key(input_text, translation_mode, tone, explain_context):
    if not input_text:
        return None
    text_hash = hashlib.sha256(input_text.encode()).hexdigest()
    return f"v1:{text_hash}:{translation_mode}:{tone}:{explain_context}"  # Add version prefix

@app.route("/", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def index():
    if request.method == "POST":
        input_text = request.form.get("input_text")
        input_text = sanitize_input(input_text)
        translation_mode = request.form.get("mode")
        tone = request.form.get("tone", "neutral").lower()
        explain_context = request.form.get("explain_context", "no").lower()

        if not input_text:
            return jsonify({"error": "Please enter some text to translate."})

        if len(input_text) > 1000:
            return jsonify({"error": "Text is too long (maximum 1000 characters). Please shorten your message."})

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
                raise ValueError("No response received from the translation service")

            result = response.choices[0].text.strip()
            formatted_result, error = validate_and_format_response(result)

            if formatted_result:
                cache.set(cache_key, formatted_result, timeout=1800)
                return jsonify({"result": formatted_result})
            else:
                return jsonify({"error": error})
        except OpenAIError as e:
            log.error(f"OpenAI API error: {str(e)}")
            return jsonify({"error": "The translation service is temporarily unavailable. Please try again in a few moments."})
        except Exception as e:
            log.error(f"Unexpected error: {str(e)}")
            return jsonify({"error": "Something went wrong. This is not your fault. Please try again."})

    # Pass feature flags to the template to hide/show UI elements based on available features
    return render_template("index.html", features=app_features)

@app.route("/process-image", methods=["POST"])
@limiter.limit("10 per minute")
def process_image():
    # Check if Tesseract is available
    if not tesseract_available:
        return jsonify({"error": "Image processing is not available right now. Please type your text instead."})
        
    if "image" not in request.files:
        return jsonify({"error": "No image was uploaded. Please select an image file."})
    
    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "No file was selected. Please choose an image."})
    
    is_valid, error = validate_image(file)
    if not is_valid:
        return jsonify({"error": error})
    
    try:
        image = Image.open(file)
        image = image.convert('L')
        image = image.point(lambda x: 0 if x < 128 else 255, '1')
        text = pytesseract.image_to_string(image, lang='eng').strip()

        if not text:
            return jsonify({"error": "No text could be found in the image. Please try a clearer image or type your text."})
        if len(text) > 1000:
            return jsonify({"error": "The text from the image is too long. Please use a shorter text or type it manually."})

        return jsonify({"text": text})

    except Exception as e:
        log.error(f"Error processing image: {str(e)}")
        return jsonify({"error": "There was a problem reading the image. Please try again or type your text."})

@app.route("/static/social-preview.png")
def social_preview():
    return send_from_directory('static', 'social-preview.png')

@app.route("/apple-touch-icon.png")
@app.route("/apple-touch-icon-precomposed.png")
def apple_touch_icon():
    return send_from_directory('static', 'favicon.ico')

@app.route("/features")
def get_features():
    """Endpoint to check available features - useful for client-side adaptation"""
    return jsonify(app_features)

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, OpenAIError):
        log.error(f"OpenAI API error: {str(e)}")
        return jsonify({"error": "The translation service is temporarily unavailable. Please try again later."}), 503
    log.error(f"Unexpected error: {str(e)}")
    return jsonify({"error": "Something went wrong. This is not your fault. Please try again."}), 500

if __name__ == "__main__":
    app.run(debug=True)
    