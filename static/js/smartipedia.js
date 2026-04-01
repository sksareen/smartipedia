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

    // Cmd+I / Ctrl+I to toggle dark mode (skip if notepad editor is focused)
    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'i') {
        var active = document.activeElement;
        if (active && active.id === 'notepad-editor') return; // let italic work in editor
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

    // ==================== USER MENU ====================
    var avatarBtn = document.getElementById('nav-avatar-btn');
    var userDropdown = document.getElementById('nav-user-dropdown');
    if (avatarBtn && userDropdown) {
      avatarBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        userDropdown.classList.toggle('open');
      });
      document.addEventListener('click', function (e) {
        if (!e.target.closest('.nav-user-menu')) {
          userDropdown.classList.remove('open');
        }
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

    // ==================== RABBIT HOLE (text selection) ====================
    initRabbitHole();

    // ==================== JOURNEY TRACKER ====================
    initJourney();

    // ==================== JOURNEY SYNC (if logged in) ====================
    initJourneySync();

    // ==================== NOTEPAD DRAWER ====================
    initNotepad();
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
      // Cmd+Enter / Ctrl+Enter: generate article from search query
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        var q = input.value.trim();
        if (q.length >= 2) {
          var form = document.createElement('form');
          form.method = 'POST';
          form.action = '/generate-async';
          var inp = document.createElement('input');
          inp.type = 'hidden';
          inp.name = 'title';
          inp.value = q;
          form.appendChild(inp);
          document.body.appendChild(form);
          form.submit();
        }
        return;
      }

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

      // Word-boundary match: keyword must not be inside a larger word
      var text = node.textContent;
      var lowerText = text.toLowerCase();
      var idx = -1;
      var searchFrom = 0;
      while (true) {
        idx = lowerText.indexOf(lowerKeyword, searchFrom);
        if (idx === -1) break;
        var charBefore = idx > 0 ? lowerText[idx - 1] : ' ';
        var charAfter = idx + keyword.length < lowerText.length ? lowerText[idx + keyword.length] : ' ';
        var wordBoundaryBefore = !/[a-z0-9]/.test(charBefore);
        var wordBoundaryAfter = !/[a-z0-9]/.test(charAfter);
        if (wordBoundaryBefore && wordBoundaryAfter) break;
        searchFrom = idx + 1;
      }
      if (idx === -1) continue;

      var before = text.slice(0, idx);
      var match = text.slice(idx, idx + keyword.length);
      var after = text.slice(idx + keyword.length);

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
  var keywordTooltipHideTimer = null;

  function showKeywordTooltip(e) {
    clearTimeout(keywordTooltipHideTimer);
    var el = e.target.closest('.keyword-link') || e.target;
    if (!keywordTooltipEl) {
      keywordTooltipEl = document.createElement('div');
      keywordTooltipEl.className = 'keyword-tooltip';
      document.body.appendChild(keywordTooltipEl);
      // Desktop: keep tooltip open when hovering over it
      keywordTooltipEl.addEventListener('mouseenter', function () {
        clearTimeout(keywordTooltipHideTimer);
      });
      keywordTooltipEl.addEventListener('mouseleave', function () {
        keywordTooltipHideTimer = setTimeout(function () {
          keywordTooltipEl.classList.remove('visible');
        }, 200);
      });
    }

    var html = '<span class="keyword-tooltip-title">' + escHtml(el.dataset.title) + '</span>';
    if (el.dataset.summary)
      html += '<span class="keyword-tooltip-desc">' + escHtml(el.dataset.summary) + '</span>';
    html += '<a href="/topic/' + escHtml(el.dataset.slug) + '" class="explore-btn">Open article &rarr;</a>';
    keywordTooltipEl.innerHTML = html;
    positionTooltip(keywordTooltipEl, el);
    keywordTooltipEl.classList.add('visible');
  }

  function hideKeywordTooltip() {
    keywordTooltipHideTimer = setTimeout(function () {
      if (keywordTooltipEl) keywordTooltipEl.classList.remove('visible');
    }, 200);
  }


  // ==================== RABBIT HOLE (text selection to explore) ====================
  function initRabbitHole() {
    var content = document.querySelector('.topic-content');
    if (!content) return;

    var exploreTooltip = document.createElement('div');
    exploreTooltip.className = 'explore-tooltip';
    exploreTooltip.style.display = 'none';
    document.body.appendChild(exploreTooltip);

    var currentRequest = null;

    function hideExploreTooltip() {
      exploreTooltip.style.display = 'none';
      exploreTooltip.classList.remove('visible');
    }

    function showExploreForSelection(e) {
      // Don't trigger on clicks on links or buttons
      if (e && e.target && (e.target.closest('a') || e.target.closest('button') || e.target.closest('.explore-tooltip'))) return;

      setTimeout(function () {
        var sel = window.getSelection();
        var text = sel ? sel.toString().trim() : '';

        // Must be 2-200 chars, not just whitespace
        if (!text || text.length < 2 || text.length > 200) {
          hideExploreTooltip();
          return;
        }

        // Don't trigger for single common words
        if (text.split(/\s+/).length === 1 && text.length < 4) {
          hideExploreTooltip();
          return;
        }

        // Get selection position
        var range = sel.getRangeAt(0);
        var rect = range.getBoundingClientRect();

        // Show loading state in tooltip
        exploreTooltip.innerHTML =
          '<span class="explore-tooltip-title">' + escHtml(text) + '</span>' +
          '<span class="explore-tooltip-desc">Looking up...</span>';
        exploreTooltip.style.display = 'block';
        positionTooltip(exploreTooltip, { getBoundingClientRect: function () { return rect; } });
        exploreTooltip.classList.add('visible');

        // Abort previous request if still pending
        if (currentRequest) currentRequest.abort();
        var controller = new AbortController();
        currentRequest = controller;

        // Call preview API
        fetch('/api/v1/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text }),
          signal: controller.signal,
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            currentRequest = null;
            var html = '<span class="explore-tooltip-title">' + escHtml(data.title) + '</span>';
            html += '<span class="explore-tooltip-desc">' + escHtml(data.preview) + '</span>';

            if (data.exists) {
              html += '<a href="/topic/' + escHtml(data.slug) + '" class="explore-btn">Open article &rarr;</a>';
            } else {
              html += '<a href="#" class="explore-btn explore-generate" data-title="' + escHtml(data.title) + '" data-slug="' + escHtml(data.slug) + '">Generate article &rarr;</a>';
            }
            exploreTooltip.innerHTML = html;
            positionTooltip(exploreTooltip, { getBoundingClientRect: function () { return rect; } });

            // Bind generate button
            var genBtn = exploreTooltip.querySelector('.explore-generate');
            if (genBtn) {
              genBtn.addEventListener('click', function (ev) {
                ev.preventDefault();
                var title = this.dataset.title;
                var slug = this.dataset.slug;
                // Submit a form to generate-async
                var form = document.createElement('form');
                form.method = 'POST';
                form.action = '/generate-async';
                var inp = document.createElement('input');
                inp.type = 'hidden';
                inp.name = 'title';
                inp.value = title;
                form.appendChild(inp);
                document.body.appendChild(form);
                form.submit();
              });
            }
          })
          .catch(function (err) {
            if (err.name !== 'AbortError') {
              currentRequest = null;
              exploreTooltip.innerHTML =
                '<span class="explore-tooltip-title">' + escHtml(text) + '</span>' +
                '<span class="explore-tooltip-desc">Could not load preview</span>';
            }
          });
      }, 10);
    }

    // Desktop: mouseup on content
    content.addEventListener('mouseup', showExploreForSelection);

    // Hide tooltip when clicking outside
    document.addEventListener('mousedown', function (e) {
      if (!e.target.closest('.explore-tooltip')) {
        hideExploreTooltip();
      }
    });

    // Hide on scroll
    var scrollTimer = null;
    window.addEventListener('scroll', function () {
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(hideExploreTooltip, 100);
    }, { passive: true });
  }

  // ==================== JOURNEY TRACKER ====================
  var JOURNEY_KEY = 'smartipedia-journeys';
  var JOURNEY_SESSION_KEY = 'smartipedia-current-journey';
  var JOURNEY_LAST_SLUG_KEY = 'smartipedia-last-slug';
  var JOURNEY_LAST_NODE_KEY = 'smartipedia-last-node';

  function getJourneys() {
    try { return JSON.parse(localStorage.getItem(JOURNEY_KEY)) || []; }
    catch (e) { return []; }
  }

  function saveJourneys(journeys) {
    localStorage.setItem(JOURNEY_KEY, JSON.stringify(journeys));
  }

  function getCurrentJourneyId() {
    return sessionStorage.getItem(JOURNEY_SESSION_KEY);
  }

  function setCurrentJourneyId(id) {
    sessionStorage.setItem(JOURNEY_SESSION_KEY, id);
  }

  function initJourney() {
    var topicDataEl = document.getElementById('topic-data');
    if (!topicDataEl) return;

    var topicData;
    try { topicData = JSON.parse(topicDataEl.textContent); }
    catch (e) { return; }

    var slug = topicData.slug;
    var title = topicData.title;
    var journeys = getJourneys();
    var journeyId = getCurrentJourneyId();
    var journey = null;
    var nodeId = null;

    // Find or figure out the current journey
    if (journeyId) {
      journey = journeys.find(function (j) { return j.id === journeyId; });
    }

    // Get the previous topic from sessionStorage (reliable, unlike referrer)
    var fromSlug = sessionStorage.getItem(JOURNEY_LAST_SLUG_KEY);
    var fromNodeId = sessionStorage.getItem(JOURNEY_LAST_NODE_KEY);

    if (journey) {
      // Check if we're already in this journey at this slug
      var existingNode = journey.nodes.find(function (n) { return n.slug === slug; });
      if (existingNode) {
        nodeId = existingNode.id;
      } else {
        // Add new node to journey, linked to the page we came from
        var parentId = null;
        if (fromSlug && fromSlug !== slug && fromNodeId) {
          parentId = fromNodeId;
        }
        nodeId = 'n' + Date.now();
        journey.nodes.push({
          id: nodeId,
          slug: slug,
          title: title,
          parentId: parentId,
          timestamp: new Date().toISOString(),
        });
      }
      journey.updatedAt = new Date().toISOString();
    } else {
      // Start a new journey
      nodeId = 'n' + Date.now();
      journey = {
        id: 'j' + Date.now(),
        startedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        nodes: [{
          id: nodeId,
          slug: slug,
          title: title,
          parentId: null,
          timestamp: new Date().toISOString(),
        }],
      };
      journeys.push(journey);
    }

    setCurrentJourneyId(journey.id);
    // Store current slug+nodeId so the NEXT page knows its parent
    sessionStorage.setItem(JOURNEY_LAST_SLUG_KEY, slug);
    sessionStorage.setItem(JOURNEY_LAST_NODE_KEY, nodeId);
    saveJourneys(journeys);

    // Render breadcrumb trail
    renderJourneyBreadcrumb(journey, nodeId);
  }

  function renderJourneyBreadcrumb(journey, currentNodeId) {
    var bar = document.getElementById('journey-bar');
    var trail = document.getElementById('journey-trail');
    if (!bar || !trail || !journey || journey.nodes.length < 2) return;

    // Build path from root to current node
    var nodeMap = {};
    journey.nodes.forEach(function (n) { nodeMap[n.id] = n; });

    var path = [];
    var node = nodeMap[currentNodeId];
    while (node) {
      path.unshift(node);
      node = node.parentId ? nodeMap[node.parentId] : null;
    }

    // If path is just one node, don't show breadcrumb
    if (path.length < 2) return;

    var html = '';
    path.forEach(function (n, i) {
      if (i > 0) html += '<span class="journey-sep">&rsaquo;</span>';
      if (n.id === currentNodeId) {
        html += '<span class="journey-current">' + escHtml(n.title) + '</span>';
      } else {
        html += '<a href="/topic/' + escHtml(n.slug) + '" class="journey-link">' + escHtml(n.title) + '</a>';
      }
    });

    // Add suggested next branches (greyed out)
    var relatedEl = document.getElementById('related-data');
    if (relatedEl) {
      try {
        var allTopics = JSON.parse(relatedEl.textContent);
        var visitedSlugs = {};
        journey.nodes.forEach(function (n) { visitedSlugs[n.slug] = true; });
        var suggestions = allTopics.filter(function (t) {
          return !visitedSlugs[t.slug];
        }).slice(0, 3);
        if (suggestions.length > 0) {
          html += '<span class="journey-sep">&rsaquo;</span>';
          suggestions.forEach(function (s, i) {
            if (i > 0) html += '<span class="journey-suggested-sep">/</span>';
            html += '<a href="/topic/' + escHtml(s.slug) + '" class="journey-suggested">' + escHtml(s.title) + '</a>';
          });
        }
      } catch (e) {}
    }

    trail.innerHTML = html;
    bar.style.display = 'block';
  }

  // ==================== JOURNEY SYNC ====================
  function initJourneySync() {
    // Debounced sync: save journeys to server when logged in
    var syncTimer = null;
    function syncJourneys() {
      clearTimeout(syncTimer);
      syncTimer = setTimeout(function () {
        var journeys = getJourneys();
        fetch('/auth/journeys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ journeys: journeys }),
        }).catch(function () {}); // silent fail
      }, 2000);
    }

    // Check if logged in, then load server journeys on first visit
    fetch('/auth/me').then(function (r) { return r.json(); }).then(function (data) {
      if (!data.logged_in) return;
      // Merge: load server journeys, merge with local, save back
      fetch('/auth/journeys').then(function (r) { return r.json(); }).then(function (serverData) {
        var serverJourneys = serverData.journeys || [];
        var localJourneys = getJourneys();
        if (serverJourneys.length > 0 && localJourneys.length === 0) {
          // First login on this device — restore from server
          saveJourneys(serverJourneys);
        } else if (localJourneys.length > 0) {
          // Merge: local wins for matching IDs, add server-only journeys
          var localIds = {};
          localJourneys.forEach(function (j) { localIds[j.id] = true; });
          serverJourneys.forEach(function (j) {
            if (!localIds[j.id]) localJourneys.push(j);
          });
          saveJourneys(localJourneys);
          syncJourneys(); // push merged result to server
        }
      }).catch(function () {});

      // Watch for journey changes and sync
      var origSave = saveJourneys;
      saveJourneys = function (journeys) {
        origSave(journeys);
        syncJourneys();
      };
    }).catch(function () {});
  }

  // ==================== NOTEPAD DRAWER ====================
  var NOTEPAD_KEY = 'smartipedia-notepad-';
  var NOTEPAD_CLIPPINGS_KEY = 'smartipedia-clippings-';

  function initNotepad() {
    var drawer = document.getElementById('notepad-drawer');
    var panel = document.getElementById('notepad-panel');
    var toggleBtn = document.getElementById('notepad-toggle-btn');
    var closeBtn = document.getElementById('notepad-close-btn');
    var collapsedBar = document.getElementById('notepad-collapsed-bar');
    var editor = document.getElementById('notepad-editor');
    var clippingsList = document.getElementById('notepad-clippings-list');
    var clippingsContainer = document.getElementById('notepad-clippings');
    var copyBtn = document.getElementById('notepad-copy-btn');
    var downloadBtn = document.getElementById('notepad-download-btn');
    var toast = document.getElementById('notepad-toast');

    if (!drawer || !editor) return;

    var journeyId = getCurrentJourneyId();

    var DRAWER_STATE_KEY = 'smartipedia-drawer-open';

    // ---- Toggle open/close ----
    function openDrawer() {
      drawer.classList.add('open');
      sessionStorage.setItem(DRAWER_STATE_KEY, '1');
      editor.focus();
    }
    function closeDrawer() {
      drawer.classList.remove('open');
      sessionStorage.setItem(DRAWER_STATE_KEY, '0');
    }
    function toggleDrawer() {
      if (drawer.classList.contains('open')) closeDrawer();
      else openDrawer();
    }

    // Restore drawer state from previous page
    if (sessionStorage.getItem(DRAWER_STATE_KEY) === '1') {
      drawer.classList.add('open');
    }

    if (toggleBtn) toggleBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleDrawer(); });
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    if (collapsedBar) collapsedBar.addEventListener('click', function (e) {
      if (e.target.closest('.notepad-toggle-btn')) return;
      if (e.target.closest('a')) return; // let breadcrumb/journey links navigate
      toggleDrawer();
    });

    // Cmd+J / Ctrl+J
    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'j') {
        e.preventDefault();
        toggleDrawer();
      }
      // Esc to close drawer if open
      if (e.key === 'Escape' && drawer.classList.contains('open')) {
        closeDrawer();
      }
    });

    // ---- Format buttons ----
    document.querySelectorAll('.notepad-fmt-btn').forEach(function (btn) {
      btn.addEventListener('mousedown', function (e) {
        e.preventDefault(); // prevent focus loss
        var cmd = btn.dataset.cmd;
        document.execCommand(cmd, false, null);
        updateFormatButtons();
      });
    });

    function updateFormatButtons() {
      document.querySelectorAll('.notepad-fmt-btn').forEach(function (btn) {
        var cmd = btn.dataset.cmd;
        btn.classList.toggle('active', document.queryCommandState(cmd));
      });
    }
    editor.addEventListener('keyup', updateFormatButtons);
    editor.addEventListener('mouseup', updateFormatButtons);

    // ---- Persistence (per journey) ----
    function getNoteKey() {
      var jid = getCurrentJourneyId();
      return jid ? NOTEPAD_KEY + jid : NOTEPAD_KEY + 'global';
    }
    function getClippingsKey() {
      var jid = getCurrentJourneyId();
      return jid ? NOTEPAD_CLIPPINGS_KEY + jid : NOTEPAD_CLIPPINGS_KEY + 'global';
    }

    // Load saved content
    var savedContent = localStorage.getItem(getNoteKey());
    if (savedContent) editor.innerHTML = savedContent;

    // Save on input (debounced)
    var saveTimer = null;
    editor.addEventListener('input', function () {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(function () {
        localStorage.setItem(getNoteKey(), editor.innerHTML);
      }, 300);
    });

    // ---- Clippings ----
    function getClippings() {
      try { return JSON.parse(localStorage.getItem(getClippingsKey())) || []; }
      catch (e) { return []; }
    }
    function saveClippings(clips) {
      localStorage.setItem(getClippingsKey(), JSON.stringify(clips));
    }

    function insertIntoEditor(text) {
      editor.focus();
      // Insert at end
      var sel = window.getSelection();
      var range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
      // Insert as a new block
      document.execCommand('insertHTML', false, '<div>' + escHtml(text) + '</div>');
      // Save
      localStorage.setItem(getNoteKey(), editor.innerHTML);
    }

    function renderClippings() {
      var clips = getClippings();
      if (!clippingsList) return;
      if (clips.length === 0) {
        clippingsList.innerHTML = '<div style="padding:0.5rem;color:var(--text-light);font-size:0.78rem;">Copy text on any page to capture it here.</div>';
        return;
      }
      clippingsList.innerHTML = '';
      clips.forEach(function (clip, i) {
        var div = document.createElement('div');
        div.className = 'notepad-clipping';
        div.title = 'Click to insert into notes';

        var textSpan = document.createElement('span');
        textSpan.className = 'notepad-clipping-text';
        textSpan.textContent = clip.text;
        div.appendChild(textSpan);

        if (clip.source) {
          var link = document.createElement('a');
          link.className = 'notepad-clipping-source';
          link.href = '/topic/' + clip.sourceSlug;
          link.textContent = clip.source;
          link.addEventListener('click', function (e) { e.stopPropagation(); });
          div.appendChild(link);
        }

        var removeBtn = document.createElement('button');
        removeBtn.className = 'notepad-clipping-remove';
        removeBtn.textContent = '\u00d7';
        removeBtn.title = 'Remove';
        removeBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          var c = getClippings();
          c.splice(i, 1);
          saveClippings(c);
          renderClippings();
        });
        div.appendChild(removeBtn);

        // Click to insert into editor
        div.addEventListener('click', function () {
          insertIntoEditor(clip.text);
          showToast('Inserted into notes');
        });

        clippingsList.appendChild(div);
      });
    }
    renderClippings();

    // ---- Copy intercept: capture text copied from topic content ----
    document.addEventListener('copy', function () {
      var sel = window.getSelection();
      var text = sel ? sel.toString().trim() : '';
      if (!text || text.length < 3) return;

      // Only capture from topic content area
      var topicContent = document.querySelector('.topic-content');
      if (!topicContent) return;
      var node = sel.anchorNode;
      if (!node) return;
      var el = node.nodeType === 3 ? node.parentElement : node;
      if (!topicContent.contains(el)) return;

      // Get current topic info
      var topicDataEl = document.getElementById('topic-data');
      var sourceName = '';
      var sourceSlug = '';
      if (topicDataEl) {
        try {
          var td = JSON.parse(topicDataEl.textContent);
          sourceName = td.title || '';
          sourceSlug = td.slug || '';
        } catch (e) {}
      }

      var clips = getClippings();
      clips.push({ text: text.slice(0, 500), source: sourceName, sourceSlug: sourceSlug, ts: Date.now() });
      saveClippings(clips);
      renderClippings();
      showToast('Clipped to notepad');
    });

    // ---- Toast ----
    var toastTimer = null;
    function showToast(msg) {
      if (!toast) return;
      toast.textContent = msg;
      toast.classList.add('visible');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function () {
        toast.classList.remove('visible');
      }, 2000);
    }

    // ---- Export: Copy to clipboard ----
    if (copyBtn) copyBtn.addEventListener('click', function () {
      var md = htmlToMarkdown(editor);
      var clips = getClippings();
      if (clips.length > 0) {
        md += '\n\n---\n\n## Clippings\n\n';
        clips.forEach(function (c) {
          md += '> ' + c.text.replace(/\n/g, '\n> ') + '\n';
          if (c.source) md += '> — [' + c.source + '](/topic/' + c.sourceSlug + ')\n';
          md += '\n';
        });
      }
      navigator.clipboard.writeText(md).then(function () {
        showToast('Copied to clipboard');
      });
    });

    // ---- Export: Download as .md ----
    if (downloadBtn) downloadBtn.addEventListener('click', function () {
      var md = htmlToMarkdown(editor);
      var clips = getClippings();
      if (clips.length > 0) {
        md += '\n\n---\n\n## Clippings\n\n';
        clips.forEach(function (c) {
          md += '> ' + c.text.replace(/\n/g, '\n> ') + '\n';
          if (c.source) md += '> — [' + c.source + '](/topic/' + c.sourceSlug + ')\n';
          md += '\n';
        });
      }
      var blob = new Blob([md], { type: 'text/markdown' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      var dateStr = new Date().toISOString().slice(0, 10);
      a.download = 'smartipedia-notes-' + dateStr + '.md';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('Downloaded .md file');
    });

    // ---- New journey button ----
    var newJourneyBtn = document.getElementById('notepad-new-journey');
    if (newJourneyBtn) newJourneyBtn.addEventListener('click', function () {
      sessionStorage.removeItem(JOURNEY_SESSION_KEY);
      sessionStorage.removeItem(JOURNEY_LAST_SLUG_KEY);
      sessionStorage.removeItem(JOURNEY_LAST_NODE_KEY);
      updateNotepadJourneyTrail();
      showToast('New journey started — visit a topic to begin');
    });

    // ---- Journey trail in collapsed bar ----
    updateNotepadJourneyTrail();
  }

  function updateNotepadJourneyTrail() {
    var trail = document.getElementById('notepad-journey-trail');
    if (!trail) return;

    var journeyId = getCurrentJourneyId();
    if (!journeyId) {
      trail.innerHTML = '<span style="color:var(--text-light);font-size:0.82rem;">Start exploring to begin a journey</span>';
      return;
    }

    var journeys = getJourneys();
    var journey = journeys.find(function (j) { return j.id === journeyId; });
    if (!journey || journey.nodes.length === 0) {
      trail.innerHTML = '<span style="color:var(--text-light);font-size:0.82rem;">Start exploring to begin a journey</span>';
      return;
    }

    // Determine current slug from the page URL
    var currentSlug = '';
    var pathMatch = window.location.pathname.match(/^\/topic\/(.+)$/);
    if (pathMatch) currentSlug = decodeURIComponent(pathMatch[1]);

    var nodeMap = {};
    journey.nodes.forEach(function (n) { nodeMap[n.id] = n; });

    // Build children map: parentId -> [child nodes], sorted by timestamp (most recent last)
    var childrenMap = {};
    journey.nodes.forEach(function (n) {
      if (n.parentId) {
        if (!childrenMap[n.parentId]) childrenMap[n.parentId] = [];
        childrenMap[n.parentId].push(n);
      }
    });
    // Sort children by timestamp so most recent branch is last
    Object.keys(childrenMap).forEach(function (pid) {
      childrenMap[pid].sort(function (a, b) {
        return (a.timestamp || '').localeCompare(b.timestamp || '');
      });
    });

    // Find the node matching current slug
    var currentNode = null;
    if (currentSlug) {
      currentNode = journey.nodes.find(function (n) { return n.slug === currentSlug; });
    }
    if (!currentNode) currentNode = journey.nodes[journey.nodes.length - 1];

    // Build path from root to current (backward walk)
    var backPath = [];
    var node = currentNode;
    while (node) {
      backPath.unshift(node);
      node = node.parentId ? nodeMap[node.parentId] : null;
    }

    // Build forward path from current (follow most recent child at each step)
    var forwardPath = [];
    var fwd = currentNode;
    while (true) {
      var children = childrenMap[fwd.id];
      if (!children || children.length === 0) break;
      // Pick the most recently visited child (last after sort)
      fwd = children[children.length - 1];
      forwardPath.push(fwd);
    }

    // Render: [...backPath] [CURRENT] [...forwardPath faded]
    var totalLen = backPath.length + forwardPath.length;
    var html = '';

    // Truncate back path if total is too long (keep last 4 back nodes + all forward)
    var backStart = Math.max(0, backPath.length - 4);
    if (backStart > 0) html += '<span style="color:var(--text-light);">&hellip;</span><span class="notepad-sep">&rsaquo;</span>';

    for (var i = backStart; i < backPath.length; i++) {
      if (i > backStart) html += '<span class="notepad-sep">&rsaquo;</span>';
      var n = backPath[i];
      if (n.slug === currentSlug) {
        html += '<span class="notepad-current">' + escHtml(n.title) + '</span>';
      } else {
        html += '<a href="/topic/' + escHtml(n.slug) + '" class="notepad-visited">' + escHtml(n.title) + '</a>';
      }
    }

    // Forward path (faded, clickable — "resume" nodes)
    for (var j = 0; j < forwardPath.length; j++) {
      html += '<span class="notepad-sep">&rsaquo;</span>';
      var f = forwardPath[j];
      html += '<a href="/topic/' + escHtml(f.slug) + '" class="notepad-forward">' + escHtml(f.title) + '</a>';
    }

    trail.innerHTML = html;
  }

  // Simple HTML to Markdown converter for the editor content
  function htmlToMarkdown(editorEl) {
    var html = editorEl.innerHTML;
    // Convert common HTML to markdown
    var md = html
      .replace(/<b>|<strong>/gi, '**').replace(/<\/b>|<\/strong>/gi, '**')
      .replace(/<i>|<em>/gi, '*').replace(/<\/i>|<\/em>/gi, '*')
      .replace(/<u>/gi, '__').replace(/<\/u>/gi, '__')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<div>/gi, '\n').replace(/<\/div>/gi, '')
      .replace(/<p>/gi, '\n').replace(/<\/p>/gi, '')
      .replace(/<[^>]+>/g, '') // strip remaining tags
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/^\n+/, '') // trim leading newlines
      .replace(/\n{3,}/g, '\n\n'); // collapse excessive newlines
    return md;
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


