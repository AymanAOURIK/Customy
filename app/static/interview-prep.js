(function () {
  "use strict";

  /* ── State ──────────────────────────────────────────────── */

  var sessions = [];       // full list from /api/interview-prep
  var openSession = null;  // currently open session object

  /* ── DOM refs — section ─────────────────────────────────── */

  var sectionEl     = document.getElementById("section-interview-prep");
  var kpiGrid       = document.getElementById("ip-kpi-grid");
  var loadingMsg    = document.getElementById("ip-loading");
  var emptyMsg      = document.getElementById("ip-empty");
  var tableWrap     = document.getElementById("ip-table-wrap");
  var tbody         = document.getElementById("ip-tbody");
  var newBtn        = document.getElementById("ip-new-btn");

  /* ── DOM refs — modal ───────────────────────────────────── */

  var modal         = document.getElementById("ip-modal");
  var modalClose    = document.getElementById("ip-modal-close");
  var modalCancel   = document.getElementById("ip-modal-cancel");
  var form          = document.getElementById("ip-form");
  var fApp          = document.getElementById("ip-f-app");
  var fCompany      = document.getElementById("ip-f-company");
  var fRole         = document.getElementById("ip-f-role");
  var formError     = document.getElementById("ip-form-error");
  var submitBtn     = document.getElementById("ip-submit");

  /* ── DOM refs — drawer ──────────────────────────────────── */

  var drawerOverlay   = document.getElementById("ip-drawer-overlay");
  var drawerClose     = document.getElementById("ip-drawer-close");
  var drawerCompany   = document.getElementById("ip-drawer-company");
  var drawerRole      = document.getElementById("ip-drawer-role");
  var drawerNotes     = document.getElementById("ip-drawer-notes");
  var notesSaveBtn    = document.getElementById("ip-notes-save-btn");
  var notesSaved      = document.getElementById("ip-notes-saved");
  var questionsList   = document.getElementById("ip-questions-list");
  var progressLabel   = document.getElementById("ip-progress-label");
  var deleteBtn       = document.getElementById("ip-delete-session-btn");

  /* ── Helpers ────────────────────────────────────────────── */

  function fetchJson(url, options) {
    var fetcher = window.CAuth ? CAuth.authFetch.bind(CAuth) : fetch.bind(window);
    return fetcher(url, options || {})
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error(data.error || "Request failed (" + res.status + ")");
          return data;
        });
      });
  }

  if (window.CUSTOMY_CONFIG && window.CUSTOMY_CONFIG.mode === "saas") {
    if (loadingMsg) loadingMsg.setAttribute("hidden", "");
    if (tableWrap) tableWrap.setAttribute("hidden", "");
    if (emptyMsg) {
      emptyMsg.textContent =
        "Interview Prep is currently disabled in public SaaS mode.";
      emptyMsg.removeAttribute("hidden");
    }
    if (newBtn) {
      newBtn.disabled = true;
      newBtn.title = "Available only in local mode";
    }
    window.CustomyInterviewPrep = {
      refresh: function () {
        return Promise.resolve();
      },
    };
    return;
  }

  function formatDate(dateStr) {
    if (!dateStr) return "-";
    var d = new Date(dateStr.replace(" ", "T") + (dateStr.includes("T") ? "" : "Z"));
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function categoryBadge(cat) {
    var colors = {
      behavioral: "var(--shell-info-soft)",
      technical:  "var(--shell-success-soft)",
      situational: "var(--shell-warning-soft)",
    };
    var borders = {
      behavioral: "var(--shell-info-border-soft,rgba(37,99,235,.18))",
      technical:  "var(--shell-success-border-soft,rgba(5,150,105,.14))",
      situational: "var(--shell-warning-border-soft,rgba(217,119,6,.16))",
    };
    var bg     = colors[cat]  || "var(--shell-surface-soft-alt)";
    var border = borders[cat] || "var(--shell-border)";
    return (
      '<span style="display:inline-block;padding:1px 8px;border-radius:4px;font-size:0.7rem;' +
      'font-weight:500;background:' + bg + ';border:1px solid ' + border + ';color:var(--shell-text)">' +
      escapeHtml(cat) +
      "</span>"
    );
  }

  function confidenceClass(c) {
    if (c === "high")   return "color:var(--shell-success)";
    if (c === "medium") return "color:var(--shell-warning)";
    if (c === "low")    return "color:var(--shell-danger)";
    return "color:var(--shell-text-soft)";
  }

  function countAnswered(questions) {
    return (questions || []).filter(function (q) { return (q.answer || "").trim().length > 0; }).length;
  }

  /* ── KPI bar ────────────────────────────────────────────── */

  function renderKpi(sessionsData) {
    if (!kpiGrid) return;
    var total     = sessionsData.length;
    var answered  = sessionsData.reduce(function (acc, s) {
      var qs = parseQuestions(s.questions_json);
      return acc + countAnswered(qs);
    }, 0);
    var totalQ    = sessionsData.reduce(function (acc, s) {
      return acc + parseQuestions(s.questions_json).length;
    }, 0);

    var kpis = [
      { label: "Prep Sessions", value: total },
      { label: "Total Questions", value: totalQ },
      { label: "Answered", value: answered },
      { label: "Remaining", value: totalQ - answered },
    ];

    kpiGrid.innerHTML = kpis.map(function (k) {
      return (
        '<div class="kpi-card">' +
        '<div class="kpi-value">' + k.value + "</div>" +
        '<div class="kpi-label">' + escapeHtml(k.label) + "</div>" +
        "</div>"
      );
    }).join("");
  }

  /* ── Table rendering ────────────────────────────────────── */

  function parseQuestions(raw) {
    try { return JSON.parse(raw || "[]"); } catch (_) { return []; }
  }

  function renderTable(sessionsData) {
    if (!sessionsData || sessionsData.length === 0) {
      if (tableWrap)  tableWrap.setAttribute("hidden", "");
      if (loadingMsg) loadingMsg.setAttribute("hidden", "");
      if (emptyMsg)   emptyMsg.removeAttribute("hidden");
      return;
    }
    if (loadingMsg) loadingMsg.setAttribute("hidden", "");
    if (emptyMsg)   emptyMsg.setAttribute("hidden", "");
    if (tableWrap)  tableWrap.removeAttribute("hidden");

    tbody.innerHTML = "";
    sessionsData.forEach(function (s) {
      var qs       = parseQuestions(s.questions_json);
      var answered = countAnswered(qs);
      var total    = qs.length;
      var pct      = total > 0 ? Math.round((answered / total) * 100) : 0;

      var tr = document.createElement("tr");
      tr.style.cursor = "pointer";
      tr.title = "Open prep session";

      tr.innerHTML =
        "<td>" + escapeHtml(s.company || "—") + "</td>" +
        "<td>" + escapeHtml(s.role || "—") + "</td>" +
        "<td>" + formatDate(s.created_at) + "</td>" +
        "<td>" + total + "</td>" +
        "<td>" +
          '<div style="display:flex;align-items:center;gap:8px">' +
            '<div style="flex:1;height:6px;background:var(--shell-border);border-radius:3px;min-width:60px">' +
              '<div style="width:' + pct + '%;height:100%;background:var(--shell-accent);border-radius:3px"></div>' +
            "</div>" +
            '<span style="font-size:0.75rem;color:var(--shell-text-soft);white-space:nowrap">' + answered + "/" + total + "</span>" +
          "</div>" +
        "</td>" +
        '<td><button class="ip-open-btn btn-secondary" style="font-size:0.8rem;padding:4px 10px" data-id="' + s.id + '">Open</button></td>';

      tr.querySelector(".ip-open-btn").addEventListener("click", function (e) {
        e.stopPropagation();
        openDrawer(s.id);
      });
      tr.addEventListener("click", function () { openDrawer(s.id); });
      tbody.appendChild(tr);
    });
  }

  /* ── Load sessions ──────────────────────────────────────── */

  function loadSessions() {
    if (loadingMsg) loadingMsg.removeAttribute("hidden");
    if (tableWrap)  tableWrap.setAttribute("hidden", "");
    if (emptyMsg)   emptyMsg.setAttribute("hidden", "");

    return fetchJson("/api/interview-prep")
      .then(function (data) {
        sessions = data.sessions || [];
        renderKpi(sessions);
        renderTable(sessions);
      })
      .catch(function (err) {
        if (loadingMsg) loadingMsg.textContent = "Failed to load sessions: " + err.message;
      });
  }

  /* ── Modal ──────────────────────────────────────────────── */

  function openModal() {
    if (formError) formError.setAttribute("hidden", "");
    if (fCompany)  fCompany.value = "";
    if (fRole)     fRole.value    = "";
    if (fApp)      fApp.value     = "";
    if (submitBtn) submitBtn.disabled = false;
    populateApplicationSelect();
    if (modal) modal.removeAttribute("hidden");
  }

  function closeModal() {
    if (modal) modal.setAttribute("hidden", "");
  }

  function populateApplicationSelect() {
    if (!fApp) return;
    // Keep the "None" option, remove others
    while (fApp.options.length > 1) fApp.remove(1);
    fetchJson("/api/applications?limit=100")
      .then(function (data) {
        (data.items || []).forEach(function (app) {
          var opt = document.createElement("option");
          opt.value = app.id;
          opt.textContent = (app.company || "Unknown") + " — " + (app.role || "Untitled");
          fApp.appendChild(opt);
        });
      })
      .catch(function () { /* silently ignore */ });
  }

  if (fApp) {
    fApp.addEventListener("change", function () {
      var selected = fApp.options[fApp.selectedIndex];
      if (!selected || !selected.value) return;
      // Parse "Company — Role" text to prefill fields
      var parts = selected.textContent.split(" — ");
      if (parts.length >= 2 && fCompany && !fCompany.value) {
        fCompany.value = parts[0].trim();
      }
      if (parts.length >= 2 && fRole && !fRole.value) {
        fRole.value = parts.slice(1).join(" — ").trim();
      }
    });
  }

  if (newBtn)     newBtn.addEventListener("click", openModal);
  if (modalClose) modalClose.addEventListener("click", closeModal);
  if (modalCancel) modalCancel.addEventListener("click", closeModal);

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var role    = (fRole    ? fRole.value.trim()    : "");
      var company = (fCompany ? fCompany.value.trim() : "");
      var appId   = fApp && fApp.value ? parseInt(fApp.value, 10) : null;

      if (!role) {
        if (formError) { formError.textContent = "Role is required."; formError.removeAttribute("hidden"); }
        return;
      }
      if (submitBtn) submitBtn.disabled = true;

      var body = { role: role, company: company };
      if (appId) body.application_id = appId;

      fetchJson("/api/interview-prep", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (data) {
          closeModal();
          return loadSessions().then(function () {
            if (data.session) openDrawer(data.session.id);
          });
        })
        .catch(function (err) {
          if (formError) { formError.textContent = err.message; formError.removeAttribute("hidden"); }
          if (submitBtn) submitBtn.disabled = false;
        });
    });
  }

  /* ── Drawer ─────────────────────────────────────────────── */

  function openDrawer(sessionId) {
    fetchJson("/api/interview-prep/" + sessionId)
      .then(function (data) {
        openSession = data.session;
        renderDrawer(openSession);
        if (drawerOverlay) drawerOverlay.removeAttribute("hidden");
      })
      .catch(function (err) {
        alert("Could not load prep session: " + err.message);
      });
  }

  function closeDrawer() {
    if (drawerOverlay) drawerOverlay.setAttribute("hidden", "");
    openSession = null;
  }

  if (drawerClose)   drawerClose.addEventListener("click", closeDrawer);
  if (drawerOverlay) {
    drawerOverlay.addEventListener("click", function (e) {
      if (e.target === drawerOverlay) closeDrawer();
    });
  }

  function renderDrawer(session) {
    if (drawerCompany) drawerCompany.textContent = session.company || "—";
    if (drawerRole)    drawerRole.textContent    = session.role    || "—";
    if (drawerNotes)   drawerNotes.value         = session.notes   || "";
    if (notesSaved)    notesSaved.setAttribute("hidden", "");

    var qs       = parseQuestions(session.questions_json);
    var answered = countAnswered(qs);
    if (progressLabel) progressLabel.textContent = answered + "/" + qs.length + " answered";

    renderQuestions(qs);
  }

  function renderQuestions(qs) {
    if (!questionsList) return;
    questionsList.innerHTML = "";

    if (qs.length === 0) {
      questionsList.innerHTML = '<p style="color:var(--shell-text-soft);font-size:0.85rem">No questions in this session.</p>';
      return;
    }

    qs.forEach(function (q, idx) {
      var card = document.createElement("div");
      card.style.cssText = "background:var(--shell-surface-soft);border:1px solid var(--shell-border);border-radius:8px;padding:12px 14px";

      var header = document.createElement("div");
      header.style.cssText = "display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:8px";

      var titleRow = document.createElement("div");
      titleRow.style.cssText = "display:flex;align-items:flex-start;gap:8px;flex:1";
      titleRow.innerHTML =
        '<span style="font-size:0.75rem;color:var(--shell-text-soft);flex-shrink:0;padding-top:2px">' + (idx + 1) + ".</span>" +
        '<span style="font-size:0.85rem;font-weight:500;color:var(--shell-text-strong);line-height:1.4">' +
        escapeHtml(q.text) +
        "</span>";

      var badgeRow = document.createElement("div");
      badgeRow.style.cssText = "flex-shrink:0";
      badgeRow.innerHTML = categoryBadge(q.category);

      header.appendChild(titleRow);
      header.appendChild(badgeRow);
      card.appendChild(header);

      // Confidence selector
      var confRow = document.createElement("div");
      confRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:6px";
      confRow.innerHTML = '<span style="font-size:0.75rem;color:var(--shell-text-soft)">Confidence:</span>';
      var confSel = document.createElement("select");
      confSel.style.cssText = "font-size:0.75rem;padding:2px 6px;border:1px solid var(--shell-border);border-radius:4px;background:var(--shell-surface);color:var(--shell-text);cursor:pointer";
      confSel.dataset.qid = q.id;
      [["", "Not set"], ["low", "Low"], ["medium", "Medium"], ["high", "High"]].forEach(function (pair) {
        var opt = document.createElement("option");
        opt.value = pair[0];
        opt.textContent = pair[1];
        if ((q.confidence || "") === pair[0]) opt.selected = true;
        confSel.appendChild(opt);
      });
      confRow.appendChild(confSel);

      var confIndicator = document.createElement("span");
      confIndicator.style.cssText = "font-size:0.75rem;font-weight:600;" + confidenceClass(q.confidence);
      confIndicator.textContent = q.confidence || "";
      confRow.appendChild(confIndicator);
      card.appendChild(confRow);

      // Answer textarea
      var answerLabel = document.createElement("div");
      answerLabel.style.cssText = "font-size:0.75rem;color:var(--shell-text-soft);margin-bottom:4px";
      answerLabel.textContent = "Your answer (STAR format)";
      card.appendChild(answerLabel);

      var textarea = document.createElement("textarea");
      textarea.style.cssText = "width:100%;box-sizing:border-box;font-size:0.8rem;padding:8px;border:1px solid var(--shell-border);border-radius:6px;background:var(--shell-surface);color:var(--shell-text);resize:vertical;min-height:80px;font-family:inherit";
      textarea.placeholder = "Situation, Task, Action, Result…";
      textarea.value = q.answer || "";
      textarea.dataset.qid = q.id;
      card.appendChild(textarea);

      // Save button
      var saveRow = document.createElement("div");
      saveRow.style.cssText = "display:flex;justify-content:flex-end;margin-top:6px;gap:8px;align-items:center";
      var savedTick = document.createElement("span");
      savedTick.style.cssText = "font-size:0.75rem;color:var(--shell-success);display:none";
      savedTick.textContent = "Saved";
      var saveQBtn = document.createElement("button");
      saveQBtn.className = "btn-primary";
      saveQBtn.style.cssText = "font-size:0.75rem;padding:4px 10px";
      saveQBtn.textContent = "Save";
      saveRow.appendChild(savedTick);
      saveRow.appendChild(saveQBtn);
      card.appendChild(saveRow);

      // Event handlers
      confSel.addEventListener("change", function () {
        confIndicator.textContent = confSel.value;
        confIndicator.style.cssText = "font-size:0.75rem;font-weight:600;" + confidenceClass(confSel.value);
      });

      saveQBtn.addEventListener("click", function () {
        saveQBtn.disabled = true;
        var updatedQuestions = getCurrentQuestions();
        saveQuestions(updatedQuestions, function () {
          savedTick.style.display = "inline";
          setTimeout(function () { savedTick.style.display = "none"; }, 2000);
          saveQBtn.disabled = false;
        }, function (err) {
          alert("Save failed: " + err.message);
          saveQBtn.disabled = false;
        });
      });

      questionsList.appendChild(card);
    });
  }

  function getCurrentQuestions() {
    if (!openSession) return [];
    var qs = parseQuestions(openSession.questions_json);
    if (!questionsList) return qs;

    questionsList.querySelectorAll("textarea[data-qid]").forEach(function (ta) {
      var q = qs.find(function (x) { return x.id === ta.dataset.qid; });
      if (q) q.answer = ta.value;
    });
    questionsList.querySelectorAll("select[data-qid]").forEach(function (sel) {
      var q = qs.find(function (x) { return x.id === sel.dataset.qid; });
      if (q) q.confidence = sel.value;
    });
    return qs;
  }

  function saveQuestions(questions, onSuccess, onError) {
    if (!openSession) return;
    fetchJson("/api/interview-prep/" + openSession.id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ questions: questions }),
    })
      .then(function (data) {
        if (data.session) {
          openSession = data.session;
          var answered = countAnswered(parseQuestions(openSession.questions_json));
          var total    = parseQuestions(openSession.questions_json).length;
          if (progressLabel) progressLabel.textContent = answered + "/" + total + " answered";
          // Refresh table row without full reload
          updateSessionInList(openSession);
        }
        if (onSuccess) onSuccess();
      })
      .catch(function (err) {
        if (onError) onError(err);
      });
  }

  function updateSessionInList(session) {
    var idx = sessions.findIndex(function (s) { return s.id === session.id; });
    if (idx !== -1) sessions[idx] = session;
    renderKpi(sessions);
    renderTable(sessions);
  }

  /* ── Notes save ─────────────────────────────────────────── */

  if (notesSaveBtn) {
    notesSaveBtn.addEventListener("click", function () {
      if (!openSession) return;
      notesSaveBtn.disabled = true;
      var notes = drawerNotes ? drawerNotes.value : "";
      fetchJson("/api/interview-prep/" + openSession.id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes }),
      })
        .then(function (data) {
          if (data.session) {
            openSession = data.session;
            updateSessionInList(openSession);
          }
          if (notesSaved) { notesSaved.removeAttribute("hidden"); setTimeout(function () { notesSaved.setAttribute("hidden", ""); }, 2000); }
          notesSaveBtn.disabled = false;
        })
        .catch(function (err) {
          alert("Save failed: " + err.message);
          notesSaveBtn.disabled = false;
        });
    });
  }

  /* ── Delete session ─────────────────────────────────────── */

  if (deleteBtn) {
    deleteBtn.addEventListener("click", function () {
      if (!openSession) return;
      if (!confirm("Delete this prep session? This cannot be undone.")) return;
      fetchJson("/api/interview-prep/" + openSession.id + "/delete", { method: "POST" })
        .then(function () {
          closeDrawer();
          loadSessions();
        })
        .catch(function (err) {
          alert("Delete failed: " + err.message);
        });
    });
  }

  /* ── Init: load when section becomes active ─────────────── */

  if (sectionEl) {
    var observer = new MutationObserver(function () {
      if (sectionEl.classList.contains("active") && sessions.length === 0) {
        loadSessions();
      }
    });
    observer.observe(sectionEl, { attributes: true, attributeFilter: ["class"] });
  }

  if (window.CUSTOMY_CONFIG && window.CUSTOMY_CONFIG.mode === "local") {
    loadSessions();
  }

  window.CustomyInterviewPrep = { refresh: loadSessions };
})();
