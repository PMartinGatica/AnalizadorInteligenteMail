document.addEventListener('DOMContentLoaded', () => {
    // Referencias a elementos DOM necesarios
    const searchForm = document.getElementById('searchForm');
    const asuntoInput = document.getElementById('asuntoInput');
    const fechaDesdeInput = document.getElementById('fechaDesdeInput');
    const fechaHastaInput = document.getElementById('fechaHastaInput');
    const estadoDiv = document.getElementById('estadoDiv');
    const resumenConsolidadoContainer = document.getElementById('resumenConsolidadoContainer');
    const resumenConsolidadoDiv = document.getElementById('resumenConsolidadoDiv');
    
    // Referencias para el chat del asistente
    const chatContainer = document.getElementById('chat-container');
    const chatInput = document.getElementById('chat-input');
    const sendMessageButton = document.getElementById('send-message');
    
    // Verificar que los elementos existan antes de usar
    if (!searchForm || !asuntoInput || !estadoDiv) {
        console.error('No se encontraron elementos DOM necesarios');
        return;
    }
    
    // Inicializar convertidor de Markdown si es necesario
    let markdownConverter;
    try {
        markdownConverter = new showdown.Converter({
            simplifiedAutoLink: true,
            strikethrough: true,
            tables: true,
            tasklists: true,
            openLinksInNewWindow: true
        });
    } catch (e) {
        console.error('Error al inicializar el convertidor de Markdown:', e);
        // Crear un convertidor simple como fallback
        markdownConverter = {
            makeHtml: (text) => {
                return text.replace(/\n/g, '<br>');
            }
        };
    }
    
    // Evento para manejar el envío del formulario de búsqueda
    searchForm.addEventListener('submit', async (event) => {
        // Esto es crucial para prevenir el comportamiento predeterminado
        event.preventDefault();
        console.log("Formulario enviado - evento prevenido");
        
        // Obtener valores del formulario
        const asunto = asuntoInput.value.trim();
        const fechaDesde = fechaDesdeInput.value;
        const fechaHasta = fechaHastaInput.value;
        
        console.log({ asunto, fechaDesde, fechaHasta });
        
        // Validaciones
        if (!asunto) {
            mostrarEstado("Por favor, ingresa un término de búsqueda para el asunto.", "error");
            return;
        }
        
        if (fechaDesde && !fechaHasta) {
            mostrarEstado("Por favor, ingresa una Fecha Hasta si ingresaste una Fecha Desde.", "error");
            return;
        }
        if (!fechaDesde && fechaHasta) {
            mostrarEstado("Por favor, ingresa una Fecha Desde si ingresaste una Fecha Hasta.", "error");
            return;
        }
        if (fechaDesde && fechaHasta && new Date(fechaDesde) > new Date(fechaHasta)) {
            mostrarEstado("La Fecha Desde no puede ser posterior a la Fecha Hasta.", "error");
            return;
        }
        
        // Mostrar estado de procesamiento
        mostrarEstado("Procesando solicitud y generando informe... Esto puede tardar unos momentos.", "info", true);
        const submitButton = searchForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.disabled = true;
        
        if (resumenConsolidadoDiv) resumenConsolidadoDiv.innerHTML = '';
        if (resumenConsolidadoContainer) resumenConsolidadoContainer.style.display = 'none';
        
        try {
            // Construir URL de la API
            let apiUrl = `http://127.0.0.1:5000/api/buscar_correos?asunto=${encodeURIComponent(asunto)}`;
            if (fechaDesde) apiUrl += `&fecha_desde=${fechaDesde}`;
            if (fechaHasta) apiUrl += `&fecha_hasta=${fechaHasta}`;
            
            console.log("Llamando a la API:", apiUrl);
            
            // Realizar la petición al servidor
            const response = await fetch(apiUrl);
            
            // Manejar errores de la respuesta
            if (!response.ok) {
                let errorMsg = `Error del servidor: ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorMsg = errorData.error || errorData.mensaje || errorMsg;
                } catch (e) { /* No se pudo parsear JSON de error */ }
                throw new Error(errorMsg);
            }
            
            // Procesar respuesta exitosa
            const data = await response.json();
            console.log("Respuesta recibida:", data);
            
            if (data.error) {
                mostrarEstado(`Error: ${data.error}`, "error");
            } else if (data.resumen_consolidado) {
                if (resumenConsolidadoDiv && markdownConverter) {
                    resumenConsolidadoDiv.innerHTML = markdownConverter.makeHtml(data.resumen_consolidado);
                    if (resumenConsolidadoContainer) {
                        resumenConsolidadoContainer.style.display = 'block';
                    }
                    mostrarEstado("Informe generado exitosamente.", "success");
                    
                    // AÑADIR ESTE BLOQUE:
                    // Guardar los datos en el contexto del chat
                    chatContext.lastAnalysisData = {
                        tipo: "informe_correo",
                        asunto: asuntoInput.value,
                        fechas: {
                            desde: fechaDesdeInput.value,
                            hasta: fechaHastaInput.value
                        },
                        contenido: data.resumen_consolidado
                    };
                    
                    // Notificar que hay nuevos datos disponibles
                    const event = new CustomEvent('informeGenerado', {
                        detail: chatContext.lastAnalysisData
                    });
                    document.dispatchEvent(event);
                    console.log("Datos de informe compartidos con el asistente:", chatContext.lastAnalysisData);
                }
            } else if (data.mensaje_general) {
                mostrarEstado(data.mensaje_general, "info");
            } else {
                mostrarEstado("No se pudo generar el informe o no se encontraron datos.", "info");
            }
            
        } catch (error) {
            console.error('Error al buscar correos o generar informe:', error);
            mostrarEstado(`Error crítico: ${error.message}`, "error");
        } finally {
            // Habilitar el botón nuevamente
            if (submitButton) submitButton.disabled = false;
            // Quitar loader si existe
            const loader = estadoDiv ? estadoDiv.querySelector('.loader') : null;
            if (loader) loader.remove();
        }
    });
    
    // Función para mostrar mensajes de estado
    function mostrarEstado(mensaje, tipo = "info", mostrarLoader = false) {
        if (!estadoDiv) return;
        
        // Definir clases según el tipo de mensaje
        let claseAlerta = "alert ";
        let icono = "";
        
        switch (tipo) {
            case "error":
                claseAlerta += "alert-danger";
                icono = '<i class="fas fa-times-circle me-2"></i>';
                break;
            case "success":
                claseAlerta += "alert-success";
                icono = '<i class="fas fa-check-circle me-2"></i>';
                break;
            case "warning":
                claseAlerta += "alert-warning";
                icono = '<i class="fas fa-exclamation-triangle me-2"></i>';
                break;
            default:
                claseAlerta += "alert-info";
                icono = '<i class="fas fa-info-circle me-2"></i>';
        }
        
        // Crear HTML del mensaje
        let html = `<div class="${claseAlerta}">${icono}${mensaje}`;
        
        // Añadir loader si es necesario
        if (mostrarLoader) {
            html += '<div class="loader mt-2"></div>';
        }
        
        html += '</div>';
        
        // Mostrar el mensaje
        estadoDiv.innerHTML = html;
    }
    
    // ----- Código para el Asistente IA -----
    
    // Contexto del chat
    let chatContext = {
        lastAnalysisData: null,
        conversationHistory: []
    };
    
    // Evento para enviar mensaje al presionar Enter
    if (chatInput) {
        chatInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                sendMessage();
            }
        });
    }
    
    // Evento para enviar mensaje al hacer clic en el botón
    if (sendMessageButton) {
        sendMessageButton.addEventListener('click', sendMessage);
    }
    
    // Función para enviar mensaje
    function sendMessage() {
        if (!chatInput || !chatContainer) return;
        
        const userMessage = chatInput.value.trim();
        if (!userMessage) return;
        
        // Añadir mensaje del usuario al chat
        addMessageToChat('user', userMessage);
        chatInput.value = '';
        
        // Mostrar indicador de escritura
        const typingIndicator = addTypingIndicator();
        
        // Verificar si tenemos datos para analizar
        if (!chatContext.lastAnalysisData) {
            // Simular retraso para una experiencia más natural
            setTimeout(() => {
                typingIndicator.remove();
                addMessageToChat('assistant', "No tengo datos específicos para analizar. Por favor, primero genera un informe en la pestaña 'Analizador de Correos'.");
            }, 1000);
            return;
        }
        
        // Preparar la consulta para el asistente
        processChatQuery(userMessage, chatContext.lastAnalysisData, typingIndicator);
    }
    
    // Función para procesar la consulta con el backend
    async function processChatQuery(userMessage, analysisData, typingIndicator) {
        try {
            // Preparar datos para la consulta
            const queryData = {
                query: userMessage,
                context: chatContext.conversationHistory.slice(-4),
                analysisData: analysisData
            };
            
            // Hacer petición al backend
            const response = await fetch('http://127.0.0.1:5000/api/asistente_consulta', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(queryData)
            });
            
            // Eliminar indicador de escritura
            if (typingIndicator) typingIndicator.remove();
            
            if (!response.ok) {
                throw new Error(`Error del servidor: ${response.status}`);
            }
            
            // Procesar respuesta
            const data = await response.json();
            
            // Añadir respuesta del asistente al chat
            addMessageToChat('assistant', data.response);
            
            // Actualizar historial de conversación
            chatContext.conversationHistory.push({
                role: 'user',
                content: userMessage
            });
            chatContext.conversationHistory.push({
                role: 'assistant',
                content: data.response
            });
            
        } catch (error) {
            console.error('Error al procesar la consulta:', error);
            if (typingIndicator) typingIndicator.remove();
            addMessageToChat('assistant', `Lo siento, ha ocurrido un error: ${error.message}. ¿Podrías intentarlo de nuevo?`);
        }
    }
    
    // Función para añadir mensaje al chat
    function addMessageToChat(role, content) {
        if (!chatContainer) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = role === 'user' ? 'user-message' : 'assistant-message';
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        
        const icon = document.createElement('i');
        icon.className = role === 'user' ? 'fas fa-user' : 'fas fa-robot';
        avatarDiv.appendChild(icon);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const paragraph = document.createElement('p');
        paragraph.innerHTML = role === 'assistant' && markdownConverter
            ? markdownConverter.makeHtml(content)
            : content;
        contentDiv.appendChild(paragraph);
        
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        
        chatContainer.appendChild(messageDiv);
        
        // Scroll al final del chat
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
    
    // Función para añadir indicador de escritura
    function addTypingIndicator() {
        if (!chatContainer) return document.createElement('div');
        
        const typingDiv = document.createElement('div');
        typingDiv.className = 'assistant-message message-typing';
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        
        const icon = document.createElement('i');
        icon.className = 'fas fa-robot';
        avatarDiv.appendChild(icon);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const indicatorDiv = document.createElement('div');
        indicatorDiv.className = 'typing-indicator';
        indicatorDiv.innerHTML = '<span></span><span></span><span></span>';
        
        contentDiv.appendChild(indicatorDiv);
        typingDiv.appendChild(avatarDiv);
        typingDiv.appendChild(contentDiv);
        
        chatContainer.appendChild(typingDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        
        return typingDiv;
    }
    
    // Evento para actualizar contexto cuando se genera un informe
    document.addEventListener('informeGenerado', (event) => {
        if (event.detail) {
            chatContext.lastAnalysisData = event.detail;
            console.log('Datos de informe actualizados en el contexto del chat', chatContext.lastAnalysisData);
        }
    });
});

