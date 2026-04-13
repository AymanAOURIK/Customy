/**
 * COnboarding — Phase 1 onboarding controller.
 *
 * Manages the upload panel and draft summary panel inside #section-profile-editor.
 * Called by the auth bootstrap in dashboard.html when no profile exists.
 *
 * Flow:
 *  1. init() — fetch GET /api/onboarding/draft
 *     → 200 exists=false: show upload panel, bind upload handler
 *     → 200 exists=true: show draft summary, enable "Pre-fill My Profile" button
 *  2. User uploads resume → POST /api/resume/upload → show draft summary
 *  3. User clicks "Pre-fill My Profile" → CProfileEditor.populate(draft_data)
 *  4. User reviews form, clicks "Create Profile" → customy:profile-created → gate removed
 */
(function () {
  "use strict";

  var _draft = null;

  function _$(id) {
    return document.getElementById(id);
  }

  function _esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function _showPanel(which) {
    var upload = _$("onboarding-upload-panel");
    var draft  = _$("onboarding-draft-panel");
    if (upload) upload.hidden = (which !== "upload");
    if (draft)  draft.hidden  = (which !== "draft");
  }

  function _errorMessage(body, fallback) {
    if (!body) return fallback;
    if (body.error && typeof body.error === "object" && body.error.message) {
      return body.error.message;
    }
    return body.detail || body.error || fallback;
  }

  /* ── Draft summary rendering ──────────────────────────── */

  function _renderDraftSummary(data) {
    var container = _$("onboarding-draft-summary");
    if (!container) return;

    var dd  = data.draft_data  || {};
    var gap = data.gap_analysis || {};

    var lines = [];

    if (dd.full_name) {
      lines.push("<strong>" + _esc(dd.full_name) + "</strong>");
    }
    if (dd.headline) {
      lines.push(_esc(dd.headline));
    }

    var expCount   = (dd.experiences || []).length;
    var skillCount = gap.skill_count || 0;
    var meta = [];
    if (expCount   > 0) meta.push(expCount   + " experience" + (expCount   !== 1 ? "s" : "") + " extracted");
    if (skillCount > 0) meta.push(skillCount + " skill"      + (skillCount !== 1 ? "s" : "") + " detected");
    if (meta.length > 0) lines.push(meta.join(" &middot; "));

    if (gap.resume_currency_uncertain) {
      lines.push(
        "<span class=\"onboarding-warning\">" +
        "&#9888;&nbsp;Resume may be outdated — confirm your current role in the next step." +
        "</span>"
      );
    }

    var missingMetrics = (gap.bullets_missing_metrics || []).length;
    var thinSkills     = gap.thin_skills;
    var notes = [];
    if (missingMetrics > 0) notes.push(missingMetrics + " bullet" + (missingMetrics !== 1 ? "s" : "") + " could benefit from quantification");
    if (thinSkills)         notes.push("skill inventory looks thin — you&rsquo;ll be asked to confirm and expand it");
    if (notes.length > 0) {
      lines.push("<span class=\"onboarding-note\">" + notes.join(" &middot; ") + "</span>");
    }

    container.innerHTML = lines.join("<br>");
  }

  /* ── Upload handler ───────────────────────────────────── */

  function _bindUpload() {
    var btn    = _$("onboarding-upload-btn");
    var input  = _$("onboarding-file-input");
    var status = _$("onboarding-upload-status");

    if (!btn || !input) return;

    btn.addEventListener("click", function () {
      if (!input.files || !input.files[0]) {
        if (status) status.textContent = "Please select a file first.";
        return;
      }

      var file = input.files[0];
      var formData = new FormData();
      formData.append("file", file);

      btn.disabled      = true;
      btn.textContent   = "Uploading\u2026";
      if (status) {
        status.textContent  = "Extracting resume data\u2026 this may take a few seconds.";
        status.className    = "onboarding-status onboarding-status--info";
      }

      CAuth.authFetch("/api/resume/upload", { method: "POST", body: formData })
        .then(function (r) {
          return r.json().then(function (body) { return { status: r.status, body: body }; });
        })
        .then(function (result) {
          btn.disabled    = false;
          btn.textContent = "Upload Resume";

          if (result.status !== 200) {
            var msg = _errorMessage(result.body, "Upload failed.");
            if (status) {
              status.textContent = msg;
              status.className   = "onboarding-status onboarding-status--error";
            }
            return;
          }

          _draft = result.body;
          _showPanel("draft");
          _renderDraftSummary(result.body);
          _bindPrefill(result.body.draft_data);
          _bindReupload();
        })
        .catch(function () {
          btn.disabled    = false;
          btn.textContent = "Upload Resume";
          if (status) {
            status.textContent = "Upload failed. Check your connection and try again.";
            status.className   = "onboarding-status onboarding-status--error";
          }
        });
    });
  }

  /* ── Pre-fill button ──────────────────────────────────── */

  function _bindPrefill(draft_data) {
    var prefillBtn = _$("onboarding-prefill-btn");
    if (!prefillBtn) return;

    prefillBtn.removeAttribute("hidden");
    prefillBtn.addEventListener("click", function () {
      if (window.CProfileEditor && typeof CProfileEditor.populate === "function") {
        CProfileEditor.populate(draft_data);
        prefillBtn.textContent = "Form pre-filled — review and save below";
        prefillBtn.disabled    = true;

        // Scroll the form into view
        var formWrap = _$("profile-editor-form-wrap");
        if (formWrap) formWrap.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  /* ── Re-upload button ─────────────────────────────────── */

  function _bindReupload() {
    var btn = _$("onboarding-reupload-btn");
    if (!btn) return;
    btn.addEventListener("click", function () {
      _showPanel("upload");
      _bindUpload();
    });
  }

  /* ── Public init ──────────────────────────────────────── */

  function init() {
    var cfg = window.CUSTOMY_CONFIG || { mode: "local" };
    if (cfg.mode !== "saas") return;
    if (!window.CAuth || !CAuth.getToken()) return;

    CAuth.authFetch("/api/onboarding/draft")
      .then(function (r) {
        return r.json().then(function (data) {
          return { status: r.status, body: data };
        });
      })
      .then(function (result) {
        if (result.status === 200 && result.body && result.body.exists === true) {
          _draft = result.body;
          _showPanel("draft");
          _renderDraftSummary(result.body);
          _bindPrefill((result.body.draft_data || {}));
          _bindReupload();
          return;
        }
        _showPanel("upload");
        _bindUpload();
      })
      .catch(function () {
        _showPanel("upload");
        _bindUpload();
      });
  }

  window.COnboarding = { init: init };
})();
