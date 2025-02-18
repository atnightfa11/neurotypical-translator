from flask import Flask, request, render_template, jsonify, send_from_directory
from openai import OpenAI
from openai import OpenAIError
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
    os.getenv('TESSERACT_PATH'),  # From environment variable
    '/usr/bin/tesseract',         # Linux default
    '/usr/local/bin/tesseract',   # Mac default
    '/opt/homebrew/bin/tesseract', # Mac Homebrew
    'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'  # Windows
]

for path in tesseract_paths:
    if path and os.path.exists(path):
        pytesseract.pytesseract.tesseract_cmd = path
        print(f"Using Tesseract at: {path}")
        break
else:
    print("Warning: Tesseract not found in standard locations")

print(f"Starting app with Tesseract path: {pytesseract.pytesseract.tesseract_cmd}")
try:
    import subprocess
    result = subprocess.run([pytesseract.pytesseract.tesseract_cmd, '--version'],
                            capture_output=True, text=True)
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
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB limit

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_input(text):
    """Sanitize user input"""
    text = html.escape(text)
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
    text = ' '.join(text.split())
    return text

def validate_and_format_response(text):
    """Validate and format the response for better readability"""
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
    """
    Constructs the prompt for the OpenAI API.
    mode: "nt-to-nd" or "nd-to-nt"
    tone: one of "neutral", "formal", "casual", "empathetic"
    explain_context: "yes" or "no"
    """
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
                "You are a translator between neurotypical (NT) and neurodivergent (ND) communication. "
                "The user is neurodivergent. First, analyze the following neurotypical phrase by answering:\n"
                "1. Which part of the phrase appears optional but is actually required?\n"
                "2. Why might a neurotypical speaker use optional language?\n"
                "3. What is the underlying expectation?\n\n"
                "Present your analysis in a numbered format as described above. "
                "Then, convert the phrase into a clear, direct command that removes optional language and makes implicit requirements explicit. "
                "Retain any deadlines or key details, and ensure the final translation is presented in natural, flowing language without numbered lists.\n\n"
                f"Input:\n\"{input_text}\"\n\n"
                f"Provide your Analysis and Translation. Tone: {tone_instruction}"
            )
        else:
            prompt = (
                "You are a translator between neurotypical (NT) and neurodivergent (ND) communication. "
                "The user is neurodivergent. Convert the following neurotypical phrase into a clear, direct command that a neurodivergent individual can easily understand. "
                "Remove any optional language and make implicit requirements explicit, while keeping all important details intact. "
                "Present the translation in natural, flowing language without numbered lists.\n\n"
                f"Input:\n\"{input_text}\"\n\n"
                f"Direct Command: Tone: {tone_instruction}"
            )
    elif mode == "nd-to-nt":
        prompt = (
            "You are a translator between neurodivergent (ND) and neurotypical (NT) communication. "
            "The user is neurodivergent. Convert the following direct ND phrase into a version that is more neurotypical-friendly. "
            "Soften the language with polite phrasing and context while keeping the core message and important details unchanged. "
            "Present the translation in natural, flowing language without numbered lists.\n\n"
            f"Input:\n\"{input_text}\"\n\n"
            f"Polite Translation: Tone: {tone_instruction}"
        )
    else:
        prompt = f"Translate the following phrase:\n\"{input_text}\"\n\nTone: {tone_instruction}"
    
    return prompt

def validate_image(file):
    """Validate file is a legitimate image and within size limits"""
    try:
        # Check file size
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if size > MAX_FILE_SIZE:
            return False, "File too large (max 5MB)"
            
        # Verify file is actually an image
        header = file.read(512)
        file.seek(0)
        file_type = imghdr.what(None, header)
        
        if not file_type or file_type not in ALLOWED_EXTENSIONS:
            return False, "Invalid image format"
            
        return True, None
    except Exception:
        return False, "Error validating image"

def generate_cache_key(input_text, translation_mode, tone, explain_context):
    """Create a secure hashed cache key instead of storing raw input text."""
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
        
        print("Form data received:", {
            "explain_context": explain_context,
            "mode": translation_mode,
            "tone": tone
        })

        if not input_text:
            return jsonify({"error": "Please enter some text."})

        if len(input_text) > 1000:
            return jsonify({"error": "Text exceeds 1000 characters. Please shorten your message."})

        # Generate secure cache key
        cache_key = generate_cache_key(input_text, translation_mode, tone, explain_context)
        
        # Check cache first
        cached_result = cache.get(cache_key)
        if cached_result:
            return jsonify({"result": cached_result})

        # Build the improved prompt
        prompt = build_prompt(input_text, translation_mode, tone, explain_context)

        try:
            response = client.completions.create(
                model="gpt-3.5-turbo-instruct",
                prompt=prompt,
                max_tokens=300,
                temperature=0.7,
                presence_penalty=0.6
            )

            result = response.choices[0].text.strip()
            formatted_result, error = validate_and_format_response(result)
            
            if formatted_result:
                cache.set(cache_key, formatted_result, timeout=1800)
                return jsonify({"result": formatted_result})
            else:
                return jsonify({"error": error})
            
        except OpenAIError as e:
            print(f"OpenAI API error: {str(e)}")
            return jsonify({"error": "Translation service temporarily unavailable. Please try again in a moment."})
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return jsonify({"error": "An unexpected error occurred. Please try again."})

    return render_template("index.html")

@app.route("/process-image", methods=["POST"])
def process_image():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"})
    
    file = request.files["image"]
    is_valid, error = validate_image(file)
    if not is_valid:
        return jsonify({"error": error})
    
    try:
        image = Image.open(io.BytesIO(file.read()))
        if not hasattr(pytesseract.pytesseract, 'tesseract_cmd'):
            return jsonify({"error": "OCR software not found. Please try again later."})
        
        text = pytesseract.image_to_string(image, lang='eng')
        text = text.strip()
        
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
