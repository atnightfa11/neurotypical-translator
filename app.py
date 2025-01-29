from flask import Flask, request, render_template, jsonify, send_from_directory
from openai import OpenAI
from openai import OpenAIError
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

load_dotenv()

# Set Tesseract path based on environment
if os.path.exists('/opt/homebrew/bin/tesseract'):  # Mac with Homebrew
    pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'
elif os.path.exists('/usr/local/bin/tesseract'):  # Mac with alternative install
    pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'
else:  # Default path
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# Print debug info at startup
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

def sanitize_input(text):
    """Sanitize user input"""
    # Remove any HTML
    text = html.escape(text)
    # Remove any potential script injections
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
    # Remove excessive whitespace
    text = ' '.join(text.split())
    return text

def validate_and_format_response(text):
    """Validate and format the response for better readability"""
    try:
        # Check for minimum content
        if len(text.strip()) < 10:
            return None, "Response too short"
            
        # Format sections
        if "Analysis:" in text:
            parts = text.split("Translation:", 1)
            if len(parts) == 2:
                analysis, translation = parts
                # Clean up the sections
                analysis = analysis.replace('Analysis:', '').strip()
                translation = translation.strip()
                
                # Format with clear separation
                formatted = f"""<div class="analysis">
                    <h3>Analysis</h3>
                    <div class="analysis-content">
                        {analysis}
                    </div>
                </div>
                <div class="translation">
                    <h3>Translation</h3>
                    <div class="translation-content">
                        {translation}
                    </div>
                </div>"""
                return formatted, None
                
        return text, None
    except Exception as e:
        return None, str(e)

@app.route("/", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def index():
    if request.method == "POST":
        input_text = request.form.get("input_text")
        input_text = sanitize_input(input_text)
        translation_mode = request.form.get("mode")
        tone = request.form.get("tone", "neutral").lower()
        explain_context = request.form.get("explain_context", "no").lower()
        
        # Debug print for form data
        print("Form data received:", {
            "explain_context": explain_context,
            "mode": translation_mode,
            "tone": tone
        })

        if not input_text:
            return jsonify({"error": "Please enter some text."})

        # Check character count
        if len(input_text) > 1000:
            return jsonify({"error": "Text exceeds 1000 characters. Please shorten your message."})

        # Start building prompt
        prompt = ""

        # 1) Add explanation only if requested
        if explain_context == "yes":
            prompt += (
                "Analysis:\n"
                "This is a neurotypical phrase that contains:\n"
                "1. A polite suggestion that is actually a requirement\n"
                "2. Social expectations hidden behind optional-sounding language\n"
                "3. The real meaning behind the polite phrasing\n\n"
                f"{input_text}\n\n"
                "\nTranslation:\n"
            )

        # 2) Translation Mode
        if translation_mode == "nt-to-nd":
            prompt += (
                "Convert this into a clear instruction by:\n"
                "1. Removing ALL optional language ('if you want', 'when you can', etc)\n"
                "2. Making it a direct command\n"
                "3. Specifying exact requirements\n"
                "4. Using the shortest possible clear statement\n\n"
                "Example:\n"
                "NT: 'If you could possibly get that report to me whenever you have a chance...'\n"
                "ND: 'Submit the report by 5pm today.'\n\n"
                f"Phrase: {input_text}\n\n"
            )
        elif translation_mode == "nd-to-nt":
            prompt += (
                "Translate this from Neurodivergent to Neurotypical communication style:\n\n"
                "- Add appropriate social cushioning\n"
                "- Include context where helpful\n"
                "- Maintain the core message while adjusting tone\n"
                "- Keep directness when needed for clarity\n"
                "- Balance honesty with social expectations\n"
                "- Add appropriate transitions and softeners\n"
                "- Include relevant emotional context\n"
                "- Preserve important specific details\n\n"
                f"Phrase: {input_text}\n\n"
            )

        # 3) Tone instructions
        tone_prompts = {
            "neutral": "Keep the tone balanced and clear, focusing on factual communication while maintaining respect.",
            "formal": "Use professional language appropriate for work or academic settings, with clear structure and proper etiquette.",
            "casual": "Use a friendly, conversational tone while maintaining clarity and respect.",
            "empathetic": "Emphasize understanding and emotional awareness, acknowledge feelings, and show support."
        }
        prompt += tone_prompts.get(tone, tone_prompts["neutral"])

        # 4) Optional disclaimer at the end
        prompt += (
            "\n\nNote: This is a helpful suggestion, not a perfect translation. "
            "Real communication styles can vary widely."
        )

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
                # Cache the result
                cache_key = f"{input_text}:{translation_mode}:{tone}:{explain_context}"
                cache.set(cache_key, formatted_result, timeout=3600)
                
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
    
    try:
        # Read the image using PIL
        image = Image.open(io.BytesIO(file.read()))
        
        # Use full path for tesseract check
        tesseract_path = pytesseract.pytesseract.tesseract_cmd
        if not os.path.exists(tesseract_path):
            return jsonify({"error": "OCR software not found. Please try again later."})
        
        # Extract text from image
        text = pytesseract.image_to_string(image, lang='eng')
        
        # Clean up the extracted text
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
