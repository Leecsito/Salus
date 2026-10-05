document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message-input');
    const chatMessages = document.getElementById('chat-messages');
    const sendBtn = document.getElementById('send-btn');
    const resetBtn = document.getElementById('reset-btn');

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

    // ── Panel de logs del servidor ──────────────────────────────
    const logBtn     = document.getElementById('log-btn');
    const logPanel   = document.getElementById('log-panel');
    const logEntries = document.getElementById('log-entries');
    const logClose   = document.getElementById('log-close');
    const logClear   = document.getElementById('log-clear');
    const logAuto    = document.getElementById('log-autoscroll');
    const logStatus  = document.getElementById('log-status');

    let logTimer = null;

    // Token opcional: viaja en la URL (?log_token=...) y se guarda en la pestaña
    const params = new URLSearchParams(window.location.search);
    if (params.has('log_token')) {
        sessionStorage.setItem('salus_log_token', params.get('log_token'));
        params.delete('log_token');
        const resto = params.toString();
        history.replaceState(null, '', window.location.pathname + (resto ? '?' + resto : ''));
    }

    function crearCelda(clase, texto) {
        const celda = document.createElement('span');
        celda.className = clase;
        celda.textContent = texto;
        return celda;
    }

    function renderAviso(mensaje) {
        logEntries.textContent = '';
        const aviso = document.createElement('div');
        aviso.className = 'log-empty';
        aviso.textContent = mensaje;
        logEntries.appendChild(aviso);
    }

    function renderLogs(entradas) {
        logEntries.textContent = '';
        if (!entradas.length) {
            renderAviso('Sin actividad todavía.');
            return;
        }
        for (const entrada of entradas) {
            const fila = document.createElement('div');
            fila.className = 'log-row log-' + (entrada.nivel || 'info').toLowerCase();
            fila.append(
                crearCelda('log-time', entrada.ts || ''),
                crearCelda('log-level', entrada.nivel || ''),
                crearCelda('log-module', entrada.modulo || ''),
                crearCelda('log-msg', entrada.mensaje || '')
            );
            logEntries.appendChild(fila);
        }
        if (logAuto.checked) {
            logEntries.scrollTop = logEntries.scrollHeight;
        }
    }

    async function cargarLogs() {
        const token = sessionStorage.getItem('salus_log_token') || '';
        try {
            const url = '/api/logs?limit=200' + (token ? '&token=' + encodeURIComponent(token) : '');
            const respuesta = await fetch(url);
            const datos = await respuesta.json();
            if (respuesta.ok) {
                logStatus.textContent = 'en vivo';
                logStatus.className = 'log-status ok';
                renderLogs(datos.logs || []);
            } else {
                logStatus.textContent = respuesta.status === 403 ? 'falta token' : 'deshabilitado';
                logStatus.className = 'log-status error';
                renderAviso(datos.respuesta || 'Logs no disponibles.');
            }
        } catch (error) {
            logStatus.textContent = 'sin conexión';
            logStatus.className = 'log-status error';
            renderAviso('No se pudo conectar con /api/logs.');
        }
    }

    function detenerLogs() {
        if (logTimer) {
            clearInterval(logTimer);
            logTimer = null;
        }
    }

    logBtn.addEventListener('click', () => {
        const estabaAbierto = !logPanel.hidden;
        logPanel.hidden = estabaAbierto;
        logBtn.classList.toggle('active', !estabaAbierto);
        if (estabaAbierto) {
            detenerLogs();
        } else {
            cargarLogs();
            logTimer = setInterval(cargarLogs, 3000);
        }
    });

    logClose.addEventListener('click', () => {
        logPanel.hidden = true;
        logBtn.classList.remove('active');
        detenerLogs();
    });

    logClear.addEventListener('click', () => {
        logEntries.textContent = '';
    });
});
