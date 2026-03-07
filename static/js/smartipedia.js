/* Smartipedia — Dark mode, text size, ToC, Cmd+K, source tooltips, keyword links */

(function () {
  // ==================== DARK MODE ====================
  const THEME_KEY = 'smartipedia-theme';

  function getPreferredTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored) return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    localStorage.setItem(THEME_KEY, theme);
    const btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.innerHTML = theme === 'dark'
        ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    }
  }

  applyTheme(getPreferredTheme());

  document.addEventListener('DOMContentLoaded', function () {
    applyTheme(getPreferredTheme());

    var themeBtn = document.getElementById('theme-toggle');
    function toggleTheme() {
      var current = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
      applyTheme(current === 'dark' ? 'light' : 'dark');
    }
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

    // Cmd+I / Ctrl+I to toggle dark mode
    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'i') {
        e.preventDefault();
        toggleTheme();
      }
    });

    // ==================== TEXT SIZE ====================
    var SIZE_KEY = 'smartipedia-textsize';
    var sizes = ['text-sm', 'text-md', 'text-lg'];
    var sizeLabels = ['A-', 'A', 'A+'];

    function getTextSize() { return localStorage.getItem(SIZE_KEY) || 'text-md'; }
    function applyTextSize(size) {
      sizes.forEach(function (s) { document.documentElement.classList.remove(s); });
      document.documentElement.classList.add(size);
      localStorage.setItem(SIZE_KEY, size);
      var btn = document.getElementById('text-size-toggle');
      if (btn) btn.textContent = sizeLabels[sizes.indexOf(size)];
    }
    applyTextSize(getTextSize());

    var sizeBtn = document.getElementById('text-size-toggle');
    if (sizeBtn) {
      sizeBtn.addEventListener('click', function () {
        var idx = sizes.indexOf(getTextSize());
        applyTextSize(sizes[(idx + 1) % sizes.length]);
      });
    }

    // ==================== CMD+K MODAL ====================
    initCmdK();

    // ==================== TABLE OF CONTENTS ====================
    initToc();

    // ==================== SOURCE TOOLTIPS ====================
    initSourceTooltips();

    // ==================== KEYWORD LINKS ====================
    initKeywordLinks();
  });

  // ==================== CMD+K ====================
  function initCmdK() {
    var modal = document.getElementById('cmdk-modal');
    var input = document.getElementById('cmdk-input');
    var trigger = document.getElementById('cmdk-trigger');
    if (!modal || !input) return;

    function openModal() {
      modal.style.display = 'flex';
      input.value = '';
      input.focus();
      document.getElementById('cmdk-results').innerHTML = '';
    }
    function closeModal() {
      modal.style.display = 'none';
      input.value = '';
    }

    if (trigger) trigger.addEventListener('click', openModal);

    // Cmd+K / Ctrl+K
    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (modal.style.display === 'none' || !modal.style.display) openModal();
        else closeModal();
      }
      if (e.key === 'Escape' && modal.style.display !== 'none') {
        closeModal();
      }
    });

    // Close on overlay click
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeModal();
    });

    // Keyboard nav in results
    var selectedIdx = -1;
    input.addEventListener('keydown', function (e) {
      var results = document.querySelectorAll('#cmdk-results .cmdk-result');
      if (!results.length) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedIdx = Math.min(selectedIdx + 1, results.length - 1);
        updateSelected(results);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedIdx = Math.max(selectedIdx - 1, 0);
        updateSelected(results);
      } else if (e.key === 'Enter' && selectedIdx >= 0 && results[selectedIdx]) {
        e.preventDefault();
        window.location.href = results[selectedIdx].href;
      }
    });

    // Reset selection on new results
    var observer = new MutationObserver(function () { selectedIdx = -1; });
    observer.observe(document.getElementById('cmdk-results'), { childList: true });

    function updateSelected(results) {
      results.forEach(function (r, i) {
        r.classList.toggle('selected', i === selectedIdx);
      });
    }
  }

  // ==================== TABLE OF CONTENTS ====================
  function initToc() {
    var content = document.getElementById('topic-content');
    var tocList = document.getElementById('toc-list');
    if (!content || !tocList) return;

    var headings = content.querySelectorAll('h2, h3');
    if (headings.length === 0) return;

    headings.forEach(function (h, i) {
      // Add id to heading for anchor
      if (!h.id) h.id = 'heading-' + i;

      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.textContent = h.textContent;
      a.dataset.headingId = h.id;
      if (h.tagName === 'H3') a.classList.add('toc-h3');
      tocList.appendChild(a);

      // Smooth scroll
      a.addEventListener('click', function (e) {
        e.preventDefault();
        h.scrollIntoView({ behavior: 'smooth', block: 'start' });
        history.replaceState(null, '', '#' + h.id);
      });
    });

    // Scroll spy: highlight active section
    var tocLinks = tocList.querySelectorAll('a');
    var headingEls = Array.from(headings);

    function updateActiveHeading() {
      var scrollY = window.scrollY + 100;
      var activeIdx = 0;

      for (var i = 0; i < headingEls.length; i++) {
        if (headingEls[i].offsetTop <= scrollY) activeIdx = i;
      }

      tocLinks.forEach(function (link, i) {
        link.classList.toggle('active', i === activeIdx);
      });
    }

    window.addEventListener('scroll', updateActiveHeading, { passive: true });
    updateActiveHeading();
  }

  // ==================== SOURCE FOOTNOTE TOOLTIPS ====================
  function initSourceTooltips() {
    var content = document.querySelector('.topic-content');
    if (!content) return;

    var sourcesEl = document.getElementById('sources-data');
    if (!sourcesEl) return;

    var sources;
    try { sources = JSON.parse(sourcesEl.textContent); }
    catch (e) { return; }

    var walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    var refPattern = /\[(\d+)\]/g;
    var nodesToReplace = [];

    var node;
    while ((node = walker.nextNode())) {
      if (refPattern.test(node.textContent)) nodesToReplace.push(node);
      refPattern.lastIndex = 0;
    }

    nodesToReplace.forEach(function (textNode) {
      var fragment = document.createDocumentFragment();
      var text = textNode.textContent;
      var lastIndex = 0;
      var match;
      refPattern.lastIndex = 0;

      while ((match = refPattern.exec(text)) !== null) {
        if (match.index > lastIndex)
          fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));

        var num = parseInt(match[1], 10);
        var source = sources[num - 1];
        var span = document.createElement('span');
        span.className = 'footnote-ref';
        span.textContent = match[1];
        span.dataset.sourceIndex = num - 1;

        if (source) {
          span.addEventListener('mouseenter', showSourceTooltip);
          span.addEventListener('mouseleave', hideSourceTooltip);
          span.addEventListener('click', function () {
            var s = sources[parseInt(this.dataset.sourceIndex, 10)];
            if (s && s.url) window.open(s.url, '_blank');
          });
        }
        fragment.appendChild(span);
        lastIndex = match.index + match[0].length;
      }

      if (lastIndex < text.length)
        fragment.appendChild(document.createTextNode(text.slice(lastIndex)));

      textNode.parentNode.replaceChild(fragment, textNode);
    });
  }

  var sourceTooltipEl = null;

  function showSourceTooltip(e) {
    var sourcesEl = document.getElementById('sources-data');
    if (!sourcesEl) return;
    var sources = JSON.parse(sourcesEl.textContent);
    var idx = parseInt(e.target.dataset.sourceIndex, 10);
    var source = sources[idx];
    if (!source) return;

    if (!sourceTooltipEl) {
      sourceTooltipEl = document.createElement('div');
      sourceTooltipEl.className = 'source-tooltip';
      document.body.appendChild(sourceTooltipEl);
    }

    var html = '';
    if (source.title) html += '<span class="source-tooltip-title">' + escHtml(source.title) + '</span>';
    if (source.snippet) html += '<span class="source-tooltip-snippet">' + escHtml(source.snippet).slice(0, 200) + '</span>';
    if (source.url) {
      var shortUrl = source.url.replace(/^https?:\/\//, '').split('/')[0];
      html += '<span class="source-tooltip-url">' + escHtml(shortUrl) + '</span>';
    }
    sourceTooltipEl.innerHTML = html;
    positionTooltip(sourceTooltipEl, e.target);
    sourceTooltipEl.classList.add('visible');
  }

  function hideSourceTooltip() {
    if (sourceTooltipEl) sourceTooltipEl.classList.remove('visible');
  }

  // ==================== KEYWORD LINKS ====================
  function initKeywordLinks() {
    var content = document.querySelector('.topic-content');
    if (!content) return;

    var relatedEl = document.getElementById('related-data');
    if (!relatedEl) return;

    var related;
    try { related = JSON.parse(relatedEl.textContent); }
    catch (e) { return; }

    if (!related || related.length === 0) return;

    related.sort(function (a, b) { return b.title.length - a.title.length; });

    var linked = new Set();
    related.forEach(function (topic) {
      if (linked.has(topic.slug)) return;
      if (linkKeywordInContent(content, topic.title, topic)) linked.add(topic.slug);
    });
  }

  function linkKeywordInContent(container, keyword, topicData) {
    var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    var lowerKeyword = keyword.toLowerCase();
    var found = false;

    var node;
    while ((node = walker.nextNode())) {
      var parent = node.parentElement;
      if (!parent) continue;
      var tag = parent.tagName;
      if (tag === 'A' || tag === 'H1' || tag === 'H2' || tag === 'H3' || tag === 'H4' || tag === 'CODE' || tag === 'PRE') continue;
      if (parent.classList.contains('keyword-link') || parent.classList.contains('footnote-ref')) continue;

      var idx = node.textContent.toLowerCase().indexOf(lowerKeyword);
      if (idx === -1) continue;

      var before = node.textContent.slice(0, idx);
      var match = node.textContent.slice(idx, idx + keyword.length);
      var after = node.textContent.slice(idx + keyword.length);

      var a = document.createElement('a');
      a.className = 'keyword-link';
      a.href = '/topic/' + topicData.slug;
      a.textContent = match;
      a.dataset.slug = topicData.slug;
      a.dataset.title = topicData.title;
      a.dataset.summary = topicData.summary || '';

      a.addEventListener('mouseenter', showKeywordTooltip);
      a.addEventListener('mouseleave', hideKeywordTooltip);

      var fragment = document.createDocumentFragment();
      if (before) fragment.appendChild(document.createTextNode(before));
      fragment.appendChild(a);
      if (after) fragment.appendChild(document.createTextNode(after));

      node.parentNode.replaceChild(fragment, node);
      found = true;
      break;
    }
    return found;
  }

  var keywordTooltipEl = null;

  function showKeywordTooltip(e) {
    var el = e.target;
    if (!keywordTooltipEl) {
      keywordTooltipEl = document.createElement('div');
      keywordTooltipEl.className = 'keyword-tooltip';
      document.body.appendChild(keywordTooltipEl);
    }

    var html = '<span class="keyword-tooltip-title">' + escHtml(el.dataset.title) + '</span>';
    if (el.dataset.summary)
      html += '<span class="keyword-tooltip-desc">' + escHtml(el.dataset.summary) + '</span>';
    html += '<span class="keyword-tooltip-link">Click to read full article</span>';
    keywordTooltipEl.innerHTML = html;
    positionTooltip(keywordTooltipEl, el);
    keywordTooltipEl.classList.add('visible');
  }

  function hideKeywordTooltip() {
    if (keywordTooltipEl) keywordTooltipEl.classList.remove('visible');
  }

  // ==================== HELPERS ====================
  function positionTooltip(tooltip, anchor) {
    var rect = anchor.getBoundingClientRect();
    var tooltipWidth = 320;
    var left = rect.left + rect.width / 2 - tooltipWidth / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - tooltipWidth - 8));
    var top = rect.bottom + 8;
    if (top + 120 > window.innerHeight) {
      top = rect.top - 8;
      tooltip.style.transform = 'translateY(-100%)';
    } else {
      tooltip.style.transform = '';
    }
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
  }

  function escHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
})();
