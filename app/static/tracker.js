(function () {
  "use strict";

  /* ── State ──────────────────────────────────────────────── */

  var allItems = [];          // full list from /api/tracker
  var activeFilter = "active"; // current tab
  var openAppId = null;       // drawer app id

  var STATUS_ORDER = ["generated", "applied", "interviewing", "offer", "rejected", "ghosted"];

  /* ── DOM refs ───────────────────────────────────────────── */

  var tbody        = document.getElementById("tracker-tbody");
  var tableWrap    = document.getElementById("tracker-table-wrap");
  var loadingMsg   = document.getElementById("tracker-loading");
  var emptyMsg     = document.getElementById("tracker-empty");
  var refreshBtn   = document.getElementById("tracker-refresh-btn");
  var filterBtns   = document.querySelectorAll(".tracker-tab");

  var drawerOverlay    = document.getElementById("app-drawer-overlay");
  var drawerClose      = document.getElementById("app-drawer-close");
  var drawerCompany    = document.getElementById("drawer-company");
  var drawerRole       = document.getElementById("drawer-role");
  var drawerStatusBadge = document.getElementById("drawer-status-badge");
  var drawerInitScore  = document.getElementById("drawer-initial-score");
  var drawerUpdScore   = document.getElementById("drawer-updated-score");
  var drawerCreatedAt  = document.getElementById("drawer-created-at");
  var drawerStatusSel  = document.getElementById("drawer-status-select");
  var drawerStatusSave = document.getElementById("drawer-status-save");
  var drawerTimeline   = document.getElementById("drawer-timeline");
  var drawerTimelineEmpty = document.getElementById("drawer-timeline-empty");
  var drawerNotes      = document.getElementById("drawer-notes");
  var drawerNotesSave  = document.getElementById("drawer-notes-save-btn");
  var drawerNotesSaved = document.getElementById("drawer-notes-saved");

  /* ── Helpers ────────────────────────────────────────────── */

  function fetchJson(url, options) {
    var fetcher = window.CAuth ? CAuth.authFetch.bind(CAuth) : fetch.bind(window);
    return fetcher(url, options || {})
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        return data;
      });
  }

  function daysSince(dateStr) {
    if (!dateStr) return null;
    var d = new Date(dateStr.replace(" ", "T") + (dateStr.includes("T") ? "" : "Z"));
    var diff = Date.now() - d.getTime();
    return Math.max(0, Math.floor(diff / 86400000));
  }

  function formatDate(dateStr) {
    if (!dateStr) return "-";
    var d = new Date(dateStr.replace(" ", "T") + (dateStr.includes("T") ? "" : "Z"));
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function formatScore(val) {
    if (val === null || val === undefined) return "-";
    var n = Number(val);
    return Number.isFinite(n) ? n.toFixed(1) : "-";
  }

  function statusBadgeClass(status) {
    switch (status) {
      case "offer":        return "tracker-status--offer";
      case "interviewing": return "tracker-status--interviewing";
      case "applied":      return "tracker-status--applied";
      case "generated":    return "tracker-status--generated";
      case "rejected":     return "tracker-status--rejected";
      case "ghosted":      return "tracker-status--ghosted";
      default:             return "";
    }
  }

  function statusLabel(status) {
    var labels = {
      offer: "Offer", interviewing: "Interviewing", applied: "Applied",
      generated: "Generated", rejected: "Rejected", ghosted: "Ghosted",
    };
    return labels[status] || status;
  }

  function filterItems(items, filter) {
    switch (filter) {
      case "active":
        return items.filter(function (i) {
          return ["generated", "applied", "interviewing", "offer"].indexOf(i.status) !== -1;
        });
      case "closed":
        return items.filter(function (i) {
          return ["rejected", "ghosted"].indexOf(i.status) !== -1;
        });
      case "all":
        return items.slice();
      default:
        return items.filter(function (i) { return i.status === filter; });
    }
  }

  /* ── Table rendering ────────────────────────────────────── */

  function renderTable(items) {
    var filtered = filterItems(items, activeFilter);

    if (filtered.length === 0) {
      tableWrap.setAttribute("hidden", "");
      emptyMsg.removeAttribute("hidden");
      return;
    }

    emptyMsg.setAttribute("hidden", "");
    tableWrap.removeAttribute("hidden");
    tbody.innerHTML = "";

    filtered.forEach(function (item) {
      var tr = document.createElement("tr");

      /* Status badge cell */
      var statusTd = document.createElement("td");
      var badge = document.createElement("span");
      badge.className = "tracker-status-badge " + statusBadgeClass(item.status);
      badge.textContent = statusLabel(item.status);
      statusTd.appendChild(badge);

      /* Days in status cell */
      var days = daysSince(item.last_status_at);
      var daysTd = document.createElement("td");
      if (days !== null) {
        var daysSpan = document.createElement("span");
        daysSpan.className = "tracker-days-badge" + (days >= 7 ? " tracker-days--stale" : "");
        daysSpan.textContent = days + "d";
        daysSpan.title = "Days in current status";
        daysTd.appendChild(daysSpan);
      } else {
        daysTd.textContent = "-";
      }

      /* Notes cell */
      var notesTd = document.createElement("td");
      var notesPreview = document.createElement("span");
      notesPreview.className = "tracker-notes-preview";
      notesPreview.textContent = (item.notes || "").slice(0, 60) || "\u2014";
      if (item.notes && item.notes.length > 60) notesPreview.textContent += "\u2026";
      notesTd.appendChild(notesPreview);

      /* Actions cell */
      var actionsTd = document.createElement("td");
      var actionWrap = document.createElement("div");
      actionWrap.className = "shell-action-row";

      var histBtn = document.createElement("button");
      histBtn.type = "button";
      histBtn.className = "shell-small-btn";
      histBtn.textContent = "History";
      histBtn.addEventListener("click", function () { openDrawer(item); });
      actionWrap.appendChild(histBtn);

      /* Inline status select */
      var sel = document.createElement("select");
      sel.className = "shell-status-select";
      STATUS_ORDER.forEach(function (s) {
        var opt = document.createElement("option");
        opt.value = s;
        opt.textContent = statusLabel(s);
        opt.selected = s === item.status;
        sel.appendChild(opt);
      });
      sel.addEventListener("change", function () {
        var prev = item.status;
        fetchJson("/api/applications/" + item.id + "/status", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ new_status: sel.value }),
        })
          .then(function () { return loadTracker(); })
          .catch(function (err) { alert(err.message); sel.value = prev; });
      });
      actionWrap.appendChild(sel);
      actionsTd.appendChild(actionWrap);

      /* Assemble row */
      tr.innerHTML =
        "<td>" + (item.company || "-") + "</td>" +
        "<td>" + (item.role || "-") + "</td>" +
        "<td>" + formatScore(item.score) + "</td>";

      tr.insertBefore(statusTd, tr.firstChild);
      tr.appendChild(daysTd);
      tr.appendChild(notesTd);
      tr.appendChild(actionsTd);

      tbody.appendChild(tr);
    });
  }

  /* ── Load tracker data ──────────────────────────────────── */

  function loadTracker() {
    return fetchJson("/api/tracker")
      .then(function (data) {
        allItems = data.items || [];
        loadingMsg.setAttribute("hidden", "");
        renderTable(allItems);
      })
      .catch(function (err) {
        loadingMsg.setAttribute("hidden", "");
        emptyMsg.textContent = "Failed to load tracker: " + err.message;
        emptyMsg.removeAttribute("hidden");
      });
  }

  /* ── Drawer ─────────────────────────────────────────────── */

  function openDrawer(item) {
    openAppId = item.id;

    /* Header */
    drawerCompany.textContent = item.company || "Unknown Company";
    drawerRole.textContent    = item.role    || "Untitled Role";

    /* Status badge */
    drawerStatusBadge.className = "tracker-status-badge " + statusBadgeClass(item.status);
    drawerStatusBadge.textContent = statusLabel(item.status);

    /* Score */
    drawerInitScore.textContent = formatScore(item.initial_score);
    drawerUpdScore.textContent  = formatScore(item.updated_score);

    /* Date */
    drawerCreatedAt.textContent = formatDate(item.created_at);

    /* Status select */
    drawerStatusSel.innerHTML = "";
    STATUS_ORDER.forEach(function (s) {
      var opt = document.createElement("option");
      opt.value = s;
      opt.textContent = statusLabel(s);
      opt.selected = s === item.status;
      drawerStatusSel.appendChild(opt);
    });

    /* Notes */
    drawerNotes.value = item.notes || "";
    drawerNotesSaved.setAttribute("hidden", "");

    /* Show drawer */
    drawerOverlay.removeAttribute("hidden");
    document.body.style.overflow = "hidden";

    /* Load events */
    loadEvents(item.id);
  }

  function closeDrawer() {
    drawerOverlay.setAttribute("hidden", "");
    document.body.style.overflow = "";
    openAppId = null;
  }

  function loadEvents(appId) {
    drawerTimeline.innerHTML = "";
    var spinner = document.createElement("div");
    spinner.className = "app-drawer-timeline-empty";
    spinner.textContent = "Loading history\u2026";
    drawerTimeline.appendChild(spinner);

    fetchJson("/api/applications/" + appId + "/events")
      .then(function (data) {
        renderTimeline(data.events || []);
      })
      .catch(function (err) {
        drawerTimeline.innerHTML =
          '<div class="app-drawer-timeline-empty">Failed to load history: ' + err.message + "</div>";
      });
  }

  function renderTimeline(events) {
    drawerTimeline.innerHTML = "";

    /* Filter to status_change events only for the main timeline */
    var statusEvents = events.filter(function (e) {
      return e.event_type === "status_change";
    });

    if (statusEvents.length === 0) {
      var emptyDiv = document.createElement("div");
      emptyDiv.className = "app-drawer-timeline-empty";
      emptyDiv.textContent = "No status changes recorded yet.";
      drawerTimeline.appendChild(emptyDiv);
      return;
    }

    statusEvents.forEach(function (ev, idx) {
      var item = document.createElement("div");
      item.className = "timeline-item" + (idx === statusEvents.length - 1 ? " timeline-item--last" : "");

      var dot = document.createElement("div");
      dot.className = "timeline-dot " + statusBadgeClass(ev.new_status || ev.old_status);

      var content = document.createElement("div");
      content.className = "timeline-content";

      var arrow = ev.old_status && ev.new_status
        ? '<span class="timeline-arrow">' + statusLabel(ev.old_status) + " &rarr; " + statusLabel(ev.new_status) + "</span>"
        : '<span class="timeline-arrow">' + statusLabel(ev.new_status || ev.old_status || "?") + "</span>";

      var detail = ev.detail
        ? '<div class="timeline-detail">' + escapeHtml(ev.detail) + "</div>"
        : "";

      content.innerHTML =
        '<div class="timeline-date">' + formatDate(ev.created_at) + "</div>" +
        arrow +
        detail;

      item.appendChild(dot);
      item.appendChild(content);
      drawerTimeline.appendChild(item);
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ── Drawer event bindings ──────────────────────────────── */

  drawerClose.addEventListener("click", closeDrawer);

  drawerOverlay.addEventListener("click", function (e) {
    if (e.target === drawerOverlay) closeDrawer();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !drawerOverlay.hasAttribute("hidden")) closeDrawer();
  });

  drawerStatusSave.addEventListener("click", function () {
    if (openAppId === null) return;
    var newStatus = drawerStatusSel.value;
    drawerStatusSave.disabled = true;
    fetchJson("/api/applications/" + openAppId + "/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_status: newStatus }),
    })
      .then(function (data) {
        /* Update badge and refresh timeline + table */
        var updated = (data.application || {});
        drawerStatusBadge.className = "tracker-status-badge " + statusBadgeClass(updated.status || newStatus);
        drawerStatusBadge.textContent = statusLabel(updated.status || newStatus);
        loadEvents(openAppId);
        loadTracker();
      })
      .catch(function (err) { alert(err.message); })
      .finally(function () { drawerStatusSave.disabled = false; });
  });

  drawerNotesSave.addEventListener("click", function () {
    if (openAppId === null) return;
    drawerNotesSave.disabled = true;
    fetchJson("/api/applications/" + openAppId + "/notes", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: drawerNotes.value }),
    })
      .then(function () {
        drawerNotesSaved.removeAttribute("hidden");
        setTimeout(function () { drawerNotesSaved.setAttribute("hidden", ""); }, 2000);
        /* Refresh tracker table to show updated notes preview */
        loadTracker();
      })
      .catch(function (err) { alert(err.message); })
      .finally(function () { drawerNotesSave.disabled = false; });
  });

  /* ── Filter tabs ────────────────────────────────────────── */

  filterBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      activeFilter = btn.dataset.filter;
      filterBtns.forEach(function (b) { b.classList.remove("tracker-tab--active"); });
      btn.classList.add("tracker-tab--active");
      renderTable(allItems);
    });
  });

  /* ── Refresh button ─────────────────────────────────────── */

  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      refreshBtn.disabled = true;
      loadTracker().finally(function () { refreshBtn.disabled = false; });
    });
  }

  /* ── Init ───────────────────────────────────────────────── */

  /* Load when the tracker section becomes visible */
  var sectionEl = document.getElementById("section-tracker");
  if (sectionEl) {
    var observer = new MutationObserver(function () {
      if (sectionEl.classList.contains("active") && allItems.length === 0) {
        loadTracker();
      }
    });
    observer.observe(sectionEl, { attributes: true, attributeFilter: ["class"] });
  }

  /* Also load eagerly in local mode (no auth wait needed) */
  if (window.CUSTOMY_CONFIG && window.CUSTOMY_CONFIG.mode === "local") {
    loadTracker();
  }

  /* In SaaS mode, load after auth confirms a session */
  window.addEventListener("customy:application-generated", function () {
    if (sectionEl && sectionEl.classList.contains("active")) {
      loadTracker();
    }
  });

  /* Export for external refresh (e.g. from dashboard-shell after a status update) */
  window.CustomyTracker = { refresh: loadTracker };
})();
