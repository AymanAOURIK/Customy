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

  if (!jdInput || !generateBtn || !statusBanner || !downloadLinks || !tabButtons || !tabPanes) {
    return;
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

  function formatNumber(value) {
    var numeric = Number(value || 0);
    return Number.isFinite(numeric) ? numeric.toLocaleString() : "-";
  }

  function formatUsd(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) return "-";
    return "$" + numeric.toFixed(numeric < 0.01 ? 6 : 4);
  }

  function formatScore(value) {
    if (value === null || value === undefined || value === "") return "-";
    var numeric = Number(value);
    return Number.isFinite(numeric) ? numeric.toFixed(1) : "-";
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
    if ((pack.focus_areas || []).length) {
      lines.push(isFrench ? "AXES DE CIBLAGE" : "FOCUS AREAS");
      pack.focus_areas.forEach(function (item) {
        lines.push("- " + item);
      });
    }
    if ((pack.profile_update_hints || []).length) {
      lines.push("");
      lines.push(isFrench ? "NOTES DE PROFIL" : "PROFILE REVIEW NOTES");
      pack.profile_update_hints.forEach(function (item) {
        lines.push("- " + item);
      });
    }
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
    if (emptyState) {
      tabPanes.appendChild(emptyState);
    }
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
    downloadLinks.innerHTML = "";
    Object.entries(files || {}).forEach(function (entry) {
      var key = entry[0];
      var file = entry[1];
      if (!file || !file.url) return;

      var filename = (file.path || file.url || "").split(/[\\/]/).pop();
      var link = document.createElement("a");
      link.className = "studio-download-link";
      link.href = file.url;
      if (key === "cover_letter") {
        link.download = filename || "Ayman_Aourik_Cover_letter.txt";
      } else {
        link.target = "_blank";
        link.rel = "noreferrer";
      }
      link.textContent =
        key === "cover_letter" ? filename || "cover_letter.txt" : key.replaceAll("_", " ");
      link.title = filename || key;
      downloadLinks.appendChild(link);
    });
  }

  function renderAnalysis(data) {
    var usage = data.usage || {};
    document.getElementById("studio-analysis-company").textContent =
      data.company || "-";
    document.getElementById("studio-analysis-role").textContent =
      data.role || "-";
    document.getElementById("studio-analysis-language").textContent =
      (data.analysis && data.analysis.language) || "-";
    document.getElementById("studio-analysis-initial-score").textContent =
      formatScore(data.initial_score);
    document.getElementById("studio-analysis-updated-score").textContent =
      formatScore(data.updated_score);
    document.getElementById("studio-analysis-model").textContent =
      usage.model_used || "-";
    document.getElementById("studio-analysis-prompt-tokens").textContent =
      formatNumber(usage.prompt_tokens);
    document.getElementById("studio-analysis-output-tokens").textContent =
      formatNumber(usage.completion_tokens);
    document.getElementById("studio-analysis-cached-tokens").textContent =
      formatNumber(usage.cached_prompt_tokens);
    document.getElementById("studio-analysis-cost").textContent =
      formatUsd(usage.total_cost_usd);
  }

  function dispatchGenerationEvent(data) {
    window.dispatchEvent(
      new CustomEvent("customy:application-generated", { detail: data })
    );
  }

  function generate() {
    var jdText = jdInput.value.trim();
    if (!jdText) {
      setStatus("Paste a job description first.", "error");
      return;
    }

    generateBtn.disabled = true;
    setStatus("Generating tailored materials...", "loading");

    fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jd: jdText,
        application_url: applicationUrlInput.value.trim(),
        outputs: selectedOutputs(),
      }),
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.error) {
          throw new Error(data.error);
        }

        renderAnalysis(data);
        renderDownloads(data.files);
        renderTabs(data);
        dispatchGenerationEvent(data);

        var costSuffix =
          data.usage && Number.isFinite(Number(data.usage.total_cost_usd))
            ? " OpenAI cost " + formatUsd(data.usage.total_cost_usd) + "."
            : "";
        setStatus("Saved under " + data.slug + "." + costSuffix, "success");
      })
      .catch(function (error) {
        setStatus(error.message || "Request failed.", "error");
      })
      .finally(function () {
        generateBtn.disabled = false;
      });
  }

  clearPreview();
  generateBtn.addEventListener("click", generate);
})();
