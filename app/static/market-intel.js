/* market-intel.js — Market Intel section for Customy platform
 * Renders into #market-intel-section (the placeholder shell-card).
 * All unverified claims are labeled Hypothesis or Needs Research.
 * No backend required. No external dependencies. */

(function () {
  'use strict';

  /* ── Status labels ─────────────────────────────────────── */

  var S = {
    VERIFIED:   { label: 'Verified',       cls: 'mi-badge-verified'  },
    HYPOTHESIS: { label: 'Hypothesis',     cls: 'mi-badge-hypothesis' },
    RESEARCH:   { label: 'Needs Research', cls: 'mi-badge-research'   },
  };

  /* ── Data ──────────────────────────────────────────────── */

  var pains = [
    {
      title: 'One-size-fits-all resumes',
      body: 'Generic builders produce identical documents regardless of role. Manual tailoring is slow and inconsistent.',
      status: S.VERIFIED,
    },
    {
      title: 'Fragmented application workflow',
      body: 'Cover letter, email draft, LinkedIn message, and follow-up each require a separate tool with no shared history.',
      status: S.VERIFIED,
    },
    {
      title: 'Privacy risk with cloud-based tools',
      body: 'Most AI resume tools upload candidate data to cloud servers. Privacy-conscious users have no local alternative at equivalent quality.',
      status: S.VERIFIED,
    },
    {
      title: 'ATS keyword screening',
      body: 'A large proportion of applications are filtered before any human review. Keyword and format matching is critical but opaque.',
      status: S.RESEARCH,
    },
    {
      title: 'High time cost per application',
      body: 'Each tailored application may take 1–3 hours when done manually. This compounds across 10–50+ applications in a serious search.',
      status: S.HYPOTHESIS,
    },
    {
      title: 'No structured application history',
      body: 'Most job seekers lack a reliable log of what was sent, which resume version was used, cost incurred, and follow-up status.',
      status: S.VERIFIED,
    },
  ];

  var categories = [
    {
      title: 'Generic Resume Builders',
      examples: 'Online drag-and-drop tools',
      has:  ['Templates', 'PDF / DOCX export'],
      gaps: ['No AI tailoring', 'Cloud-only', 'No pipeline'],
    },
    {
      title: 'AI Tailoring Tools',
      examples: 'Cloud-based AI resume apps',
      has:  ['AI rewriting', 'ATS scoring'],
      gaps: ['Cloud-only storage', 'Partial pipeline', 'No history'],
    },
    {
      title: 'Manual / Coaching Services',
      examples: 'Career coaches, resume writers',
      has:  ['Deep personalisation', 'Human judgment'],
      gaps: ['High cost', 'Slow turnaround', 'Not scalable'],
    },
    {
      title: 'DIY Multi-tool Stack',
      examples: 'ChatGPT + Notion + Word',
      has:  ['Flexible', 'Low direct cost'],
      gaps: ['No structure', 'No history', 'No pipeline'],
    },
  ];

  var matrix = {
    headers: ['Capability', 'Generic Builders', 'AI Tools', 'Manual Services', 'Customy'],
    rows: [
      ['Local / privacy-first',               '✗', '✗',       '✗',       '✓'],
      ['LLM tailoring',                        '✗', '✓',       '✗',       '✓'],
      ['LaTeX output quality',                 '✗', '✗',       '✗',       '✓'],
      ['Cover letter + email + LinkedIn',      '✗', 'Partial', '✓',       '✓'],
      ['Application history tracking',         '✗', 'Partial', '✗',       '✓'],
      ['EN / FR language matching',            '✗', 'Partial', '✓',       '✓'],
      ['No subscription required',             '✗', '✗',       '✗',       '✓'],
    ],
  };

  var pricing = [
    {
      label: 'Free / Local Forever',
      desc:  'No charge. User runs locally with their own API key. Current state.',
      status: S.VERIFIED,
    },
    {
      label: 'Freemium + Cloud Sync',
      desc:  'Local core free; optional paid tier adds cloud backup, sync, and mobile access.',
      status: S.HYPOTHESIS,
    },
    {
      label: 'One-time License',
      desc:  'Single payment for lifetime use. Appeals to privacy-first users who avoid subscriptions.',
      status: S.HYPOTHESIS,
    },
    {
      label: 'Per-resume Credits',
      desc:  'Pay per tailored output. Low-commitment entry point for occasional users.',
      status: S.HYPOTHESIS,
    },
    {
      label: 'B2B — Career Coach License',
      desc:  'Career coaches license Customy for use with clients. Recurring revenue without consumer marketing.',
      status: S.HYPOTHESIS,
    },
  ];

  var positioning = {
    headline: 'The local-first AI tailoring platform for serious job seekers.',
    body: 'Customy handles the full application pipeline — keyword extraction, LLM tailoring, LaTeX PDF output, cover letter, LinkedIn message, email draft, and application history — entirely on your machine. No cloud, no subscription, no data exposure.',
    differentiators: [
      'Local-only by design — no cloud, no auth, no data exposure',
      'Structured pipeline, not a one-off prompt tool',
      'LaTeX-grade output quality, not template fill-in',
      'Full history: application log, cost tracking, and document versions in SQLite',
      'Language-matched output: English and French',
    ],
  };

  var objections = [
    {
      q: '"Why not just use ChatGPT?"',
      a: 'ChatGPT gives raw text. Customy gives a structured pipeline: keyword extraction before any LLM call, language matching, LaTeX output, and application history — in one reproducible local workflow.',
    },
    {
      q: '"Why local-only? Cloud tools are fine."',
      a: 'Cloud tools store your career history, salary expectations, and personal narrative on servers you don\'t control. Local-only is a principled product decision, not a technical limitation.',
    },
    {
      q: '"LaTeX output is overkill."',
      a: 'LaTeX is precise, format-stable across machines, and produces consistent PDF output that doesn\'t reflow the way Word documents do. It\'s also version-controllable.',
    },
    {
      q: '"Who actually has this problem?"',
      a: 'Anyone running a serious job search: 10+ applications, multiple role types, bilingual markets. Developers, designers, PMs, and consultants who value quality and want to reduce repetition.',
    },
  ];

  var gtm = [
    {
      title: 'Developer Community Seeding',
      desc:  'Post on Hacker News, Reddit (r/cscareerquestions, r/devops). The privacy-first and local-only angle resonates strongly with technical audiences.',
      status: S.HYPOTHESIS,
    },
    {
      title: 'LinkedIn Content Loop',
      desc:  'Share before/after tailored resume walkthroughs. Target job seekers mid-search who are frustrated with low response rates.',
      status: S.HYPOTHESIS,
    },
    {
      title: 'Career Coach B2B Pilot',
      desc:  'Give 3–5 career coaches free access to use with clients. Collect feedback, referrals, and case studies.',
      status: S.HYPOTHESIS,
    },
    {
      title: 'Open Source Core',
      desc:  'Release the tailoring engine as open source. Keep the platform shell premium. Build community trust and organic discovery.',
      status: S.HYPOTHESIS,
    },
    {
      title: 'Job Board Integration',
      desc:  '"Tailor for this role" as a one-click feature adjacent to job listings. Requires partnership negotiation.',
      status: S.RESEARCH,
    },
  ];

  var researchBoard = {
    verified: [
      'Local-first architecture — no cloud or auth dependency',
      'LLM tailoring pipeline: analyzer → LLM → LaTeX',
      'SQLite application history and API cost tracking',
      'LaTeX PDF output via pdflatex',
      'English and French language matching from JD',
      'Full output set: resume, cover letter, LinkedIn message, email draft',
    ],
    hypothesis: [
      'Average manual time cost per tailored application',
      'Price sensitivity of privacy-first users',
      'Willingness to pay: one-time vs subscription',
      'Career coach licensing as a viable B2B channel',
      'Developer community as the primary acquisition channel',
    ],
    research: [
      'ATS rejection rates and measurable keyword impact',
      'Actual addressable market size for AI-assisted applications',
      'Current competitor feature parity and pricing',
      'Customer LTV under different pricing models',
      'Conversion path: free local tool → paid upgrade',
    ],
  };

  /* ── Helpers ───────────────────────────────────────────── */

  function badge(s) {
    return '<span class="mi-badge ' + s.cls + '">' + s.label + '</span>';
  }

  function cardHeader(title, sub) {
    return (
      '<div class="shell-card-header" style="margin-bottom:18px">' +
        '<div>' +
          '<h3 class="shell-card-title">' + title + '</h3>' +
          (sub ? '<p class="shell-card-subtitle">' + sub + '</p>' : '') +
        '</div>' +
      '</div>'
    );
  }

  function card(content) {
    return '<div class="shell-card mi-card">' + content + '</div>';
  }

  /* ── Render blocks ─────────────────────────────────────── */

  function renderSummary() {
    return card(
      cardHeader('Market Summary', 'What Customy is and why it exists') +
      '<p class="mi-body-text">' +
        'Customy is a <strong>local-first, LLM-powered job application platform</strong>. It solves a fragmented workflow: ' +
        'job seekers spend significant time manually tailoring resumes, writing cover letters, and crafting outreach — and most tools ' +
        'either produce generic output or require uploading sensitive career data to the cloud.' +
      '</p>' +
      '<p class="mi-body-text">' +
        'Customy owns the full pipeline: keyword extraction, LLM tailoring, LaTeX PDF output, application history, cost tracking, ' +
        'and document variants — all running locally with no cloud dependency.' +
      '</p>' +
      '<div class="mi-tags">' +
        ['Local-first', 'AI-assisted', 'Full pipeline', 'Privacy-preserving', 'LaTeX output', 'SQLite history']
          .map(function (t) { return '<span class="mi-tag">' + t + '</span>'; }).join('') +
      '</div>'
    );
  }

  function renderPains() {
    var items = pains.map(function (p) {
      return (
        '<div class="mi-inner-card">' +
          '<div class="mi-inner-header">' +
            '<span class="mi-inner-title">' + p.title + '</span>' +
            badge(p.status) +
          '</div>' +
          '<p class="mi-inner-body">' + p.body + '</p>' +
        '</div>'
      );
    }).join('');

    return card(
      cardHeader('Problem / Pain Landscape', 'Core friction points this product addresses') +
      '<div class="mi-grid-3">' + items + '</div>'
    );
  }

  function renderCategories() {
    var items = categories.map(function (c) {
      return (
        '<div class="mi-inner-card">' +
          '<div class="mi-cat-title">' + c.title + '</div>' +
          '<div class="mi-cat-sub">' + c.examples + '</div>' +
          '<div class="mi-cat-label">Has</div>' +
          c.has.map(function (f) { return '<div class="mi-cat-row mi-has">✓ ' + f + '</div>'; }).join('') +
          '<div class="mi-cat-label">Missing</div>' +
          c.gaps.map(function (g) { return '<div class="mi-cat-row mi-gap">✗ ' + g + '</div>'; }).join('') +
        '</div>'
      );
    }).join('');

    return card(
      cardHeader('Competitor Categories', 'Alternative approaches — categories only, not specific product claims') +
      '<p class="mi-note">Specific tool names are omitted to avoid unverified claims. ' +
        badge(S.RESEARCH) + ' Detailed competitive research pending.' +
      '</p>' +
      '<div class="mi-grid-4">' + items + '</div>'
    );
  }

  function renderMatrix() {
    var ths = matrix.headers.map(function (h, i) {
      return '<th' + (i === 4 ? ' class="mi-m-customy"' : '') + '>' + h + '</th>';
    }).join('');

    var rows = matrix.rows.map(function (row) {
      var cells = row.map(function (cell, i) {
        var cls = i === 4 ? ' class="mi-m-customy"' : '';
        var val = cell === '✓' ? '<span class="mi-check">✓</span>'
                : cell === '✗' ? '<span class="mi-cross">✗</span>'
                : cell;
        return '<td' + cls + '>' + val + '</td>';
      }).join('');
      return '<tr>' + cells + '</tr>';
    }).join('');

    return card(
      cardHeader('Offer Comparison Matrix', 'Customy vs alternative categories') +
      '<div class="mi-matrix-wrap">' +
        '<table class="mi-matrix">' +
          '<thead><tr>' + ths + '</tr></thead>' +
          '<tbody>' + rows + '</tbody>' +
        '</table>' +
      '</div>' +
      '<p class="mi-note" style="margin-top:12px">Competitor columns represent category capabilities, not verified specific-product data. ' +
        badge(S.RESEARCH) +
      '</p>'
    );
  }

  function renderPricing() {
    var items = pricing.map(function (p) {
      return (
        '<div class="mi-inner-card">' +
          '<div class="mi-inner-header">' +
            '<span class="mi-inner-title">' + p.label + '</span>' +
            badge(p.status) +
          '</div>' +
          '<p class="mi-inner-body">' + p.desc + '</p>' +
        '</div>'
      );
    }).join('');

    return card(
      cardHeader('Pricing Hypotheses', 'Possible monetisation models — none confirmed') +
      '<div class="mi-grid-auto">' + items + '</div>'
    );
  }

  function renderPositioning() {
    var diffs = positioning.differentiators.map(function (d) {
      return '<li class="mi-diff-item">' + d + '</li>';
    }).join('');

    return card(
      cardHeader('Positioning Statement', 'Draft — subject to validation') +
      '<div class="mi-pos-headline">"' + positioning.headline + '"</div>' +
      '<p class="mi-body-text">' + positioning.body + '</p>' +
      '<div class="mi-diff-label">Key differentiators</div>' +
      '<ul class="mi-diff-list">' + diffs + '</ul>'
    );
  }

  function renderObjections() {
    var items = objections.map(function (o) {
      return (
        '<div class="mi-inner-card">' +
          '<div class="mi-obj-q">' + o.q + '</div>' +
          '<div class="mi-inner-body">' + o.a + '</div>' +
        '</div>'
      );
    }).join('');

    return card(
      cardHeader('Objections & Responses', 'Common pushback and how to answer it') +
      '<div class="mi-grid-2">' + items + '</div>'
    );
  }

  function renderGTM() {
    var items = gtm.map(function (e) {
      return (
        '<div class="mi-inner-card">' +
          '<div class="mi-inner-header">' +
            '<span class="mi-inner-title">' + e.title + '</span>' +
            badge(e.status) +
          '</div>' +
          '<p class="mi-inner-body">' + e.desc + '</p>' +
        '</div>'
      );
    }).join('');

    return card(
      cardHeader('GTM Experiments', 'Go-to-market ideas to validate — all labeled as hypothesis') +
      '<div class="mi-grid-auto">' + items + '</div>'
    );
  }

  function renderResearchBoard() {
    function col(status, items) {
      var rows = items.map(function (item) {
        return '<div class="mi-rb-item mi-rb-' + status.cls.replace('mi-badge-', '') + '">' + item + '</div>';
      }).join('');
      return (
        '<div class="mi-rb-col">' +
          '<div class="mi-rb-col-head">' +
            badge(status) +
            '<span class="mi-rb-count">' + items.length + '</span>' +
          '</div>' +
          rows +
        '</div>'
      );
    }

    return card(
      cardHeader('Research Status Board', 'What we know, what we believe, what we need to find out') +
      '<div class="mi-rb-grid">' +
        col(S.VERIFIED,   researchBoard.verified)  +
        col(S.HYPOTHESIS, researchBoard.hypothesis) +
        col(S.RESEARCH,   researchBoard.research)   +
      '</div>'
    );
  }

  /* ── Mount ─────────────────────────────────────────────── */

  function mount() {
    var container = document.getElementById('market-intel-section');
    if (!container) return;

    /* Build the full Market Intel page */
    var html =
      renderSummary()       +
      renderPains()         +
      renderCategories()    +
      renderMatrix()        +
      renderPricing()       +
      renderPositioning()   +
      renderObjections()    +
      renderGTM()           +
      renderResearchBoard();

    /* Replace the single placeholder card with the multi-card layout */
    var section = container.parentElement;
    container.remove();

    var tmp = document.createElement('div');
    tmp.innerHTML = html;
    while (tmp.firstChild) {
      section.appendChild(tmp.firstChild);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }

}());
