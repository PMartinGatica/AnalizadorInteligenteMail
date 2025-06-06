// Variables globales y contexto del chat
let chatContext = {
    lastAnalysisData: null,
    conversationHistory: []
};

// Elementos del DOM
document.addEventListener('DOMContentLoaded', () => {
    const searchForm = document.getElementById('searchForm');
    const asuntoInput = document.getElementById('asuntoInput');
    const fechaDesdeInput = document.getElementById('fechaDesdeInput');
    const fechaHastaInput = document.getElementById('fechaHastaInput');
    const estadoDiv = document.getElementById('estadoDiv');
    const chatContainer = document.getElementById('chat-container');
    const chatInput = document.getElementById('chat-input');
    const sendMessageButton = document.getElementById('send-message');
    const suggestionsDiv = document.getElementById('suggestions');

    // Inicializar convertidor de Markdown
    let markdownConverter = new showdown.Converter({
        tables: true,
        tasklists: true,
        openLinksInNewWindow: true
    });

    // Event Listeners
    chatInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            sendMessage();
        }
    });

    sendMessageButton.addEventListener('click', sendMessage);

    // Función para enviar mensaje
    async function sendMessage() {
        if (!chatInput || !chatContainer) return;
        
        const message = chatInput.value.trim();
        if (!message) return;

        // Añadir mensaje del usuario al chat
        addMessageToChat('user', message);
        chatInput.value = '';

        // Mostrar indicador de escritura
        const typingIndicator = addTypingIndicator();

        try {
            const response = await fetch('http://127.0.0.1:5000/api/asistente_consulta', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: message,
                    context: chatContext.conversationHistory,
                    analysisData: chatContext.lastAnalysisData
                })
            });

            if (!response.ok) {
                throw new Error(`Error del servidor: ${response.status}`);
            }

            const data = await response.json();
            typingIndicator.remove();

            if (data.response) {
                addMessageToChat('assistant', data.response);
            }

        } catch (error) {
            console.error('Error:', error);
            typingIndicator.remove();
            addMessageToChat('assistant', 'Lo siento, ocurrió un error al procesar tu mensaje.');
        }
    }

    // Función para añadir mensajes al chat
    function addMessageToChat(role, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = role === 'user' ? 'user-message' : 'assistant-message';

        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        
        const icon = document.createElement('i');
        icon.className = role === 'user' ? 'fas fa-user' : 'fas fa-robot';
        avatarDiv.appendChild(icon);

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        if (role === 'assistant' && content.includes('🔗')) {
            contentDiv.innerHTML = markdownConverter.makeHtml(content);
        } else {
            contentDiv.textContent = content;
        }

        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    // Función para mostrar indicador de escritura
    function addTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message-typing';
        typingDiv.innerHTML = `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;
        chatContainer.appendChild(typingDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return typingDiv;
    }

    // Manejar búsqueda en Drive
    chatInput.addEventListener('input', async (event) => {
        const input = event.target.value.toLowerCase();
        if (input.includes('buscar') && input.includes('drive')) {
            const searchTerm = input.replace(/buscar|en|drive/g, '').trim();
            if (searchTerm) {
                try {
                    const response = await fetch('http://127.0.0.1:5000/api/buscar_drive', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ query: searchTerm })
                    });

                    const data = await response.json();
                    if (data.archivos && data.archivos.length > 0) {
                        suggestionsDiv.innerHTML = data.archivos.map(archivo => `
                            <div class="file-suggestion" data-file-id="${archivo.id}">
                                📄 ${archivo.name}
                            </div>
                        `).join('');
                    }
                } catch (error) {
                    console.error('Error al buscar en Drive:', error);
                }
            }
        }
    });

    searchForm.addEventListener('submit', async (event) => {
        event.preventDefault(); // Evitar el envío predeterminado del formulario

        const asunto = asuntoInput.value.trim();
        const fechaDesde = fechaDesdeInput.value.trim();
        const fechaHasta = fechaHastaInput.value.trim();

        if (!asunto) {
            estadoDiv.textContent = 'Por favor, ingresa un asunto para buscar.';
            estadoDiv.className = 'error';
            return;
        }

        estadoDiv.textContent = 'Generando reporte...';
        estadoDiv.className = 'loading';

        try {
            const response = await fetch(`http://127.0.0.1:5000/api/buscar_correos?asunto=${encodeURIComponent(asunto)}&fecha_desde=${encodeURIComponent(fechaDesde)}&fecha_hasta=${encodeURIComponent(fechaHasta)}`);
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || `Error del servidor: ${response.status}`);
            }

            // Mostrar el resultado
            if (data.resumen_consolidado) {
                estadoDiv.innerHTML = `
                    <div class="success">
                        <h3>Reporte Generado Exitosamente</h3>
                        <p><strong>Total de correos analizados:</strong> ${data.total_correos || 0}</p>
                        <div class="resumen-content">
                            ${data.resumen_consolidado.replace(/\n/g, '<br>')}
                        </div>
                    </div>
                `;
                estadoDiv.className = 'success';
            } else if (data.mensaje_general) {
                estadoDiv.textContent = data.mensaje_general;
                estadoDiv.className = 'warning';
            } else {
                estadoDiv.textContent = 'No se pudo generar el reporte.';
                estadoDiv.className = 'error';
            }
        } catch (error) {
            console.error('Error completo:', error);
            estadoDiv.textContent = `Error: ${error.message}`;
            estadoDiv.className = 'error';
        }
    });
});

