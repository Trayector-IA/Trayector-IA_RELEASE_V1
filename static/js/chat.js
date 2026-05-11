/**
 * chat.js — Trayector-IA Chat Interface
 * Handles the full conversation flow with the Flask API.
 */

(function () {
  'use strict';

  // ── Lucide SVG icons (inline, evita dependencia externa en runtime) ──
  const SVG_ICONS = {
    bot: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 186.66 138.03" fill="currentColor" aria-hidden="true"><path d="m186.66,67.44l-12.54,8.6v31.28c3.71,1.77,6.28,5.56,6.28,9.95,0,2.58-.89,4.95-2.37,6.83l5.01,8.67-9.1,5.25-4.56-7.9-4.56,7.9-9.1-5.25,5.01-8.67c-1.48-1.88-2.37-4.25-2.37-6.83,0-4.39,2.57-8.18,6.28-9.95v-24.77l-12.35,8.47L42.97,32.52l92.59,69.91.06,35.6-20.86-21.34-31.06,21.34L0,0l186.66,67.44Z"/></svg>`,
    user: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 1 0-16 0"/></svg>`,
    alertTriangle: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`,
    xCircle: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>`,
  };

  // ── DOM refs ──────────────────────────────────────────────────
  const messagesContainer = document.getElementById('messages-container');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  const progressBar = document.getElementById('progress-bar');
  const progressCurrent = document.getElementById('progress-current');
  const completionBanner = document.getElementById('completion-banner');
  const viewResultsBtn = document.getElementById('view-results-btn');
  const wordCountEl = document.getElementById('word-count');
  const resetBtn = document.getElementById('reset-btn');
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const orientadorLayout = document.getElementById('orientador-layout');

  // ── State ──────────────────────────────────────────────────────
  let totalPreguntas = window.TOTAL_PREGUNTAS || 10;
  let indicePregunta = 0;
  let chatActive = false;
  let isProcessing = false;

  // ── localStorage persistence ───────────────────────────────────
  // Guarda el historial visual del chat por usuario para que sobreviva
  // recargas de página. Las respuestas reales persisten en MongoDB.
  const STORAGE_TTL = 24 * 60 * 60 * 1000; // 24 horas en ms

  function storageKey() {
    return `trayectoria_chat_${window._USUARIO_ID || 'guest'}`;
  }

  /**
   * Serializa los mensajes actuales (.message-row) a localStorage.
   * Se llama después de cada addMessage().
   */
  function persistChat() {
    if (!window._USUARIO_ID) return;
    try {
      const rows = Array.from(messagesContainer.querySelectorAll('.message-row'))
        .filter(el => !el.querySelector('.typing-indicator'))
        .map(el => el.outerHTML);
      localStorage.setItem(storageKey(), JSON.stringify({
        rows,
        indice: indicePregunta,
        ts: Date.now(),
      }));
    } catch (_) { /* cuota excedida o modo privado — ignorar */ }
  }

  /**
   * Reconstruye el historial desde localStorage.
   * Devuelve true si hubo datos válidos, false si no.
   */
  function restoreChat() {
    if (!window._USUARIO_ID) return false;
    try {
      const raw = localStorage.getItem(storageKey());
      if (!raw) return false;
      const saved = JSON.parse(raw);

      // Caducar datos con más de 24 horas
      if (Date.now() - saved.ts > STORAGE_TTL) {
        localStorage.removeItem(storageKey());
        return false;
      }
      if (!saved.rows || saved.rows.length === 0) return false;

      saved.rows.forEach(html => {
        const tmp = document.createElement('div');
        tmp.innerHTML = html;
        if (tmp.firstElementChild) messagesContainer.appendChild(tmp.firstElementChild);
      });

      indicePregunta = saved.indice || 0;
      updateProgress(indicePregunta);
      scrollToBottom();
      return true;
    } catch (_) {
      return false;
    }
  }

  /** Elimina el historial local del usuario (al completar o reiniciar). */
  function clearPersistedChat() {
    try { localStorage.removeItem(storageKey()); } catch (_) {}
  }

  // ── Init ───────────────────────────────────────────────────────
  function init() {
    disableInput(true);

    // Si el modal no existe (porque ya inició sesión), arrancamos el test
    if (!document.getElementById('modal-acceso')) {
      startSession();
    }
  }

  window.validarAcceso = async function () {
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
        body: JSON.stringify({ usuario_id: usuarioId, password: password })
      });

      const data = await response.json();

      if (data.success) {
        // Exponer el ID al módulo para que persistChat() use la clave correcta
        window._USUARIO_ID = usuarioId;
        document.getElementById('modal-acceso').style.display = 'none';

        if (data.rol === 'estudiante') {
          await startSession();
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
      const res = await fetch('/api/start', {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({})
      });

      const data = await res.json();

      if (data.success) {
        totalPreguntas = data.total_preguntas || window.TOTAL_PREGUNTAS || 10;

        if (data.reanudado) {
          // ── Sesión reanudada ────────────────────────────────────
          // Primero intentar restaurar el historial visual desde localStorage.
          // Si está disponible, el usuario ve exactamente donde lo dejó.
          const restored = restoreChat();

          if (!restored) {
            // Sin localStorage (otro dispositivo, modo privado, etc.):
            // mostramos el mensaje de reanudación que preparó el backend,
            // que incluye la pregunta actual en negritas.
            addMessage('bot', formatMarkdown(data.message));
          }

          // El backend es la fuente de verdad del índice.
          indicePregunta = data.pregunta_actual || 0;
          updateProgress(indicePregunta);

        } else {
          // ── Sesión nueva ────────────────────────────────────────
          // Limpiar cualquier estado anterior residual.
          clearPersistedChat();
          // 'top': el saludo puede ser largo; mostrar el comienzo.
          addMessage('bot', formatMarkdown(data.message), 'top');
          updateProgress(0);
        }

        chatActive = true;
        disableInput(false);

      } else {
        // Backend rechazó al usuario (ej. "ya completó la prueba")
        alert(data.error);
        window.location.href = '/';
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
      const res = await fetch('/api/answer', {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ respuesta: text }),
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
      const res = await fetch('/api/result', { method: 'POST', headers: jsonHeaders() });
      const data = await res.json();
      removeTyping(typingId);

      const payload = data.resultado || data;

      if (payload.error) {
        addError(payload.explicacion);

        const row = document.createElement('div');
        row.style.textAlign = 'center';
        row.style.marginTop = '15px';
        row.innerHTML = `<button onclick="window.location.reload()" style="padding: 10px 20px; background-color: #dc3545; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">Reintentar Test</button>`;
        messagesContainer.appendChild(row);
        scrollToBottom();

      } else if (data.success || payload.carrera_recomendada) {
        // Test completado con éxito: limpiar persistencia local
        clearPersistedChat();
        showCompletionBanner();
      } else {
        addError('No se pudo procesar el análisis. ' + (data.error || ''));
      }
    } catch (err) {
      removeTyping(typingId);
      addError('Error de comunicación con el servidor al obtener resultados.');
      console.error(err);
    }
  }

  // ── UI helpers ─────────────────────────────────────────────────

  // scrollToStart: muestra el inicio del contenedor (primer mensaje)
  // scrollToBottom: muestra el mensaje más reciente
  // El parámetro scroll='top' se usa para el saludo inicial, que puede ser
  // muy largo — scrollToBottom lo ocultaría dejando visible solo el final.
  function addMessage(role, html, scroll = 'bottom') {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const avatar = document.createElement('div');
    avatar.className = `msg-avatar ${role === 'bot' ? 'ai-av' : 'user-av'}`;
    avatar.innerHTML = role === 'bot' ? SVG_ICONS.bot : SVG_ICONS.user;

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = html;

    row.appendChild(avatar);
    row.appendChild(bubble);
    messagesContainer.appendChild(row);

    // Persistir después de cada mensaje para no perder nada
    persistChat();

    if (scroll === 'top') {
      setTimeout(() => { messagesContainer.scrollTop = 0; }, 50);
    } else {
      scrollToBottom();
    }
  }

  function addWarning(text) {
    const el = document.createElement('div');
    el.className = 'msg-warning';
    el.innerHTML = `<span>${SVG_ICONS.alertTriangle}</span><span>${formatMarkdown(text)}</span>`;
    messagesContainer.appendChild(el);
    scrollToBottom();
  }

  function addError(text) {
    const el = document.createElement('div');
    el.className = 'msg-warning';
    el.innerHTML = `<span>${SVG_ICONS.xCircle}</span><span>${formatMarkdown(text)}</span>`;
    messagesContainer.appendChild(el);
    scrollToBottom();
  }

  function addTyping() {
    const id = 'typing-' + Date.now();
    const row = document.createElement('div');
    row.className = 'message-row bot';
    row.id = id;

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar ai-av';
    avatar.innerHTML = SVG_ICONS.bot;

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
    if (progressBar) progressBar.style.width = pct + '%';
    if (progressCurrent) progressCurrent.textContent = current;

    // Update question dots
    for (let i = 0; i < totalPreguntas; i++) {
      const dot = document.getElementById(`q-dot-${i}`);
      if (!dot) continue;
      dot.classList.remove('done', 'active');
      if (i < current) dot.classList.add('done');
      else if (i === current) dot.classList.add('active');
    }

    // Update step items
    document.querySelectorAll('.step-item').forEach((el, idx) => {
      el.classList.remove('done', 'active');
      if (idx < current) el.classList.add('done');
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
    sendBtn.disabled = disabled;
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
    wordCountEl.className = 'wc-number ' + (words >= 10 ? 'ok' : 'warn');
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
      clearPersistedChat(); // limpiar historial local antes de reiniciar
      await fetch('/api/reset', { method: 'POST', headers: jsonHeaders() });
      window.location.reload();
    });
  }

  if (sidebarToggle && orientadorLayout) {
    sidebarToggle.addEventListener('click', () => {
      const isCollapsed = orientadorLayout.classList.toggle('sidebar-collapsed');
      sidebarToggle.setAttribute(
        'aria-label',
        isCollapsed ? 'Mostrar panel de progreso' : 'Ocultar panel de progreso'
      );
      sidebarToggle.setAttribute(
        'title',
        isCollapsed ? 'Mostrar panel de progreso' : 'Ocultar panel de progreso'
      );
    });
  }

if (viewResultsBtn) {
    viewResultsBtn.addEventListener('click', () => {
      // Redirigimos con la bandera de "finalizado" para mostrar el agradecimiento
      window.location.href = '/resultados?finalizado=true';
    });
  }

  // ── Bootstrap ──────────────────────────────────────────────────
  init();

})();
