/**
 * chat.js — Trayector-IA Chat Interface
 * Handles the full conversation flow with the Flask API.
 */

(function () {
  'use strict';

  // ── DOM refs ──────────────────────────────────────────────────
  const messagesContainer = document.getElementById('messages-container');
  const chatInput         = document.getElementById('chat-input');
  const sendBtn           = document.getElementById('send-btn');
  const progressBar       = document.getElementById('progress-bar');
  const progressCurrent   = document.getElementById('progress-current');
  const completionBanner  = document.getElementById('completion-banner');
  const viewResultsBtn    = document.getElementById('view-results-btn');
  const wordCountEl       = document.getElementById('word-count');
  const resetBtn          = document.getElementById('reset-btn');

  // ── State ──────────────────────────────────────────────────────
  let totalPreguntas  = window.TOTAL_PREGUNTAS || 10;
  let indicePregunta  = 0;
  let chatActive      = false;
  let isProcessing    = false;

  // ── Init ───────────────────────────────────────────────────────
function init() {
    disableInput(true);
    
    // Si el modal no existe (porque ya inició sesión), arrancamos el test
    if (!document.getElementById('modal-acceso')) {
        startSession();
    }
  }



window.validarAcceso = async function() {
    console.log("1. Botón presionado. Iniciando validación...");
    
    const inputCodigo = document.getElementById('input-codigo');
    const inputPassword = document.getElementById('input-password');
    
    if (!inputCodigo || !inputPassword) {
        console.error("ERROR FATAL: No encuentro los cuadros de texto.");
        return;
    }

    const usuarioId = inputCodigo.value.trim();
    const password = inputPassword.value.trim();

    if (!usuarioId) {
        alert("Por favor, ingresa tu código.");
        return;
    }

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                usuario_id: usuarioId,
                password: password 
            })
        });

        const data = await response.json();

        if (data.success) {
            document.getElementById('modal-acceso').style.display = 'none';
            
            if (data.rol === 'estudiante') {
                console.log("Acceso concedido. Iniciando sesión...");
                await startSession(); // Aquí estaba el error del nombre
            } else if (data.rol === 'admin') {
                alert("Bienvenido, Administrador.");
            }
        } else {
            alert(data.error);
        }
    } catch (error) {
        console.error("Error crítico en la petición Fetch:", error);
        alert("Ocurrió un error de red o de servidor.");
    }
};
  // ── API calls ──────────────────────────────────────────────────

