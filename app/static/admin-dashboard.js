/**
 * CAdminDashboard — Admin section module for Customy V3.
 *
 * Only loaded/called when the backend confirms is_admin === true via /api/auth/me.
 * Surfaces: platform stats, user list, user detail panel, ideas board CRUD.
 *
 * All API calls use CAuth.authFetch() so the admin JWT is injected automatically.
 */
(function () {
  "use strict";

  /* ── State ────────────────────────────────────────────── */

  var _ideasCache = [];        // last loaded ideas list
  var _editingIdeaId = null;   // null = creating new
  var _eventsWired  = false;   // guard: bindStaticEvents runs once

  /* ── Utility helpers ──────────────────────────────────── */

  function fmt(val, fallback) {
    return (val !== null && val !== undefined && val !== "") ? val : (fallback !== undefined ? fallback : "—");
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }); }
    catch (_) { return iso; }
  }

  function fmtCost(v) {
    if (v === null || v === undefined) return "—";
    var n = Number(v);
    return isNaN(n) ? "—" : "$" + n.toFixed(4);
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function authFetch(url, opts) {
    var fn = window.CAuth ? CAuth.authFetch.bind(CAuth) : window.fetch.bind(window);
    return fn(url, opts || {}).then(function (r) { return r.json(); });
  }

  /* ── Status / priority badges ─────────────────────────── */

  var STATUS_CLASS = {
    "idea":        "admin-badge--idea",
    "planned":     "admin-badge--planned",
    "in-progress": "admin-badge--inprogress",
    "done":        "admin-badge--done",
    "cancelled":   "admin-badge--cancelled"
  };

  var PRIORITY_CLASS = {
    "high":   "admin-badge--high",
    "medium": "admin-badge--medium",
    "low":    "admin-badge--low"
  };

  function statusBadge(status) {
    if (!status) return '<span class="shell-dash">—</span>';
    return '<span class="admin-badge ' + (STATUS_CLASS[status] || "") + '">' + escHtml(status) + '</span>';
  }

  function priorityBadge(priority) {
    if (!priority) return '<span class="shell-dash">—</span>';
    return '<span class="admin-badge ' + (PRIORITY_CLASS[priority] || "") + '">' + escHtml(priority) + '</span>';
  }

  /* ── Platform stats ───────────────────────────────────── */

  function loadStats() {
    var grid = document.getElementById("admin-stats-grid");
    if (!grid) return;
    grid.innerHTML = '<div class="quick-stat-card"><span class="quick-stat-label">Loading&hellip;</span></div>';

    authFetch("/api/admin/stats")
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        var items = [
          ["Total Users",    data.total_users],
          ["Active (7 d)",   data.active_users_7d],
          ["Active (30 d)",  data.active_users_30d],
          ["Total Apps",     data.total_applications],
          ["Total API Cost", fmtCost(data.total_cost_usd)],
          ["API Requests",   data.total_api_requests],
        ];
        grid.innerHTML = items.map(function (p) {
          return (
            '<div class="quick-stat-card">' +
              '<div class="quick-stat-label">' + escHtml(p[0]) + "</div>" +
              '<div class="quick-stat-value">' + escHtml(String(fmt(p[1], 0))) + "</div>" +
            "</div>"
          );
        }).join("");
      })
      .catch(function (err) {
        grid.innerHTML =
          '<div class="quick-stat-card"><span class="quick-stat-label" style="color:var(--shell-danger,#c00)">Failed: ' +
          escHtml(err.message) + "</span></div>";
      });
  }

  /* ── Users list ───────────────────────────────────────── */

  function loadUsers() {
    var tbody = document.getElementById("admin-users-body");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="8" class="aq-empty-row">Loading&hellip;</td></tr>';

    authFetch("/api/admin/users")
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        var users = data.users || [];
        if (!users.length) {
          tbody.innerHTML = '<tr><td colspan="8" class="aq-empty-row">No users found.</td></tr>';
          return;
        }
        tbody.innerHTML = users.map(function (u) {
          return (
            "<tr>" +
            "<td>" + escHtml(fmt(u.email)) + "</td>" +
            "<td>" + escHtml(fmt(u.full_name)) + "</td>" +
            "<td>" + fmtDate(u.registered_at) + "</td>" +
            "<td>" + fmtDate(u.last_sign_in_at) + "</td>" +
            "<td>" + escHtml(String(fmt(u.total_applications, 0))) + "</td>" +
            "<td>" + fmtDate(u.last_generated_at) + "</td>" +
            "<td>" + fmtCost(u.total_cost_usd) + "</td>" +
            '<td><button class="aq-btn admin-detail-btn" data-uid="' + escHtml(u.user_id) + '">View</button></td>' +
            "</tr>"
          );
        }).join("");

        tbody.querySelectorAll(".admin-detail-btn").forEach(function (btn) {
          btn.addEventListener("click", function () {
            loadUserDetail(btn.dataset.uid);
          });
        });
      })
      .catch(function (err) {
        tbody.innerHTML =
          '<tr><td colspan="8" class="aq-empty-row">Failed to load users: ' + escHtml(err.message) + "</td></tr>";
      });
  }

  /* ── User detail panel ────────────────────────────────── */

  function loadUserDetail(userId) {
    var panel      = document.getElementById("admin-user-detail");
    var statsGrid  = document.getElementById("admin-detail-stats-grid");
    var appsBody   = document.getElementById("admin-detail-apps-body");
    var titleEl    = document.getElementById("admin-detail-title");
    var emailEl    = document.getElementById("admin-detail-email");
    if (!panel) return;

    // Show panel immediately with loading state
    titleEl.textContent  = "Loading…";
    emailEl.textContent  = "";
    statsGrid.innerHTML  = '<div class="quick-stat-card"><span class="quick-stat-label">Loading&hellip;</span></div>';
    appsBody.innerHTML   = '<tr><td colspan="6" class="aq-empty-row">Loading&hellip;</td></tr>';
    panel.removeAttribute("hidden");
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });

    authFetch("/api/admin/users/" + encodeURIComponent(userId))
      .then(function (d) {
        if (d.error) throw new Error(d.error);

        titleEl.textContent = fmt(d.full_name, "User Detail");
        emailEl.textContent = fmt(d.email);

        var usage = d.api_usage || {};
        var usageItems = [
          ["API Requests",      fmt(usage.request_count,      0)],
          ["Total Cost",        fmtCost(usage.total_cost_usd)],
          ["Prompt Tokens",     fmt(usage.prompt_tokens,      0)],
          ["Completion Tokens", fmt(usage.completion_tokens,  0)],
        ];
        statsGrid.innerHTML = usageItems.map(function (p) {
          return (
            '<div class="quick-stat-card">' +
              '<div class="quick-stat-label">' + escHtml(p[0]) + "</div>" +
              '<div class="quick-stat-value">' + escHtml(String(p[1])) + "</div>" +
            "</div>"
          );
        }).join("");

        var apps = d.applications || [];
        if (!apps.length) {
          appsBody.innerHTML = '<tr><td colspan="6" class="aq-empty-row">No applications yet.</td></tr>';
          return;
        }
        appsBody.innerHTML = apps.map(function (a) {
          var score = a.updated_score !== null && a.updated_score !== undefined
            ? a.updated_score : a.initial_score;
          return (
            "<tr>" +
            "<td>" + fmtDate(a.created_at) + "</td>" +
            "<td>" + escHtml(fmt(a.company_name)) + "</td>" +
            "<td>" + escHtml(fmt(a.role_title)) + "</td>" +
            "<td>" + escHtml(String(fmt(score))) + "</td>" +
            "<td>" + fmtCost(a.total_cost_usd) + "</td>" +
            "<td>" + escHtml(fmt(a.status)) + "</td>" +
            "</tr>"
          );
        }).join("");
      })
      .catch(function (err) {
        titleEl.textContent = "Error";
        statsGrid.innerHTML =
          '<div class="quick-stat-card"><span class="quick-stat-label" style="color:var(--shell-danger,#c00)">Failed: ' +
          escHtml(err.message) + "</span></div>";
        appsBody.innerHTML =
          '<tr><td colspan="6" class="aq-empty-row">Failed to load: ' + escHtml(err.message) + "</td></tr>";
      });
  }

  /* ── Ideas board ──────────────────────────────────────── */

  function currentIdeasFilter() {
    var sel = document.getElementById("admin-ideas-filter");
    return sel ? sel.value : "";
  }

  function loadIdeas(status) {
    var tbody = document.getElementById("admin-ideas-body");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" class="aq-empty-row">Loading&hellip;</td></tr>';

    var url = "/api/admin/ideas" + (status ? "?status=" + encodeURIComponent(status) : "");
    authFetch(url)
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        _ideasCache = data.ideas || [];
        if (!_ideasCache.length) {
          tbody.innerHTML = '<tr><td colspan="7" class="aq-empty-row">No ideas found.</td></tr>';
          return;
        }
        tbody.innerHTML = _ideasCache.map(function (idea) {
          return (
            "<tr>" +
            "<td>" + escHtml(fmt(idea.title)) + "</td>" +
            "<td>" + escHtml(fmt(idea.category)) + "</td>" +
            "<td>" + priorityBadge(idea.priority) + "</td>" +
            "<td>" + statusBadge(idea.status) + "</td>" +
            "<td>" + escHtml(fmt(idea.target_version)) + "</td>" +
            "<td>" + fmtDate(idea.created_at) + "</td>" +
            '<td class="admin-idea-actions">' +
              '<button class="aq-btn admin-idea-edit-btn" data-idea-id="' + idea.id + '">Edit</button>' +
              '<button class="aq-btn admin-idea-delete-btn" data-idea-id="' + idea.id + '">Delete</button>' +
            "</td>" +
            "</tr>"
          );
        }).join("");

        tbody.querySelectorAll(".admin-idea-edit-btn").forEach(function (btn) {
          btn.addEventListener("click", function () {
            openIdeaModal(Number(btn.dataset.ideaId));
          });
        });
        tbody.querySelectorAll(".admin-idea-delete-btn").forEach(function (btn) {
          btn.addEventListener("click", function () {
            deleteIdea(Number(btn.dataset.ideaId));
          });
        });
      })
      .catch(function (err) {
        tbody.innerHTML =
          '<tr><td colspan="7" class="aq-empty-row">Failed to load ideas: ' + escHtml(err.message) + "</td></tr>";
      });
  }

  /* ── Idea modal ───────────────────────────────────────── */

  function openIdeaModal(ideaId) {
    _editingIdeaId = ideaId || null;
    var overlay  = document.getElementById("admin-idea-modal-overlay");
    var titleEl  = document.getElementById("admin-idea-modal-title");
    var errEl    = document.getElementById("admin-idea-modal-error");
    if (!overlay) return;

    errEl.textContent = "";

    if (_editingIdeaId) {
      titleEl.textContent = "Edit Idea";
      var idea = _ideasCache.find(function (i) { return i.id === _editingIdeaId; });
      if (idea) {
        document.getElementById("admin-idea-title").value    = idea.title || "";
        document.getElementById("admin-idea-desc").value     = idea.description || "";
        document.getElementById("admin-idea-category").value = idea.category || "";
        document.getElementById("admin-idea-priority").value = idea.priority || "";
        document.getElementById("admin-idea-status").value   = idea.status || "idea";
        document.getElementById("admin-idea-version").value  = idea.target_version || "";
      }
    } else {
      titleEl.textContent = "New Idea";
      document.getElementById("admin-idea-title").value    = "";
      document.getElementById("admin-idea-desc").value     = "";
      document.getElementById("admin-idea-category").value = "";
      document.getElementById("admin-idea-priority").value = "";
      document.getElementById("admin-idea-status").value   = "idea";
      document.getElementById("admin-idea-version").value  = "";
    }

    overlay.classList.add("aq-modal-overlay--visible");
  }

  function closeIdeaModal() {
    var overlay = document.getElementById("admin-idea-modal-overlay");
    if (overlay) overlay.classList.remove("aq-modal-overlay--visible");
    _editingIdeaId = null;
  }

  function saveIdea() {
    var titleVal = (document.getElementById("admin-idea-title").value || "").trim();
    var errEl    = document.getElementById("admin-idea-modal-error");
    var saveBtn  = document.getElementById("admin-idea-save-btn");

    if (!titleVal) {
      errEl.textContent = "Title is required.";
      return;
    }
    errEl.textContent = "";
    saveBtn.disabled = true;

    var payload = {
      title:          titleVal,
      description:    (document.getElementById("admin-idea-desc").value     || "").trim() || null,
      category:       document.getElementById("admin-idea-category").value  || null,
      priority:       document.getElementById("admin-idea-priority").value  || null,
      status:         document.getElementById("admin-idea-status").value    || "idea",
      target_version: (document.getElementById("admin-idea-version").value  || "").trim() || null,
    };

    var url    = _editingIdeaId ? "/api/admin/ideas/" + _editingIdeaId : "/api/admin/ideas";
    var method = _editingIdeaId ? "PUT" : "POST";

    var fn = window.CAuth ? CAuth.authFetch.bind(CAuth) : window.fetch.bind(window);
    fn(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        saveBtn.disabled = false;
        if (data.error) { errEl.textContent = data.error; return; }
        closeIdeaModal();
        loadIdeas(currentIdeasFilter());
      })
      .catch(function (err) {
        saveBtn.disabled = false;
        errEl.textContent = "Save failed: " + err.message;
      });
  }

  function deleteIdea(ideaId) {
    if (!window.confirm("Delete this idea?")) return;

    var fn = window.CAuth ? CAuth.authFetch.bind(CAuth) : window.fetch.bind(window);
    fn("/api/admin/ideas/" + ideaId, { method: "DELETE" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { alert("Delete failed: " + data.error); return; }
        loadIdeas(currentIdeasFilter());
      })
      .catch(function (err) {
        alert("Delete failed: " + err.message);
      });
  }

  /* ── Wire up static event listeners ──────────────────── */

  function bindStaticEvents() {
    // Refresh button
    var refreshBtn = document.getElementById("admin-refresh-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", function () { refresh(); });
    }

    // Close user detail panel
    var detailClose = document.getElementById("admin-detail-close");
    if (detailClose) {
      detailClose.addEventListener("click", function () {
        var panel = document.getElementById("admin-user-detail");
        if (panel) panel.setAttribute("hidden", "");
      });
    }

    // Ideas status filter
    var ideasFilter = document.getElementById("admin-ideas-filter");
    if (ideasFilter) {
      ideasFilter.addEventListener("change", function () {
        loadIdeas(ideasFilter.value);
      });
    }

    // New idea button
    var newIdeaBtn = document.getElementById("admin-idea-new-btn");
    if (newIdeaBtn) {
      newIdeaBtn.addEventListener("click", function () { openIdeaModal(null); });
    }

    // Idea modal close / backdrop click
    var ideaModalClose = document.getElementById("admin-idea-modal-close");
    if (ideaModalClose) {
      ideaModalClose.addEventListener("click", closeIdeaModal);
    }
    var ideaModalOverlay = document.getElementById("admin-idea-modal-overlay");
    if (ideaModalOverlay) {
      ideaModalOverlay.addEventListener("click", function (e) {
        if (e.target === ideaModalOverlay) closeIdeaModal();
      });
    }

    // Idea save
    var saveBtn = document.getElementById("admin-idea-save-btn");
    if (saveBtn) {
      saveBtn.addEventListener("click", saveIdea);
    }
  }

  /* ── Public API ───────────────────────────────────────── */

  function init() {
    if (!_eventsWired) {
      bindStaticEvents();
      _eventsWired = true;
    }
    refresh();
  }

  function refresh() {
    loadStats();
    loadUsers();
    loadIdeas(currentIdeasFilter());
  }

  window.CAdminDashboard = {
    init: init,
    refresh: refresh,
  };
})();
