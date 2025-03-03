document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById("translator-form");
    const input = document.getElementById("input-text");
    const modeDisplay = document.getElementById("mode-display");
    const loading = document.getElementById("loading");
    const charCount = document.getElementById("char-count");
    const contrastToggle = document.querySelector(".contrast-toggle");
    const submitButton = form.querySelector('button[type="submit"]');
    
    // Update character count
    input.addEventListener('input', function() {
      charCount.textContent = `${this.value.length}/1000 characters`;
      charCount.style.color = this.value.length > 800 ? '#ff4444' : '#666';
    });
    
    // Update mode display
    document.querySelectorAll('input[name="mode"]').forEach(radio => {
      radio.addEventListener('change', function() {
        modeDisplay.textContent = this.value === 'nt-to-nd' 
          ? 'Neurotypical to Neurodivergent'
          : 'Neurodivergent to Neurotypical';
      });
    });
    
    // Specifically target the header elements with title and description
    function forceHeaderDarkMode(isDarkMode) {
      // First try to find by tag and position
      const mainTitle = document.querySelector('h1');
      const description = document.querySelector('p.description') || 
                         document.querySelector('.container > p') ||
                         document.querySelector('p:nth-child(2)');
      
      // Target any h1 elements that might be the title
      const allH1s = document.querySelectorAll('h1');
      allH1s.forEach(h1 => {
        if (isDarkMode) {
          h1.style.color = '#e0e0e0';
          h1.style.backgroundColor = 'transparent';
          
          // Try to get the parent container too
          const parent = h1.parentElement;
          if (parent) {
            parent.style.backgroundColor = '#2d3748';
            parent.style.color = '#e0e0e0';
          }
        } else {
          h1.style.color = '';
          h1.style.backgroundColor = '';
          
          const parent = h1.parentElement;
          if (parent) {
            parent.style.backgroundColor = '';
            parent.style.color = '';
          }
        }
      });
      
      // Target specifically the title and description
      if (mainTitle) {
        if (isDarkMode) {
          mainTitle.style.color = '#e0e0e0';
          mainTitle.style.backgroundColor = 'transparent';
        } else {
          mainTitle.style.color = '';
          mainTitle.style.backgroundColor = '';
        }
      }
      
      if (description) {
        if (isDarkMode) {
          description.style.color = '#e0e0e0';
          description.style.backgroundColor = 'transparent';
        } else {
          description.style.color = '';
          description.style.backgroundColor = '';
        }
      }
      
      // Try to get all paragraphs, some might be the description
      const allPs = document.querySelectorAll('p');
      allPs.forEach(p => {
        if (isDarkMode) {
          p.style.color = '#e0e0e0';
          p.style.backgroundColor = 'transparent';
        } else {
          p.style.color = '';
          p.style.backgroundColor = '';
        }
      });
      
      // Also try to directly get the container
      const container = document.querySelector('.container');
      if (container) {
        if (isDarkMode) {
          container.style.backgroundColor = '#2d3748';
          container.style.color = '#e0e0e0';
        } else {
          container.style.backgroundColor = '';
          container.style.color = '';
        }
      }
    }

    function applyDarkModeToAllElements(isDarkMode) {
      // First target the header specifically
      forceHeaderDarkMode(isDarkMode);
      
      // Then continue with other elements
      // Style all text-containing elements
      const textElements = document.querySelectorAll('h1, h2, h3, h4, h5, h6, p, span, label, a, div');
      textElements.forEach(el => {
        if (isDarkMode) {
          el.style.color = '#e0e0e0';
        } else {
          el.style.color = '';
        }
      });
      
      // Style all containers
      const containers = document.querySelectorAll('.container, div.container, main > div, section');
      containers.forEach(el => {
        if (isDarkMode) {
          el.style.backgroundColor = '#2d3748';
          el.style.borderColor = '#4a5568';
        } else {
          el.style.backgroundColor = '';
          el.style.borderColor = '';
        }
      });
      
      // Style all form elements
      const formElements = document.querySelectorAll('input, textarea, select, button, .input-area');
      formElements.forEach(el => {
        if (isDarkMode) {
          if (el.tagName === 'BUTTON' && el.type === 'submit') {
            el.style.backgroundColor = '#4299e1';
            el.style.color = '#ffffff';
          } else {
            el.style.backgroundColor = '#1a202c';
            el.style.color = '#e0e0e0';
          }
          el.style.borderColor = '#4a5568';
        } else {
          el.style.backgroundColor = '';
          el.style.color = '';
          el.style.borderColor = '';
        }
      });
      
      // Style result areas
      const resultAreas = document.querySelectorAll('#result, .result-container, .output-area');
      resultAreas.forEach(el => {
        if (isDarkMode) {
          el.style.backgroundColor = '#2d3748';
          el.style.borderColor = '#4a5568';
          el.style.color = '#e0e0e0';
        } else {
          el.style.backgroundColor = '';
          el.style.borderColor = '';
          el.style.color = '';
        }
      });
    }

    function toggleDarkMode() {
      const htmlElement = document.documentElement;
      const isDarkMode = htmlElement.classList.toggle('high-contrast');
      
      // Apply direct styling to ensure all elements update
      applyDarkModeToAllElements(isDarkMode);
      
      // Save preference to localStorage
      localStorage.setItem('darkMode', isDarkMode ? 'enabled' : 'disabled');
      
      // Update button aria-label for accessibility
      if (contrastToggle) {
        contrastToggle.setAttribute('aria-label', 
          isDarkMode ? 'Switch to light mode' : 'Switch to dark mode');
      }
      
      // Announce mode change for screen readers
      const modeAnnouncement = document.getElementById('mode-announcement');
      if (modeAnnouncement) {
        modeAnnouncement.textContent = `${isDarkMode ? 'Dark' : 'Light'} mode enabled`;
      }
    }
    
    contrastToggle.addEventListener('click', toggleDarkMode);
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        submitButton.click();
      }
      if (e.key === 'Escape') {
        input.value = '';
        charCount.textContent = '0/1000 characters';
      }
    });
    
    // Function to show toast notifications
    const notifications = {
      show(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast ${type} show`;
        setTimeout(() => toast.classList.remove('show'), 3000);
      },
      error(message) {
        this.show(message, 'error');
      },
      success(message) {
        this.show(message, 'success');
      }
    };
    
    // Form submission handler
    form.addEventListener("submit", async function(e) {
      e.preventDefault();
      submitButton.disabled = true;
      submitButton.innerHTML = `<span class="loading-spinner"></span> Translating...`;
    
      const formData = new FormData(this);
    
      try {
        loading.style.display = 'block';
        const response = await fetch("/", {
          method: "POST",
          body: formData
        });
    
        const result = await response.json();
        if (result.error) {
          notifications.error(result.error);
        } else {
          const resultDiv = document.getElementById("result");
          const formatted = result.result
            .replace(/\n{2,}/g, '<br><br>')
            .replace(/\n/g, '<br>');
          resultDiv.innerHTML = formatted;
    
          // Create and append the Copy to Clipboard button
          const copyButton = document.createElement('button');
          copyButton.className = 'copy-btn';
          copyButton.textContent = 'Copy to Clipboard';
          copyButton.addEventListener('click', () => {
            navigator.clipboard.writeText(resultDiv.innerText)
              .then(() => notifications.success("Copied to clipboard!"))
              .catch(() => notifications.error("Copy failed"));
          });
          resultDiv.appendChild(copyButton);
    
          resultDiv.scrollIntoView({ behavior: 'smooth' });
        }
      } catch (error) {
        notifications.error("An error occurred. Please try again.");
      } finally {
        loading.style.display = 'none';
        submitButton.disabled = false;
        submitButton.innerHTML = 'Translate';
      }
    });
    
    // Restore dark mode preference on page load
    function restoreDarkModePreference() {
      const savedMode = localStorage.getItem('darkMode');
      if (savedMode === 'enabled') {
        document.documentElement.classList.add('high-contrast');
        
        // Apply direct styling to ensure all elements update
        applyDarkModeToAllElements(true);
        
        // Update button aria-label for accessibility
        if (contrastToggle) {
          contrastToggle.setAttribute('aria-label', 'Switch to light mode');
        }
      }
    }
    
    // Initialize dark mode on page load
    document.addEventListener('DOMContentLoaded', function() {
      restoreDarkModePreference();
      
      // Immediately force dark mode on the header if enabled
      if (document.documentElement.classList.contains('high-contrast')) {
        forceHeaderDarkMode(true);
      }
      
      // Re-apply dark mode after a slight delay to catch any late-loading elements
      setTimeout(function() {
        if (document.documentElement.classList.contains('high-contrast')) {
          forceHeaderDarkMode(true);
          applyDarkModeToAllElements(true);
        }
      }, 500);
    });
    
    // Initialize speech recognition
    const speakButton = document.getElementById('speak-button');
    const uploadButton = document.getElementById('upload-button');
    const fileInput = document.getElementById('file-input');
    
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';
    
      let isRecording = false;
      speakButton.onclick = function() {
        if (isRecording) {
          recognition.stop();
          speakButton.innerHTML = `
            <svg viewBox="0 0 24 24" width="16" height="16">
              <path fill="currentColor" d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
              <path fill="currentColor" d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
            </svg>
            <span>Speak</span>`;
        } else {
          try {
            recognition.start();
            speakButton.innerHTML = `
              <svg viewBox="0 0 24 24" width="16" height="16">
                <circle cx="12" cy="12" r="8" fill="currentColor"/>
              </svg>
              <span>Recording...</span>`;
          } catch (err) {
            notifications.error('Failed to start recording. Please try again.');
            isRecording = false;
            return;
          }
        }
        isRecording = !isRecording;
      };
    
      recognition.onresult = function(event) {
        const textarea = document.getElementById('input-text');
        if (event.results[0][0]) {
          textarea.value = event.results[0][0].transcript;
          const submitEvent = new Event('submit', {
            bubbles: true,
            cancelable: true
          });
          document.getElementById('translator-form').dispatchEvent(submitEvent);
        }
      };
    } else {
      speakButton.style.display = 'none';
      console.log('Speech recognition is not supported in this browser');
    }
    
    // Error handling helper (used if speech recognition fails)
    function showError(message, element) {
      const errorDiv = document.createElement('div');
      errorDiv.className = 'error-message visible';
      errorDiv.textContent = message;
      element.parentNode.insertBefore(errorDiv, element.nextSibling);
      setTimeout(() => errorDiv.remove(), 5000);
    }
    
    // Handle file upload
    uploadButton.onclick = () => fileInput.click();
    
    fileInput.onchange = async function(e) {
      if (this.files && this.files[0]) {
        uploadButton.classList.add('loading');
        const formData = new FormData();
        formData.append('image', this.files[0]);
        try {
          loading.style.display = 'block';
          const response = await fetch('/process-image', {
            method: 'POST',
            body: formData
          });
          const result = await response.json();
          if (result.error) {
            notifications.error(result.error);
          } else {
            document.getElementById('input-text').value = result.text;
            document.getElementById('input-text').dispatchEvent(new Event('input'));
          }
        } catch (error) {
          notifications.error('Error processing image. Please try again.');
        } finally {
          loading.style.display = 'none';
          uploadButton.classList.remove('loading');
        }
      }
    };
  });  