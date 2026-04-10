(function () {
  "use strict";

  /* ── Constants ───────────────────────────────────────── */

  var ARCHETYPE_LABELS = {
    ai_platform: "AI Platform",
    agentic: "Agentic",
    ai_pm: "AI PM",
    ai_architect: "Architect",
    ai_forward_deployed: "Fwd Deployed",
    ai_transformation: "Transformation",
    general: "General",
  };

  var CATEGORY_LABELS = {
    work_authorization: "Work Authorization",
    salary: "Salary Expectations",
    availability: "Availability / Start Date",
    relocation: "Relocation",
    linkedin: "LinkedIn URL",
    github: "GitHub / Portfolio",
    other: "Other",
  };

  /* ── State ───────────────────────────────────────────── */

  var _queue = [];
  var _selectedArchetype = "";
  var _minScore = 0;

  /* ── DOM refs ────────────────────────────────────────── */

  var tableBody = document.getElementById("aq-table-body");
  var readyCount = document.getElementById("aq-ready-count");
  var archetypeFilters = document.getElementById("aq-archetype-filters");
  var minScoreInput = document.getElementById("aq-min-score");
  var refreshBtn = document.getElementById("aq-refresh-btn");
  var modalOverlay = document.getElementById("aq-modal-overlay");
  var modalBody = document.getElementById("aq-modal-body");
  var modalClose = document.getElementById("aq-modal-close");
  var answersList = document.getElementById("aq-answers-list");
  var newCategorySelect = document.getElementById("aq-new-category");
  var newQuestionInput = document.getElementById("aq-new-question");
  var newAnswerInput = document.getElementById("aq-new-answer");
  var saveAnswerBtn = document.getElementById("aq-save-answer-btn");

  if (!tableBody) return; // section not present

  /* ── Helpers ─────────────────────────────────────────── */

  function escHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtDate(iso) {
    if (!iso) return "-";
    try {
      return iso.slice(0, 10);
    } catch (_) {
      return iso;
    }
  }

  function scoreClass(score) {
    if (score == null) return "aq-score--none";
    if (score >= 70) return "aq-score--high";
    if (score >= 50) return "aq-score--mid";
    return "aq-score--low";
  }

  /* ── Load queue ──────────────────────────────────────── */

  function loadQueue() {
    if (tableBody) {
      tableBody.innerHTML =
        '<tr><td colspan="7" class="aq-empty-row">Loading&hellip;</td></tr>';
    }
    fetch("/api/apply-queue?min_score=" + _minScore)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _queue = data.applications || [];
        renderQueue();
      })
      .catch(function () {
        if (tableBody) {
          tableBody.innerHTML =
            '<tr><td colspan="7" class="aq-empty-row">Failed to load queue.</td></tr>';
        }
      });
  }

  /* ── Render queue table ──────────────────────────────── */

  function renderQueue() {
    var filtered = _queue.filter(function (app) {
      if (_selectedArchetype && app.archetype !== _selectedArchetype) return false;
      return true;
    });

    if (readyCount) {
      readyCount.textContent = filtered.length + " ready";
    }

    if (!filtered.length) {
      tableBody.innerHTML =
        '<tr><td colspan="7" class="aq-empty-row">No applications in queue' +
        (_selectedArchetype ? " for this archetype" : "") + ".</td></tr>";
      return;
    }

    tableBody.innerHTML = filtered
      .map(function (app) {
        var score = app.score != null ? Number(app.score).toFixed(1) : "-";
        var sClass = scoreClass(app.score);
        var arch = app.archetype || "general";
        var archLabel = ARCHETYPE_LABELS[arch] || arch;
        var ats = escHtml(app.ats_vendor || "-");
        var jobUrl = app.job_application_url
          ? '<a href="' + escHtml(app.job_application_url) + '" target="_blank" rel="noreferrer" class="aq-ext-link">Open</a>'
          : "-";

        return (
          "<tr>" +
          '<td><span class="aq-score-badge ' + sClass + '">' + score + "</span></td>" +
          '<td><span class="aq-arch-badge aq-arch--' + escHtml(arch) + '">' + escHtml(archLabel) + "</span></td>" +
          '<td class="aq-cell-company">' + escHtml(app.company || "-") + "</td>" +
          '<td class="aq-cell-role">' + escHtml(app.role || "-") + "</td>" +
          '<td class="aq-cell-date">' + fmtDate(app.created_at) + "</td>" +
          "<td>" + ats + "</td>" +
          '<td class="aq-cell-actions">' +
            '<button class="aq-btn" onclick="AQ.openFolder(' + app.id + ')">Package</button>' +
            '<button class="aq-btn" onclick="AQ.openAnswers(' + app.id + ')">Answers</button>' +
            '<button class="aq-btn aq-btn--apply" onclick="AQ.markApplied(' + app.id + ', this)">Applied ✓</button>' +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  /* ── Actions ─────────────────────────────────────────── */

  function markApplied(appId, btn) {
    if (btn) btn.disabled = true;
    fetch("/api/applications/" + appId + "/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_status: "applied" }),
    })
      .then(function () { loadQueue(); })
      .catch(function () { if (btn) btn.disabled = false; });
  }

  function openFolder(appId) {
    fetch("/api/applications/" + appId + "/open-folder", { method: "POST" }).catch(
      function () {}
    );
  }

  function openAnswers() {
    renderAnswerModal();
    if (modalOverlay) modalOverlay.classList.add("aq-modal-overlay--visible");
  }

  /* ── Answer bank modal ───────────────────────────────── */

  function renderAnswerModal() {
    fetch("/api/answer-bank")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var answers = data.answers || [];
        if (!answersList) return;
        if (!answers.length) {
          answersList.innerHTML =
            '<p class="aq-modal-hint">No answers saved yet. Add your first answer below.</p>';
          return;
        }
        answersList.innerHTML = answers
          .map(function (a) {
            var cat = CATEGORY_LABELS[a.category] || a.category || "Uncategorized";
            return (
              '<div class="aq-answer-item">' +
              '<div class="aq-answer-meta">' +
                '<span class="aq-answer-cat">' + escHtml(cat) + "</span>" +
                '<button class="aq-answer-delete" onclick="AQ.deleteAnswer(' + JSON.stringify(a.question_key) + ')">Delete</button>' +
              "</div>" +
              '<div class="aq-answer-q">' + escHtml(a.question_text || a.question_key) + "</div>" +
              '<div class="aq-answer-a">' + escHtml(a.answer_text) + "</div>" +
              '<button class="aq-copy-btn" onclick="AQ.copyAnswer(' + JSON.stringify(a.answer_text) + ')">Copy</button>' +
              "</div>"
            );
          })
          .join("");
      })
      .catch(function () {
        if (answersList) answersList.innerHTML = "<p>Failed to load answers.</p>";
      });
  }

  function saveAnswer() {
    var category = newCategorySelect ? newCategorySelect.value.trim() : "";
    var questionText = newQuestionInput ? newQuestionInput.value.trim() : "";
    var answerText = newAnswerInput ? newAnswerInput.value.trim() : "";
    if (!category || !answerText) {
      alert("Select a category and enter an answer.");
      return;
    }
    var key = category + (questionText ? "_" + questionText.toLowerCase().replace(/\W+/g, "_").slice(0, 30) : "");
    fetch("/api/answer-bank", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_key: key,
        question_text: questionText || CATEGORY_LABELS[category] || category,
        answer_text: answerText,
        category: category,
        language: "en",
      }),
    })
      .then(function () {
        if (newQuestionInput) newQuestionInput.value = "";
        if (newAnswerInput) newAnswerInput.value = "";
        if (newCategorySelect) newCategorySelect.value = "";
        renderAnswerModal();
      })
      .catch(function () { alert("Failed to save answer."); });
  }

  function deleteAnswer(questionKey) {
    fetch("/api/answer-bank/" + encodeURIComponent(questionKey) + "/delete", {
      method: "POST",
    })
      .then(function () { renderAnswerModal(); })
      .catch(function () {});
  }

  function copyAnswer(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () {});
    }
  }

  /* ── Filter bindings ─────────────────────────────────── */

  if (archetypeFilters) {
    archetypeFilters.addEventListener("click", function (e) {
      var pill = e.target.closest(".aq-pill");
      if (!pill) return;
      _selectedArchetype = pill.dataset.archetype || "";
      archetypeFilters.querySelectorAll(".aq-pill").forEach(function (p) {
        p.classList.toggle("aq-pill--active", p === pill);
      });
      renderQueue();
    });
  }

  if (minScoreInput) {
    minScoreInput.addEventListener("change", function () {
      _minScore = Math.max(0, parseInt(minScoreInput.value, 10) || 0);
      loadQueue();
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", loadQueue);
  }

  /* ── Modal bindings ──────────────────────────────────── */

  if (modalClose) {
    modalClose.addEventListener("click", function () {
      if (modalOverlay) modalOverlay.classList.remove("aq-modal-overlay--visible");
    });
  }

  if (modalOverlay) {
    modalOverlay.addEventListener("click", function (e) {
      if (e.target === modalOverlay) {
        modalOverlay.classList.remove("aq-modal-overlay--visible");
      }
    });
  }

  if (saveAnswerBtn) {
    saveAnswerBtn.addEventListener("click", saveAnswer);
  }

  /* ── Refresh on generation ───────────────────────────── */

  window.addEventListener("customy:application-generated", function () {
    var aqSection = document.getElementById("section-apply-queue");
    if (aqSection && aqSection.classList.contains("active")) {
      loadQueue();
    }
  });

  /* ── Load on section activation ──────────────────────── */

  document.querySelectorAll('.sidebar-link[data-section="section-apply-queue"]').forEach(
    function (link) {
      link.addEventListener("click", function () {
        setTimeout(loadQueue, 50);
      });
    }
  );

  /* ── Public API ──────────────────────────────────────── */

  window.AQ = {
    markApplied: markApplied,
    openFolder: openFolder,
    openAnswers: openAnswers,
    deleteAnswer: deleteAnswer,
    copyAnswer: copyAnswer,
  };

  /* ── Init: load if queue section is active on page load ── */

  if (document.getElementById("section-apply-queue") &&
      document.getElementById("section-apply-queue").classList.contains("active")) {
    loadQueue();
  }
})();
