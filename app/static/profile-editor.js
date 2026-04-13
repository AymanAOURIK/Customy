/**
 * CProfileEditor — profile create/edit form for SaaS mode.
 *
 * Usage:
 *   CProfileEditor.init()  — called once from the auth bootstrap when a session
 *                            is confirmed, or immediately in local mode to show
 *                            the gated notice.
 *
 * GET /api/profile  → 200 { exists:true,  profile } populate form in update mode
 *                  → 200 { exists:false, profile } show prefilled create mode
 * POST /api/profile → create
 * PUT  /api/profile → update or upsert
 *
 * All API calls use CAuth.authFetch() so the JWT is injected automatically.
 */
(function () {
  "use strict";

  var _mode = null;        // "create" | "update"
  var _initialized = false;

  function _$(id) {
    return document.getElementById(id);
  }

  function _setStatus(msg, type) {
    var el = _$("profile-editor-status");
    if (!el) return;
    el.textContent = msg;
    el.className = "profile-editor-status" +
      (type ? " profile-editor-status--" + type : "");
  }

  function _normalizeProfileResponse(body) {
    if (body && typeof body === "object" && Object.prototype.hasOwnProperty.call(body, "exists")) {
      return body;
    }
    return { exists: true, profile: body || {} };
  }

  function _getFormData() {
    var data = {};

    var scalarFields = [
      "full_name", "email", "phone", "location",
      "linkedin", "github", "headline",
    ];
    scalarFields.forEach(function (f) {
      var el = _$("pe-" + f);
      if (el) data[f] = el.value.trim();
    });

    var summaryEl = _$("pe-summary");
    if (summaryEl) data.summary = summaryEl.value.trim();

    var jsonFields = [
      "skills", "experiences", "education",
      "spoken_languages", "scoring_keywords",
    ];
    jsonFields.forEach(function (f) {
      var el = _$("pe-" + f);
      if (!el) return;
      var raw = el.value.trim();
      if (!raw) return;
      try {
        data[f] = JSON.parse(raw);
      } catch (_e) {
        // pass raw string; server will surface the error
        data[f] = raw;
      }
    });

    return data;
  }

  function _populateForm(profile) {
    var scalarFields = [
      "full_name", "email", "phone", "location",
      "linkedin", "github", "headline",
    ];
    scalarFields.forEach(function (f) {
      var el = _$("pe-" + f);
      if (el) el.value = profile[f] || "";
    });

    var summaryEl = _$("pe-summary");
    if (summaryEl) summaryEl.value = profile.summary || "";

    var jsonFields = [
      "skills", "experiences", "education",
      "spoken_languages", "scoring_keywords",
    ];
    jsonFields.forEach(function (f) {
      var el = _$("pe-" + f);
      if (!el) return;
      var val = profile[f];
      if (val !== undefined && val !== null) {
        el.value = typeof val === "string"
          ? val
          : JSON.stringify(val, null, 2);
      } else {
        el.value = (f === "skills") ? "{}" : "[]";
      }
    });
  }

  function _setCreateMode(profile) {
    _mode = "create";
    var label = _$("profile-editor-mode-label");
    if (label) label.textContent = "New Profile";
    var btn = _$("profile-editor-save-btn");
    if (btn) btn.textContent = "Create Profile";
    _populateForm(profile || {});
  }

  function _setUpdateMode(profile) {
    _mode = "update";
    var label = _$("profile-editor-mode-label");
    if (label) label.textContent = "Edit Profile";
    var btn = _$("profile-editor-save-btn");
    if (btn) btn.textContent = "Save Changes";
    _populateForm(profile);
  }

  function _save() {
    var data = _getFormData();
    if (!data.full_name) {
      _setStatus("Full name is required.", "error");
      return;
    }

    var method = (_mode === "create") ? "POST" : "PUT";
    var btn = _$("profile-editor-save-btn");
    if (btn) btn.disabled = true;
    _setStatus("Saving\u2026", "saving");

    CAuth.authFetch("/api/profile", {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { status: res.status, body: body };
        });
      })
      .then(function (result) {
        if (btn) btn.disabled = false;
        if (result.status === 200 || result.status === 201) {
          _setUpdateMode(result.body);
          _setStatus("Saved.", "success");
          setTimeout(function () { _setStatus(""); }, 3000);
          if (result.status === 201) {
            window.dispatchEvent(new CustomEvent("customy:profile-created"));
          }
        } else {
          var msg = (result.body && result.body.error) || "Save failed.";
          _setStatus(msg, "error");
        }
      })
      .catch(function (err) {
        if (btn) btn.disabled = false;
        _setStatus("Network error: " + (err.message || String(err)), "error");
      });
  }

  function _loadProfile() {
    _setStatus("Loading\u2026", "saving");
    CAuth.authFetch("/api/profile")
      .then(function (res) {
        return res.json().then(function (body) {
          return { status: res.status, body: body };
        });
      })
      .then(function (result) {
        _setStatus("");
        if (result.status === 200) {
          var payload = _normalizeProfileResponse(result.body);
          if (payload.exists === false) {
            _setCreateMode(payload.profile || {});
          } else {
            _setUpdateMode(payload.profile || {});
          }
        } else {
          var msg = (result.body && result.body.error) || "Failed to load profile.";
          _setStatus(msg, "error");
        }
      })
      .catch(function (err) {
        _setStatus("Network error: " + (err.message || String(err)), "error");
      });
  }

  function init() {
    var section = _$("section-profile-editor");
    if (!section) return;

    var cfg = window.CUSTOMY_CONFIG || { mode: "local" };
    var localNotice = _$("profile-editor-local-notice");
    var formWrap    = _$("profile-editor-form-wrap");

    if (cfg.mode !== "saas") {
      if (localNotice) localNotice.removeAttribute("hidden");
      if (formWrap)    formWrap.setAttribute("hidden", "");
      return;
    }

    // SaaS mode — wire save button and fetch profile
    if (localNotice) localNotice.setAttribute("hidden", "");
    if (formWrap)    formWrap.removeAttribute("hidden");

    // Wire save button only once (auth-state can fire on every token refresh)
    if (!_initialized) {
      _initialized = true;
      var btn = _$("profile-editor-save-btn");
      if (btn) btn.addEventListener("click", _save);
    }

    _loadProfile();
  }

  window.CProfileEditor = { init: init, populate: _populateForm };
})();
