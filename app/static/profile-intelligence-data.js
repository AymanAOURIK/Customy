/**
 * profile-intelligence-data.js
 *
 * Single source of truth for Profile Intelligence content.
 * All facts are grounded in candidate.yaml.
 * Role recommendations are inferred from demonstrated experience
 * and are explicitly framed as recommendations, not factual past roles.
 *
 * Structure is future-ready: swap `source: "static"` for `source: "api"`
 * and replace the payload when dynamic generation is added.
 */

(function () {
  "use strict";

  window.PROFILE_INTELLIGENCE = {
    meta: {
      source: "static",
      generated_at: "2026-04-09",
      version: "1.0.0",
    },

    /* ── Identity ─────────────────────────────────────────── */

    identity: {
      name: "Ayman AOURIK",
      initials: "AA",
      headline: "AI & Data Science Lead",
      summary:
        "AI & Data Lead with 4 years of experience. Builds systems that run in production and replace real human workload — not demos or prototypes. Leads engineers, owns the roadmap, and makes cost and accuracy tradeoffs that move the needle.",
      location: "Casablanca, Morocco",
      years_experience: 4,
      current_role: "AI & Data Science Lead",
      current_company: "Auto Dealers Digital",
      current_start: "2025-07",
      education: {
        degree: "Data Analysis and Mining Engineer",
        institution: "Mohammadia School of Engineering",
        year: 2022,
      },
      spoken_languages: ["English (Fluent)", "French (Fluent)", "Arabic (Native)"],
      top_skills: ["Python", "LangChain", "RAG", "SQL", "Docker", "LLM-as-Judge", "LoRA Fine-tuning", "XGBoost", "FastAPI", "Power BI"],
    },

    /* ── Original resume / base profile ──────────────────── */

    resume: {
      base_headline: "AI & Data Science Lead",
      total_roles: 3,
      career_span: "2022 – present",
      latest_role: "AI & Data Science Lead @ Auto Dealers Digital",
      strongest_proof_points: [
        "Intent-based LLM auto-responder: ~20K leads/month at 96% accuracy",
        "Zoom call intelligence: ~2,400 calls/week, ~60 hrs/week saved across 30 agents",
        "AI customer support: −15% agent workload, −25% ticket escalations",
        "CV pipeline replacement: $20K+ GPU cost avoided",
        "Web scraping + dedup pipeline: $15K+ vendor spend eliminated",
      ],
    },

    /* ── Capability map (strengths) ──────────────────────── */

    capabilities: [
      {
        title: "Production LLM Systems",
        icon: "cpu",
        description:
          "Shipped intent-based responders, call intelligence pipelines, and AI coordination agents at scale — 20K leads/month, 2,400 calls/week. Production-grade, not proof-of-concept.",
      },
      {
        title: "Cost-Driven AI Architecture",
        icon: "savings",
        description:
          "Repeatedly replaced expensive pipelines with leaner LLM-based approaches. Documented savings: $20K+ GPU costs, $15K+ vendor spend, $10K+ labeling costs across multiple projects.",
      },
      {
        title: "End-to-End Delivery",
        icon: "ship",
        description:
          "Owns full pipeline lifecycle: scoping, design, build, deployment. Not a modeling specialist — a delivery-focused AI lead who ships.",
      },
      {
        title: "Team Leadership & Roadmap",
        icon: "team",
        description:
          "Led cross-functional teams of 4–5 engineers. Owns AI roadmap, stakeholder communication, and AI-to-business translation at the leadership level.",
      },
      {
        title: "Data Engineering & Retrieval",
        icon: "data",
        description:
          "Built scraping, deduplication, synthetic data generation, and hybrid BM25+contextual RAG pipelines. Strong in both data acquisition and intelligent retrieval.",
      },
      {
        title: "Multi-modal & Document Intelligence",
        icon: "document",
        description:
          "Image segmentation pipelines (vehicles at scale), speech transcription via Deepgram, PDF intelligence, and multi-source document extraction with LangChain.",
      },
    ],

    /* ── Target roles (recommended — not factual past roles) */

    target_roles: [
      {
        title: "AI Engineering Lead",
        fit: "strong",
        fit_label: "Strong fit",
        rationale:
          "Direct match to current title. Production LLM systems + team leadership + roadmap ownership makes this the highest-confidence target.",
      },
      {
        title: "Head of AI / VP of AI",
        fit: "strong",
        fit_label: "Strong fit",
        rationale:
          "Best at Series A–C companies (10–200 person AI team). Leadership track record + cost-optimization framing is exactly what growth-stage companies hire for.",
      },
      {
        title: "LLM Platform Lead",
        fit: "strong",
        fit_label: "Strong fit",
        rationale:
          "Direct skill match: production LLM systems, cost architecture, multi-tool agent integration (Jira, Calendar, Notion, Deepgram). Strong technical IC + leadership blend.",
      },
      {
        title: "Senior AI/ML Engineer (IC)",
        fit: "good",
        fit_label: "Good fit",
        rationale:
          "Stack breadth (LangChain, RAG, LoRA, Deepgram, Docker, Airflow, XGBoost) enables strong IC positioning at companies that want a technical generalist who ships.",
      },
      {
        title: "AI Product Lead",
        fit: "good",
        fit_label: "Good fit",
        rationale:
          "AI-to-business translation skills and roadmap ownership position for technical product leadership at the AI layer — suited for companies where the AI lead doubles as product owner.",
      },
    ],

    /* ── Why these roles fit ──────────────────────────────── */

    role_fit_explanation: {
      headline: "Why these roles match your actual profile",
      intro:
        "These recommendations are grounded in documented production output — not buzzwords. Here's the fit logic:",
      points: [
        "Your current work is product-grade: 96% accuracy, 20K leads/month, 60hrs/week saved — these are production metrics that lead and head roles require.",
        "Team leadership of 4–5 engineers and AI roadmap ownership is direct evidence for Lead and Head roles, not just Senior IC.",
        "The cost-efficiency pattern ($40K+ in documented savings) is a rare and valued differentiator at scale-up companies where ROI justification matters.",
        "Stack breadth (LangChain + RAG + LoRA + Deepgram + Airflow + Docker) makes Senior IC roles accessible in parallel without competing with the Lead track.",
        "Fluent French and English opens EU/FR markets — a structural advantage most AI lead candidates don't have.",
      ],
    },

    /* ── Focus industries ─────────────────────────────────── */

    focus_industries: [
      {
        label: "B2B SaaS · Automation",
        note: "Core fit — workflow automation background translates directly.",
      },
      {
        label: "Customer Experience · CX Tech",
        note: "Freshdesk integration + AI support systems are a direct reference.",
      },
      {
        label: "Marketplaces · Automotive",
        note: "Current employer context; deep domain knowledge available.",
      },
      {
        label: "Enterprise AI Tooling",
        note: "Agent frameworks, PM coordination, document intelligence — strong match.",
      },
      {
        label: "Growth-Stage AI-Native (A–C)",
        note: "Best environment for Lead/Head track. Needs a builder, not a manager.",
      },
      {
        label: "Professional Services Automation",
        note: "PDF intelligence, call transcription, Zoom pipeline — direct proof points.",
      },
    ],

    /* ── Workflow guidance ────────────────────────────────── */

    workflow: {
      next_actions: [
        {
          priority: 1,
          action: "Apply to AI Engineering Lead and Head of AI roles at B2B SaaS companies with 50–500 employees",
          type: "apply",
        },
        {
          priority: 2,
          action: "Tailor resume for LLM Platform Lead roles — emphasize system scale metrics (20K leads/month, 2,400 calls/week)",
          type: "tailor",
        },
        {
          priority: 3,
          action: "Target companies in CX tech and marketplace verticals where the Freshdesk + call intelligence background lands directly",
          type: "target",
        },
        {
          priority: 4,
          action: "Identify 3–5 warm intro paths in EN/FR markets — French fluency opens EU companies that most AI leads can't reach",
          type: "network",
        },
        {
          priority: 5,
          action: "Keep at least one Senior IC application active per week as a parallel track to Lead/Head applications",
          type: "hedge",
        },
      ],

      followup_priorities: [
        "Applications to Head of AI or AI Lead roles where initial score ≥ 75 — follow up within 5 business days",
        "Interview invites from CX tech, marketplace, or automation companies — these are highest-fit verticals",
        "Any role at a Series B–C AI-native company — the growth-stage window for Lead track is now",
        "International roles in France or EU — FR language is a structural differentiator; pursue actively",
        "Roles specifying 'LLM Systems', 'AI Platform', or 'AI Lead' in the title — title match signals fit",
      ],

      interview_focus_areas: [
        {
          area: "Production LLM Architecture",
          note: "Be specific: 20K leads/month at 96% accuracy, 2,400 calls/week pipeline, 60hrs/week saved. Numbers make the story credible.",
        },
        {
          area: "Cost-Efficiency Decision Making",
          note: "The $40K+ documented savings across projects is rare. Walk through the build-vs-buy or LLM-vs-CV decisions that drove each saving.",
        },
        {
          area: "Team Leadership & Roadmap Ownership",
          note: "Cross-functional team of 4, AI roadmap, stakeholder communication. Frame decisions you owned end-to-end, not just contributions.",
        },
        {
          area: "Technical Depth: LLM Stack",
          note: "LangChain pipeline design, hybrid BM25+contextual RAG, LoRA fine-tuning rationale, LLM-as-Judge evaluation setup.",
        },
        {
          area: "Business Impact Translation",
          note: "Every project has a business outcome. Lead with the outcome (agent workload −15%, escalations −25%) before explaining the implementation.",
        },
      ],
    },
  };
})();
