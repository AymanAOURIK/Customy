/**
 * profile-intelligence.js
 *
 * Renders the Profile Intelligence section and populates Overview hooks.
 * Depends on profile-intelligence-data.js (window.PROFILE_INTELLIGENCE).
 *
 * Owned files:
 *   - app/static/profile-intelligence.js  (this file)
 *   - app/static/profile-intelligence-data.js
 *
 * Overview hooks populated (if present):
 *   - #overview-profile-slot
 *   - #overview-target-roles-slot
 *   - #overview-resume-slot
 *
 * Profile Intelligence section rendered into:
 *   - #profile-intelligence-section  (inside #section-profile-intelligence)
 */

(function () {
  "use strict";

  /* ── Wait for data ──────────────────────────────────────── */

  if (!window.PROFILE_INTELLIGENCE) {
    console.warn("[PI] profile-intelligence-data.js not loaded");
    return;
  }

  var PI = window.PROFILE_INTELLIGENCE;

  /* ── Inject scoped styles ───────────────────────────────── */

  var STYLES = [
    /* Hero card */
    ".pi-hero{display:grid;grid-template-columns:auto 1fr;gap:20px;align-items:start;padding:20px 22px;background:#FFFFFF;border:1px solid #E5E7EB;border-radius:14px;margin-bottom:20px}",
    ".pi-hero-left{display:flex;align-items:flex-start;gap:16px}",
    ".pi-avatar{width:52px;height:52px;border-radius:12px;background:#0F766E;color:#fff;display:flex;align-items:center;justify-content:center;font-size:1.1rem;font-weight:700;flex-shrink:0;letter-spacing:-0.02em}",
    ".pi-identity h2{font-size:1.15rem;font-weight:700;color:#111827;margin:0 0 3px}",
    ".pi-identity .pi-hl{font-size:0.875rem;font-weight:500;color:#0F766E;margin:0 0 2px}",
    ".pi-identity .pi-meta{font-size:0.78rem;color:#6B7280;margin:0}",
    ".pi-summary-col{padding-left:4px}",
    ".pi-summary-text{font-size:0.85rem;color:#374151;line-height:1.6;margin:0 0 14px;font-style:italic;border-left:3px solid #E5E7EB;padding-left:12px}",
    ".pi-skill-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:0}",
    ".pi-skill-chip{padding:3px 9px;border-radius:5px;background:#F3F4F6;border:1px solid #E5E7EB;font-size:0.72rem;font-weight:500;color:#374151}",
    ".pi-lang-chip{padding:3px 9px;border-radius:5px;background:rgba(15,118,110,0.07);border:1px solid rgba(15,118,110,0.18);font-size:0.72rem;font-weight:500;color:#0F766E}",
    /* 2-col content grid */
    ".pi-2col{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}",
    ".pi-3col{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:20px}",
    /* Card sub-sections (shares .shell-card, .shell-card-header, .shell-card-title) */
    ".pi-section-label{font-size:0.68rem;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:#9CA3AF;margin:0 0 12px}",
    /* Capability items */
    ".pi-capability-list{display:grid;gap:10px}",
    ".pi-cap-item{padding:12px 14px;border-radius:10px;background:#F9FAFB;border:1px solid #F0F1F3}",
    ".pi-cap-title{font-size:0.82rem;font-weight:600;color:#111827;margin:0 0 4px}",
    ".pi-cap-desc{font-size:0.78rem;color:#6B7280;margin:0;line-height:1.5}",
    /* Target role items */
    ".pi-role-list{display:grid;gap:8px}",
    ".pi-role-item{display:flex;flex-direction:column;gap:4px;padding:12px 14px;border-radius:10px;background:#F9FAFB;border:1px solid #F0F1F3}",
    ".pi-role-header{display:flex;align-items:center;justify-content:space-between;gap:8px}",
    ".pi-role-title{font-size:0.85rem;font-weight:600;color:#111827;margin:0}",
    ".pi-role-rationale{font-size:0.75rem;color:#6B7280;margin:0;line-height:1.45}",
    ".pi-fit-strong{padding:2px 8px;border-radius:5px;background:rgba(5,150,105,0.1);color:#059669;font-size:0.68rem;font-weight:600;white-space:nowrap}",
    ".pi-fit-good{padding:2px 8px;border-radius:5px;background:rgba(217,119,6,0.1);color:#B45309;font-size:0.68rem;font-weight:600;white-space:nowrap}",
    ".pi-rec-notice{font-size:0.72rem;color:#9CA3AF;font-style:italic;margin:12px 0 0;padding-top:10px;border-top:1px solid #F0F1F3}",
    /* Fit explanation */
    ".pi-fit-intro{font-size:0.85rem;color:#374151;line-height:1.6;margin:0 0 12px}",
    ".pi-fit-points{margin:0;padding-left:18px;display:grid;gap:6px}",
    ".pi-fit-points li{font-size:0.82rem;color:#374151;line-height:1.5}",
    /* Industry chips */
    ".pi-industry-list{display:grid;gap:8px}",
    ".pi-industry-item{padding:10px 12px;border-radius:9px;background:#F9FAFB;border:1px solid #F0F1F3}",
    ".pi-industry-label{font-size:0.82rem;font-weight:600;color:#111827;margin:0 0 2px}",
    ".pi-industry-note{font-size:0.75rem;color:#6B7280;margin:0}",
    /* Workflow guidance */
    ".pi-workflow-header{font-size:0.82rem;font-weight:600;color:#111827;margin:0 0 10px;padding-bottom:8px;border-bottom:1px solid #F0F1F3}",
    ".pi-action-list{display:grid;gap:8px;margin:0;padding:0;list-style:none}",
    ".pi-action-item{display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border-radius:9px;background:#F9FAFB;border:1px solid #F0F1F3}",
    ".pi-action-num{width:20px;height:20px;border-radius:5px;background:#0F766E;color:#fff;font-size:0.68rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px}",
    ".pi-action-text{font-size:0.8rem;color:#374151;line-height:1.5;margin:0}",
    ".pi-followup-list{display:grid;gap:7px;margin:0;padding:0;list-style:none}",
    ".pi-followup-item{font-size:0.8rem;color:#374151;line-height:1.45;padding:8px 10px;border-radius:8px;background:#F9FAFB;border-left:3px solid #0F766E}",
    ".pi-interview-list{display:grid;gap:8px}",
    ".pi-interview-item{padding:10px 12px;border-radius:9px;background:#F9FAFB;border:1px solid #F0F1F3}",
    ".pi-interview-area{font-size:0.8rem;font-weight:600;color:#111827;margin:0 0 3px}",
    ".pi-interview-note{font-size:0.75rem;color:#6B7280;margin:0;line-height:1.45}",
    /* Overview slot overrides */
    ".pi-ov-profile{display:grid;gap:12px}",
    ".pi-ov-avatar-row{display:flex;align-items:center;gap:12px}",
    ".pi-ov-avatar{width:40px;height:40px;border-radius:10px;background:#0F766E;color:#fff;display:flex;align-items:center;justify-content:center;font-size:0.9rem;font-weight:700;flex-shrink:0}",
    ".pi-ov-name{font-size:0.95rem;font-weight:600;color:#111827;margin:0}",
    ".pi-ov-sub{font-size:0.78rem;color:#6B7280;margin:2px 0 0}",
    ".pi-ov-stat-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}",
    ".pi-ov-stat{padding:8px 10px;border-radius:8px;background:#F9FAFB;border:1px solid #F0F1F3}",
    ".pi-ov-stat-label{font-size:0.68rem;font-weight:500;color:#6B7280;text-transform:uppercase;letter-spacing:0.04em}",
    ".pi-ov-stat-val{font-size:0.9rem;font-weight:600;color:#111827;margin-top:2px}",
    ".pi-ov-role-list{display:grid;gap:6px}",
    ".pi-ov-role-item{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border-radius:8px;background:#F9FAFB;border:1px solid #F0F1F3}",
    ".pi-ov-role-title{font-size:0.82rem;font-weight:500;color:#111827}",
    ".pi-ov-resume-body{display:grid;gap:10px}",
    ".pi-ov-resume-headline{font-size:0.95rem;font-weight:600;color:#111827;margin:0}",
    ".pi-ov-resume-meta{font-size:0.78rem;color:#6B7280;margin:2px 0 0}",
    ".pi-ov-proof-list{margin:0;padding-left:16px;display:grid;gap:4px}",
    ".pi-ov-proof-list li{font-size:0.75rem;color:#374151;line-height:1.45}",
    /* Responsive */
    "@media(max-width:1024px){.pi-2col,.pi-3col{grid-template-columns:1fr}}",
    "@media(max-width:640px){.pi-hero{grid-template-columns:1fr}}",
  ].join("\n");

  var styleEl = document.createElement("style");
  styleEl.id = "pi-styles";
  styleEl.textContent = STYLES;
  document.head.appendChild(styleEl);

  /* ── Utility ────────────────────────────────────────────── */

  function el(tag, attrs, html) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "class") node.className = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    if (html !== undefined) node.innerHTML = html;
    return node;
  }

  function fitBadgeClass(fit) {
    return fit === "strong" ? "pi-fit-strong" : "pi-fit-good";
  }

  /* ── Build: Hero card ───────────────────────────────────── */

  function buildHero() {
    var id = PI.identity;
    var yrs = id.years_experience + "+ years";

    var skillsHtml = id.top_skills
      .map(function (s) {
        return '<span class="pi-skill-chip">' + s + "</span>";
      })
      .join("");

    var langsHtml = id.spoken_languages
      .map(function (l) {
        return '<span class="pi-lang-chip">' + l + "</span>";
      })
      .join("");

    var hero = el("div", { class: "pi-hero" });
    hero.innerHTML =
      '<div class="pi-hero-left">' +
      '<div class="pi-avatar">' + id.initials + "</div>" +
      '<div class="pi-identity">' +
      "<h2>" + id.name + "</h2>" +
      '<p class="pi-hl">' + id.headline + "</p>" +
      '<p class="pi-meta">' + yrs + " &middot; " + id.location + " &middot; " + id.education.institution + " " + id.education.year + "</p>" +
      "</div>" +
      "</div>" +
      '<div class="pi-summary-col">' +
      '<p class="pi-summary-text">' + id.summary + "</p>" +
      '<div class="pi-skill-row">' + skillsHtml + langsHtml + "</div>" +
      "</div>";
    return hero;
  }

  /* ── Build: Capability map ──────────────────────────────── */

  function buildCapabilityMap() {
    var wrap = el("div", { class: "shell-card" });
    wrap.innerHTML =
      '<div class="shell-card-header"><div>' +
      '<h3 class="shell-card-title">Capability Map</h3>' +
      '<p class="shell-card-subtitle">Core strengths grounded in delivered work</p>' +
      "</div></div>";

    var list = el("div", { class: "pi-capability-list" });
    PI.capabilities.forEach(function (cap) {
      var item = el("div", { class: "pi-cap-item" });
      item.innerHTML =
        '<p class="pi-cap-title">' + cap.title + "</p>" +
        '<p class="pi-cap-desc">' + cap.description + "</p>";
      list.appendChild(item);
    });
    wrap.appendChild(list);
    return wrap;
  }

  /* ── Build: Target roles ────────────────────────────────── */

  function buildTargetRoles() {
    var wrap = el("div", { class: "shell-card" });
    wrap.innerHTML =
      '<div class="shell-card-header"><div>' +
      '<h3 class="shell-card-title">Recommended Target Roles</h3>' +
      '<p class="shell-card-subtitle">Inferred from profile — not factual past roles</p>' +
      "</div></div>";

    var list = el("div", { class: "pi-role-list" });
    PI.target_roles.forEach(function (role) {
      var item = el("div", { class: "pi-role-item" });
      item.innerHTML =
        '<div class="pi-role-header">' +
        '<p class="pi-role-title">' + role.title + "</p>" +
        '<span class="' + fitBadgeClass(role.fit) + '">' + role.fit_label + "</span>" +
        "</div>" +
        '<p class="pi-role-rationale">' + role.rationale + "</p>";
      list.appendChild(item);
    });

    var notice = el("p", { class: "pi-rec-notice" });
    notice.textContent =
      "These are recommendations inferred from demonstrated experience. They reflect likely fit, not a historical record.";
    list.appendChild(notice);

    wrap.appendChild(list);
    return wrap;
  }

  /* ── Build: Why these roles fit ─────────────────────────── */

  function buildRoleFitExplanation() {
    var fit = PI.role_fit_explanation;
    var wrap = el("div", { class: "shell-card" });
    wrap.innerHTML =
      '<div class="shell-card-header"><div>' +
      '<h3 class="shell-card-title">' + fit.headline + "</h3>" +
      '<p class="shell-card-subtitle">Logic behind the role recommendations</p>' +
      "</div></div>" +
      '<p class="pi-fit-intro">' + fit.intro + "</p>" +
      "<ul class=\"pi-fit-points\">" +
      fit.points
        .map(function (p) {
          return "<li>" + p + "</li>";
        })
        .join("") +
      "</ul>";
    return wrap;
  }

  /* ── Build: Focus industries ────────────────────────────── */

  function buildFocusIndustries() {
    var wrap = el("div", { class: "shell-card" });
    wrap.innerHTML =
      '<div class="shell-card-header"><div>' +
      '<h3 class="shell-card-title">Focus Industries</h3>' +
      '<p class="shell-card-subtitle">Verticals where your profile lands best</p>' +
      "</div></div>";

    var list = el("div", { class: "pi-industry-list" });
    PI.focus_industries.forEach(function (ind) {
      var item = el("div", { class: "pi-industry-item" });
      item.innerHTML =
        '<p class="pi-industry-label">' + ind.label + "</p>" +
        '<p class="pi-industry-note">' + ind.note + "</p>";
      list.appendChild(item);
    });
    wrap.appendChild(list);
    return wrap;
  }

  /* ── Build: Workflow guidance ───────────────────────────── */

  function buildWorkflow() {
    var wf = PI.workflow;

    /* Next actions */
    var actionsCard = el("div", { class: "shell-card" });
    actionsCard.innerHTML =
      '<div class="shell-card-header"><div>' +
      '<h3 class="shell-card-title">Next Best Actions</h3>' +
      '<p class="shell-card-subtitle">Priority steps for your job search</p>' +
      "</div></div>";
    var actionList = el("ul", { class: "pi-action-list" });
    wf.next_actions.forEach(function (item) {
      var li = el("li", { class: "pi-action-item" });
      li.innerHTML =
        '<span class="pi-action-num">' + item.priority + "</span>" +
        '<p class="pi-action-text">' + item.action + "</p>";
      actionList.appendChild(li);
    });
    actionsCard.appendChild(actionList);

    /* Follow-up priorities */
    var followupCard = el("div", { class: "shell-card" });
    followupCard.innerHTML =
      '<div class="shell-card-header"><div>' +
      '<h3 class="shell-card-title">Follow-Up Priorities</h3>' +
      '<p class="shell-card-subtitle">Where to invest follow-up energy</p>' +
      "</div></div>";
    var followupList = el("ul", { class: "pi-followup-list" });
    wf.followup_priorities.forEach(function (item) {
      var li = el("li", { class: "pi-followup-item" });
      li.textContent = item;
      followupList.appendChild(li);
    });
    followupCard.appendChild(followupList);

    /* Interview focus */
    var interviewCard = el("div", { class: "shell-card" });
    interviewCard.innerHTML =
      '<div class="shell-card-header"><div>' +
      '<h3 class="shell-card-title">Interview Focus Areas</h3>' +
      '<p class="shell-card-subtitle">What to prepare and how to frame it</p>' +
      "</div></div>";
    var interviewList = el("div", { class: "pi-interview-list" });
    wf.interview_focus_areas.forEach(function (item) {
      var entry = el("div", { class: "pi-interview-item" });
      entry.innerHTML =
        '<p class="pi-interview-area">' + item.area + "</p>" +
        '<p class="pi-interview-note">' + item.note + "</p>";
      interviewList.appendChild(entry);
    });
    interviewCard.appendChild(interviewList);

    return { actionsCard: actionsCard, followupCard: followupCard, interviewCard: interviewCard };
  }

  /* ── Render: Profile Intelligence section ───────────────── */

  function renderProfileIntelligence() {
    var container = document.getElementById("profile-intelligence-section");
    if (!container) return;

    container.innerHTML = "";

    container.appendChild(buildHero());

    var row1 = el("div", { class: "pi-2col" });
    row1.appendChild(buildCapabilityMap());
    row1.appendChild(buildTargetRoles());
    container.appendChild(row1);

    var row2 = el("div", { class: "pi-2col" });
    row2.appendChild(buildRoleFitExplanation());
    row2.appendChild(buildFocusIndustries());
    container.appendChild(row2);

    var wf = buildWorkflow();
    var row3 = el("div", { class: "pi-3col" });
    row3.appendChild(wf.actionsCard);
    row3.appendChild(wf.followupCard);
    row3.appendChild(wf.interviewCard);
    container.appendChild(row3);
  }

  /* ── Populate: Overview — Profile Snapshot slot ─────────── */

  function populateProfileSlot() {
    var slot = document.getElementById("overview-profile-slot");
    if (!slot) return;

    var id = PI.identity;
    var header = slot.querySelector(".shell-card-header");
    var body = el("div", { class: "pi-ov-profile" });

    body.innerHTML =
      '<div class="pi-ov-avatar-row">' +
      '<div class="pi-ov-avatar">' + id.initials + "</div>" +
      "<div>" +
      '<p class="pi-ov-name">' + id.name + "</p>" +
      '<p class="pi-ov-sub">' + id.headline + " &middot; " + id.location + "</p>" +
      "</div>" +
      "</div>" +
      '<div class="pi-ov-stat-row">' +
      '<div class="pi-ov-stat"><div class="pi-ov-stat-label">Experience</div><div class="pi-ov-stat-val">' + id.years_experience + "+ yrs</div></div>" +
      '<div class="pi-ov-stat"><div class="pi-ov-stat-label">Current Role</div><div class="pi-ov-stat-val">' + id.current_role + "</div></div>" +
      '<div class="pi-ov-stat"><div class="pi-ov-stat-label">Location</div><div class="pi-ov-stat-val">' + id.location + "</div></div>" +
      '<div class="pi-ov-stat"><div class="pi-ov-stat-label">Degree</div><div class="pi-ov-stat-val">' + id.education.degree.split(" ").slice(0, 3).join(" ") + "</div></div>" +
      "</div>" +
      '<div class="pi-skill-row">' +
      id.top_skills.slice(0, 6).map(function (s) {
        return '<span class="pi-skill-chip">' + s + "</span>";
      }).join("") +
      "</div>";

    // Remove placeholder, insert body
    var placeholder = slot.querySelector(".placeholder-section");
    if (placeholder) placeholder.remove();
    if (header) header.after(body);
    else slot.appendChild(body);
  }

  /* ── Populate: Overview — Target Roles slot ─────────────── */

  function populateTargetRolesSlot() {
    var slot = document.getElementById("overview-target-roles-slot");
    if (!slot) return;

    var header = slot.querySelector(".shell-card-header");
    var list = el("div", { class: "pi-ov-role-list" });

    PI.target_roles.forEach(function (role) {
      var item = el("div", { class: "pi-ov-role-item" });
      item.innerHTML =
        '<span class="pi-ov-role-title">' + role.title + "</span>" +
        '<span class="' + fitBadgeClass(role.fit) + '">' + role.fit_label + "</span>";
      list.appendChild(item);
    });

    var notice = el("p", { class: "pi-rec-notice" });
    notice.textContent = "Recommendations inferred from profile — not historical roles.";
    list.appendChild(notice);

    var placeholder = slot.querySelector(".placeholder-section");
    if (placeholder) placeholder.remove();
    if (header) header.after(list);
    else slot.appendChild(list);
  }

  /* ── Populate: Overview — Resume slot ───────────────────── */

  function populateResumeSlot() {
    var slot = document.getElementById("overview-resume-slot");
    if (!slot) return;

    var id = PI.identity;
    var resume = PI.resume;
    var header = slot.querySelector(".shell-card-header");

    var body = el("div", { class: "pi-ov-resume-body" });
    body.innerHTML =
      '<p class="pi-ov-resume-headline">' + resume.base_headline + "</p>" +
      '<p class="pi-ov-resume-meta">' + resume.career_span + " &middot; " + resume.total_roles + " roles &middot; " + id.education.institution + "</p>" +
      "<div>" +
      '<p class="pi-section-label" style="margin-bottom:6px">Strongest proof points</p>' +
      "<ul class=\"pi-ov-proof-list\">" +
      resume.strongest_proof_points
        .map(function (p) {
          return "<li>" + p + "</li>";
        })
        .join("") +
      "</ul>" +
      "</div>";

    var placeholder = slot.querySelector(".placeholder-section");
    if (placeholder) placeholder.remove();
    if (header) header.after(body);
    else slot.appendChild(body);
  }

  /* ── Init ───────────────────────────────────────────────── */

  function init() {
    renderProfileIntelligence();
    populateProfileSlot();
    populateTargetRolesSlot();
    populateResumeSlot();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
