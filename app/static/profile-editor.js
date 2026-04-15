/**
 * CProfileEditor — profile create/edit form for SaaS mode.
 *
 * The backend contract remains JSON-based. The visible UI uses structured
 * editors and keeps hidden JSON fields in sync before save.
 */
(function () {
  "use strict";

  var _mode = null;
  var _initialized = false;
  var _state = {
    skills: { languages: [], frameworks: [], tools: [], soft: [] },
    experiences: [],
    education: [],
    spoken_languages: [],
  };

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

  function _esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function _cleanText(value) {
    return String(value || "").trim();
  }

  function _stringList(items) {
    if (!Array.isArray(items)) return [];
    var seen = {};
    var out = [];
    items.forEach(function (item) {
      var value = _cleanText(item);
      var key = value.toLowerCase();
      if (!value || seen[key]) return;
      seen[key] = true;
      out.push(value);
    });
    return out;
  }

  function _parseJsonField(field, fallback) {
    var el = _$("pe-" + field);
    if (!el) return fallback;
    var raw = el.value.trim();
    if (!raw) return fallback;
    try {
      return JSON.parse(raw);
    } catch (_err) {
      return fallback;
    }
  }

  function _syncJsonField(field, value) {
    var el = _$("pe-" + field);
    if (!el) return;
    el.value = JSON.stringify(value, null, 2);
  }

  function _normalizeSkills(raw) {
    var skills = raw && typeof raw === "object" ? raw : {};
    return {
      languages: _stringList(skills.languages),
      frameworks: _stringList(skills.frameworks),
      tools: _stringList(skills.tools),
      soft: _stringList(skills.soft),
    };
  }

  function _normalizeExperience(item) {
    var source = item && typeof item === "object" ? item : {};
    return {
      role: _cleanText(source.role || source.title || source.position),
      company: _cleanText(source.company || source.organization),
      start: _cleanText(source.start),
      end: _cleanText(source.end),
      bullets: _stringList(source.bullets),
    };
  }

  function _normalizeEducation(item) {
    var source = item && typeof item === "object" ? item : {};
    return {
      degree: _cleanText(source.degree),
      school: _cleanText(source.school || source.institution),
      year: _cleanText(source.year || source.end_year || source.start_year),
    };
  }

  function _serializeEducation(item) {
    var entry = {};
    if (item.degree) entry.degree = item.degree;
    if (item.school) entry.institution = item.school;
    if (item.year) entry.year = item.year;
    return entry;
  }

  function _serializeExperience(item) {
    var entry = {};
    if (item.role) entry.role = item.role;
    if (item.company) entry.company = item.company;
    if (item.start) entry.start = item.start;
    if (item.end) entry.end = item.end;
    entry.bullets = _stringList(item.bullets);
    return entry;
  }

  function _setStructuredStateFromHiddenFields() {
    _state.skills = _normalizeSkills(_parseJsonField("skills", {}));
    _state.experiences = _parseJsonField("experiences", []).map(_normalizeExperience);
    _state.education = _parseJsonField("education", []).map(_normalizeEducation);
    _state.spoken_languages = _stringList(_parseJsonField("spoken_languages", []));
  }

  function _syncHiddenFieldsFromState() {
    _syncJsonField("skills", {
      languages: _stringList(_state.skills.languages),
      frameworks: _stringList(_state.skills.frameworks),
      tools: _stringList(_state.skills.tools),
      soft: _stringList(_state.skills.soft),
    });
    _syncJsonField("experiences", _state.experiences.map(_serializeExperience));
    _syncJsonField("education", _state.education.map(_serializeEducation));
    _syncJsonField("spoken_languages", _stringList(_state.spoken_languages));
  }

  function _renderChipList(listId, items, removeAction) {
    var el = _$(listId);
    if (!el) return;
    if (!items.length) {
      el.innerHTML = '<div class="pe-empty-state">No entries yet.</div>';
      return;
    }
    el.innerHTML = items.map(function (item, index) {
      return (
        '<span class="pe-chip">' +
        '<span>' + _esc(item) + "</span>" +
        '<button type="button" class="pe-chip-remove" data-pe-action="' + removeAction + '" data-index="' + index + '" aria-label="Remove">' +
        "&times;</button></span>"
      );
    }).join("");
  }

  function _renderSkills() {
    _renderChipList("pe-skill-list-languages", _state.skills.languages, "remove-skill-languages");
    _renderChipList("pe-skill-list-frameworks", _state.skills.frameworks, "remove-skill-frameworks");
    _renderChipList("pe-skill-list-tools", _state.skills.tools, "remove-skill-tools");
    _renderChipList("pe-skill-list-soft", _state.skills.soft, "remove-skill-soft");
  }

  function _renderSpokenLanguages() {
    _renderChipList("pe-spoken-language-list", _state.spoken_languages, "remove-spoken-language");
  }

  function _renderExperiences() {
    var el = _$("pe-experiences-list");
    if (!el) return;
    if (!_state.experiences.length) {
      el.innerHTML = '<div class="pe-empty-state">Add roles, companies, dates, and resume bullets.</div>';
      return;
    }

    el.innerHTML = _state.experiences.map(function (item, index) {
      var bulletsHtml = item.bullets.length
        ? item.bullets.map(function (bullet, bulletIndex) {
          return (
            '<div class="pe-bullet-row">' +
            '<input type="text" class="pe-input" data-pe-action="experience-bullet" data-index="' + index + '" data-bullet-index="' + bulletIndex + '" value="' + _esc(bullet) + '" placeholder="Resume bullet" />' +
            '<button type="button" class="pe-bullet-remove" data-pe-action="remove-experience-bullet" data-index="' + index + '" data-bullet-index="' + bulletIndex + '" aria-label="Remove bullet">&times;</button>' +
            "</div>"
          );
        }).join("")
        : '<div class="pe-empty-state">No bullets yet.</div>';

      return (
        '<div class="pe-entry-card">' +
        '<div class="pe-entry-card-header">' +
        '<div class="pe-entry-card-title">Experience ' + (index + 1) + "</div>" +
        '<button type="button" class="pe-card-remove" data-pe-action="remove-experience" data-index="' + index + '">Remove</button>' +
        "</div>" +
        '<div class="pe-entry-card-fields pe-entry-card-fields--triple">' +
        '<div class="pe-field"><label class="pe-label">Role</label><input type="text" class="pe-input" data-pe-action="experience-field" data-index="' + index + '" data-field="role" value="' + _esc(item.role) + '" placeholder="e.g. Senior AI Engineer" /></div>' +
        '<div class="pe-field"><label class="pe-label">Company</label><input type="text" class="pe-input" data-pe-action="experience-field" data-index="' + index + '" data-field="company" value="' + _esc(item.company) + '" placeholder="e.g. Acme" /></div>' +
        '<div class="pe-field"><label class="pe-label">Start</label><input type="text" class="pe-input" data-pe-action="experience-field" data-index="' + index + '" data-field="start" value="' + _esc(item.start) + '" placeholder="e.g. 2022-01" /></div>' +
        '<div class="pe-field"><label class="pe-label">End</label><input type="text" class="pe-input" data-pe-action="experience-field" data-index="' + index + '" data-field="end" value="' + _esc(item.end) + '" placeholder="e.g. Present" /></div>' +
        "</div>" +
        '<div class="pe-field">' +
        '<label class="pe-label">Bullets</label>' +
        '<div class="pe-bullet-list">' + bulletsHtml + "</div>" +
        '<div class="pe-bullet-add-row">' +
        '<input type="text" class="pe-input pe-bullet-input" data-pe-action="new-experience-bullet" data-index="' + index + '" placeholder="Add a bullet and press Enter" />' +
        '<button type="button" class="btn-secondary" data-pe-action="add-experience-bullet" data-index="' + index + '">Add Bullet</button>' +
        "</div></div></div>"
      );
    }).join("");
  }

  function _renderEducation() {
    var el = _$("pe-education-list");
    if (!el) return;
    if (!_state.education.length) {
      el.innerHTML = '<div class="pe-empty-state">Add degree, school, and year details.</div>';
      return;
    }

    el.innerHTML = _state.education.map(function (item, index) {
      return (
        '<div class="pe-entry-card">' +
        '<div class="pe-entry-card-header">' +
        '<div class="pe-entry-card-title">Education ' + (index + 1) + "</div>" +
        '<button type="button" class="pe-card-remove" data-pe-action="remove-education" data-index="' + index + '">Remove</button>' +
        "</div>" +
        '<div class="pe-entry-card-fields pe-entry-card-fields--triple">' +
        '<div class="pe-field"><label class="pe-label">Degree</label><input type="text" class="pe-input" data-pe-action="education-field" data-index="' + index + '" data-field="degree" value="' + _esc(item.degree) + '" placeholder="e.g. MSc Computer Science" /></div>' +
        '<div class="pe-field"><label class="pe-label">School</label><input type="text" class="pe-input" data-pe-action="education-field" data-index="' + index + '" data-field="school" value="' + _esc(item.school) + '" placeholder="e.g. University Name" /></div>' +
        '<div class="pe-field"><label class="pe-label">Year</label><input type="text" class="pe-input" data-pe-action="education-field" data-index="' + index + '" data-field="year" value="' + _esc(item.year) + '" placeholder="e.g. 2020" /></div>' +
        "</div></div>"
      );
    }).join("");
  }

  function _renderStructuredEditors() {
    _syncHiddenFieldsFromState();
    _renderSkills();
    _renderExperiences();
    _renderEducation();
    _renderSpokenLanguages();
  }

  function _addTag(field, inputId) {
    var input = _$(inputId);
    var value = input ? _cleanText(input.value) : "";
    if (!value) return;
    if (field === "spoken_languages") {
      _state.spoken_languages = _stringList(_state.spoken_languages.concat([value]));
    } else {
      _state.skills[field] = _stringList((_state.skills[field] || []).concat([value]));
    }
    if (input) input.value = "";
    _renderStructuredEditors();
  }

  function _addExperience() {
    _state.experiences.push({ role: "", company: "", start: "", end: "", bullets: [] });
    _renderStructuredEditors();
  }

  function _addEducation() {
    _state.education.push({ degree: "", school: "", year: "" });
    _renderStructuredEditors();
  }

  function _addExperienceBullet(index) {
    var input = document.querySelector('[data-pe-action="new-experience-bullet"][data-index="' + index + '"]');
    var value = input ? _cleanText(input.value) : "";
    if (!value || !_state.experiences[index]) return;
    _state.experiences[index].bullets = _stringList(_state.experiences[index].bullets.concat([value]));
    if (input) input.value = "";
    _renderStructuredEditors();
  }

  function _handleClick(event) {
    var target = event.target;
    if (!target) return;

    var action = target.getAttribute("data-pe-action");
    var addTagField = target.getAttribute("data-pe-add-tag");
    var index = Number(target.getAttribute("data-index"));
    var bulletIndex = Number(target.getAttribute("data-bullet-index"));

    if (addTagField) {
      event.preventDefault();
      if (addTagField === "spoken_languages") {
        _addTag("spoken_languages", "pe-spoken-language-input");
      } else {
        _addTag(addTagField, "pe-skill-input-" + addTagField);
      }
      return;
    }

    if (target.id === "pe-add-experience-btn") {
      event.preventDefault();
      _addExperience();
      return;
    }
    if (target.id === "pe-add-education-btn") {
      event.preventDefault();
      _addEducation();
      return;
    }

    if (!action) return;
    event.preventDefault();

    if (action.indexOf("remove-skill-") === 0) {
      var skillField = action.replace("remove-skill-", "");
      _state.skills[skillField].splice(index, 1);
      _renderStructuredEditors();
      return;
    }
    if (action === "remove-spoken-language") {
      _state.spoken_languages.splice(index, 1);
      _renderStructuredEditors();
      return;
    }
    if (action === "remove-experience") {
      _state.experiences.splice(index, 1);
      _renderStructuredEditors();
      return;
    }
    if (action === "remove-education") {
      _state.education.splice(index, 1);
      _renderStructuredEditors();
      return;
    }
    if (action === "add-experience-bullet") {
      _addExperienceBullet(index);
      return;
    }
    if (action === "remove-experience-bullet" && _state.experiences[index]) {
      _state.experiences[index].bullets.splice(bulletIndex, 1);
      _renderStructuredEditors();
    }
  }

  function _handleInput(event) {
    var target = event.target;
    if (!target) return;
    var action = target.getAttribute("data-pe-action");
    var index = Number(target.getAttribute("data-index"));
    var field = target.getAttribute("data-field");

    if (action === "experience-field" && _state.experiences[index]) {
      _state.experiences[index][field] = target.value;
      _syncHiddenFieldsFromState();
      return;
    }
    if (action === "education-field" && _state.education[index]) {
      _state.education[index][field] = target.value;
      _syncHiddenFieldsFromState();
      return;
    }
    if (action === "experience-bullet" && _state.experiences[index]) {
      var bulletIndex = Number(target.getAttribute("data-bullet-index"));
      _state.experiences[index].bullets[bulletIndex] = target.value;
      _syncHiddenFieldsFromState();
    }
  }

  function _handleKeydown(event) {
    var target = event.target;
    if (!target || event.key !== "Enter") return;

    if (target.id === "pe-skill-input-languages") {
      event.preventDefault();
      _addTag("languages", target.id);
      return;
    }
    if (target.id === "pe-skill-input-frameworks") {
      event.preventDefault();
      _addTag("frameworks", target.id);
      return;
    }
    if (target.id === "pe-skill-input-tools") {
      event.preventDefault();
      _addTag("tools", target.id);
      return;
    }
    if (target.id === "pe-skill-input-soft") {
      event.preventDefault();
      _addTag("soft", target.id);
      return;
    }
    if (target.id === "pe-spoken-language-input") {
      event.preventDefault();
      _addTag("spoken_languages", target.id);
      return;
    }
    if (target.getAttribute("data-pe-action") === "new-experience-bullet") {
      event.preventDefault();
      _addExperienceBullet(Number(target.getAttribute("data-index")));
    }
  }

  function _getFormData() {
    _syncHiddenFieldsFromState();

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
        el.value = typeof val === "string" ? val : JSON.stringify(val, null, 2);
      } else {
        el.value = (f === "skills") ? "{}" : "[]";
      }
    });

    _setStructuredStateFromHiddenFields();
    _renderStructuredEditors();
  }

  function _renderReadinessBanner(qualityReport, enrichmentPlan, sourceCoverage) {
    var slot = _$("pe-readiness-slot");
    if (!slot) return;
    if (!qualityReport) { slot.hidden = true; return; }

    var status = qualityReport.overall_status || "review";
    var statusClass =
      status === "ready" ? "intel-status-ready" :
      status === "review" ? "intel-status-review" : "intel-status-blocked";
    var statusLabel =
      status === "ready" ? "Ready" :
      status === "review" ? "Review" : "Blocked";

    var blockers = (qualityReport.blockers || []).slice(0, 3);
    var warnings = (qualityReport.warnings || []).slice(0, 2);
    var issues = blockers.length ? blockers : warnings;

    var recs = ((enrichmentPlan && enrichmentPlan.targets) || [])
      .filter(function (r) { return r.priority === "high"; })
      .slice(0, 3);
    if (!recs.length) {
      recs = ((enrichmentPlan && enrichmentPlan.targets) || []).slice(0, 3);
    }

    var html =
      '<div class="pe-readiness-header">' +
      '<span class="intel-status-badge ' + statusClass + '">' + statusLabel + "</span>" +
      '<span class="pe-readiness-label">Profile Readiness</span>' +
      "</div>";

    if (issues.length) {
      html += '<ul class="pe-readiness-blockers">';
      issues.forEach(function (item) {
        html +=
          "<li>" +
          (item.field ? "<strong>" + _esc(item.field) + "</strong> - " : "") +
          _esc(item.message || item.fix || "") +
          "</li>";
      });
      html += "</ul>";
    }

    if (recs.length) {
      html +=
        '<div class="pe-readiness-enrichment">' +
        '<div class="pe-readiness-enrichment-label">Suggested improvements</div>' +
        '<ul class="pe-readiness-enrichment-list">';
      recs.forEach(function (r) {
        html += "<li>" + _esc(r.title || r.instruction || "") + "</li>";
      });
      html += "</ul></div>";
    }

    if (sourceCoverage && sourceCoverage.lost_signals_count > 0) {
      html +=
        '<p class="pe-readiness-source-note">' +
        sourceCoverage.lost_signals_count +
        " detail" + (sourceCoverage.lost_signals_count !== 1 ? "s" : "") +
        " from your source resume not yet captured in your profile." +
        "</p>";
    }

    slot.innerHTML = html;
    slot.hidden = false;
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
    _setStatus("Saving...", "saving");

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
          _renderReadinessBanner(
            result.body.profile_quality_report,
            result.body.profile_enrichment_plan,
            result.body.source_coverage_report
          );
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
    _setStatus("Loading...", "saving");
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
          _renderReadinessBanner(
            payload.profile_quality_report,
            payload.profile_enrichment_plan,
            payload.source_coverage_report
          );
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
    var formWrap = _$("profile-editor-form-wrap");

    if (cfg.mode !== "saas") {
      if (localNotice) localNotice.removeAttribute("hidden");
      if (formWrap) formWrap.setAttribute("hidden", "");
      return;
    }

    if (localNotice) localNotice.setAttribute("hidden", "");
    if (formWrap) formWrap.removeAttribute("hidden");

    if (!_initialized) {
      _initialized = true;
      var btn = _$("profile-editor-save-btn");
      if (btn) btn.addEventListener("click", _save);
      document.addEventListener("click", _handleClick);
      document.addEventListener("input", _handleInput);
      document.addEventListener("keydown", _handleKeydown);
    }

    _loadProfile();
  }

  window.CProfileEditor = { init: init, populate: _populateForm };
})();
