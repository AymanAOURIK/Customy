(function () {
  "use strict";

  /* ── Navigation ─────────────────────────────────────── */

  var sidebar = document.getElementById("sidebar");
  var sidebarToggle = document.getElementById("sidebar-toggle");
  var sidebarOverlay = document.getElementById("sidebar-overlay");
  var sidebarLinks = document.querySelectorAll(".sidebar-link[data-section]");
  var navTriggers = document.querySelectorAll("[data-section-target]");
  var sections = document.querySelectorAll(".platform-section");

  function navigateTo(sectionId) {
    sections.forEach(function (s) {
      s.classList.toggle("active", s.id === sectionId);
    });
    sidebarLinks.forEach(function (l) {
      l.classList.toggle("active", l.dataset.section === sectionId);
    });
    if (sidebar.classList.contains("open")) {
      sidebar.classList.remove("open");
      sidebarOverlay.classList.remove("visible");
    }
  }

  function bindNavigationLink(link, sectionId) {
    link.addEventListener("click", function (e) {
      e.preventDefault();
      navigateTo(sectionId);
      history.replaceState(null, "", link.getAttribute("href"));
    });
  }

  sidebarLinks.forEach(function (link) {
    bindNavigationLink(link, link.dataset.section);
  });

  navTriggers.forEach(function (link) {
    bindNavigationLink(link, link.dataset.sectionTarget);
  });

  sidebarToggle.addEventListener("click", function () {
    sidebar.classList.toggle("open");
    sidebarOverlay.classList.toggle("visible");
  });

  sidebarOverlay.addEventListener("click", function () {
    sidebar.classList.remove("open");
    sidebarOverlay.classList.remove("visible");
  });

  // Activate section from URL hash on load
  if (window.location.hash) {
    var target = document.querySelector(
      '.sidebar-link[href="' + window.location.hash + '"]'
    );
    if (target) navigateTo(target.dataset.section);
  }

  /* ── Dashboard data ─────────────────────────────────── */

  var kpiGrid = document.getElementById("kpi-grid");
  var quickStats = document.getElementById("quick-stats");
  var costStats = document.getElementById("cost-stats");
  var costStatsCard = document.getElementById("dashboard-cost-stats-card");
  var applicationsCostHeader = document.getElementById("applications-cost-header");
  var applicationsBody = document.getElementById("applications-body");
  var chart = document.getElementById("activity-chart");
  var tooltip = document.getElementById("chart-tooltip");
  var svgNS = "http://www.w3.org/2000/svg";
  var isSaas = !!(window.CUSTOMY_CONFIG && window.CUSTOMY_CONFIG.mode === "saas");
  var statusOptions = [
    "generated",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "ghosted",
  ];

  function percent(value, total) {
    if (!total) return "0%";
    return Math.round((value / total) * 100) + "%";
  }

  function scoreClass(score) {
    var n = Number(score || 0);
    if (n >= 70) return "shell-score-green";
    if (n >= 40) return "shell-score-amber";
    return "shell-score-red";
  }

  var formatUsd = CUtils.formatUsd;
  var formatScore = CUtils.formatScore;

  function isAdminView() {
    return !isSaas || !!window.CUSTOMY_IS_ADMIN;
  }

  function syncAdminVisibility() {
    var adminView = isAdminView();
    if (costStatsCard) {
      costStatsCard.hidden = !adminView;
    }
    if (applicationsCostHeader) {
      applicationsCostHeader.hidden = !adminView;
    }
  }

  function scoreBadge(score) {
    if (score === null || score === undefined || score === "")
      return '<span class="shell-dash">-</span>';
    var n = Number(score);
    if (!Number.isFinite(n))
      return '<span class="shell-dash">-</span>';
    return (
      '<span class="shell-score-badge ' +
      scoreClass(n) +
      '">' +
      n.toFixed(1) +
      "</span>"
    );
  }

  function fetchJson(url, options) {
    // Use CAuth.authFetch so that SaaS mode requests carry the JWT.
    // In local mode CAuth.getToken() returns null and authFetch is plain fetch.
    var fetcher = window.CAuth ? CAuth.authFetch.bind(CAuth) : fetch.bind(window);
    return fetcher(url, options || {})
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        return data;
      });
  }

  /* ── KPI cards ──────────────────────────────────────── */

  function renderKpis(funnel) {
    var labels = [
      ["generated", "Generated"],
      ["applied", "Applied"],
      ["interviewing", "Interviewing"],
      ["offer", "Offer"],
      ["rejected", "Rejected"],
      ["ghosted", "Ghosted"],
    ];
    var total = Object.values(funnel).reduce(function (s, v) {
      return s + Number(v || 0);
    }, 0);
    kpiGrid.innerHTML = "";
    labels.forEach(function (pair) {
      var key = pair[0];
      var label = pair[1];
      var el = document.createElement("div");
      el.className = "kpi-card";
      el.innerHTML =
        '<div class="kpi-label">' +
        label +
        "</div>" +
        '<div class="kpi-value">' +
        (funnel[key] || 0) +
        "</div>" +
        '<div class="kpi-meta">' +
        percent(funnel[key] || 0, total) +
        " of total</div>";
      kpiGrid.appendChild(el);
    });
  }

  /* ── Quick stats + cost stats ───────────────────────── */

  function renderQuickStats(stats) {
    var items = [
      ["This Week", stats.applications_this_week || 0],
      ["This Month", stats.applications_this_month || 0],
      ["Avg Initial Score", formatScore(stats.average_initial_score)],
      ["Avg Updated Score", formatScore(stats.average_updated_score)],
      ["Top Role", stats.most_targeted_role || "-"],
    ];
    quickStats.innerHTML = "";
    items.forEach(function (pair) {
      var el = document.createElement("div");
      el.className = "quick-stat-card";
      el.innerHTML =
        '<div class="quick-stat-label">' +
        pair[0] +
        "</div>" +
        '<div class="quick-stat-value">' +
        pair[1] +
        "</div>";
      quickStats.appendChild(el);
    });

    if (!isAdminView()) {
      if (costStats) {
        costStats.innerHTML = "";
      }
      syncAdminVisibility();
      return;
    }

    var costItems = [
      ["Total API Cost", formatUsd(stats.openai_total_cost_usd)],
      ["Avg Cost / Gen", formatUsd(stats.openai_average_cost_usd)],
      ["Total Tokens", (stats.openai_total_tokens || 0).toLocaleString()],
      ["Prompt Tokens", (stats.openai_prompt_tokens || 0).toLocaleString()],
      [
        "Cached Tokens",
        (stats.openai_cached_prompt_tokens || 0).toLocaleString(),
      ],
      [
        "Completion Tokens",
        (stats.openai_completion_tokens || 0).toLocaleString(),
      ],
      ["API Requests", stats.openai_request_count || 0],
      ["Failed Requests", stats.openai_failed_request_count || 0],
    ];
    costStats.innerHTML = "";
    costItems.forEach(function (pair) {
      var el = document.createElement("div");
      el.className = "quick-stat-card";
      el.innerHTML =
        '<div class="quick-stat-label">' +
        pair[0] +
        "</div>" +
        '<div class="quick-stat-value">' +
        pair[1] +
        "</div>";
      costStats.appendChild(el);
    });
  }

  /* ── Status & duplicate mutations ───────────────────── */

  function updateStatus(id, newStatus) {
    return fetchJson("/api/applications/" + id + "/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_status: newStatus }),
    });
  }

  function updateDuplicateFlag(id, isDuplicate) {
    return fetchJson("/api/applications/" + id + "/duplicate", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_duplicate: isDuplicate }),
    });
  }

  function openFolder(folderUrl) {
    return fetchJson(folderUrl, { method: "POST" });
  }

  /* ── Table rendering ────────────────────────────────── */

  function outputLinks(outputs) {
    var labels = {
      resume_pdf: "PDF",
      cover_letter: "CL",
      linkedin_message: "LI",
      email_draft: "EM",
      resume_tex: "TEX",
    };
    var wrap = document.createElement("div");
    wrap.className = "shell-outputs-cell";
    Object.entries(outputs || {}).forEach(function (entry) {
      var key = entry[0];
      var url = entry[1];
      if (key === "generated_json") return;
      var filename = (function () {
        try {
          return new URL(url, window.location.origin).pathname
            .split("/")
            .pop();
        } catch (_) {
          return "";
        }
      })();
      var link = document.createElement("a");
      link.className = "shell-icon-link";
      link.href = url;
      if (key === "cover_letter") {
        link.download = filename || "cover_letter.txt";
      } else {
        link.target = "_blank";
        link.rel = "noreferrer";
      }
      link.textContent = labels[key] || key[0].toUpperCase();
      link.title = filename || key;
      wrap.appendChild(link);
    });
    return wrap;
  }

  function jobApplicationLink(url) {
    if (!url) {
      var s = document.createElement("span");
      s.className = "shell-dash";
      s.textContent = "-";
      return s;
    }
    var link = document.createElement("a");
    link.className = "shell-job-link";
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    try {
      link.textContent = new URL(url).hostname.replace(/^www\./, "");
    } catch (_) {
      link.textContent = "Open";
    }
    link.title = url;
    return link;
  }

  function renderApplications(items) {
    var adminView = isAdminView();
    applicationsBody.innerHTML = "";
    items.forEach(function (item) {
      var row = document.createElement("tr");
      if (item.is_duplicate) row.classList.add("duplicate-row");

      var select = document.createElement("select");
      select.className = "shell-status-select";
      statusOptions.forEach(function (status) {
        var opt = document.createElement("option");
        opt.value = status;
        opt.textContent = status;
        opt.selected = item.status === status;
        select.appendChild(opt);
      });
      select.addEventListener("change", function () {
        var prev = item.status;
        updateStatus(item.id, select.value)
          .then(function () {
            return loadDashboard();
          })
          .catch(function (err) {
            alert(err.message);
            select.value = prev;
          });
      });

      var actionWrap = document.createElement("div");
      actionWrap.className = "shell-action-row";

      var filesBtn = document.createElement("button");
      filesBtn.type = "button";
      filesBtn.className = "shell-small-btn";
      filesBtn.textContent = isSaas ? "Files" : "Folder";
      filesBtn.title = isSaas ? "Open generated files" : item.folder_path || "";
      filesBtn.disabled = isSaas ? !item.id : !item.folder_url;
      filesBtn.addEventListener("click", function () {
        if (isSaas) {
          if (!item.id || !window.CustomyFiles) return;
          filesBtn.disabled = true;
          window.CustomyFiles
            .open(item.id)
            .catch(function (err) {
              alert(err.message);
            })
            .finally(function () {
              filesBtn.disabled = false;
            });
          return;
        }
        if (!item.folder_url) return;
        filesBtn.disabled = true;
        openFolder(item.folder_url)
          .catch(function (err) {
            alert(err.message);
          })
          .finally(function () {
            filesBtn.disabled = false;
          });
      });
      actionWrap.appendChild(filesBtn);

      var dupBtn = document.createElement("button");
      dupBtn.type = "button";
      dupBtn.className =
        "shell-small-btn" + (item.is_duplicate ? " flag-active" : "");
      dupBtn.textContent = item.is_duplicate ? "Undup" : "Dup";
      dupBtn.title = item.is_duplicate
        ? "Include in stats again"
        : "Mark as duplicate, exclude from stats";
      dupBtn.addEventListener("click", function () {
        dupBtn.disabled = true;
        updateDuplicateFlag(item.id, !item.is_duplicate)
          .then(function () {
            return loadDashboard();
          })
          .catch(function (err) {
            alert(err.message);
          })
          .finally(function () {
            dupBtn.disabled = false;
          });
      });
      actionWrap.appendChild(dupBtn);

      row.innerHTML =
        "<td>" +
        (item.created_at || "").slice(0, 10) +
        "</td>" +
        "<td>" +
        (item.company || "") +
        (item.is_duplicate
          ? ' <span class="shell-flag-badge">Dup</span>'
          : "") +
        "</td>" +
        "<td>" +
        (item.role || "") +
        "</td>" +
        "<td>" +
        scoreBadge(item.initial_score) +
        "</td>" +
        "<td>" +
        scoreBadge(item.updated_score) +
        "</td>" +
        (adminView
          ? "<td>" +
            (item.total_cost_usd != null ? formatUsd(item.total_cost_usd) : "-") +
            "</td>"
          : "");

      var statusCell = document.createElement("td");
      statusCell.appendChild(select);
      var jobUrlCell = document.createElement("td");
      jobUrlCell.appendChild(jobApplicationLink(item.job_application_url));
      var outputsCell = document.createElement("td");
      outputsCell.appendChild(outputLinks(item.outputs));
      var actionsCell = document.createElement("td");
      actionsCell.appendChild(actionWrap);

      row.appendChild(statusCell);
      row.appendChild(jobUrlCell);
      row.appendChild(outputsCell);
      row.appendChild(actionsCell);
      applicationsBody.appendChild(row);
    });
  }

  /* ── Chart ──────────────────────────────────────────── */

  function svgNode(name, attrs) {
    var node = document.createElementNS(svgNS, name);
    Object.entries(attrs || {}).forEach(function (entry) {
      node.setAttribute(entry[0], entry[1]);
    });
    return node;
  }

  function drawChart(points) {
    chart.innerHTML = "";
    var w = 820,
      h = 260;
    var m = { top: 20, right: 20, bottom: 42, left: 40 };
    var iw = w - m.left - m.right;
    var ih = h - m.top - m.bottom;
    var maxVal = Math.max(
      1,
      Math.max.apply(
        null,
        points.map(function (p) {
          return Number(p.generated || 0);
        })
      )
    );

    // Axes
    chart.appendChild(
      svgNode("line", {
        x1: m.left,
        y1: h - m.bottom,
        x2: w - m.right,
        y2: h - m.bottom,
        style: "stroke: var(--shell-chart-axis);",
      })
    );
    chart.appendChild(
      svgNode("line", {
        x1: m.left,
        y1: m.top,
        x2: m.left,
        y2: h - m.bottom,
        style: "stroke: var(--shell-chart-axis);",
      })
    );

    // Tick marks
    [0, maxVal].forEach(function (tick) {
      var y = m.top + ih - (tick / maxVal) * ih;
      var t = svgNode("text", {
        x: 8,
        y: y + 4,
        style: "fill: var(--shell-chart-label);",
        "font-size": "12",
      });
      t.textContent = String(tick);
      chart.appendChild(t);
      chart.appendChild(
        svgNode("line", {
          x1: m.left,
          y1: y,
          x2: w - m.right,
          y2: y,
          style: "stroke: var(--shell-chart-grid);",
        })
      );
    });

    // Bars
    var bw = iw / Math.max(points.length, 1) - 4;
    points.forEach(function (pt, i) {
      var val = Number(pt.generated || 0);
      var bh = (val / maxVal) * ih;
      var x = m.left + i * (bw + 4);
      var y = m.top + ih - bh;
      var rect = svgNode("rect", {
        x: x,
        y: y,
        width: Math.max(bw, 4),
        height: bh,
        rx: 4,
        style: "fill: var(--shell-accent);",
      });
      rect.addEventListener("mousemove", function (e) {
        tooltip.classList.add("visible");
        tooltip.innerHTML = pt.date + "<br>Generated: " + val;
        var bounds = chart.getBoundingClientRect();
        tooltip.style.left = e.clientX - bounds.left + "px";
        tooltip.style.top = e.clientY - bounds.top + "px";
      });
      rect.addEventListener("mouseleave", function () {
        tooltip.classList.remove("visible");
      });
      chart.appendChild(rect);

      if (i % 7 === 0 || i === points.length - 1) {
        var label = svgNode("text", {
          x: x + Math.max(bw, 4) / 2,
          y: h - 12,
          style: "fill: var(--shell-chart-label);",
          "font-size": "11",
          "text-anchor": "middle",
        });
        label.textContent = pt.date.slice(5);
        chart.appendChild(label);
      }
    });
  }

  /* ── Load all dashboard data ────────────────────────── */

  function loadDashboard() {
    return Promise.all([
      fetchJson("/api/stats"),
      fetchJson("/api/applications?limit=100&offset=0"),
    ])
      .then(function (results) {
        var stats = results[0];
        var applications = results[1];
        renderKpis(stats.funnel || {});
        renderQuickStats(stats.quick_stats || {});
        drawChart(stats.daily_stats || []);
        renderApplications(applications.items || []);
      })
      .catch(function (err) {
        console.error("Dashboard load failed:", err);
      });
  }

  window.CustomyDashboard = {
    navigateTo: navigateTo,
    refresh: loadDashboard,
  };

  window.addEventListener("customy:user-role-changed", function () {
    syncAdminVisibility();
  });

  window.addEventListener("customy:application-generated", function () {
    loadDashboard();
  });

  syncAdminVisibility();
  loadDashboard();
})();
