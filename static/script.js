document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message-input');
    const chatMessages = document.getElementById('chat-messages');
    const sendBtn = document.getElementById('send-btn');
    const resetBtn = document.getElementById('reset-btn');

    // ── Debug banner ────────────────────────────────────────────
    const elFase    = document.getElementById('debug-fase');
    const elModulo  = document.getElementById('debug-modulo');
    const elCarpeta = document.getElementById('debug-carpeta');

    function updateDebugBanner(debug) {
        if (!debug) return;
        if (elFase)    elFase.textContent    = debug.fase    || '?';
        if (elModulo)  elModulo.textContent  = debug.modulo  || '?';
        if (elCarpeta) elCarpeta.textContent = debug.carpeta || '?';
    }
    // ───────────────────────────────────────────────────────────
    // Auto-focus input
    messageInput.focus();

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addMessage(content, type) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${type}-message`;
        
        // Convierte saltos de línea en <br> y URLs en enlaces si es necesario
        // En este caso, solo ponemos el texto con saltos de línea preservados
        let formattedContent = content.replace(/\n/g, '<br>');
        
        // Detectar URLs simples y hacerlas clickeables si es bot (muy básico)
        if (type === 'bot') {
            const urlRegex = /(https?:\/\/[^\s]+)/g;
            formattedContent = formattedContent.replace(urlRegex, '<a href="$1" target="_blank" rel="noopener noreferrer">Ver Producto</a>');
        }

        msgDiv.innerHTML = `<p>${formattedContent}</p>`;
        chatMessages.appendChild(msgDiv);
        scrollToBottom();
    }

    function showTypingIndicator() {
        const indicatorDiv = document.createElement('div');
        indicatorDiv.className = 'message bot-message typing-container';
        indicatorDiv.id = 'typing-indicator';
        indicatorDiv.innerHTML = `
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;
        chatMessages.appendChild(indicatorDiv);
        scrollToBottom();
    }

    function hideTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const message = messageInput.value.trim();
        if (!message) return;

        // UI: Add user message
        addMessage(message, 'user');
        messageInput.value = '';
        messageInput.disabled = true;
        sendBtn.disabled = true;

        // UI: Show typing
        showTypingIndicator();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ mensaje: message })
            });

            const data = await response.json();
            
            hideTypingIndicator();
            
            if (response.ok) {
                addMessage(data.respuesta, 'bot');
                updateDebugBanner(data.debug);
            } else {
                addMessage('Lo siento, ocurrió un error de conexión.', 'system');
            }

        } catch (error) {
            hideTypingIndicator();
            addMessage('Lo siento, no pude conectar con el servidor.', 'system');
            console.error('Error:', error);
        } finally {
            messageInput.disabled = false;
            sendBtn.disabled = false;
            messageInput.focus();
        }
    });

    resetBtn.addEventListener('click', async () => {
        if (confirm("¿Estás seguro de reiniciar el chat?")) {
            try {
                await fetch('/api/reset', { method: 'POST' });
                chatMessages.innerHTML = `
                    <div class="message system-message">
                        <p>Chat reiniciado. ¿En qué te podemos ayudar hoy?</p>
                    </div>
                `;
            } catch (error) {
                console.error("Error al reiniciar", error);
            }
        }
    });
});
