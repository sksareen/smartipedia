/* Knowledge graph explorer — category constellations + inspector. */
(function () {
  var DEFAULT_LIMIT = 180;
  var MORE_LIMIT = 400;

  var canvas = document.getElementById("graph-canvas");
  var stage = document.getElementById("graph-stage");
  var searchInput = document.getElementById("graph-search");
  var suggestEl = document.getElementById("graph-suggest");
  var toggleBtn = document.getElementById("graph-toggle");
  var countEl = document.getElementById("graph-count");
  var legendEl = document.getElementById("graph-legend");
  var hintEl = document.getElementById("graph-hint");
  var inspector = document.getElementById("graph-inspector");
  var inspClose = document.getElementById("graph-inspector-close");
  var inspCat = document.getElementById("graph-inspector-cat");
  var inspTitle = document.getElementById("graph-inspector-title");
  var inspSummary = document.getElementById("graph-inspector-summary");
  var inspMeta = document.getElementById("graph-inspector-meta");
  var inspNeighbors = document.getElementById("graph-inspector-neighbors");
  var inspOpen = document.getElementById("graph-inspector-open");
  if (!canvas || !stage) return;

  var ctx = canvas.getContext("2d");
  var nodes = [];
  var edges = [];
  var nodeMap = {};
  var adj = {};
  var hovered = null;
  var selected = null;
  var dragNode = null;
  var didDrag = false;
  var scale = 1;
  var panX = 0;
  var panY = 0;
  var isPanning = false;
  var lastMouse = { x: 0, y: 0 };
  var searchQuery = "";
  var activeCats = {};
  var showingMore = false;
  var labelMinDegree = 1;
  var energy = 1;
  var cssW = 0;
  var cssH = 0;
  var fly = null;
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var CATEGORY_COLORS = {
    Science: "#2563eb",
    Technology: "#7c3aed",
    Mathematics: "#db2777",
    History: "#b45309",
    Society: "#059669",
    Arts: "#dc2626",
    Philosophy: "#4f46e5",
    Health: "#0d9488",
    Economics: "#65a30d",
    Geography: "#0284c7",
    Law: "#9333ea",
    Engineering: "#ea580c",
    "": "#6b7280",
  };

  function colorOf(n) {
    return CATEGORY_COLORS[n.category] || CATEGORY_COLORS[""];
  }

  function isDark() {
    return document.documentElement.classList.contains("dark");
  }

  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    cssW = stage.clientWidth;
    cssH = stage.clientHeight;
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener("resize", function () {
    var prevW = cssW;
    var prevH = cssH;
    resize();
    if (nodes.length && (Math.abs(cssW - prevW) > 40 || Math.abs(cssH - prevH) > 40)) {
      fitView(true);
    }
  });
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      var prevW = cssW;
      var prevH = cssH;
      resize();
      if (nodes.length && prevW < 80 && cssW >= 80) fitView(true);
    }).observe(stage);
  }

  function neighborsOf(id) {
    return adj[id] || [];
  }

  function isLinked(a, b) {
    if (!a || !b) return false;
    var list = adj[a.id] || [];
    return list.indexOf(b.id) !== -1;
  }

  function catVisible(n) {
    var keys = Object.keys(activeCats);
    if (!keys.length) return true;
    return !!activeCats[n.category || ""];
  }

  function matchesSearch(n) {
    if (!searchQuery) return true;
    return n.title.toLowerCase().indexOf(searchQuery) !== -1;
  }

  function isDim(n) {
    if (!catVisible(n)) return true;
    if (selected) return false;
    if (searchQuery && !matchesSearch(n)) return true;
    return false;
  }

  function hopOf(n) {
    if (!selected) return 0;
    if (n.id === selected.id) return 0;
    if (isLinked(selected, n)) return 1;
    var nbrs = neighborsOf(selected.id);
    for (var i = 0; i < nbrs.length; i++) {
      var mid = nodeMap[nbrs[i]];
      if (mid && isLinked(mid, n)) return 2;
    }
    return 3;
  }

  function shortTitle(t) {
    t = t || "";
    return t.length > 26 ? t.slice(0, 24) + "…" : t;
  }

  function loadGraph(limit) {
    if (countEl) countEl.textContent = "Loading the atlas…";
    var url = "/api/v1/graph?limit=" + (limit || DEFAULT_LIMIT);
    fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("graph " + r.status);
        return r.json();
      })
      .then(buildGraph)
      .catch(function () {
        if (countEl) countEl.textContent = "Couldn’t load the graph.";
      });
  }

  function buildGraph(data) {
    resize();
    nodeMap = {};
    adj = {};
    var cats = {};
    (data.nodes || []).forEach(function (n) {
      cats[n.category || ""] = (cats[n.category || ""] || 0) + 1;
    });
    var catNames = Object.keys(cats).sort();
    var R = Math.min(cssW, cssH) * 0.4;
    var centers = {};
    catNames.forEach(function (c, i) {
      var a = (i / Math.max(catNames.length, 1)) * Math.PI * 2 - Math.PI / 2;
      centers[c] = {
        x: cssW / 2 + Math.cos(a) * R,
        y: cssH / 2 + Math.sin(a) * R,
      };
    });

    var idxInCat = {};
    nodes = (data.nodes || []).map(function (n) {
      var cat = n.category || "";
      var i = idxInCat[cat] || 0;
      idxInCat[cat] = i + 1;
      var c = centers[cat] || { x: cssW / 2, y: cssH / 2 };
      var ring = 36 + Math.sqrt(i) * 22;
      var a = i * 2.39996;
      var x = c.x + Math.cos(a) * ring;
      var y = c.y + Math.sin(a) * ring;
      return {
        id: n.id,
        title: n.title,
        summary: n.summary || "",
        views: n.views || 0,
        category: cat,
        x: x,
        y: y,
        homeX: x,
        homeY: y,
        vx: 0,
        vy: 0,
        radius: 6,
        degree: 0,
      };
    });
    nodes.forEach(function (n) {
      nodeMap[n.id] = n;
    });

    edges = (data.edges || []).filter(function (e) {
      return nodeMap[e.source] && nodeMap[e.target];
    });
    edges.forEach(function (e) {
      if (!adj[e.source]) adj[e.source] = [];
      if (!adj[e.target]) adj[e.target] = [];
      adj[e.source].push(e.target);
      adj[e.target].push(e.source);
    });
    nodes.forEach(function (n) {
      n.degree = (adj[n.id] || []).length;
      n.radius = Math.max(6, Math.min(18, 6 + Math.sqrt(n.degree) * 2.4 + Math.sqrt(n.views) * 0.4));
    });

    var degrees = nodes.map(function (n) { return n.degree; }).sort(function (a, b) { return b - a; });
    labelMinDegree = degrees.length ? Math.max(degrees[Math.min(11, degrees.length - 1)] || 2, 2) : 2;

    if (countEl) {
      var total = data.total || nodes.length;
      countEl.textContent = data.limited
        ? nodes.length + " of " + total + " topics"
        : nodes.length + " topics";
    }
    renderLegend();
    selected = null;
    closeInspector();
    energy = reducedMotion ? 0 : 1;
    fitView(true);
    if (location.hash) {
      var want = location.hash.slice(1);
      var hit = nodeMap[want];
      if (hit) selectNode(hit, true);
    }
  }

  function renderLegend() {
    if (!legendEl) return;
    var present = {};
    nodes.forEach(function (n) {
      if (n.category) present[n.category] = true;
    });
    var cats = Object.keys(present).sort();
    legendEl.innerHTML = cats
      .map(function (c) {
        var on = !Object.keys(activeCats).length || activeCats[c];
        return (
          '<button type="button" class="graph-legend-item' +
          (on ? " is-on" : "") +
          '" data-cat="' +
          c +
          '"><span class="graph-legend-dot" style="background:' +
          (CATEGORY_COLORS[c] || CATEGORY_COLORS[""]) +
          '"></span>' +
          c +
          "</button>"
        );
      })
      .join("");
  }

  if (legendEl) {
    legendEl.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-cat]");
      if (!btn) return;
      var cat = btn.getAttribute("data-cat");
      if (activeCats[cat] && Object.keys(activeCats).length === 1) {
        activeCats = {};
      } else if (!Object.keys(activeCats).length) {
        activeCats = {};
        activeCats[cat] = true;
      } else if (activeCats[cat]) {
        delete activeCats[cat];
      } else {
        activeCats[cat] = true;
      }
      renderLegend();
      fitView(false);
    });
  }

  if (toggleBtn) {
    toggleBtn.addEventListener("click", function () {
      showingMore = !showingMore;
      toggleBtn.textContent = showingMore ? "Fewer topics" : "More topics";
      loadGraph(showingMore ? MORE_LIMIT : DEFAULT_LIMIT);
    });
  }

  function flyTo(n) {
    var pts = [n].concat(
      neighborsOf(n.id).map(function (id) { return nodeMap[id]; }).filter(Boolean)
    );
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    pts.forEach(function (p) {
      minX = Math.min(minX, p.x - p.radius);
      minY = Math.min(minY, p.y - p.radius);
      maxX = Math.max(maxX, p.x + p.radius);
      maxY = Math.max(maxY, p.y + p.radius);
    });
    var pad = 90;
    var w = maxX - minX || 1;
    var h = maxY - minY || 1;
    var targetScale = Math.min((cssW - pad * 2) / w, (cssH - pad * 2) / h, 2.4);
    targetScale = Math.max(1.05, targetScale);
    var tx = cssW / 2 - ((minX + maxX) / 2) * targetScale;
    var ty = cssH / 2 - ((minY + maxY) / 2) * targetScale;
    if (reducedMotion) {
      scale = targetScale;
      panX = tx;
      panY = ty;
      return;
    }
    fly = {
      t: 0,
      sx: panX,
      sy: panY,
      ss: scale,
      tx: tx,
      ty: ty,
      ts: targetScale,
    };
  }

  function fitView(instant) {
    if (!nodes.length) {
      scale = 1;
      panX = 0;
      panY = 0;
      return;
    }
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(function (n) {
      if (isDim(n)) return;
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x);
      maxY = Math.max(maxY, n.y);
    });
    if (!isFinite(minX)) {
      nodes.forEach(function (n) {
        minX = Math.min(minX, n.x);
        minY = Math.min(minY, n.y);
        maxX = Math.max(maxX, n.x);
        maxY = Math.max(maxY, n.y);
      });
    }
    var pad = 72;
    var w = maxX - minX || 1;
    var h = maxY - minY || 1;
    var next = Math.min((cssW - pad * 2) / w, (cssH - pad * 2) / h, 2.2);
    next = Math.max(0.25, next);
    var tx = cssW / 2 - ((minX + maxX) / 2) * next;
    var ty = cssH / 2 - ((minY + maxY) / 2) * next;
    if (instant || reducedMotion) {
      scale = next;
      panX = tx;
      panY = ty;
      return;
    }
    fly = { t: 0, sx: panX, sy: panY, ss: scale, tx: tx, ty: ty, ts: next };
  }

  function selectNode(n, move) {
    selected = n;
    if (move) flyTo(n);
    if (n) {
      history.replaceState(null, "", "#" + n.id);
      openInspector(n);
    } else {
      if (location.hash) history.replaceState(null, "", location.pathname);
      closeInspector();
    }
  }

  function openInspector(n) {
    if (!inspector) return;
    inspector.hidden = false;
    inspCat.textContent = n.category || "Uncategorized";
    inspTitle.textContent = n.title;
    inspSummary.textContent = n.summary || "No summary yet.";
    var deg = n.degree;
    inspMeta.textContent =
      deg + (deg === 1 ? " connection" : " connections") +
      " · " + n.views + (n.views === 1 ? " view" : " views");
    inspOpen.href = "/topic/" + n.id;
    var neigh = neighborsOf(n.id)
      .map(function (id) { return nodeMap[id]; })
      .filter(Boolean)
      .sort(function (a, b) { return b.degree - a.degree; })
      .slice(0, 8);
    inspNeighbors.innerHTML = neigh
      .map(function (m) {
        return '<button type="button" data-id="' + m.id + '">' + escapeHtml(m.title) + "</button>";
      })
      .join("");
  }

  function closeInspector() {
    if (inspector) inspector.hidden = true;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  if (inspClose) {
    inspClose.addEventListener("click", function () {
      selectNode(null);
    });
  }
  if (inspNeighbors) {
    inspNeighbors.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-id]");
      if (!btn) return;
      var n = nodeMap[btn.getAttribute("data-id")];
      if (n) selectNode(n, true);
    });
  }

  function renderSuggestions() {
    if (!suggestEl) return;
    if (!searchQuery) {
      suggestEl.hidden = true;
      suggestEl.innerHTML = "";
      return;
    }
    var hits = nodes.filter(matchesSearch).slice(0, 8);
    if (!hits.length) {
      suggestEl.hidden = true;
      return;
    }
    suggestEl.innerHTML = hits
      .map(function (n) {
        return (
          '<button type="button" data-id="' +
          n.id +
          '"><span>' +
          escapeHtml(n.title) +
          "</span><em>" +
          escapeHtml(n.category || "") +
          "</em></button>"
        );
      })
      .join("");
    suggestEl.hidden = false;
  }

  if (searchInput) {
    searchInput.addEventListener("input", function () {
      searchQuery = searchInput.value.trim().toLowerCase();
      renderSuggestions();
    });
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        searchInput.blur();
        suggestEl.hidden = true;
        return;
      }
      if (e.key === "Enter" && searchQuery) {
        var hit = nodes.find(matchesSearch);
        if (hit) {
          searchQuery = "";
          selectNode(hit, true);
          suggestEl.hidden = true;
        }
      }
    });
  }
  if (suggestEl) {
    suggestEl.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-id]");
      if (!btn) return;
      var n = nodeMap[btn.getAttribute("data-id")];
      if (n) {
        searchInput.value = n.title;
        searchQuery = "";
        selectNode(n, true);
        suggestEl.hidden = true;
      }
    });
  }

  document.getElementById("graph-zoom-in").addEventListener("click", function () {
    zoomAt(cssW / 2, cssH / 2, 1.18);
  });
  document.getElementById("graph-zoom-out").addEventListener("click", function () {
    zoomAt(cssW / 2, cssH / 2, 0.85);
  });
  document.getElementById("graph-fit").addEventListener("click", function () {
    fitView(false);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") selectNode(null);
  });

  function zoomAt(mx, my, factor) {
    var next = scale * factor;
    if (next < 0.18 || next > 5) return;
    panX = mx - (mx - panX) * factor;
    panY = my - (my - panY) * factor;
    scale = next;
    energy = Math.max(energy, 0.15);
  }

  function tickPhysics() {
    if (reducedMotion || !nodes.length) return;
    var active = energy >= 0.02;
    if (active) {
      var cell = 88;
      var buckets = {};
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var key = ((n.x / cell) | 0) + ":" + ((n.y / cell) | 0);
        if (!buckets[key]) buckets[key] = [];
        buckets[key].push(n);
      }
      var repulsion = 1600 * energy;
      Object.keys(buckets).forEach(function (key) {
        var parts = key.split(":");
        var cx = +parts[0];
        var cy = +parts[1];
        var group = [];
        for (var ox = -1; ox <= 1; ox++) {
          for (var oy = -1; oy <= 1; oy++) {
            var near = buckets[cx + ox + ":" + (cy + oy)];
            if (near) group = group.concat(near);
          }
        }
        var mine = buckets[key];
        for (var a = 0; a < mine.length; a++) {
          for (var b = 0; b < group.length; b++) {
            var u = mine[a];
            var v = group[b];
            if (u.id >= v.id) continue;
            var dx = v.x - u.x;
            var dy = v.y - u.y;
            var dist = Math.sqrt(dx * dx + dy * dy) || 0.1;
            if (dist > 150) continue;
            var force = repulsion / (dist * dist);
            var fx = (dx / dist) * force;
            var fy = (dy / dist) * force;
            u.vx -= fx;
            u.vy -= fy;
            v.vx += fx;
            v.vy += fy;
          }
        }
      });

      for (var e = 0; e < edges.length; e++) {
        var s = nodeMap[edges[e].source];
        var t = nodeMap[edges[e].target];
        if (!s || !t) continue;
        var same = s.category === t.category;
        var attraction = (same ? 0.016 : 0.004) * energy;
        var rest = same ? 78 : 160;
        var dx = t.x - s.x;
        var dy = t.y - s.y;
        var dist = Math.sqrt(dx * dx + dy * dy) || 0.1;
        var force = (dist - rest) * attraction;
        var fx = (dx / dist) * force;
        var fy = (dy / dist) * force;
        s.vx += fx;
        s.vy += fy;
        t.vx -= fx;
        t.vy -= fy;
      }
    }

    var damp = active ? 0.78 : 0.86;
    var home = active ? 0.018 : 0.008;
    for (var k = 0; k < nodes.length; k++) {
      var p = nodes[k];
      if (p === dragNode) continue;
      if (p.homeX !== undefined) {
        p.vx += (p.homeX - p.x) * home;
        p.vy += (p.homeY - p.y) * home;
      }
      p.vx *= damp;
      p.vy *= damp;
      p.x += p.vx;
      p.y += p.vy;
    }
    if (active) energy *= 0.988;
  }

  function stepFly() {
    if (!fly) return;
    fly.t += 0.08;
    var u = fly.t >= 1 ? 1 : fly.t;
    var ease = 1 - Math.pow(1 - u, 3);
    panX = fly.sx + (fly.tx - fly.sx) * ease;
    panY = fly.sy + (fly.ty - fly.sy) * ease;
    scale = fly.ss + (fly.ts - fly.ss) * ease;
    if (u >= 1) fly = null;
  }

  function draw() {
    ctx.clearRect(0, 0, cssW, cssH);
    ctx.save();
    ctx.translate(panX, panY);
    ctx.scale(scale, scale);

    var dark = isDark();
    var edgeHot = dark ? "rgba(147,197,253,0.75)" : "rgba(37,99,235,0.55)";
    var text = dark ? "#f3f4f6" : "#111827";
    var textMute = dark ? "#9ca3af" : "#4b5563";
    var labelBg = dark ? "rgba(17,17,17,0.86)" : "rgba(255,255,255,0.92)";
    var focus = selected || hovered;

    var centroids = {};
    for (var ci = 0; ci < nodes.length; ci++) {
      var cn = nodes[ci];
      if (isDim(cn) || !cn.category) continue;
      if (!centroids[cn.category]) centroids[cn.category] = { x: 0, y: 0, n: 0 };
      centroids[cn.category].x += cn.x;
      centroids[cn.category].y += cn.y;
      centroids[cn.category].n += 1;
    }
    var gx = 0, gy = 0, gn = 0;
    Object.keys(centroids).forEach(function (cat) {
      gx += centroids[cat].x;
      gy += centroids[cat].y;
      gn += centroids[cat].n;
    });
    gx = gn ? gx / gn : 0;
    gy = gn ? gy / gn : 0;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    Object.keys(centroids).forEach(function (cat) {
      var c = centroids[cat];
      if (c.n < 3) return;
      var mx = c.x / c.n;
      var my = c.y / c.n;
      var dx = mx - gx;
      var dy = my - gy;
      var len = Math.sqrt(dx * dx + dy * dy) || 1;
      ctx.globalAlpha = selected ? 0.14 : 0.28;
      ctx.fillStyle = CATEGORY_COLORS[cat] || CATEGORY_COLORS[""];
      ctx.font = "italic " + Math.max(16, 24 / Math.sqrt(scale)) + "px 'Libre Baskerville', Georgia, serif";
      ctx.fillText(cat, mx + (dx / len) * 64, my + (dy / len) * 64);
    });
    ctx.globalAlpha = 1;

    for (var i = 0; i < edges.length; i++) {
      var e = edges[i];
      var s = nodeMap[e.source];
      var t = nodeMap[e.target];
      if (!s || !t) continue;
      if (isDim(s) && isDim(t)) continue;
      var hot = focus && (e.source === focus.id || e.target === focus.id);
      var same = s.category === t.category;
      if (selected && !hot) {
        ctx.globalAlpha = 0.04;
      } else {
        ctx.globalAlpha = same ? 0.28 : 0.1;
      }
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.strokeStyle = hot ? edgeHot : (dark ? "rgba(255,255,255,0.55)" : "rgba(17,17,17,0.45)");
      ctx.lineWidth = (hot ? 2 : same ? 1.15 : 0.7) / scale;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    var labelQueue = nodes.slice().sort(function (a, b) {
      var ap = (selected && a.id === selected.id ? 1000 : 0) + (hovered && a.id === hovered.id ? 500 : 0) + a.degree;
      var bp = (selected && b.id === selected.id ? 1000 : 0) + (hovered && b.id === hovered.id ? 500 : 0) + b.degree;
      return bp - ap;
    });
    var placed = [];

    for (var j = 0; j < labelQueue.length; j++) {
      var n = labelQueue[j];
      var dim = isDim(n);
      var isSel = selected && selected.id === n.id;
      var isHov = hovered && hovered.id === n.id;
      var hop = selected ? hopOf(n) : 0;
      var linked = hop === 1;
      var alpha = 1;
      if (dim) alpha = 0.07;
      else if (selected && hop >= 3) alpha = 0.1;
      else if (selected && hop === 2) alpha = 0.35;
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
      ctx.fillStyle = colorOf(n);
      if (isSel || isHov) {
        ctx.shadowColor = colorOf(n);
        ctx.shadowBlur = 18;
      }
      ctx.fill();
      ctx.shadowBlur = 0;
      if (isSel) {
        ctx.lineWidth = 1.8 / scale;
        ctx.strokeStyle = dark ? "#fff" : "#111";
        ctx.stroke();
      }

      var wantLabel =
        !dim &&
        (isSel || isHov || linked || (!selected && (scale > 1.8 || n.degree >= labelMinDegree)));
      if (wantLabel) {
        var label = shortTitle(n.title);
        var serif = isSel || n.degree >= labelMinDegree;
        var size = Math.max(11, (isSel ? 15 : 12) / Math.sqrt(Math.max(scale, 0.8)));
        ctx.font = (serif ? "italic " : "") + (isSel || isHov ? "600 " : "400 ") + size + "px " +
          (serif ? "'Libre Baskerville', Georgia, serif" : "ui-sans-serif, system-ui, sans-serif");
        var tw = ctx.measureText(label).width;
        var lx = n.x - tw / 2 - 5;
        var ly = n.y + n.radius + 5;
        var lw = tw + 10;
        var lh = size + 8;
        var clash = false;
        if (!isSel && !isHov) {
          for (var p = 0; p < placed.length; p++) {
            var box = placed[p];
            if (lx < box.x + box.w && lx + lw > box.x && ly < box.y + box.h && ly + lh > box.y) {
              clash = true;
              break;
            }
          }
        }
        if (!clash) {
          placed.push({ x: lx, y: ly, w: lw, h: lh });
          ctx.globalAlpha = alpha;
          ctx.fillStyle = labelBg;
          ctx.fillRect(lx, ly, lw, lh);
          ctx.fillStyle = isSel || isHov || linked ? text : textMute;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillText(label, n.x, ly + 4);
        }
      }
      ctx.globalAlpha = 1;
    }
    ctx.restore();
  }

  function loop() {
    stepFly();
    tickPhysics();
    draw();
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  function worldFromEvent(e) {
    var rect = canvas.getBoundingClientRect();
    return {
      mx: e.clientX - rect.left,
      my: e.clientY - rect.top,
      x: (e.clientX - rect.left - panX) / scale,
      y: (e.clientY - rect.top - panY) / scale,
    };
  }

  function nodeAt(x, y) {
    for (var i = nodes.length - 1; i >= 0; i--) {
      var n = nodes[i];
      if (isDim(n)) continue;
      var dx = x - n.x;
      var dy = y - n.y;
      var hit = n.radius + 5;
      if (dx * dx + dy * dy < hit * hit) return n;
    }
    return null;
  }

  canvas.addEventListener("mousemove", function (e) {
    var p = worldFromEvent(e);
    if (dragNode) {
      dragNode.x = p.x;
      dragNode.y = p.y;
      dragNode.vx = 0;
      dragNode.vy = 0;
      didDrag = true;
      energy = Math.max(energy, 0.35);
      return;
    }
    if (isPanning) {
      panX += p.mx - lastMouse.x;
      panY += p.my - lastMouse.y;
      lastMouse.x = p.mx;
      lastMouse.y = p.my;
      didDrag = true;
      return;
    }
    hovered = nodeAt(p.x, p.y);
    canvas.style.cursor = hovered ? "pointer" : "grab";
  });

  canvas.addEventListener("mousedown", function (e) {
    var p = worldFromEvent(e);
    var n = nodeAt(p.x, p.y);
    didDrag = false;
    if (n) {
      dragNode = n;
    } else {
      isPanning = true;
      lastMouse.x = p.mx;
      lastMouse.y = p.my;
    }
    canvas.style.cursor = "grabbing";
  });

  window.addEventListener("mouseup", function () {
    dragNode = null;
    isPanning = false;
    canvas.style.cursor = hovered ? "pointer" : "grab";
  });

  canvas.addEventListener("click", function (e) {
    if (didDrag) return;
    var p = worldFromEvent(e);
    var n = nodeAt(p.x, p.y);
    if (n) selectNode(n, true);
    else selectNode(null);
  });

  canvas.addEventListener("dblclick", function (e) {
    var p = worldFromEvent(e);
    var n = nodeAt(p.x, p.y);
    if (n) window.location.href = "/topic/" + n.id;
  });

  canvas.addEventListener(
    "wheel",
    function (e) {
      e.preventDefault();
      var p = worldFromEvent(e);
      zoomAt(p.mx, p.my, e.deltaY > 0 ? 0.9 : 1.1);
    },
    { passive: false }
  );

  canvas.addEventListener("mouseleave", function () {
    hovered = null;
  });

  document.addEventListener("smartipedia:theme-change", function () {
    /* redraw on next frame via loop */
  });

  if (hintEl) {
    setTimeout(function () {
      hintEl.classList.add("is-faded");
    }, 5000);
  }

  loadGraph(DEFAULT_LIMIT);
})();
