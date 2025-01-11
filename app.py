from flask import Flask, request, render_template, jsonify
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Initialize the client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        input_text = request.form.get("input_text")
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

        # Start building prompt
        prompt = ""

        # 1) Add explanation only if requested
        if explain_context == "yes":
            prompt += (
                "Explain the overall intent and social context of this phrase, especially how it might be "
                "interpreted by someone neurodivergent vs. neurotypical. If there are any implied social "
                "norms or hidden expectations, please mention them:\n\n"
                f"{input_text}\n\n"
                "After explaining, please translate.\n\n"
            )

        # 2) Translation Mode
        if translation_mode == "nt-to-nd":
            prompt += (
                "Now, translate this phrase from Neurotypical to Neurodivergent communication style. "
                "Remove indirect or optional phrasings, and make it straightforward and clear.\n\n"
                f"Phrase: {input_text}\n\n"
            )
        elif translation_mode == "nd-to-nt":
            prompt += (
                "Now, translate this phrase from Neurodivergent to Neurotypical communication style. "
                "You can add gentle or indirect language if needed, but keep it respectful.\n\n"
                f"Phrase: {input_text}\n\n"
            )

        # 3) Tone instructions
        tone_prompts = {
            "neutral": "Try to keep the result neutral and polite.",
            "formal": "Make the result formal and professional.",
            "casual": "Use a relaxed, friendly style.",
            "empathetic": "Use an empathetic tone, focusing on support and understanding."
        }
        prompt += tone_prompts.get(tone, tone_prompts["neutral"])

        # 4) Optional disclaimer at the end
        prompt += (
            "\n\nNote: This is a helpful suggestion, not a perfect translation. "
            "Real communication styles can vary widely."
        )

        response = client.completions.create(
            model="gpt-3.5-turbo-instruct",  # or whichever model you use
            prompt=prompt,
            max_tokens=300
        )

        result = response.choices[0].text.strip()
        return jsonify({"result": result})

    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