// ==================== AI CHAT (Tab to toggle) ====================
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var chatPanel = document.getElementById('ai-chat-panel');
    var chatInput = document.getElementById('ai-chat-input');
    var chatSend = document.getElementById('ai-chat-send');
    var chatMessages = document.getElementById('ai-chat-messages');
    var chatClose = document.getElementById('ai-chat-close');
    var editor = document.getElementById('notepad-editor');
    var notepadBody = document.querySelector('.notepad-body');
    var drawer = document.getElementById('notepad-drawer');

    if (!chatPanel || !chatInput || !editor) return;

    var chatHistory = []; // [{role, content}]
    var chatActive = false;

    function getPageContext() {
      // Grab visible article content
      var article = document.querySelector('.topic-content') || document.querySelector('.content') || document.querySelector('main');
      if (!article) return document.title;
      var text = article.innerText || article.textContent || '';
      return text.substring(0, 6000);
    }

    function getJourneyContext() {
      var trail = document.getElementById('notepad-journey-trail');
      if (!trail) return '';
      return trail.innerText || trail.textContent || '';
    }

    function showChat() {
      chatActive = true;
      chatPanel.style.display = 'flex';
      if (notepadBody) notepadBody.style.display = 'none';
      // Make sure drawer is open
      if (drawer && !drawer.classList.contains('open')) {
        drawer.classList.add('open');
        sessionStorage.setItem('smartipedia-drawer-open', '1');
      }
      chatInput.focus();
    }

    function hideChat() {
      chatActive = false;
      chatPanel.style.display = 'none';
      if (notepadBody) notepadBody.style.display = '';
      editor.focus();
    }

    function appendMessage(role, text) {
      var div = document.createElement('div');
      div.className = 'ai-chat-msg ai-chat-' + role;
      div.textContent = text;
      chatMessages.appendChild(div);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      return div;
    }

    async function sendMessage() {
      var msg = chatInput.value.trim();
      if (!msg) return;

      chatInput.value = '';
      appendMessage('user', msg);
      chatSend.disabled = true;

      var loadingDiv = appendMessage('assistant', 'Thinking');
      loadingDiv.classList.add('ai-chat-loading');

      try {
        var resp = await fetch('/api/v1/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: msg,
            history: chatHistory.slice(-20),
            page_context: getPageContext(),
            journey_context: getJourneyContext(),
          }),
        });
        var data = await resp.json();
        loadingDiv.classList.remove('ai-chat-loading');
        loadingDiv.textContent = data.reply || 'No response.';
        chatHistory.push({ role: 'user', content: msg });
        chatHistory.push({ role: 'assistant', content: data.reply || '' });
      } catch (err) {
        loadingDiv.classList.remove('ai-chat-loading');
        loadingDiv.textContent = 'Failed to reach AI. Try again.';
      }
      chatSend.disabled = false;
      chatInput.focus();
    }

    chatSend.addEventListener('click', sendMessage);
    chatInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
      // Tab to go back to notes
      if (e.key === 'Tab') {
        e.preventDefault();
        hideChat();
      }
    });

    if (chatClose) chatClose.addEventListener('click', hideChat);

    // Tab key in notepad editor → open chat
    editor.addEventListener('keydown', function (e) {
      if (e.key === 'Tab') {
        e.preventDefault();
        showChat();
      }
    });

    // Global Tab toggle: open chat from drawer, close chat from anywhere in chat panel
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Tab' || !drawer || !drawer.classList.contains('open')) return;
      if (chatActive) {
        // Tab anywhere while chat is open → back to notes
        if (chatPanel.contains(document.activeElement) || document.activeElement === document.body) {
          e.preventDefault();
          hideChat();
        }
      } else {
        // Tab in drawer → open chat
        if (drawer.contains(document.activeElement) || document.activeElement === editor) {
          e.preventDefault();
          showChat();
        }
      }
    });
  });
})();


  // ==================== GENERATE LOADING STATE ====================
  document.addEventListener('DOMContentLoaded', function () {
    var overlay = document.getElementById('generating-overlay');
    if (!overlay) return;

    // Intercept all forms that POST to /generate
    document.querySelectorAll('form[action="/generate"], form[action="/generate-async"]').forEach(function (form) {
      form.addEventListener('submit', function () {
        overlay.classList.add('active');
        // Disable all buttons and inputs to prevent double-clicks
        document.querySelectorAll('button, input[type="submit"], a.btn, a.nav-btn').forEach(function (el) {
          el.style.pointerEvents = 'none';
          el.style.opacity = '0.5';
        });
      });
    });
  });