async function startSession() {
    try {
      // El cuerpo vacío {} evita que Flask lance el Error 400
      const res  = await fetch('/api/start', { 
          method: 'POST', 
          headers: jsonHeaders(),
          body: JSON.stringify({}) 
      });
      
      const data = await res.json();

      if (data.success) {
        totalPreguntas = data.total_preguntas || window.TOTAL_PREGUNTAS || 10;
        indicePregunta = data.pregunta_actual || 0;
        addMessage('bot', formatMarkdown(data.message));
        updateProgress(indicePregunta);
        chatActive = true;
        disableInput(false);
      } else {
        // Si el backend lo rechaza (ej. "Este usuario ya completó la prueba")
        alert(data.error);
        window.location.href = '/'; // Lo regresamos a la página principal
      }
    } catch (err) {
      addError('Error de conexión. Verifica que el servidor esté activo.');
      console.error("Detalle del error:", err);
    }
  }

  async function sendAnswer(text) {
    if (isProcessing) return;
    isProcessing = true;
    disableInput(true);

    // Show user message
    addMessage('user', text);
    chatInput.value = '';
    updateWordCount();

    // Show typing indicator
    const typingId = addTyping();

    try {
      const res  = await fetch('/api/answer', {
        method:  'POST',
        headers: jsonHeaders(),
        body:    JSON.stringify({ respuesta: text }),
      });
      const data = await res.json();

      removeTyping(typingId);

      if (!data.success) {
        addError(data.error || 'Ocurrió un error al procesar tu respuesta.');
        disableInput(false);
        isProcessing = false;
        return;
      }

      if (!data.es_valida) {
        addWarning(data.message);
        disableInput(false);
        isProcessing = false;
        return;
      }

      // Valid answer accepted
      addMessage('bot', formatMarkdown(data.message));
      indicePregunta = data.indice;
      updateProgress(indicePregunta);

      if (data.finalizado) {
        // Process results
        disableInput(true, true);
        await fetchResults();
      } else {
        disableInput(false);
      }
    } catch (err) {
      removeTyping(typingId);
      addError('Error de red. Inténtalo de nuevo.');
      disableInput(false);
      console.error(err);
    }

    isProcessing = false;
  }

  async function fetchResults() {
    const typingId = addTyping();
    try {
      const res  = await fetch('/api/result', { method: 'POST', headers: jsonHeaders() });
      const data = await res.json();
      removeTyping(typingId);

      if (data.success) {
        showCompletionBanner();
      } else {
        addError('No se pudo obtener el resultado. ' + (data.error || ''));
      }
    } catch (err) {
      removeTyping(typingId);
      addError('Error al obtener resultados.');
      console.error(err);
    }
  }

  // ── UI helpers ─────────────────────────────────────────────────

  function addMessage(role, html) {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const avatar = document.createElement('div');
    avatar.className = `msg-avatar ${role === 'bot' ? 'ai-av' : 'user-av'}`;
    avatar.textContent = role === 'bot' ? '🤖' : '👤';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = html;

    row.appendChild(avatar);
    row.appendChild(bubble);
    messagesContainer.appendChild(row);
    scrollToBottom();
  }

  function addWarning(text) {
    const el = document.createElement('div');
    el.className = 'msg-warning';
    el.innerHTML = `<span>⚠️</span><span>${formatMarkdown(text)}</span>`;
    messagesContainer.appendChild(el);
    scrollToBottom();
  }

  function addError(text) {
    addWarning('❌ ' + text);
  }

  function addTyping() {
    const id  = 'typing-' + Date.now();
    const row = document.createElement('div');
    row.className = 'message-row bot';
    row.id        = id;

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar ai-av';
    avatar.textContent = '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = `<div class="typing-indicator"><span></span><span></span><span></span></div>`;

    row.appendChild(avatar);
    row.appendChild(bubble);
    messagesContainer.appendChild(row);
    scrollToBottom();
    return id;
  }

  function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function updateProgress(current) {
    const pct = (current / totalPreguntas) * 100;
    if (progressBar)     progressBar.style.width = pct + '%';
    if (progressCurrent) progressCurrent.textContent = current;

    // Update question dots
    for (let i = 0; i < totalPreguntas; i++) {
      const dot = document.getElementById(`q-dot-${i}`);
      if (!dot) continue;
      dot.classList.remove('done', 'active');
      if (i < current)      dot.classList.add('done');
      else if (i === current) dot.classList.add('active');
    }

    // Update step items
    document.querySelectorAll('.step-item').forEach((el, idx) => {
      el.classList.remove('done', 'active');
      if (idx < current)      el.classList.add('done');
      else if (idx === current) el.classList.add('active');
    });
  }

  function showCompletionBanner() {
    if (completionBanner) completionBanner.classList.add('show');
    chatInput.closest('.chat-input-area').style.display = 'none';
    scrollToBottom();
  }

  function disableInput(disabled, hide = false) {
    if (!chatInput || !sendBtn) return;
    chatInput.disabled = disabled;
    sendBtn.disabled   = disabled;
    if (hide) chatInput.placeholder = 'Entrevista finalizada.';
  }

  function scrollToBottom() {
    setTimeout(() => {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }, 50);
  }

  function updateWordCount() {
    if (!chatInput || !wordCountEl) return;
    const words = chatInput.value.trim() ? chatInput.value.trim().split(/\s+/).length : 0;
    wordCountEl.textContent = words;
    wordCountEl.className   = 'wc-number ' + (words >= 10 ? 'ok' : 'warn');
  }

  // ── Minimal markdown → HTML ────────────────────────────────────
  function formatMarkdown(text) {
    if (!text) return '';
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n\n/g, '</p><p>')
      .replace(/\n/g, '<br>')
      .replace(/^/, '<p>')
      .replace(/$/, '</p>');
  }

  function jsonHeaders() {
    return { 'Content-Type': 'application/json' };
  }

  // ── Event Listeners ────────────────────────────────────────────

  if (sendBtn) {
    sendBtn.addEventListener('click', () => {
      const text = chatInput.value.trim();
      if (text && chatActive && !isProcessing) sendAnswer(text);
    });
  }

  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (text && chatActive && !isProcessing) sendAnswer(text);
      }
    });

    chatInput.addEventListener('input', () => {
      updateWordCount();
      // Auto-resize
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', async () => {
      await fetch('/api/reset', { method: 'POST', headers: jsonHeaders() });
      window.location.reload();
    });
  }

  if (viewResultsBtn) {
    viewResultsBtn.addEventListener('click', () => {
      window.location.href = '/resultados';
    });
  }

  // ── Bootstrap ──────────────────────────────────────────────────
  init();

})();
