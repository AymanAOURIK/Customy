/**
 * CAuth — Customy authentication module.
 *
 * Local mode  (CUSTOMY_CONFIG.mode !== "saas"):
 *   CAuth.init() is never called. getToken() returns null.
 *   authFetch() behaves as plain fetch() — no header injected.
 *
 * SaaS mode:
 *   CAuth.init(url, key) initialises the Supabase client after the CDN loads.
 *   Session is restored from localStorage automatically by the SDK.
 *   Auth-state changes dispatch a "customy:auth-change" DOM event whose
 *   detail.session is the active session object (or null when signed out).
 *   authFetch() injects "Authorization: Bearer <token>" on every request.
 *
 * WT4 contract — authenticated API calls:
 *   Replace every fetch() that hits a protected endpoint with CAuth.authFetch().
 *   The call signature is identical to the native fetch(url, options).
 */
(function () {
  "use strict";

  var _client = null;
  var _session = null;

  function _dispatch(session) {
    window.dispatchEvent(
      new CustomEvent("customy:auth-change", { detail: { session: session } })
    );
  }

  var CAuth = {
    /**
     * Initialise the Supabase client.
     * Must be called once, after the Supabase JS SDK CDN script has loaded.
     * Only call this in SaaS mode.
     */
    init: function (supabaseUrl, supabaseAnonKey) {
      var createClient = window.supabase && window.supabase.createClient;
      if (!createClient) {
        console.error("[CAuth] Supabase JS SDK not found. Ensure the CDN script loaded.");
        return;
      }
      _client = createClient(supabaseUrl, supabaseAnonKey);

      // Restore existing persisted session (reads from localStorage)
      _client.auth.getSession().then(function (result) {
        _session = (result.data && result.data.session) || null;
        _dispatch(_session);
      });

      // Keep _session in sync with future token refreshes and sign-out events
      _client.auth.onAuthStateChange(function (_event, session) {
        _session = session || null;
        _dispatch(_session);
      });
    },

    /** Returns the active Supabase session object, or null. */
    getSession: function () {
      return _session;
    },

    /** Returns the JWT access-token string, or null when not authenticated. */
    getToken: function () {
      return (_session && _session.access_token) || null;
    },

    /**
     * Sign in with email + password.
     * Returns Promise<{ user: object|null, error: object|null }>.
     */
    signIn: function (email, password) {
      if (!_client) {
        return Promise.resolve({ user: null, error: { message: "Auth not initialised" } });
      }
      return _client.auth
        .signInWithPassword({ email: email, password: password })
        .then(function (result) {
          return {
            user: (result.data && result.data.user) || null,
            error: result.error || null,
          };
        });
    },

    /**
     * Register a new account with email + password.
     * Returns Promise<{ user: object|null, error: object|null }>.
     * Supabase may require email confirmation depending on project settings.
     */
    signUp: function (email, password) {
      if (!_client) {
        return Promise.resolve({ user: null, error: { message: "Auth not initialised" } });
      }
      return _client.auth
        .signUp({ email: email, password: password })
        .then(function (result) {
          return {
            user: (result.data && result.data.user) || null,
            error: result.error || null,
          };
        });
    },

    /**
     * Sign out the current user and clear the local session.
     * Returns Promise<{ error: object|null }>.
     */
    signOut: function () {
      if (!_client) {
        return Promise.resolve({ error: null });
      }
      return _client.auth.signOut().then(function (result) {
        return { error: result.error || null };
      });
    },

    /**
     * Subscribe to auth state changes.
     * callback(session) is invoked each time the session changes.
     * session is null when signed out, a session object when signed in.
     *
     * This wrapper listens to the "customy:auth-change" DOM event so that
     * multiple callers can subscribe without holding a Supabase handle.
     */
    onAuthStateChange: function (callback) {
      window.addEventListener("customy:auth-change", function (e) {
        callback(e.detail.session);
      });
    },

    /**
     * Authenticated fetch — drop-in replacement for window.fetch().
     *
     * When a session is active, injects:
     *   Authorization: Bearer <access_token>
     * into the request headers. Passes through unchanged when no session
     * exists (local mode or unauthenticated SaaS request).
     *
     * WT4: use this for every call to a protected /api/* endpoint.
     */
    authFetch: function (url, options) {
      var opts = Object.assign({}, options || {});
      var token = CAuth.getToken();
      if (token) {
        opts.headers = Object.assign({}, opts.headers || {}, {
          Authorization: "Bearer " + token,
        });
      }
      return fetch(url, opts);
    },
  };

  window.CAuth = CAuth;
})();
