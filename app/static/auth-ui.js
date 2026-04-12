/**
 * CAuthUI — auth overlay controller.
 *
 * Manages the #auth-overlay element: login form, sign-up form, tab switching.
 * All Supabase calls are delegated to CAuth — this module only handles UI.
 *
 * CAuthUI.show()  show the overlay (called when session is null in SaaS mode)
 * CAuthUI.hide()  hide the overlay (called on successful sign-in)
 */
(function () {
  "use strict";

  var _overlay = null;

  function _$(id) {
    return document.getElementById(id);
  }

  function _show() {
    if (_overlay) _overlay.removeAttribute("hidden");
  }

  function _hide() {
    if (_overlay) _overlay.setAttribute("hidden", "");
  }

  function _activateTab(which) {
    var loginForm   = _$("auth-form-login");
    var signupForm  = _$("auth-form-signup");
    var loginTab    = _$("auth-tab-login");
    var signupTab   = _$("auth-tab-signup");
    if (!loginForm || !signupForm) return;
    if (which === "login") {
      loginForm.removeAttribute("hidden");
      signupForm.setAttribute("hidden", "");
      loginTab.classList.add("auth-tab--active");
      signupTab.classList.remove("auth-tab--active");
    } else {
      signupForm.removeAttribute("hidden");
      loginForm.setAttribute("hidden", "");
      signupTab.classList.add("auth-tab--active");
      loginTab.classList.remove("auth-tab--active");
    }
  }

  function _init() {
    _overlay = _$("auth-overlay");
    if (!_overlay) return;

    var loginTab       = _$("auth-tab-login");
    var signupTab      = _$("auth-tab-signup");
    var loginEmail     = _$("auth-login-email");
    var loginPassword  = _$("auth-login-password");
    var loginBtn       = _$("auth-login-btn");
    var loginError     = _$("auth-login-error");
    var signupEmail    = _$("auth-signup-email");
    var signupPassword = _$("auth-signup-password");
    var signupBtn      = _$("auth-signup-btn");
    var signupError    = _$("auth-signup-error");
    var signupSuccess  = _$("auth-signup-success");

    loginTab.addEventListener("click",  function () { _activateTab("login");  });
    signupTab.addEventListener("click", function () { _activateTab("signup"); });

    /* ── Sign-in ─────────────────────────────────────────── */

    function doLogin() {
      var email    = loginEmail.value.trim();
      var password = loginPassword.value;
      loginError.textContent = "";
      if (!email || !password) {
        loginError.textContent = "Email and password are required.";
        return;
      }
      loginBtn.disabled = true;
      loginBtn.textContent = "Signing in\u2026";
      CAuth.signIn(email, password).then(function (result) {
        loginBtn.disabled = false;
        loginBtn.textContent = "Sign In";
        if (result.error) {
          loginError.textContent = result.error.message || "Sign-in failed.";
        }
        // On success the customy:auth-change event fires and CAuthUI.hide() is
        // called from the init script in dashboard.html.
      });
    }

    loginBtn.addEventListener("click", doLogin);
    loginPassword.addEventListener("keydown", function (e) {
      if (e.key === "Enter") doLogin();
    });

    /* ── Sign-up ─────────────────────────────────────────── */

    function doSignup() {
      var email    = signupEmail.value.trim();
      var password = signupPassword.value;
      signupError.textContent   = "";
      signupSuccess.textContent = "";
      if (!email || !password) {
        signupError.textContent = "Email and password are required.";
        return;
      }
      if (password.length < 6) {
        signupError.textContent = "Password must be at least 6 characters.";
        return;
      }
      signupBtn.disabled = true;
      signupBtn.textContent = "Signing up\u2026";
      CAuth.signUp(email, password).then(function (result) {
        signupBtn.disabled = false;
        signupBtn.textContent = "Sign Up";
        if (result.error) {
          signupError.textContent = result.error.message || "Sign-up failed.";
        } else {
          signupSuccess.textContent =
            "Account created! Check your email to confirm, then sign in.";
          signupEmail.value   = "";
          signupPassword.value = "";
        }
      });
    }

    signupBtn.addEventListener("click", doSignup);
    signupPassword.addEventListener("keydown", function (e) {
      if (e.key === "Enter") doSignup();
    });
  }

  window.CAuthUI = {
    show: _show,
    hide: _hide,
    init: _init,
  };

  document.addEventListener("DOMContentLoaded", _init);
})();
