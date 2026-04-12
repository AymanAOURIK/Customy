/**
 * CJobTracker — Job management UI for Customy WT6.
 *
 * Endpoints consumed:
 *   GET    /api/jobs              list (optional ?status=)
 *   POST   /api/jobs              create
 *   PATCH  /api/jobs/<id>/status  update status
 *   DELETE /api/jobs/<id>         delete
 *
 * init() is called from the auth bootstrap in dashboard.html:
 *   - In local mode  → shows the SaaS-only gate notice.
 *   - In SaaS mode   → called when a session is confirmed; loads the job list.
 *
 * The module exposes window.CJobTracker = { init }.
 */
(function () {
  "use strict";

  /* ── Constants ───────────────────────────────────────────────────────── */

  var VALID_STATUSES = [
    "saved", "applied", "interviewing", "offer",
    "rejected", "ghosted", "archived",
  ];

  /* ── State ───────────────────────────────────────────────────────────── */

  var _currentStatus = "";  // active filter tab value
  var _jobs = [];           // last loaded list (used for status-revert on error)
  var _initialized = false; // event listeners wired?

  /* ── DOM helpers ─────────────────────────────────────────────────────── */

  function _$(id) { return document.getElementById(id); }

  function _escHtml(str) {
    return String(str || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function _fmtDate(iso) {
    if (!iso) return "\u2014";
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: "numeric",
      });
    } catch (_) {
      return String(iso).slice(0, 10);
    }
  }

  /* ── API calls (via CAuth.authFetch for JWT injection) ───────────────── */

  function _apiFetch(url, opts) {
    return CAuth.authFetch(url, opts).then(function (res) {
      return res.json().then(function (body) {
        return { status: res.status, body: body };
      });
    });
  }

  function _apiLoadJobs(status) {
    var qs = status ? ("?status=" + encodeURIComponent(status)) : "";
    return _apiFetch("/api/jobs" + qs);
  }

  function _apiCreateJob(data) {
    return _apiFetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  }

  function _apiUpdateStatus(jobId, status) {
    return _apiFetch("/api/jobs/" + jobId + "/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: status }),
    });
  }

  function _apiDeleteJob(jobId) {
    return _apiFetch("/api/jobs/" + jobId, { method: "DELETE" });
  }

  /* ── Rendering ───────────────────────────────────────────────────────── */

  function _statusSelect(job) {
    var opts = VALID_STATUSES.map(function (v) {
      var label = v.charAt(0).toUpperCase() + v.slice(1);
      return '<option value="' + v + '"' + (v === job.status ? " selected" : "") + ">" + label + "</option>";
    }).join("");
    return '<select class="shell-status-select jt-status-sel" data-job-id="' + job.id + '">' + opts + "</select>";
  }

  function _renderRows(jobs) {
    var tbody = _$("jt-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    jobs.forEach(function (job) {
      var tr = document.createElement("tr");
      tr.dataset.jobId = job.id;
      var viewLink = job.source_url
        ? '<a class="jt-action-link" href="' + _escHtml(job.source_url) + '" target="_blank" rel="noopener noreferrer">View</a> '
        : "";
      var score = job.relevance_score != null
        ? Math.round(job.relevance_score * 100) + "%"
        : "\u2014";
      tr.innerHTML =
        "<td>" + _escHtml(job.title) + "</td>" +
        "<td>" + _escHtml(job.company || "\u2014") + "</td>" +
        "<td>" + _escHtml(job.location_raw || "\u2014") + "</td>" +
        "<td>" + _statusSelect(job) + "</td>" +
        "<td>" + score + "</td>" +
        "<td>" + _fmtDate(job.created_at) + "</td>" +
        '<td class="jt-actions">' +
          viewLink +
          '<button class="jt-delete-btn" data-job-id="' + job.id + '" title="Delete job">&#x2715;</button>' +
        "</td>";
      tbody.appendChild(tr);
    });
  }

  /* ── UI state machine ────────────────────────────────────────────────── */

  function _showState(state) {
    // state: "loading" | "empty" | "table"
    var loading = _$("jt-loading");
    var empty   = _$("jt-empty");
    var wrap    = _$("jt-table-wrap");
    if (loading) loading.hidden = (state !== "loading");
    if (empty)   empty.hidden   = (state !== "empty");
    if (wrap)    wrap.hidden    = (state !== "table");
  }

  /* ── Load / refresh ──────────────────────────────────────────────────── */

  function _refresh() {
    _showState("loading");
    _apiLoadJobs(_currentStatus)
      .then(function (result) {
        if (result.status !== 200) {
          _showState("empty");
          return;
        }
        _jobs = result.body.jobs || [];
        if (_jobs.length === 0) {
          _showState("empty");
        } else {
          _renderRows(_jobs);
          _showState("table");
        }
      })
      .catch(function (err) {
        console.error("[JobTracker] load error:", err);
        _showState("empty");
      });
  }

  /* ── Filter bar ──────────────────────────────────────────────────────── */

  function _initFilterBar() {
    var bar = _$("jt-filter-bar");
    if (!bar) return;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".jt-tab");
      if (!btn) return;
      bar.querySelectorAll(".jt-tab").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      _currentStatus = btn.dataset.status || "";
      _refresh();
    });
  }

  /* ── Table events (status change + delete) ───────────────────────────── */

  function _initTableEvents() {
    var tbody = _$("jt-tbody");
    if (!tbody) return;

    // Cache the selected value on focus so we can revert on error
    tbody.addEventListener("focus", function (e) {
      var sel = e.target.closest(".jt-status-sel");
      if (sel) sel.dataset.prev = sel.value;
    }, true);

    tbody.addEventListener("change", function (e) {
      var sel = e.target.closest(".jt-status-sel");
      if (!sel) return;
      var jobId = sel.dataset.jobId;
      var prev  = sel.dataset.prev || sel.value;
      _apiUpdateStatus(jobId, sel.value)
        .then(function (result) {
          if (result.status !== 200) {
            sel.value = prev;
            return;
          }
          sel.dataset.prev = sel.value;
          // Refresh list when filtering by status and this row would now be filtered out
          if (_currentStatus && sel.value !== _currentStatus) {
            _refresh();
          }
        })
        .catch(function () { sel.value = prev; });
    });

    tbody.addEventListener("click", function (e) {
      var btn = e.target.closest(".jt-delete-btn");
      if (!btn) return;
      if (!confirm("Delete this job? This cannot be undone.")) return;
      var jobId = btn.dataset.jobId;
      _apiDeleteJob(jobId)
        .then(function () { _refresh(); })
        .catch(function (err) {
          alert("Delete failed: " + (err && err.message ? err.message : String(err)));
        });
    });
  }

  /* ── Add Job modal ───────────────────────────────────────────────────── */

  function _initModal() {
    var addBtn    = _$("jt-add-btn");
    var modal     = _$("jt-modal");
    var closeBtn  = _$("jt-modal-close");
    var cancelBtn = _$("jt-modal-cancel");
    var form      = _$("jt-form");
    var errEl     = _$("jt-form-error");
    var submitBtn = _$("jt-submit");
    if (!addBtn || !modal || !form) return;

    function _openModal() {
      form.reset();
      if (errEl) errEl.hidden = true;
      modal.hidden = false;
    }

    function _closeModal() {
      modal.hidden = true;
    }

    addBtn.hidden = false;
    addBtn.addEventListener("click", _openModal);
    if (closeBtn)  closeBtn.addEventListener("click", _closeModal);
    if (cancelBtn) cancelBtn.addEventListener("click", _closeModal);
    modal.addEventListener("click", function (e) {
      if (e.target === modal) _closeModal();
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();

      var titleEl = _$("jt-f-title");
      var descEl  = _$("jt-f-description");
      var title   = titleEl ? titleEl.value.trim() : "";
      var desc    = descEl  ? descEl.value.trim()  : "";

      if (!title || !desc) {
        if (errEl) {
          errEl.textContent = "Job Title and Job Description are required.";
          errEl.hidden = false;
        }
        return;
      }

      if (submitBtn) submitBtn.disabled = true;
      if (errEl) errEl.hidden = true;

      var payload = {
        title:            title,
        company:          (_$("jt-f-company")  || {}).value ? (_$("jt-f-company").value.trim() || null)  : null,
        source_url:       (_$("jt-f-url")      || {}).value ? (_$("jt-f-url").value.trim() || null)      : null,
        location_raw:     (_$("jt-f-location") || {}).value ? (_$("jt-f-location").value.trim() || null) : null,
        salary_raw:       (_$("jt-f-salary")   || {}).value ? (_$("jt-f-salary").value.trim() || null)   : null,
        description_text: desc,
        notes:            (_$("jt-f-notes")    || {}).value ? (_$("jt-f-notes").value.trim() || null)    : null,
      };

      _apiCreateJob(payload)
        .then(function (result) {
          if (result.status === 201) {
            _closeModal();
            _refresh();
          } else {
            var msg = (result.body && result.body.error) || ("Error " + result.status);
            if (errEl) { errEl.textContent = msg; errEl.hidden = false; }
          }
        })
        .catch(function (err) {
          if (errEl) {
            errEl.textContent = "Network error: " + (err && err.message ? err.message : String(err));
            errEl.hidden = false;
          }
        })
        .finally(function () {
          if (submitBtn) submitBtn.disabled = false;
        });
    });
  }

  /* ── Public init ─────────────────────────────────────────────────────── */

  function init() {
    var cfg         = window.CUSTOMY_CONFIG || { mode: "local" };
    var localNotice = _$("jt-local-notice");
    var mainCard    = _$("jt-main");

    if (cfg.mode !== "saas") {
      if (localNotice) localNotice.hidden = false;
      if (mainCard)    mainCard.hidden    = true;
      return;
    }

    // SaaS mode
    if (localNotice) localNotice.hidden = true;
    if (mainCard)    mainCard.hidden    = false;

    // Wire event listeners once; _refresh is safe to call repeatedly
    if (!_initialized) {
      _initialized = true;
      _initFilterBar();
      _initTableEvents();
      _initModal();
    }

    _refresh();
  }

  window.CJobTracker = { init: init };
})();
