(function () {
  "use strict";

  var jdInput = document.getElementById("studio-jd-input");
  var applicationUrlInput = document.getElementById(
    "studio-application-url-input"
  );
  var generateBtn = document.getElementById("studio-generate-btn");
  var statusBanner = document.getElementById("studio-status-banner");
  var downloadLinks = document.getElementById("studio-download-links");
  var tabButtons = document.getElementById("studio-tab-buttons");
  var tabPanes = document.getElementById("studio-tab-panes");
  var emptyState = document.getElementById("studio-empty-state");
  var blockedPanel = document.getElementById("studio-blocked-panel");
  var fullnessRiskEl = document.getElementById("studio-fullness-risk");
  var profileHintsCard = document.getElementById("studio-profile-hints-card");
  var profileHintsEl = document.getElementById("studio-profile-hints");
  var adminMetricCards = document.querySelectorAll(".studio-metric-card--admin");
  var isSaas = !!(window.CUSTOMY_CONFIG && window.CUSTOMY_CONFIG.mode === "saas");

  if (!jdInput || !generateBtn || !statusBanner || !downloadLinks || !tabButtons || !tabPanes) {
    return;
  }

  function _esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setStatus(message, mode) {
    statusBanner.textContent = message;
    statusBanner.className = "studio-status-banner" + (mode ? " " + mode : "");
  }

  function selectedOutputs() {
    var outputs = [];
    if (document.getElementById("studio-cover-letter-toggle").checked) {
      outputs.push("cover_letter");
    }
    if (document.getElementById("studio-linkedin-toggle").checked) {
      outputs.push("linkedin_msg");
    }
    if (document.getElementById("studio-email-toggle").checked) {
      outputs.push("email_draft");
    }
    return outputs;
  }

  var formatNumber = CUtils.formatNumber;
  var formatUsd = CUtils.formatUsd;
  var formatScore = CUtils.formatScore;

  function isAdminView() {
    return !isSaas || !!window.CUSTOMY_IS_ADMIN;
  }

  function syncAdminMetricVisibility() {
    var adminView = isAdminView();
    adminMetricCards.forEach(function (card) {
      card.hidden = !adminView;
    });
  }

  function resetAdminMetrics() {
    document.getElementById("studio-analysis-model").textContent = "-";
    document.getElementById("studio-analysis-prompt-tokens").textContent = "-";
    document.getElementById("studio-analysis-output-tokens").textContent = "-";
    document.getElementById("studio-analysis-cached-tokens").textContent = "-";
    document.getElementById("studio-analysis-cost").textContent = "-";
  }

  function resumePreview(pack) {
    var isFrench = (pack.resume_language || "").toLowerCase() === "fr";
    var lines = [];
    lines.push(isFrench ? "RESUME" : "SUMMARY");
    lines.push(pack.tailored_summary || "");
    lines.push("");
    lines.push(isFrench ? "COMPETENCES" : "SKILLS");
    ["languages", "frameworks", "tools"].forEach(function (key) {
      var values = (pack.tailored_skills && pack.tailored_skills[key]) || [];
      lines.push(key.toUpperCase() + ": " + values.join(", "));
    });
    lines.push("");
    lines.push(isFrench ? "EXPERIENCE" : "EXPERIENCE");
    (pack.tailored_experiences || []).forEach(function (item) {
      lines.push(
        item.role + " | " + item.company + " | " + item.start + " - " + item.end
      );
      (item.bullets || []).forEach(function (bullet) {
        lines.push("- " + bullet);
      });
      lines.push("");
    });
    return lines.join("\n").trim();
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () {
        return null;
      });
    }
  }

  function activateTab(id) {
    document.querySelectorAll(".studio-tab-button").forEach(function (button) {
      button.classList.toggle("active", button.dataset.target === id);
    });
    document.querySelectorAll(".studio-output-pane").forEach(function (pane) {
      pane.classList.toggle("active", pane.id === id + "-pane");
    });
  }

  function clearPreview() {
    downloadLinks.innerHTML = "";
    tabButtons.innerHTML = "";
    tabPanes.innerHTML = "";
    clearProfileHints();
    if (emptyState) {
      tabPanes.appendChild(emptyState);
    }
  }

  function clearProfileHints() {
    if (!profileHintsCard || !profileHintsEl) return;
    profileHintsEl.innerHTML = "";
    profileHintsCard.hidden = true;
  }

  function renderProfileHints(pack) {
    if (!profileHintsCard || !profileHintsEl) return;
    var hints = (pack && pack.profile_update_hints) || [];
    profileHintsEl.innerHTML = "";
    if (!hints.length) {
      profileHintsCard.hidden = true;
      return;
    }

    var list = document.createElement("ul");
    list.className = "studio-profile-hints-list";
    hints.forEach(function (hint) {
      var item = document.createElement("li");
      item.textContent = hint;
      list.appendChild(item);
    });

    profileHintsEl.appendChild(list);
    profileHintsCard.hidden = false;
  }

  function renderTabs(data) {
    var tabs = [
      { id: "resume", label: "Resume", content: resumePreview(data.pack) },
    ];

    if (data.pack.cover_letter) {
      tabs.push({
        id: "cover_letter",
        label: "Cover Letter",
        content: data.pack.cover_letter,
      });
    }
    if (data.pack.linkedin_message) {
      tabs.push({
        id: "linkedin_message",
        label: "LinkedIn",
        content: data.pack.linkedin_message,
      });
    }
    if (data.pack.email_draft) {
      tabs.push({
        id: "email_draft",
        label: "Email",
        content: data.pack.email_draft,
      });
    }

    tabButtons.innerHTML = "";
    tabPanes.innerHTML = "";

    tabs.forEach(function (tab, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.className =
        "studio-tab-button" + (index === 0 ? " active" : "");
      button.textContent = tab.label;
      button.dataset.target = tab.id;
      button.addEventListener("click", function () {
        activateTab(tab.id);
      });
      tabButtons.appendChild(button);

      var pane = document.createElement("div");
      pane.className = "studio-output-pane" + (index === 0 ? " active" : "");
      pane.id = tab.id + "-pane";

      var toolbar = document.createElement("div");
      toolbar.className = "studio-pane-toolbar";

      var copyButton = document.createElement("button");
      copyButton.type = "button";
      copyButton.className = "studio-copy-btn";
      copyButton.textContent = "Copy";
      copyButton.addEventListener("click", function () {
        copyText(tab.content);
      });
      toolbar.appendChild(copyButton);

      var preview = document.createElement("pre");
      preview.className = "studio-output-preview";
      preview.textContent = tab.content || "No content returned.";

      pane.appendChild(toolbar);
      pane.appendChild(preview);
      tabPanes.appendChild(pane);
    });
  }

  function renderDownloads(files) {
    var DOWNLOAD_LABELS = {
      resume_pdf: "Resume PDF",
      cover_letter: "Cover Letter",
      linkedin_message: "LinkedIn Message",
      email_draft: "Email Draft",
    };

    downloadLinks.innerHTML = "";
    Object.entries(files || {}).forEach(function (entry) {
      var key = entry[0];
      var file = entry[1];
      if (!file || !file.url) return;

      var filename = (file.filename || file.path || file.url || "")
        .split("?")[0]
        .split(/[\\/]/)
        .pop();
      var link = document.createElement("a");
      link.className = "studio-download-link";
      link.href = file.url;
      if (key === "cover_letter") {
        link.download = filename || "Cover_letter.txt";
      } else {
        link.target = "_blank";
        link.rel = "noreferrer";
      }
      link.textContent = DOWNLOAD_LABELS[key] || key.replaceAll("_", " ");
      link.title = filename || key;
      downloadLinks.appendChild(link);
    });
  }

  var ARCHETYPE_LABELS = {
    ai_platform: "AI Platform / LLMOps",
    agentic: "Agentic / Automation",
    ai_pm: "Technical AI PM",
    ai_architect: "AI Solutions Architect",
    ai_forward_deployed: "AI Forward Deployed",
    ai_transformation: "AI Transformation",
    general: "General",
  };

  function renderAnalysis(data) {
    var usage = data.usage || {};
    var analysis = data.analysis || {};
    document.getElementById("studio-analysis-company").textContent =
      data.company || "-";
    document.getElementById("studio-analysis-role").textContent =
      data.role || "-";
    document.getElementById("studio-analysis-language").textContent =
      analysis.language || "-";
    var archetypeKey = data.archetype || analysis.archetype || "general";
    document.getElementById("studio-analysis-archetype").textContent =
      ARCHETYPE_LABELS[archetypeKey] || archetypeKey;
    document.getElementById("studio-analysis-ats-vendor").textContent =
      (data.ats_vendor || analysis.ats_vendor || "-");
    document.getElementById("studio-analysis-initial-score").textContent =
      formatScore(data.initial_score);
    document.getElementById("studio-analysis-updated-score").textContent =
      formatScore(data.updated_score);
    if (!isAdminView()) {
      resetAdminMetrics();
      return;
    }
    document.getElementById("studio-analysis-model").textContent = usage.model_used || "-";
    document.getElementById("studio-analysis-prompt-tokens").textContent = formatNumber(usage.prompt_tokens);
    document.getElementById("studio-analysis-output-tokens").textContent = formatNumber(usage.completion_tokens);
    document.getElementById("studio-analysis-cached-tokens").textContent = formatNumber(usage.cached_prompt_tokens);
    document.getElementById("studio-analysis-cost").textContent = formatUsd(usage.total_cost_usd);
  }

  function dispatchGenerationEvent(data) {
    window.dispatchEvent(
      new CustomEvent("customy:application-generated", { detail: data })
    );
  }

  /* ── Phase 2: profile readiness blocked state ───────────── */

  function renderBlockedState(data) {
    if (!blockedPanel) return;
    var qr = data.profile_quality_report || {};
    var ep = data.profile_enrichment_plan || {};
    var blockers = (qr.blockers || []).slice(0, 3);
    var recs = (ep.targets || [])
      .filter(function (r) { return r.priority === "high"; })
      .slice(0, 3);
    if (!recs.length) recs = (ep.targets || []).slice(0, 3);

    var html =
      '<div class="studio-blocked-header">' +
      '<span class="intel-status-badge intel-status-blocked">Blocked</span>' +
      '<span class="studio-blocked-title">Profile needs attention before generation</span>' +
      "</div>";

    if (blockers.length) {
      html +=
        '<p class="studio-blocked-section-label">What to fix</p>' +
        '<ul class="studio-blocked-list">';
      blockers.forEach(function (b) {
        html +=
          "<li>" +
          (b.field ? "<strong>" + _esc(b.field) + "</strong> \u2014 " : "") +
          _esc(b.message || b.fix || "") +
          "</li>";
      });
      html += "</ul>";
    }

    if (recs.length) {
      html +=
        '<p class="studio-blocked-section-label">Suggested improvements</p>' +
        '<ul class="studio-blocked-list">';
      recs.forEach(function (r) {
        html += "<li>" + _esc(r.title || r.instruction || "") + "</li>";
      });
      html += "</ul>";
    }

    html +=
      '<div class="studio-blocked-cta">' +
      '<button type="button" class="btn-primary studio-blocked-go-profile">' +
      "Go to My Profile" +
      "</button>" +
      "</div>";

    blockedPanel.innerHTML = html;
    blockedPanel.hidden = false;

    var goBtn = blockedPanel.querySelector(".studio-blocked-go-profile");
    if (goBtn) {
      goBtn.addEventListener("click", function () {
        if (window.CustomyDashboard && CustomyDashboard.navigateTo) {
          CustomyDashboard.navigateTo("section-profile-editor");
        }
      });
    }

    // Collapse the output area while blocked
    if (tabPanes) tabPanes.hidden = true;
    if (tabButtons) tabButtons.hidden = true;
    if (downloadLinks) downloadLinks.hidden = true;
    if (profileHintsCard) profileHintsCard.hidden = true;
  }

  function clearBlockedState() {
    if (blockedPanel) {
      blockedPanel.hidden = true;
      blockedPanel.innerHTML = "";
    }
    if (tabPanes) tabPanes.removeAttribute("hidden");
    if (tabButtons) tabButtons.removeAttribute("hidden");
    if (downloadLinks) downloadLinks.removeAttribute("hidden");
    if (profileHintsEl && profileHintsEl.innerHTML.trim()) {
      profileHintsCard.hidden = false;
    }
  }

  /* ── Phase 2: resume fullness risk card ─────────────────── */

  function renderFullnessRisk(risk) {
    if (!fullnessRiskEl) return;
    if (!risk) { fullnessRiskEl.hidden = true; return; }

    var status = risk.overall_status || "clear";
    var statusClass =
      status === "clear" ? "intel-status-ready" :
      status === "review" ? "intel-status-review" : "intel-status-blocked";
    var statusLabel =
      status === "clear" ? "Clear" :
      status === "review" ? "Review" : "Elevated Risk";

    var issues = (risk.blockers || []).slice(0, 2)
      .concat((risk.warnings || []).slice(0, 3))
      .slice(0, 3);

    var html =
      '<div class="studio-risk-header">' +
      '<span class="studio-risk-title">' +
      "<strong>Resume Fullness</strong>" +
      '<span class="intel-status-badge ' + statusClass + '">' + statusLabel + "</span>" +
      "</span>" +
      '<span class="studio-risk-scores">' +
      "Fill&nbsp;<strong>" + Math.round(risk.visual_fill_score || 0) + "</strong>%" +
      "&nbsp;&middot;&nbsp;Substance&nbsp;<strong>" +
      Math.round(risk.substance_score || 0) + "</strong>%" +
      "</span>" +
      "</div>";

    if (issues.length) {
      html += '<ul class="studio-risk-issues">';
      issues.forEach(function (issue) {
        html += "<li>" + _esc(issue.message || "") + "</li>";
      });
      html += "</ul>";
    }

    fullnessRiskEl.innerHTML = html;
    fullnessRiskEl.hidden = false;
  }

  function generate() {
    var jdText = jdInput.value.trim();
    if (!jdText) {
      setStatus("Paste a job description first.", "error");
      return;
    }

    generateBtn.disabled = true;
    setStatus("Generating tailored materials...", "loading");
    clearBlockedState();

    CAuth.authFetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jd: jdText,
        application_url: applicationUrlInput.value.trim(),
        outputs: selectedOutputs(),
      }),
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { status: res.status, body: body };
        });
      })
      .then(function (result) {
        var httpStatus = result.status;
        var data = result.body;

        // Profile readiness gate — blocked (422)
        if (httpStatus === 422 && data.profile_readiness_gate) {
          renderBlockedState(data);
          setStatus("Profile needs attention before generation.", "error");
          return;
        }

        // Score gate — below configured minimum
        if (data.score_gate) {
          setStatus(
            "Score " + formatScore(data.score) + " below minimum (" +
            formatScore(data.min_score) + "). Generation skipped.",
            "error"
          );
          return;
        }

        if (data.error) {
          throw new Error(data.error);
        }

        renderAnalysis(data);
        renderDownloads(data.files);
        renderTabs(data);
        renderProfileHints(data.pack);
        renderFullnessRisk(data.resume_fullness_risk);
        dispatchGenerationEvent(data);
        var savedLabel = [data.company, data.role].filter(Boolean).join(" - ");
        setStatus("Saved for " + (savedLabel || "this application"), "success");
      })
      .catch(function (error) {
        setStatus(error.message || "Request failed.", "error");
      })
      .finally(function () {
        generateBtn.disabled = false;
      });
  }

  clearPreview();
  syncAdminMetricVisibility();
  resetAdminMetrics();
  window.addEventListener("customy:user-role-changed", function () {
    syncAdminMetricVisibility();
    if (!isAdminView()) {
      resetAdminMetrics();
    }
  });
  generateBtn.addEventListener("click", generate);
})();
