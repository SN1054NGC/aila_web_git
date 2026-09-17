(function () {
  'use strict';

  var NL = String.fromCharCode(10);      // перевод строки
  var BT = String.fromCharCode(96);      // обратный апостроф

  // ------------------------------------------------------------------ утилиты
  function $(id) { return document.getElementById(id); }
  function now() { return (window.performance && performance.now) ? performance.now() : Date.now(); }

  function toast(text, kind) {
    var box = $('toasts');
    if (!box) return;
    var node = document.createElement('div');
    node.className = 'toast ' + (kind || '');
    node.textContent = text;
    box.appendChild(node);
    setTimeout(function () { node.remove(); }, kind === 'err' ? 9000 : 4500);
  }

  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // Мини-Markdown: сначала экранируем, потом добавляем только свои теги.
  function render(text) {
    var html = esc(text);
    html = html.replace(new RegExp('[*][*]([^*]+)[*][*]', 'g'), '<strong>$1</strong>');
    html = html.replace(new RegExp('(^|[^*])[*]([^*]{1,400})[*]', 'g'), '$1<em>$2</em>');
    html = html.replace(new RegExp(BT + '([^' + BT + ']+)' + BT, 'g'), '<code>$1</code>');
    html = html.replace(new RegExp('^[ ]*[-•][ ]+', 'gm'), '&bull; ');
    html = html.replace(new RegExp(NL + NL + '+', 'g'), '</p><p>');
    html = html.replace(new RegExp(NL, 'g'), '<br>');
    return '<p>' + html + '</p>';
  }

  function fmtTime(ms) { return (ms / 1000).toFixed(1) + ' с'; }

  // Живой счётчик ожидания: на CPU первый токен идёт долго, пользователь должен видеть прогресс.
  function startThinkTimer() {
    stopThinkTimer();
    var t0 = Date.now();
    S.thinkTimer = setInterval(function () {
      if (!S.bubble || !S.bubble.isConnected) return;
      var sec = Math.round((Date.now() - t0) / 1000);
      S.bubble.innerHTML = render('Айла думает… ' + sec + ' с.' +
        NL + 'На CPU первый ответ может занять до минуты — это нормально.');
    }, 1000);
  }

  function stopThinkTimer() {
    if (S.thinkTimer) { clearInterval(S.thinkTimer); S.thinkTimer = null; }
  }

  // ------------------------------------------------------------------ состояние
  var S = {
    ws: null,
    connected: false,
    waiting: false,
    streaming: false,
    bubble: null,
    raw: '',
    sources: [],
    lastAnswer: '',
    reconnectDelay: 800,
    mic: { stream: null, ctx: null, node: null, src: null, analyser: null, active: false,
           lastLoud: 0, spoke: false, timer: null, noiseFloor: 0, serverOn: false },
    sttReady: null,
    ttsReady: null,
    thinkTimer: null,
    audio: { ctx: null, sources: [], nextTime: 0, playing: false },
    settings: { tts: true, rag: true, lang: 'auto', rate: 1.0, sttLang: 'ru', autoSend: true,
                vad: true, pause: 1.8, pauseScale: 1.0, voice: '' }
  };

  function loadSettings() {
    try {
      var saved = JSON.parse(localStorage.getItem('aila.settings') || '{}');
      Object.keys(S.settings).forEach(function (key) {
        if (saved[key] !== undefined) S.settings[key] = saved[key];
      });
    } catch (e) { /* пустой кэш настроек */ }
  }
  function saveSettings() {
    try { localStorage.setItem('aila.settings', JSON.stringify(S.settings)); } catch (e) { /* ignore */ }
  }

  // ------------------------------------------------------------------ WebSocket
  function wsUrl() {
    return (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
  }

  function connect() {
    try { S.ws = new WebSocket(wsUrl()); } catch (e) { setTimeout(connect, 1500); return; }

    S.ws.onopen = function () {
      S.connected = true;
      S.reconnectDelay = 800;
      setPill('pillWs', true, 'соединение');
      // сообщаем сохранённые настройки, в том числе паузу между фразами
      send({ type: 'set', pause_scale: S.settings.pauseScale, tts: S.settings.tts,
             rag: S.settings.rag, lang: S.settings.lang, voice: S.settings.voice });
      loadVoices();
      send({ type: 'status' });
      refreshStatus();
    };
    S.ws.onclose = function () {
      S.connected = false;
      setPill('pillWs', false, 'нет связи');
      setTimeout(connect, S.reconnectDelay);
      S.reconnectDelay = Math.min(8000, S.reconnectDelay * 1.6);
    };
    S.ws.onerror = function () { setPill('pillWs', false, 'ошибка связи'); };
    S.ws.onmessage = function (event) {
      var data;
      try { data = JSON.parse(event.data); } catch (e) { return; }
      handle(data);
    };
  }

  function send(payload) {
    if (!S.ws || S.ws.readyState !== WebSocket.OPEN) return false;
    S.ws.send(JSON.stringify(payload));
    return true;
  }

  function sendPcm(buffer) {
    if (!S.ws || S.ws.readyState !== WebSocket.OPEN) return;
    S.ws.send(buffer);
  }

  // ------------------------------------------------------------------ сообщения сервера
  function handle(d) {
    switch (d.type) {
      case 'hello':
        if (d.config) applyConfig(d.config);
        if (d.status) applyStatus(d.status);
        break;
      case 'status':
        applyStatus(d);
        break;
      case 'start':
        S.waiting = true;
        S.streaming = true;
        S.raw = '';
        S.sources = [];
        S.bubble = addMessage('assistant', 'Айла смотрит в документацию…');
        if (S.bubble) S.bubble.classList.add('cursor');
        startThinkTimer();
        setBusy(true);
        break;
      case 'sources':
        S.sources = d.items || [];
        break;
      case 'delta':
        if (S.thinkTimer) stopThinkTimer();
        if (!S.bubble) S.bubble = addMessage('assistant', '');
        S.raw += d.text || '';
        renderBubble(S.bubble, S.raw, true);
        maybeScroll();
        break;
      case 'done':
        stopThinkTimer();
        S.streaming = false;
        S.waiting = false;
        S.lastAnswer = d.text || S.raw;
        if (S.bubble) {
          renderBubble(S.bubble, S.lastAnswer || '(пустой ответ)', false);
          if (S.sources.length) renderSources(S.bubble, S.sources);
        }
        setBusy(false);
        break;
      case 'stopped':
        stopThinkTimer();
        S.streaming = false;
        S.waiting = false;
        if (S.bubble && S.raw) renderBubble(S.bubble, S.raw, false);
        else if (S.bubble && S.bubble.parentNode) S.bubble.parentNode.remove();
        S.bubble = null;
        S.raw = '';
        setBusy(false);
        break;
      case 'error':
        stopThinkTimer();
        if (S.mic.active && /микро|распознав|vosk/i.test(d.text || '')) stopMic(false);
        addMessage('system', d.text || 'ошибка');
        toast(d.text || 'ошибка', 'err');
        break;
      case 'cleared':
        clearChat();
        break;
      case 'tts_chunk':
        playWav(d.wav);
        break;
      case 'tts_end':
        flushAudio();
        break;
      case 'tts_stop':
        stopAudio();
        break;
      case 'stt_state':
        S.mic.serverOn = (d.state === 'on');
        if (d.state === 'off' && S.mic.active) stopMic(false);
        break;
      case 'stt_partial':
        $('recLive').textContent = d.text || '';
        S.mic.spoke = true;
        break;
      case 'stt_final':
        onTranscript(d.text || '');
        break;
    }
  }

  function applyConfig(cfg) {
    if (cfg.tts_speed) {
      S.settings.rate = Number(cfg.tts_speed);
      $('rate').value = String(cfg.tts_speed);
      $('rateVal').textContent = S.settings.rate.toFixed(1);
    }
  }

  // ------------------------------------------------------------------ статус
  function setPill(id, ok, text, warn) {
    var node = $(id);
    if (!node) return;
    node.className = 'pill ' + (ok ? 'on' : (warn ? 'warn' : 'off'));
    node.innerHTML = '<i></i>' + esc(text);
  }

  function applyStatus(st) {
    if (!st) return;
    if (st.llm !== undefined) {
      var llmReady = (typeof st.llm === 'object') ? !!st.llm.ready : !!st.llm;
      setPill('pillLlm', llmReady, 'LLM');
      $('stLlm').textContent = llmReady ? 'готов' : 'нет связи';
    }
    if (st.rag) {
      setPill('pillRag', !!st.rag.ready, 'Поиск');
      $('stRag').textContent = st.rag.ready ? (st.rag.mode + ', ' + st.rag.docs + ' фр.') : 'пусто';
      $('ragSource').textContent = st.rag.source || '—';
      $('ragDocs').textContent = String(st.rag.docs || 0);
      $('ragSheets').textContent = (st.rag.sheets && st.rag.sheets.length) ? st.rag.sheets.join(', ') : '—';
    }
    if (st.tts) {
      S.ttsReady = !!st.tts.ready;
      setPill('pillTts', S.ttsReady, 'TTS');
      $('stTts').textContent = S.ttsReady
        ? (st.tts.engine + ', ' + Math.round((st.tts.sample_rate || 0) / 1000) + ' кГц')
        : 'нет моделей';
      $('ttsInfo').textContent = S.ttsReady
        ? ('движок: ' + st.tts.engine + ', ударений в словаре: ' + st.tts.accents)
        : 'TTS не готов. Один раз: python tools/fetch_models.py --only silero';
    }
    if (st.stt) {
      S.sttReady = !!st.stt.ready;
      setPill('pillStt', S.sttReady, 'Микрофон');
      $('stStt').textContent = S.sttReady ? ('vosk: ' + st.stt.langs.join(', ')) : 'нет моделей';
      $('sttInfo').textContent = S.sttReady
        ? ('движок: ' + st.stt.engine + ', языки: ' + st.stt.langs.join(', '))
        : sttHint();
    }
    var hints = [];
    if (st.llm && st.llm.error && !st.llm.ready) hints.push('LLM: ' + st.llm.error);
    if (st.rag && st.rag.error) hints.push('Поиск: ' + st.rag.error);
    $('stateHint').textContent = hints.join(' | ');
  }

  // Список голосов текущего движка (Silero: baya, aidar, kseniya…; Piper: имена голосов)
  function loadVoices() {
    fetch('/api/voices').then(function (r) { return r.json(); }).then(function (data) {
      var sel = $('voiceSel');
      if (!sel) return;
      var current = S.settings.voice;
      sel.innerHTML = '<option value="">— по умолчанию (' + esc(data.engine || '?') + ') —</option>';
      (data.ru || []).concat(data.en || []).forEach(function (item) {
        var opt = document.createElement('option');
        opt.value = item.id;
        opt.textContent = item.label;
        sel.appendChild(opt);
      });
      sel.value = current;
    }).catch(function () { /* движок ещё не готов */ });
  }

  function refreshStatus() {
    fetch('/api/status').then(function (r) { return r.json(); }).then(function (data) {
      applyStatus(data);
    }).catch(function () { setPill('pillWs', false, 'нет связи'); });
  }

  // ------------------------------------------------------------------ чат
  function chatBox() { return $('chat'); }

  function nearBottom() {
    var box = chatBox();
    return box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  }

  function maybeScroll() {
    var box = chatBox();
    if (nearBottom()) box.scrollTop = box.scrollHeight;
    $('jumpBtn').hidden = nearBottom();
  }

  function addMessage(role, text) {
    var wrap = document.createElement('div');
    wrap.className = 'msg ' + role;
    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    if (text) bubble.innerHTML = render(text);
    wrap.appendChild(bubble);
    chatBox().appendChild(wrap);
    chatBox().scrollTop = chatBox().scrollHeight;
    return bubble;
  }

  function renderBubble(bubble, text, streaming) {
    bubble.innerHTML = render(text);
    if (streaming) bubble.classList.add('cursor');
    else bubble.classList.remove('cursor');
  }

  function renderSources(bubble, items) {
    var box = document.createElement('div');
    box.className = 'sources';
    var title = document.createElement('div');
    title.className = 'sources-title';
    title.textContent = 'Источники (' + items.length + ') — нажмите, чтобы раскрыть';
    box.appendChild(title);
    var chips = document.createElement('div');
    chips.className = 'chips';
    var body = document.createElement('div');
    body.className = 'chip-body';
    body.hidden = true;

    items.forEach(function (item, i) {
      var parts = [];
      if (item.sheet) parts.push('лист ' + item.sheet);
      if (item.row) parts.push('стр. ' + item.row);
      if (item.code) parts.push('код ' + item.code);
      var chip = document.createElement('span');
      chip.className = 'chip';
      chip.textContent = (i + 1) + '. ' + (parts.length ? parts.join(', ') : 'сводка') +
        ' · ' + Math.round((item.score || 0) * 100) + '%';
      chip.title = item.equipment || '';
      chip.onclick = function () {
        var head = '[' + (i + 1) + '] ' + (parts.join(', ') || 'сводка') +
          (item.equipment ? NL + item.equipment : '') + NL + NL;
        body.textContent = head + (item.preview || '');
        body.hidden = false;
      };
      chips.appendChild(chip);
    });
    box.appendChild(chips);
    box.appendChild(body);
    bubble.appendChild(box);
  }

  function clearChat() {
    chatBox().innerHTML = '';
    addMessage('system', 'История очищена');
    S.bubble = null;
    S.raw = '';
    S.sources = [];
  }

  // Кнопка остановки видна и во время генерации, и пока играет озвучка;
  // в режиме озвучки она подписана иначе и подсвечена.
  function updateControls() {
    var busy = !!(S.waiting || S.streaming);
    var speaking = !!S.audio.playing;
    var btn = $('stopBtn');
    if (btn) {
      btn.hidden = !(busy || speaking);
      btn.textContent = busy ? 'Остановить' : 'Стоп озвучки';
      btn.classList.toggle('stop-speak', !busy && speaking);
      btn.title = busy ? 'Прервать ответ (Esc)' : 'Остановить воспроизведение (Esc)';
    }
    var state = $('speakState');
    if (state) state.hidden = !speaking;
  }

  function setBusy(busy) {
    $('sendBtn').disabled = busy;
    updateControls();
  }

  // ------------------------------------------------------------------ отправка
  function sendMessage() {
    var input = $('input');
    var text = (input.value || '').trim();
    if (!text) return;
    stopAudio(true);              // новое сообщение прерывает озвучку предыдущего
    input.value = '';
    autosize();
    addMessage('user', text);
    send({ type: 'chat', text: text, tts: S.settings.tts, rag: S.settings.rag, lang: S.settings.lang });
  }

  function stopAll() {
    send({ type: 'stop' });
    stopAudio();
    if (S.mic.active) stopMic(false);
    S.streaming = false;
    setBusy(false);
  }

  // ------------------------------------------------------------------ звук
  function audioCtx() {
    if (!S.audio.ctx) {
      var Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return null;
      S.audio.ctx = new Ctor();
    }
    if (S.audio.ctx.state === 'suspended') S.audio.ctx.resume();
    return S.audio.ctx;
  }

  function b64ToBuffer(b64) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
  }

  // Плавное воспроизведение: фрагменты стыкуются без пауз и щелчков.
  function playWav(b64) {
    if (!b64) return;
    var ctx = audioCtx();
    if (!ctx) return;
    var rate = S.settings.rate || 1;
    ctx.decodeAudioData(b64ToBuffer(b64), function (decoded) {
      var src = ctx.createBufferSource();
      src.buffer = decoded;
      src.playbackRate.value = rate;
      src.connect(ctx.destination);
      var start = Math.max(ctx.currentTime + 0.06, S.audio.nextTime);
      src.start(start);
      S.audio.nextTime = start + decoded.duration / rate;
      S.audio.sources.push(src);
      src.onended = function () {
        S.audio.sources = S.audio.sources.filter(function (s) { return s !== src; });
        if (!S.audio.sources.length) {
          S.audio.playing = false;
          S.audio.nextTime = 0;
          updateControls();
        }
      };
      S.audio.playing = true;
      updateControls();
    }, function () { /* битый фрагмент пропускаем */ });
  }

  function flushAudio() { /* очередь выстроена заранее: делать ничего не нужно */ }

  // Немедленно прекратить воспроизведение (и попросить сервер не синтезировать дальше)
  function stopAudio(notifyServer) {
    var wasPlaying = S.audio.playing || S.audio.sources.length > 0;
    S.audio.sources.forEach(function (src) { try { src.stop(); } catch (e) { /* ignore */ } });
    S.audio.sources = [];
    S.audio.nextTime = 0;
    S.audio.playing = false;
    updateControls();
    if (notifyServer && wasPlaying) send({ type: 'tts_stop' });
    return wasPlaying;
  }

  // ------------------------------------------------------------------ визуализация голоса
  // Идеи из visual_sound.html (спектр по полосам, бас/мид/верх, рябь), но без Three.js и CDN:
  // чистый Canvas 2D в палитре интерфейса, ~30 кадров/с, только во время записи.
  var VIZ = { raf: null, freq: null, wave: null, smooth: [], peak: [], demo: false, last: 0 };

  function vizResize() {
    var canvas = $('viz');
    if (!canvas) return;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.max(1, Math.round((canvas.clientWidth || 560) * dpr));
    canvas.height = Math.max(1, Math.round((canvas.clientHeight || 62) * dpr));
  }

  function vizStart() {
    var canvas = $('viz');
    if (!canvas || !S.mic.analyser) return;
    vizResize();
    if (!VIZ.freq || VIZ.freq.length !== S.mic.analyser.frequencyBinCount) {
      VIZ.freq = new Uint8Array(S.mic.analyser.frequencyBinCount);
      VIZ.wave = new Uint8Array(S.mic.analyser.fftSize);
      VIZ.smooth = [];
      VIZ.peak = [];
    }
    if (VIZ.raf) return;
    VIZ.last = 0;
    var step = function (ts) {
      if (!S.mic.active) { VIZ.raf = null; return; }
      VIZ.raf = requestAnimationFrame(step);
      if (ts - VIZ.last < 33) return;          // ~30 к/с: на слабом CPU этого достаточно
      VIZ.last = ts;
      vizDraw();
    };
    VIZ.raf = requestAnimationFrame(step);
  }

  function vizStop() {
    if (VIZ.raf) { cancelAnimationFrame(VIZ.raf); VIZ.raf = null; }
    var canvas = $('viz');
    if (canvas) canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    document.documentElement.style.setProperty('--bass', '0');
  }

  function roundBar(c, x, y, w, h, r) {
    r = Math.max(0, Math.min(r, w / 2, h / 2));
    c.beginPath();
    if (c.roundRect) { c.roundRect(x, y, w, h, r); c.fill(); return; }
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
    c.fill();
  }

  function vizDraw() {
    var canvas = $('viz');
    var analyser = S.mic.analyser;
    if (!canvas || !VIZ.freq) return;
    var c = canvas.getContext('2d');
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var W = canvas.width, H = canvas.height;
    c.clearRect(0, 0, W, H);

    if (analyser) {
      analyser.getByteFrequencyData(VIZ.freq);
      analyser.getByteTimeDomainData(VIZ.wave);
    }

    var bars = Math.max(18, Math.min(38, Math.round(W / (13 * dpr))));
    var bins = VIZ.freq.length;
    var maxBin = Math.max(24, Math.floor(bins * 0.28));   // речевые полосы до ~6 кГц
    var baseY = H * 0.63;
    var gap = Math.max(2, Math.round(3 * dpr));
    var bw = Math.max(1, (W - gap * (bars - 1)) / bars);

    var grad = c.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, '#8f6bff');
    grad.addColorStop(0.6, '#4da3ff');
    grad.addColorStop(1, 'rgba(77, 163, 255, .28)');

    var bass = 0, mid = 0, treble = 0;
    c.fillStyle = grad;
    for (var i = 0; i < bars; i++) {
      var t = bars > 1 ? i / (bars - 1) : 0;
      var bin = Math.floor(Math.pow(t, 1.7) * maxBin);
      var sum = 0, cnt = 0;
      for (var j = bin; j <= bin + 1 && j < bins; j++) { sum += VIZ.freq[j]; cnt++; }
      var value = Math.pow((sum / (cnt || 1)) / 255, 0.62);
      if (VIZ.smooth[i] === undefined) VIZ.smooth[i] = 0;
      VIZ.smooth[i] = VIZ.smooth[i] * 0.7 + value * 0.3;
      if (VIZ.peak[i] === undefined) VIZ.peak[i] = 0;
      VIZ.peak[i] = Math.max(VIZ.peak[i] * 0.93, VIZ.smooth[i]);   // шапки пиков держатся и опадают
      var amp = Math.pow(VIZ.smooth[i], 0.88);
      if (t < 0.22) bass += amp; else if (t < 0.6) mid += amp; else treble += amp;

      var h = Math.max(2 * dpr, amp * (H * 0.5));
      var x = i * (bw + gap);
      c.globalAlpha = 0.95;
      roundBar(c, x, baseY - h, bw, h, Math.min(bw / 2, 3 * dpr));
      c.globalAlpha = 0.22;                       // отражение — «рябь» из visual_sound.html
      roundBar(c, x, baseY + 2 * dpr, bw, h * 0.48, Math.min(bw / 2, 2 * dpr));
      c.globalAlpha = 0.55;                       // шапка пика
      c.fillStyle = '#cfe6ff';
      var py = baseY - Math.max(h, VIZ.peak[i] * (H * 0.5));
      roundBar(c, x, Math.max(0, py - 2 * dpr), bw, 2 * dpr, dpr);
      c.fillStyle = grad;
    }
    c.globalAlpha = 1;

    var n = VIZ.wave ? VIZ.wave.length : 0;
    if (n) {
      c.beginPath();
      for (var k = 0; k < W; k++) {
        var v = (VIZ.wave[Math.floor(k / W * (n - 1))] - 128) / 128;
        var y = baseY + v * (H * 0.22);
        if (k === 0) c.moveTo(k, y); else c.lineTo(k, y);
      }
      c.strokeStyle = 'rgba(205, 228, 255, .5)';
      c.lineWidth = Math.max(1, 1.3 * dpr);
      c.stroke();
    }

    // бас управляет свечением панели и аурой кнопки микрофона
    document.documentElement.style.setProperty('--bass', Math.min(1, bass * 1.9).toFixed(3));
  }

  // Синтетический спектр для проверки оформления без микрофона: ?demo=1
  function vizDemo() {
    VIZ.freq = new Uint8Array(512);
    VIZ.wave = new Uint8Array(1024);
    VIZ.smooth = [];
    VIZ.peak = [];
    VIZ.demo = true;
    var bar = $('recBar');
    bar.hidden = false;
    S.mic.active = true;
    vizResize();
    var t = 0;
    var step = function () {
      if (!VIZ.demo) { VIZ.raf = null; return; }
      VIZ.raf = requestAnimationFrame(step);
      t += 0.045;
      for (var i = 0; i < VIZ.freq.length; i++) {
        var env = Math.exp(-i / 85) * (1 - Math.exp(-i / 4));
        var v = Math.abs(Math.sin(t * 2.1 + i * 0.42) * 0.6 + Math.sin(t * 0.7 + i * 0.11) * 0.4);
        VIZ.freq[i] = Math.max(0, Math.min(255, 250 * env * Math.pow(v, 1.6) + 12 * Math.random() * env));
      }
      for (var k = 0; k < VIZ.wave.length; k++) {
        VIZ.wave[k] = 128 + 46 * Math.sin(t * 4 + k * 0.06) * Math.exp(-k / 2600);
      }
      vizDraw();
    };
    VIZ.raf = requestAnimationFrame(step);
  }

  function sttHint() {
    return 'Распознавание недоступно. Один раз: pip install vosk, затем ' +
      'python tools/fetch_models.py --only vosk';
  }

  async function startMic() {
    if (S.mic.active) return;
    stopAudio(true);              // микрофон прерывает озвучку — Айлу можно перебить
    // Если сервер уже сообщил, что распознавания нет, — не открываем микрофон зря.
    if (S.sttReady === false) {
      toast(sttHint(), 'err');
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast('Браузер не даёт доступ к микрофону (нужен Chrome/Edge/Firefox и адрес localhost)', 'err');
      return;
    }
    try {
      var stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      var Ctor = window.AudioContext || window.webkitAudioContext;
      var ctx = new Ctor();
      if (ctx.state === 'suspended') ctx.resume();
      await ctx.audioWorklet.addModule('/static/pcm-worklet.js');
      var src = ctx.createMediaStreamSource(stream);
      var node = new AudioWorkletNode(ctx, 'aila-pcm', { processorOptions: { targetRate: 16000 } });
      var sink = ctx.createGain();
      sink.gain.value = 0;
      src.connect(node);
      node.connect(sink);
      sink.connect(ctx.destination);

      // анализатор нужен только для красивой визуализации
      var analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.7;
      src.connect(analyser);

      S.mic.stream = stream;
      S.mic.ctx = ctx;
      S.mic.src = src;
      S.mic.node = node;
      S.mic.analyser = analyser;
      S.mic.active = true;
      S.mic.lastLoud = now();
      S.mic.spoke = false;
      S.mic.noiseFloor = 0;

      node.port.onmessage = function (event) {
        var buffer = event.data;
        if (!S.mic.active) return;
        sendPcm(buffer);
        var pcm = new Int16Array(buffer);
        var sum = 0;
        for (var i = 0; i < pcm.length; i++) {
          var v = pcm[i] / 32768;
          sum += v * v;
        }
        var rms = Math.sqrt(sum / (pcm.length || 1));
        // адаптивный порог: шумовая дорожка комнаты оценивается на ходу,
        // поэтому в тихой комнате микрофон не «схлопывается» сразу после включения
        S.mic.noiseFloor = S.mic.noiseFloor ? (S.mic.noiseFloor * 0.97 + rms * 0.03) : rms;
        var threshold = Math.max(0.012, S.mic.noiseFloor * 3);
        if (rms > threshold) {
          S.mic.lastLoud = now();
          S.mic.spoke = true;
        }
      };

      var bar = $('recBar');
      bar.hidden = false;
      bar.classList.remove('error');
      $('recTime').textContent = '0.0 с';
      $('recLive').textContent = '…';
      $('recHint').textContent = 'говорите, я слушаю';
      $('micBtn').classList.add('rec');
      var label = $('micLabel');
      if (label) label.textContent = 'Слушаю';
      vizStart();

      var t0 = now();
      var pauseMs = Math.max(300, S.settings.pause * 1000);
      S.mic.timer = setInterval(function () {
        var elapsed = now() - t0;
        $('recTime').textContent = fmtTime(elapsed);
        var quiet = now() - S.mic.lastLoud;
        if (S.settings.vad && S.mic.spoke && quiet > pauseMs && elapsed > 700) {
          stopMic(true);                       // тишина после речи — отправляем
          return;
        }
        if (elapsed > 90000) {
          stopMic(true);                       // страховка: не держим микрофон вечно
          return;
        }
        // показываем отсчёт: видно, сколько осталось до автоотправки
        if (!S.settings.vad) {
          $('recHint').textContent = 'остановить вручную (Alt+M)';
        } else if (S.mic.spoke) {
          var left = Math.max(0, (pauseMs - quiet) / 1000);
          $('recHint').textContent = 'отправлю через ' + left.toFixed(1) + ' с · нажмите «Микрофон» — сразу';
        } else {
          $('recHint').textContent = 'говорите, я слушаю';
        }
      }, 120);

      send({ type: 'stt_start', lang: S.settings.sttLang });
    } catch (err) {
      toast('Микрофон: ' + (err && err.message ? err.message : err), 'err');
      stopMic(false);
    }
  }

  function stopMic(finalize) {
    if (S.mic.timer) { clearInterval(S.mic.timer); S.mic.timer = null; }
    vizStop();
    if (S.mic.node) { try { S.mic.node.port.onmessage = null; S.mic.node.disconnect(); } catch (e) { /* ignore */ } }
    if (S.mic.src) { try { S.mic.src.disconnect(); } catch (e) { /* ignore */ } }
    if (S.mic.stream) S.mic.stream.getTracks().forEach(function (t) { t.stop(); });
    if (S.mic.ctx) { try { S.mic.ctx.close(); } catch (e) { /* ignore */ } }
    S.mic.stream = null; S.mic.ctx = null; S.mic.node = null; S.mic.src = null;
    S.mic.analyser = null;
    S.mic.active = false;
    S.mic.spoke = false;
    S.mic.noiseFloor = 0;
    $('recBar').hidden = true;
    $('recBar').classList.remove('error');
    $('micBtn').classList.remove('rec');
    var label = $('micLabel');
    if (label) label.textContent = 'Микрофон';
    $('recLive').textContent = '';
    if (finalize) send({ type: 'stt_stop' });
  }

  // Отмена записи: текст распознавания выбрасываем, ничего не отправляем.
  function cancelMic() {
    if (!S.mic.active) return;
    stopMic(false);
    send({ type: 'stt_cancel' });
    toast('Запись отменена');
  }

  function onTranscript(text) {
    var value = (text || '').trim();
    if (!value) return;
    if (S.settings.autoSend) {
      addMessage('user', value);
      send({ type: 'chat', text: value, tts: S.settings.tts, rag: S.settings.rag, lang: S.settings.sttLang });
    } else {
      var input = $('input');
      input.value = (input.value ? input.value + ' ' : '') + value;
      autosize();
      input.focus();
    }
  }

  // ------------------------------------------------------------------ загрузка Excel
  function upload(file) {
    if (!file) return;
    var form = new FormData();
    form.append('file', file);
    $('progress').classList.add('on');
    $('progressBar').style.width = '12%';
    addMessage('system', 'Загрузка и индексация: ' + file.name);
    fetch('/api/upload_excel', { method: 'POST', body: form })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        $('progressBar').style.width = '100%';
        if (data.success) {
          toast('Проиндексировано: ' + data.docs + ' фрагментов', 'ok');
          addMessage('system', 'Готово: ' + data.file + ' — ' + data.docs + ' фрагментов, листы: ' + (data.sheets || []).join(', '));
          refreshStatus();
        } else {
          toast('Ошибка: ' + data.error, 'err');
          addMessage('system', 'Ошибка индексации: ' + data.error);
        }
      })
      .catch(function (err) { toast('Ошибка загрузки: ' + err.message, 'err'); })
      .finally(function () {
        setTimeout(function () {
          $('progress').classList.remove('on');
          $('progressBar').style.width = '0';
        }, 700);
      });
  }

  // ------------------------------------------------------------------ поле ввода
  function autosize() {
    var input = $('input');
    input.style.height = 'auto';
    input.style.height = Math.min(180, input.scrollHeight + 2) + 'px';
    $('counter').textContent = input.value.length ? (input.value.length + ' симв.') : '';
  }

  // ------------------------------------------------------------------ события
  function bind() {
    $('sendBtn').onclick = sendMessage;
    $('stopBtn').onclick = stopAll;
    $('micBtn').onclick = function () { if (S.mic.active) stopMic(true); else startMic(); };
    var recCancel = $('recCancel');
    if (recCancel) recCancel.onclick = cancelMic;
    window.addEventListener('resize', function () { if (S.mic.active) vizResize(); });
    $('menuBtn').onclick = function () { $('side').classList.toggle('open'); };
    $('jumpBtn').onclick = function () { chatBox().scrollTop = chatBox().scrollHeight; };

    $('input').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    $('input').addEventListener('input', autosize);

    document.addEventListener('keydown', function (e) {
      if (e.altKey && (e.key === 'm' || e.key === 'M' || e.key === 'ь')) {
        e.preventDefault();
        if (S.mic.active) stopMic(true); else startMic();
      }
      if (e.key === 'Escape') stopAll();
    });

    $('ttsOn').checked = S.settings.tts;
    $('ttsOn').onchange = function () {
      S.settings.tts = this.checked;
      saveSettings();
      send({ type: 'set', tts: S.settings.tts });
      if (!this.checked) stopAudio();
    };
    $('ragOn').checked = S.settings.rag;
    $('ragOn').onchange = function () {
      S.settings.rag = this.checked;
      saveSettings();
      send({ type: 'set', rag: S.settings.rag });
    };
    $('voiceSel').value = S.settings.voice;
    $('voiceSel').onchange = function () {
      S.settings.voice = this.value;
      saveSettings();
      send({ type: 'set', voice: S.settings.voice });
      toast('Голос: ' + (this.options[this.selectedIndex].textContent || 'по умолчанию'));
    };
    loadVoices();

    $('langSel').value = S.settings.lang;
    $('langSel').onchange = function () {
      S.settings.lang = this.value;
      saveSettings();
      send({ type: 'set', lang: S.settings.lang });
    };
    $('sttLang').value = S.settings.sttLang;
    $('sttLang').onchange = function () { S.settings.sttLang = this.value; saveSettings(); };
    $('autoSend').checked = S.settings.autoSend;
    $('autoSend').onchange = function () { S.settings.autoSend = this.checked; saveSettings(); };
    $('vadOn').checked = S.settings.vad;
    $('vadOn').onchange = function () { S.settings.vad = this.checked; saveSettings(); };

    // пауза перед автостопом записи: главный регулятор, если не успеваете договорить
    $('pause').value = String(S.settings.pause);
    $('pauseVal').textContent = Number(S.settings.pause).toFixed(1) + ' с';
    $('pause').oninput = function () {
      S.settings.pause = Number(this.value);
      $('pauseVal').textContent = S.settings.pause.toFixed(1) + ' с';
      saveSettings();
    };

    // пауза между фразами в речи Айлы (уходит на сервер вместе с запросом)
    $('pauseScale').value = String(S.settings.pauseScale);
    $('pauseScaleVal').textContent = Number(S.settings.pauseScale).toFixed(1) + '×';
    $('pauseScale').oninput = function () {
      S.settings.pauseScale = Number(this.value);
      $('pauseScaleVal').textContent = S.settings.pauseScale.toFixed(1) + '×';
      saveSettings();
      send({ type: 'set', pause_scale: S.settings.pauseScale });
    };

    $('rate').value = String(S.settings.rate);
    $('rateVal').textContent = S.settings.rate.toFixed(1);
    $('rate').oninput = function () {
      S.settings.rate = Number(this.value);
      $('rateVal').textContent = S.settings.rate.toFixed(1);
      saveSettings();
    };

    $('speakLast').onclick = function () {
      if (!S.lastAnswer) { toast('Пока нечего произносить'); return; }
      audioCtx();
      send({ type: 'speak', text: S.lastAnswer, lang: S.settings.lang });
    };
    $('reloadTts').onclick = function () {
      toast('Перезагрузка TTS…');
      fetch('/api/tts/reload', { method: 'POST' }).then(function (r) { return r.json(); })
        .then(function (data) {
          applyStatus({ tts: data });
          toast('TTS: ' + (data.ready ? 'готов' : 'нет моделей'), data.ready ? 'ok' : 'err');
        });
    };

    $('clearRag').onclick = function () {
      if (!confirm('Очистить базу знаний?')) return;
      fetch('/api/rag/clear', { method: 'POST' }).then(function (r) { return r.json(); })
        .then(function () { toast('База очищена', 'ok'); refreshStatus(); });
    };
    $('testSearch').onclick = function () {
      var query = prompt('Что искать в документации?', 'код 3');
      if (!query) return;
      fetch('/api/search?k=5&q=' + encodeURIComponent(query)).then(function (r) { return r.json(); })
        .then(function (data) {
          var lines = (data.items || []).map(function (item, i) {
            return (i + 1) + '. [' + Math.round(item.score * 100) + '%] лист ' + (item.sheet || '-') +
              ', стр. ' + (item.row || '-') + ', код ' + (item.code || '-');
          });
          $('searchOut').textContent = lines.length ? lines.join(NL) : 'ничего не найдено';
        });
    };
    $('refresh').onclick = refreshStatus;

    var drop = $('drop');
    drop.onclick = function () { $('fileInput').click(); };
    $('fileInput').onchange = function () {
      if (this.files[0]) upload(this.files[0]);
      this.value = '';
    };
    ['dragenter', 'dragover'].forEach(function (name) {
      drop.addEventListener(name, function (e) { e.preventDefault(); drop.classList.add('over'); });
    });
    ['dragleave', 'drop'].forEach(function (name) {
      drop.addEventListener(name, function (e) { e.preventDefault(); drop.classList.remove('over'); });
    });
    drop.addEventListener('drop', function (e) {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
    });

    chatBox().addEventListener('scroll', function () { $('jumpBtn').hidden = nearBottom(); });
  }

  // ------------------------------------------------------------------ демонстрация вида
  // Открыть http://127.0.0.1:8000/?demo=1 — рисует пример диалога без сервера.
  function renderDemo() {
    addMessage('user', 'какое оборудование под кодом 3 и когда по нему ТО-3?');
    var bubble = addMessage('assistant', '');
    renderBubble(bubble, 'Оборудование с кодом 3 — преобразователь расхода ' +
      '(зав. № 000103, установка № 1). По графику ТО-3 для этой позиции назначено на 12-е число.', false);
    renderSources(bubble, [
      { score: 1.0, sheet: '1', row: 4, code: '3',
        equipment: 'Преобразователь расхода, зав. № 000103',
        preview: 'Лист: 1, строка 4, код оборудования 3 — преобразователь расхода, зав. № 000103. График ТО: ТО-3 — 12-е число.' },
      { score: 0.97, sheet: '1', row: 3, code: '3',
        equipment: 'Преобразователь расхода, зав. № 000103', preview: '…' }
    ]);
    $('recTime').textContent = '3.4 с';
    $('recLive').textContent = 'какое оборудование под кодом семь и когда по нему ТО-3';
    $('recHint').textContent = 'говорите, я слушаю';
    $('micBtn').classList.add('rec');
    var demoLabel = $('micLabel');
    if (demoLabel) demoLabel.textContent = 'Слушаю';
    vizDemo();
    S.audio.playing = true;       // демонстрация кнопки «Стоп озвучки» и индикатора
    updateControls();
    addMessage('system', 'Демонстрация интерфейса (режим ?demo=1) — сервер не используется.');
  }

  // ------------------------------------------------------------------ старт
  loadSettings();
  bind();
  autosize();
  if (/[?&]demo/.test(location.search)) {
    renderDemo();
    return;
  }
  connect();
  refreshStatus();
  setInterval(refreshStatus, 15000);
})();
