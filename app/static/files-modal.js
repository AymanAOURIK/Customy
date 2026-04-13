(function () {
  "use strict";

  var overlay = document.getElementById("files-modal-overlay");
  var closeBtn = document.getElementById("files-modal-close");
  var titleEl = document.getElementById("files-modal-title");
  var subtitleEl = document.getElementById("files-modal-subtitle");
  var hintEl = document.getElementById("files-modal-hint");
  var bodyEl = document.getElementById("files-modal-body");
  var isSaas = !!(window.CUSTOMY_CONFIG && window.CUSTOMY_CONFIG.mode === "saas");

  if (!overlay || !bodyEl) {
    window.CustomyFiles = {
      open: function () {
        return Promise.reject(new Error("Files modal is not available."));
      },
    };
    return;
  }

  function escHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fetchJson(url, options) {
    var fetcher = isSaas && window.CAuth ? CAuth.authFetch.bind(CAuth) : fetch.bind(window);
    return fetcher(url, options || {})
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || data.error) {
            throw new Error((data && data.error) || ("Request failed (" + res.status + ")"));
          }
          return data;
        });
      });
  }

  function close() {
    overlay.classList.remove("aq-modal-overlay--visible");
  }

  function openShell() {
    overlay.classList.add("aq-modal-overlay--visible");
    bodyEl.innerHTML = '<div class="files-modal-state">Loading files...</div>';
    if (titleEl) titleEl.textContent = "Application Files";
    if (subtitleEl) subtitleEl.textContent = "Fresh signed links for this generated pack.";
    if (hintEl) {
      hintEl.textContent = isSaas
        ? "Links are refreshed each time you open this panel."
        : "Open any generated file directly from the application folder.";
    }
  }

  function renderFiles(data) {
    var app = data.application || {};
    var files = data.files || [];
    var missing = data.missing || [];

    if (titleEl) {
      titleEl.textContent = (app.company || "Application") + " - " + (app.role || "Files");
    }
    if (subtitleEl) {
      subtitleEl.textContent = (app.slug || "").trim()
        ? "Pack " + app.slug
        : "Generated artifacts";
    }

    if (!files.length && !missing.length) {
      bodyEl.innerHTML = '<div class="files-modal-state">No generated files are available for this application.</div>';
      return;
    }

    var html = "";

    if (files.length) {
      html += '<div class="files-modal-group">';
      files.forEach(function (file) {
        html +=
          '<div class="files-modal-item">' +
            '<div class="files-modal-meta">' +
              '<div class="files-modal-label">' + escHtml(file.label || file.key || "File") + "</div>" +
              '<div class="files-modal-name">' + escHtml(file.filename || file.path || "") + "</div>" +
            "</div>" +
            '<a class="files-modal-link" href="' + escHtml(file.url || "#") + '" target="_blank" rel="noreferrer">Open</a>' +
          "</div>";
      });
      html += "</div>";
    }

    if (missing.length) {
      html += '<div class="files-modal-group files-modal-group--missing">';
      missing.forEach(function (file) {
        html +=
          '<div class="files-modal-item files-modal-item--missing">' +
            '<div class="files-modal-meta">' +
              '<div class="files-modal-label">' + escHtml(file.label || file.key || "File") + "</div>" +
              '<div class="files-modal-name">' + escHtml(file.reason || "Unavailable") + "</div>" +
            "</div>" +
            '<span class="files-modal-missing-badge">Unavailable</span>' +
          "</div>";
      });
      html += "</div>";
    }

    bodyEl.innerHTML = html;
  }

  function open(appId) {
    openShell();
    return fetchJson("/api/applications/" + appId + "/files")
      .then(function (data) {
        renderFiles(data);
        return data;
      })
      .catch(function (err) {
        bodyEl.innerHTML =
          '<div class="files-modal-state files-modal-state--error">' +
          escHtml(err.message || "Failed to load application files.") +
          "</div>";
        throw err;
      });
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", close);
  }

  overlay.addEventListener("click", function (event) {
    if (event.target === overlay) {
      close();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && overlay.classList.contains("aq-modal-overlay--visible")) {
      close();
    }
  });

  window.CustomyFiles = { open: open, close: close };
})();
