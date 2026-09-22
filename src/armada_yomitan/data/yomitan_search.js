// Adds scroll room under the touch preview: the page sends {armadaYomitan: 'reserve', size: N} (CSS px).
(function () {
  'use strict';
  var size = 0, pad = null;

  function ensure() {
    if (pad && pad.isConnected) { return pad; }
    var list = document.getElementById('dictionary-entries');
    var parent = list ? list.parentNode : (document.querySelector('.content-body-inner') || document.body);
    if (!parent) { return null; }
    pad = document.createElement('div');
    pad.id = 'armada-yomitan-pad';
    pad.setAttribute('aria-hidden', 'true');
    pad.style.cssText = 'pointer-events:none;flex:none;';
    parent.insertBefore(pad, list ? list.nextSibling : null);
    return pad;
  }

  function apply() {
    var el = size > 0 ? ensure() : pad;
    if (!el) { return; }
    el.style.display = size > 0 ? 'block' : 'none';
    el.style.height = (size > 0 ? 2 * size : 0) + 'px';
  }

  // Yomitan redraws the results on every search; put the padding back if that removed it.
  new MutationObserver(function () {
    if (size > 0 && !(pad && pad.isConnected)) { apply(); }
  }).observe(document.documentElement, {childList: true, subtree: true});

  window.addEventListener('message', function (e) {
    var ok = e.origin.indexOf('http://127.0.0.1:') === 0 || e.origin.indexOf('http://localhost:') === 0;
    var d = e.data;
    if (!ok || e.source !== window.parent || !d || d.armadaYomitan !== 'reserve' || typeof d.size !== 'number') { return; }
    size = Math.max(0, Math.min(400, d.size));
    apply();
  });
}());
