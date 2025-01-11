document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById("translator-form");
    const input = document.getElementById("input-text");
    const modeDisplay = document.getElementById("mode-display");
    const loading = document.getElementById("loading");
    const charCount = document.getElementById("char-count");
    const contrastToggle = document.querySelector(".contrast-toggle");

    // Update character count
    input.addEventListener('input', function() {
        const remaining = 500 - this.value.length;
        charCount.textContent = `${this.value.length}/500 characters`;
        
        // Visual feedback when approaching limit
        if (this.value.length > 400) {
            charCount.style.color = '#ff4444';
        } else {
            charCount.style.color = '#666';
        }
    });

    // Update mode display
    document.querySelectorAll('input[name="mode"]').forEach(radio => {
        radio.addEventListener('change', function() {
            modeDisplay.textContent = this.value === 'nt-to-nd' 
                ? 'Neurotypical to Neurodivergent'
                : 'Neurodivergent to Neurotypical';
        });
    });

    // High contrast mode toggle
    contrastToggle.addEventListener('click', function() {
        document.body.classList.toggle('high-contrast');
        localStorage.setItem('highContrast', 
            document.body.classList.contains('high-contrast'));
    });

    // Show loading state during translation
    form.addEventListener("submit", async function(e) {
        e.preventDefault();
        loading.style.display = 'block';
        
        try {
            const inputText = document.getElementById("input-text").value;
            const mode = document.querySelector('input[name="mode"]:checked').value;
            const tone = document.getElementById("tone").value;
            const explainContext = document.getElementById("explain-context").checked;
            
            const response = await fetch("/", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: new URLSearchParams({ 
                    input_text: inputText, 
                    mode: mode, 
                    tone: tone, 
                    explain_context: explainContext ? "yes" : "no"
                })
            });
            
            const result = await response.json();
            
            if (result.error) {
                alert(result.error);
            } else {
                const resultDiv = document.getElementById("result");
                
                // Replace double newlines with two <br> tags, and single newlines with one <br>
                // so the explanation and translation display clearly as separate lines/paragraphs
                const formatted = result.result
                    .replace(/\n{2,}/g, '<br><br>')  // two newlines => two <br>
                    .replace(/\n/g, '<br>');         // single newline => one <br>

                resultDiv.innerHTML = formatted;

                // Smooth scroll to result
                resultDiv.scrollIntoView({ behavior: 'smooth' });
            }
        } catch (error) {
            alert("An error occurred. Please try again.");
        } finally {
            loading.style.display = 'none';
        }
    });

    // Restore high contrast preference
    if (localStorage.getItem('highContrast') === 'true') {
        document.body.classList.add('high-contrast');
    }
});