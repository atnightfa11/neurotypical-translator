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
        if "Analysis:" in text and "Translation:" in text:
            parts = text.split("Translation:", 1)
            if len(parts) == 2:
                analysis, translation = parts
                analysis = analysis.replace('Analysis:', '').strip()
                translation = translation.strip()
                
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
        else:
            # Format translation only
            formatted = f"""<div class="translation">
                <h3>Translation</h3>
                <div class="translation-content">
                    {text.strip()}
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
                "First, analyze this communication:\n\n"
                "Explain:\n"
                "1. The literal meaning\n"
                "2. The actual expectation or requirement\n"
                "3. Why neurotypical people phrase it this way\n"
                "4. How neurodivergent people might interpret it\n\n"
                f"{input_text}\n\n"
                "Then provide the translation below.\n\n"
                "Analysis:\n"
            )
        else:
            prompt += "Translation:\n\n"

        # 2) Translation Mode
        if translation_mode == "nt-to-nd":
            prompt += (
                "Convert this neurotypical communication into clear, direct language.\n\n"
                "For social situations:\n"
                "1. State if this is an invitation or just information\n"
                "2. Clarify any expected responses or actions\n"
                "3. Specify timing and logistics\n"
                "4. Note if a response is needed and by when\n"
                "5. Explain any social expectations\n\n"
                "For work communications:\n"
                "1. State the main message or request clearly\n"
                "2. List specific actions needed\n"
                "3. Include deadlines and requirements\n"
                "4. Clarify any unstated expectations\n\n"
                "Examples:\n"
                "NT: 'We're going to Subway for lunch'\n"
                "ND: '1. This is an invitation to join for lunch at Subway\n2. The group is leaving now\n3. You can say yes or no\n4. If yes, bring money for lunch\n5. Expected return time: 1 hour'\n\n"
                "NT: 'Just wanted to let you know we're having cake in the break room!'\n"
                "ND: '1. There is cake available in the break room now\n2. You are invited to have some\n3. This is a social gathering - staying for 5-10 minutes is typical'\n\n"
                f"Phrase: {input_text}\n\n"
                "Direct translation:"
            )
        elif translation_mode == "nd-to-nt":
            prompt += (
                "Convert this direct communication into a neurotypical-friendly style:\n\n"
                "Important: This is a direct phrase that needs to be made more socially comfortable.\n\n"
                "Rules:\n"
                "1. Add polite phrases while keeping the core message\n"
                "2. Include social context and emotional awareness\n"
                "3. Use 'softeners' like:\n"
                "   - 'Would you mind...'\n"
                "   - 'If you could...'\n"
                "   - 'When you have a chance...'\n"
                "4. Keep important details and deadlines\n\n"
                "Examples:\n"
                "ND: 'This meeting is unnecessary.'\n"
                "NT: 'I was wondering if we could review our meeting objectives to ensure we're making the best use of everyone's time.'\n\n"
                "ND: 'You're late again. It's disrespectful.'\n"
                "NT: 'I notice we're having some challenges with meeting start times. Could we discuss how to make the schedule work better for everyone?'\n\n"
                f"Phrase: {input_text}\n\n"
                "Polite translation:"
            )

        # 3) Tone instructions
        tone_prompts = {
            "neutral": "Use clear, factual language. Focus on what needs to be done.",
            "formal": "Use professional language suitable for work emails or academic settings.",
            "casual": "Use relaxed language like you'd use with friends, but keep the message clear.",
            "empathetic": "Show understanding of feelings and acknowledge the impact of requests."
        }
        prompt += tone_prompts.get(tone, tone_prompts["neutral"])

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
