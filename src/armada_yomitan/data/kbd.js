// On-screen keyboard: drawn by the page (host), driven from Yomitan's settings page (agent).
(function () {
  'use strict';
  if (window.__armadaYomitanKbd) { return; }

  var embedded = false;
  try { embedded = window.parent !== window; } catch (err) { embedded = true; }
  var role = embedded ? 'agent' : 'host';

  var LETTERS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm'];
  var SYMBOLS = ['1234567890', '@#$&*-+=_%', '()/:;!?\'"'];
  var TEXT_TYPES = ['', 'text', 'search', 'url', 'email', 'tel', 'password', 'number'];
  var CSS = [
    ':host{all:initial}',
    '#kb{box-sizing:border-box;width:100%;padding:4px;display:flex;flex-direction:column;gap:4px;background:#1f2933;',
    'user-select:none;-webkit-user-select:none;touch-action:none;-webkit-tap-highlight-color:transparent;',
    'font:600 17px/1 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}',
    '.r{flex:1 1 0%;min-height:0;display:flex;gap:4px}',
    '.k{flex:var(--w) 1 0%;min-width:0;display:flex;align-items:center;justify-content:center;background:#3e4c59;',
    'color:#fff;border-radius:6px;overflow:hidden}',
    '.g{flex:var(--w) 1 0%}',
    '.k.sp{background:#2b3a47;font-size:14px}',
    '.k.on{background:#2f6feb}',
    '.k.down{background:#7b8794}'
  ].join('\n');

  var state = {
    layer: 'abc', shift: false, open: false, field: null, laidFor: null, tap: 0, gen: 0,
    h: 0,                                        // room to leave at the bottom of THIS page (px)
    kh: 0,                                       // the keyboard's own height (host only)
    keys: [], held: null, repeated: false, hold: 0, pointer: null,
    remote: null,                                // host: the embedded page whose field is being typed into
    agents: [], acked: false, ids: 0, poll: 0
  };
  var host = null, box = null, spacers = [], showTimer = 0, hideTimer = 0, dirty = [];

  function report(text) { if (typeof window.armadaYomitanKbdReport === 'function') { window.armadaYomitanKbdReport(text); } }

  function send(win, msg, origin) {
    try { win.postMessage(msg, origin || '*'); } catch (err) { }
  }

  function trusted(origin, prefixes) {
    var extra = window.ARMADA_YOMITAN_KBD_TRUST || [];
    return extra.indexOf(origin) >= 0 || prefixes.some(function (p) { return origin.indexOf(p) === 0; });
  }

  // ---- what the keys are: rows 20 units wide, so the widths match the keyboard in Anki
  function rowsFor(layer, shift) {
    function letters(chars) {
      return chars.split('').map(function (c) {
        var t = shift ? c.toUpperCase() : c;
        return {label: t, action: ['text', t], w: 2};
      });
    }
    function plain(chars) {
      return chars.split('').map(function (c) { return {label: c, action: ['text', c], w: 2}; });
    }
    function gap(w) { return {label: '', action: null, w: w}; }
    function del(w) { return {label: 'Del', action: ['key', 'backspace'], w: w, sp: true, repeat: true}; }
    var rows;
    if (layer === 'abc') {
      rows = [
        letters(LETTERS[0]),
        [gap(1)].concat(letters(LETTERS[1]), [gap(1)]),
        [{label: 'Shift', action: ['shift'], w: 3, sp: true, on: shift}].concat(letters(LETTERS[2]), [del(3)])
      ];
    } else {
      rows = [plain(SYMBOLS[0]), [gap(1)].concat(plain(SYMBOLS[1]), [gap(1)]), plain(SYMBOLS[2]).concat([del(2)])];
    }
    rows.push([
      {label: layer === 'abc' ? '123' : 'abc', action: ['layer', layer === 'abc' ? 'sym' : 'abc'], w: 3, sp: true},
      {label: ',', action: ['text', ','], w: 2},
      {label: 'Space', action: ['key', 'space'], w: 7},
      {label: '.', action: ['text', '.'], w: 2},
      {label: 'Enter', action: ['key', 'enter'], w: 3, sp: true},
      {label: 'Hide', action: ['hide'], w: 3, sp: true}
    ]);
    return rows;
  }

  // ---- text fields
  function isTextField(el) {
    if (!el || el.nodeType !== 1) { return false; }
    if (el.tagName === 'TEXTAREA') { return !el.readOnly && !el.disabled; }
    if (el.tagName === 'INPUT') {
      var type = (el.getAttribute('type') || '').toLowerCase();
      return TEXT_TYPES.indexOf(type) >= 0 && !el.readOnly && !el.disabled;
    }
    return !!el.isContentEditable;
  }

  function fieldFor(el) {
    while (el && el.nodeType === 1) {
      if (isTextField(el)) { return el; }
      if (el.tagName === 'LABEL' && el.control && isTextField(el.control)) { return el.control; }
      el = el.parentElement;
    }
    return null;
  }

  function usable(el) {                         // visible: Yomitan's hidden search box must not raise the keyboard
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  }

  function layerFor(el) {
    var t = (el.getAttribute('type') || '').toLowerCase(), m = (el.getAttribute('inputmode') || '').toLowerCase();
    return (['number', 'tel'].indexOf(t) >= 0 || ['numeric', 'decimal', 'tel'].indexOf(m) >= 0) ? 'sym' : 'abc';
  }

  function fieldId(el) {
    if (!el.__armadaYomitanId) { el.__armadaYomitanId = ++state.ids; }
    return el.__armadaYomitanId;
  }

  // ---- typing
  function field() {
    var el = state.field;
    if (!el || !el.isConnected) { return null; }
    var a = document.activeElement;
    if (a !== el && !(el.contains && el.contains(a))) { el.focus({preventScroll: true}); }
    return el;
  }

  function markDirty(el) { if (dirty.indexOf(el) < 0) { dirty.push(el); } }

  function flushDirty(el) {                     // edits made by script don't trigger the browser's own 'change' on blur
    var i = dirty.indexOf(el);
    if (i >= 0) {
      dirty.splice(i, 1);
      el.dispatchEvent(new Event('change', {bubbles: true}));
    }
  }

  function typeText(text) {
    var el = field();
    if (!el) { return; }
    if (document.execCommand('insertText', false, text)) { return; }
    try {                                       // fallback for a field the browser won't insert into
      if (el.selectionStart === null || el.selectionStart === undefined) { el.value += text; }
      else { el.setRangeText(text, el.selectionStart, el.selectionEnd, 'end'); }
      el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: text}));
      markDirty(el);
    } catch (err) { }
  }

  function backspace(el) {
    if (document.execCommand('delete', false)) { return; }
    try {
      var s = el.selectionStart, e = el.selectionEnd;
      if (s === null || s === undefined) { el.value = el.value.slice(0, -1); }
      else if (s !== e) { el.setRangeText('', s, e, 'end'); }
      else if (s > 0) { el.setRangeText('', s - 1, s, 'end'); }
      else { return; }
      el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'deleteContentBackward'}));
      markDirty(el);
    } catch (err) { }
  }

  function enter(el) {
    if (el.tagName === 'TEXTAREA' || (el.isContentEditable && el.tagName !== 'INPUT')) {
      if (!document.execCommand('insertText', false, '\n')) { document.execCommand('insertLineBreak'); }
      return;
    }
    var opts = {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true};
    if (el.dispatchEvent(new KeyboardEvent('keydown', opts))) {     // the page didn't handle Enter itself
      el.dispatchEvent(new KeyboardEvent('keypress', opts));
      flushDirty(el);
      el.dispatchEvent(new Event('change', {bubbles: true}));
      var f = el.form;
      if (f && typeof f.requestSubmit === 'function' &&
          (f.querySelector('[type=submit],button:not([type])') || f.querySelectorAll('input:not([type=hidden])').length === 1)) {
        f.requestSubmit();
      }
    }
    el.dispatchEvent(new KeyboardEvent('keyup', opts));
  }

  function applyOp(op, text) {
    if (op === 'text') { typeText(text); return; }
    var el = field();
    if (!el) { return; }
    if (op === 'backspace') { backspace(el); } else if (op === 'enter') { enter(el); }
  }

  // ---- making room
  function scrollerOf(el) {
    for (var a = el.parentElement; a && a !== document.body && a !== document.documentElement; a = a.parentElement) {
      var oy = getComputedStyle(a).overflowY;
      if ((oy === 'auto' || oy === 'scroll' || oy === 'overlay') && a.clientHeight >= window.innerHeight * 0.5) { return a; }
    }
    return null;
  }

  function removeRoom() {
    spacers.forEach(function (s) { if (s.parentNode) { s.parentNode.removeChild(s); } });
    spacers = [];
  }

  function reveal(el) {
    if (!el.isConnected || !state.open || !state.h) { return; }
    el.scrollIntoView({block: 'nearest', inline: 'nearest'});
    var r = el.getBoundingClientRect(), visible = window.innerHeight - state.h - 8;
    if (r.bottom > visible) {
      var dy = Math.min(r.bottom - visible, Math.max(0, r.top - 8));
      if (dy > 0) { (scrollerOf(el) || window).scrollBy(0, dy); }
    }
  }

  function makeRoom(el) {
    removeRoom();
    if (!state.h) { return; }
    var scroller = scrollerOf(el), page = document.scrollingElement;
    var scrolls = scroller || (page && page.scrollHeight > window.innerHeight + 1);
    if (!scrolls && el.getBoundingClientRect().bottom <= window.innerHeight - state.h - 8) { return; }
    var sp = document.createElement('div');
    sp.setAttribute('data-armada-yomitan-kbd-spacer', '');
    sp.style.cssText = 'height:' + state.h + 'px;flex:none;pointer-events:none;';
    (scroller || document.body).appendChild(sp);
    spacers.push(sp);
    reveal(el);
    setTimeout(function () { reveal(el); }, 250);
  }

  // ---- host keyboard
  function nearest(x, y) {
    var best = null, bd = Infinity;
    state.keys.forEach(function (k) {
      var r = k.el.getBoundingClientRect();
      var dx = Math.max(r.left - x, 0, x - r.right), dy = Math.max(r.top - y, 0, y - r.bottom);
      var d = dx * dx + dy * dy;
      if (d < bd) { best = k; bd = d; }
    });
    return best;
  }

  function sendOp(op, text) {
    if (state.remote) { send(state.remote.win, {armadaYomitanKbd: 'op', op: op, text: text}, state.remote.origin); }
    else { applyOp(op, text); }
  }

  function press(action) {
    switch (action[0]) {
      case 'text':
        sendOp('text', action[1]);
        if (state.shift) { state.shift = false; render(); }
        break;
      case 'key':
        if (action[1] === 'space') { sendOp('text', ' '); } else { sendOp(action[1]); }
        break;
      case 'shift': state.shift = !state.shift; render(); break;
      case 'layer': state.layer = action[1]; render(); break;
      case 'hide': hideSoon(); break;
    }
  }

  function onDown(e) {
    e.preventDefault();
    e.stopPropagation();
    if (state.pointer !== null && state.pointer !== e.pointerId) { return; }
    state.pointer = e.pointerId;
    try { box.setPointerCapture(e.pointerId); } catch (err) { }
    var k = state.held = nearest(e.clientX, e.clientY);
    state.repeated = false;
    state.hold += 1;
    if (!k) { return; }
    k.el.classList.add('down');
    if (k.repeat) {
      state.repeated = true;
      press(k.action);
      var gen = state.hold;
      setTimeout(function () { again(gen); }, 400);
    }
  }

  function again(gen) {
    if (!state.held || gen !== state.hold) { return; }
    press(state.held.action);
    setTimeout(function () { again(gen); }, 60);
  }

  function release(e, fire) {
    e.preventDefault();
    if (e.pointerId !== state.pointer) { return; }
    state.pointer = null;
    var k = state.held;
    state.held = null;
    state.hold += 1;
    if (!k) { return; }
    k.el.classList.remove('down');
    if (fire && !state.repeated && nearest(e.clientX, e.clientY) === k) { press(k.action); }
  }

  function render() {
    state.keys = [];
    state.held = null;
    box.textContent = '';
    rowsFor(state.layer, state.shift).forEach(function (row) {
      var r = document.createElement('div');
      r.className = 'r';
      row.forEach(function (key) {
        var el = document.createElement('div');
        el.style.setProperty('--w', key.w);
        if (!key.action) { el.className = 'g'; }
        else {
          el.className = 'k' + (key.sp ? ' sp' : '') + (key.on ? ' on' : '');
          el.textContent = key.label;
          state.keys.push({el: el, action: key.action, repeat: !!key.repeat});
        }
        r.appendChild(el);
      });
      box.appendChild(r);
    });
  }

  function build() {
    if (host) { return; }
    host = document.createElement('div');
    host.id = 'armada-yomitan-kbd-host';
    host.style.cssText = 'all:initial;position:fixed;left:0;right:0;bottom:0;z-index:2147483647;display:none;';
    var root = host.attachShadow({mode: 'open'});                                 // the page's own CSS can't reach it
    root.innerHTML = '<style>' + CSS + '</style><div id="kb"></div>';
    box = root.getElementById('kb');
    box.addEventListener('pointerdown', onDown);
    box.addEventListener('pointerup', function (e) { release(e, true); });
    box.addEventListener('pointercancel', function (e) { release(e, false); });
    ['contextmenu', 'mousedown', 'mouseup', 'click', 'dblclick'].forEach(function (name) {
      box.addEventListener(name, function (e) { e.preventDefault(); e.stopPropagation(); });   // never take the focus
    });
    (document.body || document.documentElement).appendChild(host);
  }

  function place() {
    state.kh = Math.max(150, Math.min(260, Math.round(window.innerHeight * 0.4)));
    box.style.height = state.kh + 'px';
    host.style.display = 'block';
  }

  function frameOf(win) {
    var frames = document.getElementsByTagName('iframe');
    for (var i = 0; i < frames.length; i++) { if (frames[i].contentWindow === win) { return frames[i]; } }
    return null;
  }

  function roomRemote() {
    var r = state.remote;
    if (!r) { return; }
    var covered = r.frame ? r.frame.getBoundingClientRect().bottom - (window.innerHeight - state.kh) : state.kh;
    send(r.win, {armadaYomitanKbd: 'room', px: Math.max(0, Math.round(covered))}, r.origin);
  }

  function show(el) {                           // el: a field in this page; null: the remote field in state.remote
    build();
    clearTimeout(hideTimer);
    host.style.opacity = '';
    var key = el || ('remote:' + state.remote.fid);
    if (!state.open || state.laidFor !== key) {
      state.layer = el ? layerFor(el) : state.remote.layer;
      state.shift = false;
      state.laidFor = key;
      render();
    }
    state.open = true;
    place();
    if (el) { state.h = state.kh; makeRoom(el); } else { roomRemote(); }
  }

  function hideSoon() {                         // the Hide key: the tap's leftover mouse events would land on whatever is
    if (!host) { return; }                      // underneath once the keyboard is gone, so keep swallowing them a moment
    host.style.opacity = '0';
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function () { host.style.opacity = ''; hide(); }, 450);
  }

  function hide() {
    state.gen += 1;
    clearTimeout(showTimer);
    clearInterval(state.poll);
    if (!state.open) { return; }
    state.open = false;
    host.style.display = 'none';
    removeRoom();
    if (state.remote) {
      send(state.remote.win, {armadaYomitanKbd: 'room', px: 0, closed: true}, state.remote.origin);
      state.remote = null;
    }
  }

  function openRemote(e, d) {
    build();
    var frame = frameOf(e.source);
    state.remote = {win: e.source, origin: e.origin, frame: frame, fid: d.fid, layer: d.layer === 'sym' ? 'sym' : 'abc'};
    show(null);
    clearInterval(state.poll);
    state.poll = setInterval(function () {
      if (state.remote && !(frame && frame.getClientRects().length > 0)) { hide(); }
    }, 500);
  }

  // ---- requesting the keyboard
  function requestOpen(el) {
    state.field = el;
    if (role === 'agent') {
      state.open = true;
      send(window.parent, {armadaYomitanKbd: 'open', fid: fieldId(el), layer: layerFor(el)});
    } else {
      show(el);
    }
  }

  function requestClose() {
    if (role === 'agent') {
      if (state.open) {
        state.open = false;
        send(window.parent, {armadaYomitanKbd: 'close'});
        removeRoom();
      }
    } else {
      hide();
    }
  }

  function hideLater() {
    var gen = state.gen += 1;
    setTimeout(function () {
      if (gen !== state.gen || fieldFor(document.activeElement)) { return; }
      if (role === 'host' && state.remote) { return; }
      requestClose();
    }, 300);
  }

  // ---- when to appear
  document.addEventListener('pointerdown', function (e) {
    if (e.target === host) { return; }
    state.tap = Date.now();
    var el = fieldFor(e.target);
    if (el && usable(el)) {
      state.field = el;
      state.gen += 1;
      clearTimeout(showTimer);
      showTimer = setTimeout(function () {
        if (state.field === el && (document.activeElement === el || el.contains(document.activeElement))) { requestOpen(el); }
      }, 200);
    } else if (role === 'host' && state.remote) {
      hide();
    } else {
      hideLater();
    }
  }, true);

  document.addEventListener('focusin', function (e) {
    var el = fieldFor(e.composedPath ? e.composedPath()[0] : e.target);
    if (!el || !usable(el)) { return; }
    state.field = el;
    state.gen += 1;
    if (Date.now() - state.tap < 1000 || state.open) { requestOpen(el); }
  }, true);

  document.addEventListener('focusout', function (e) { flushDirty(e.target); hideLater(); }, true);
  window.addEventListener('pagehide', function () { if (role === 'agent') { requestClose(); } else { hide(); } });
  window.addEventListener('resize', function () {
    if (role === 'host' && state.open) {
      place();
      if (state.remote) { roomRemote(); } else if (state.field) { state.h = state.kh; makeRoom(state.field); }
    }
  });

  // ---- agent/host messages
  function hostMessage(e, d) {
    switch (d.armadaYomitanKbd) {
      case 'hello':
        if (state.agents.indexOf(e.source) < 0) { state.agents.push(e.source); }
        send(e.source, {armadaYomitanKbd: 'ack'}, e.origin);
        break;
      case 'open': openRemote(e, d); break;
      case 'close': if (state.remote && state.remote.win === e.source) { hide(); } break;
      case 'error': report('The Yomitan page reported a script error in the keyboard helper: ' + d.message); break;
    }
  }

  function agentMessage(d) {
    switch (d.armadaYomitanKbd) {
      case 'ack': state.acked = true; break;
      case 'op': applyOp(d.op, d.text); break;
      case 'room':
        state.h = d.px || 0;
        if (state.h > 0 && state.field) { makeRoom(state.field); }
        else { removeRoom(); }
        if (d.closed) { state.open = false; }
        break;
    }
  }

  window.addEventListener('message', function (e) {
    var d = e.data;
    if (!d || typeof d !== 'object' || !d.armadaYomitanKbd) { return; }
    if (role === 'host') {
      if (trusted(e.origin, ['chrome-extension://'])) { hostMessage(e, d); }
    } else if (e.source === window.parent && trusted(e.origin, ['http://127.0.0.1:', 'http://localhost:'])) {
      agentMessage(d);
    }
  });

  if (role === 'agent') {
    send(window.parent, {armadaYomitanKbd: 'hello'});
    setTimeout(function () { if (!state.acked && role === 'agent') { role = 'host'; } }, 1500);   // nobody answered: draw it here
    window.addEventListener('error', function (e) {                                // only this script's own errors are passed on
      if (e.filename && e.filename.indexOf('armada-yomitan-kbd') >= 0) { send(window.parent, {armadaYomitanKbd: 'error', message: String(e.message).slice(0, 200)}); }
    });
  }

  window.__armadaYomitanKbd = {
    enabled: true,
    role: function () { return role; },
    isOpen: function () { return state.open; },
    keyAt: function (x, y) { var k = nearest(x, y); return k ? k.el.textContent : null; },
    heardFrom: function (frame) { return !!frame && state.agents.indexOf(frame.contentWindow) >= 0; }
  };
}());
