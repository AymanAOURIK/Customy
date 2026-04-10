(function () {
  "use strict";

  var STORAGE_KEY = "customy-theme";
  var root = document.documentElement;
  var buttons = document.querySelectorAll("[data-theme-toggle]");

  function storedTheme() {
    try {
      var value = localStorage.getItem(STORAGE_KEY);
      if (value === "light" || value === "dark") return value;
    } catch (_) {
      return "";
    }
    return "";
  }

  function systemTheme() {
    return window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function currentTheme() {
    return root.dataset.theme === "dark" ? "dark" : "light";
  }

  function updateButtons(theme) {
    buttons.forEach(function (button) {
      var nextTheme = theme === "dark" ? "light" : "dark";
      var label = button.querySelector("[data-theme-label]");
      if (label) label.textContent = theme === "dark" ? "Dark" : "Light";
      button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      button.setAttribute("aria-label", "Switch to " + nextTheme + " mode");
      button.setAttribute("title", "Switch to " + nextTheme + " mode");
    });
  }

  function applyTheme(theme, persist) {
    var normalized = theme === "dark" ? "dark" : "light";
    root.dataset.theme = normalized;
    root.style.colorScheme = normalized;
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, normalized);
      } catch (_) {}
    }
    updateButtons(normalized);
    window.dispatchEvent(
      new CustomEvent("customy:themechange", {
        detail: { theme: normalized },
      })
    );
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      applyTheme(currentTheme() === "dark" ? "light" : "dark", true);
    });
  });

  updateButtons(currentTheme());

  var mediaQuery = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

  if (mediaQuery && mediaQuery.addEventListener) {
    mediaQuery.addEventListener("change", function (event) {
      if (storedTheme()) return;
      applyTheme(event.matches ? "dark" : "light", false);
    });
  } else if (mediaQuery && mediaQuery.addListener) {
    mediaQuery.addListener(function (event) {
      if (storedTheme()) return;
      applyTheme(event.matches ? "dark" : "light", false);
    });
  }

  window.CustomyTheme = {
    apply: applyTheme,
    current: currentTheme,
    system: systemTheme,
  };
})();
