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

    // Add speech recognition functionality
    function initSpeechRecognition() {
        if ('webkitSpeechRecognition' in window) {
            const recognition = new webkitSpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            
            // Add speech button to UI
            const speechButton = document.createElement('button');
            speechButton.className = 'speech-input';
            speechButton.innerHTML = '<span role="img" aria-label="microphone">🎤</span> Speak';
            speechButton.setAttribute('type', 'button');  // Prevent form submission
            
            // Add button next to textarea
            const textarea = document.getElementById('input-text');
            textarea.parentNode.insertBefore(speechButton, textarea.nextSibling);
            
            let isRecording = false;
            
            // Handle speech input
            speechButton.onclick = function() {
                if (isRecording) {
                    recognition.stop();
                    speechButton.innerHTML = '<span role="img" aria-label="microphone">🎤</span> Speak';
                } else {
                    recognition.start();
                    speechButton.innerHTML = '<span role="img" aria-label="recording">⏺</span> Recording...';
                }
                isRecording = !isRecording;
            };
            
            recognition.onresult = function(event) {
                textarea.value = event.results[0][0].transcript;
                // Trigger character count update
                textarea.dispatchEvent(new Event('input'));
            };
            
            recognition.onerror = function(event) {
                console.error('Speech recognition error:', event.error);
                speechButton.innerHTML = '<span role="img" aria-label="microphone">🎤</span> Speak';
                isRecording = false;
            };
            
            recognition.onend = function() {
                speechButton.innerHTML = '<span role="img" aria-label="microphone">🎤</span> Speak';
                isRecording = false;
            };
        }
    }

    // Initialize speech recognition
    initSpeechRecognition();

    // File upload handling
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');

    // Handle drag and drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        uploadZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        uploadZone.addEventListener(eventName, unhighlight, false);
    });

    function highlight(e) {
        uploadZone.classList.add('dragover');
    }

    function unhighlight(e) {
        uploadZone.classList.remove('dragover');
    }

    uploadZone.addEventListener('drop', handleDrop, false);
    uploadZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFiles);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles({ target: { files: files } });
    }

    async function handleFiles(e) {
        const file = e.target.files[0];
        if (file && file.type.startsWith('image/')) {
            const formData = new FormData();
            formData.append('image', file);

            try {
                loading.style.display = 'block';
                const response = await fetch('/process-image', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();
                if (result.error) {
                    alert(result.error);
                } else {
                    document.getElementById('input-text').value = result.text;
                    document.getElementById('input-text').dispatchEvent(new Event('input'));
                }
            } catch (error) {
                alert('Error processing image. Please try again.');
            } finally {
                loading.style.display = 'none';
            }
        } else {
            alert('Please upload an image file.');
        }
    }
});