# Product Shell Design Reference

## Goal
Use the attached dashboard only as a **visual/layout reference**, not as a domain reference. The design language is a **clean modern SaaS admin shell** that can be reused for your job-application platform.

The key idea is simple:
- a **fixed left sidebar** for stable navigation
- a **top utility bar** for account/actions
- a **card-based main content area**
- a **light, spacious, premium admin look**

---

## 1) Overall design style
The interface uses a **minimal B2B dashboard aesthetic**:
- light background
- white cards
- very soft borders
- rounded corners
- muted gray text for secondary information
- dark text for headings
- one primary accent color for active states and important numbers

It feels polished because it avoids clutter:
- lots of whitespace
- strong alignment
- consistent spacing
- very little visual noise
- icons are simple line icons

This should be treated as a **product shell design**, not a single dashboard.

---

## 2) Page layout structure
The screen is split into **two main regions**.

### Left sidebar
A fixed vertical navigation area on the left.

Suggested width:
- **240px to 260px**

Behavior:
- full height
- always visible on desktop
- contains logo at top
- navigation items stacked vertically
- active item shown with filled background and accent color
- lower section can contain upgrade/promo/help card if needed

### Main content area
The rest of the screen is the working area.

Structure:
- top utility/header row
- page title
- KPI cards row
- primary content cards below

Suggested behavior:
- `main` scrolls, sidebar stays fixed
- content max width should remain generous, but not edge-to-edge
- use padding around the content so it breathes

Suggested spacing:
- page padding: **24px to 32px**
- gap between cards: **20px to 24px**

---

## 3) Top bar design
At the top right of the main shell there is a utility area.

Typical items:
- theme toggle
- notifications icon
- user avatar
- user name / profile menu

Design notes:
- keep this lightweight
- no heavy colored header bar
- top bar should feel like floating utilities over a white canvas
- use small circular icon buttons with soft borders or subtle background

In your app this top bar can include:
- notification bell
- profile dropdown
- usage indicator
- quick action button like **New Application** or **Run Auto Apply** depending on page

---

## 4) Sidebar structure for your application
Use the same visual pattern as the reference, but replace the menu with your product sections.

Recommended order:
1. Overview
2. Auto Apply
3. Tailoring Studio
4. Job Tracker
5. Interview Prep
6. Library
7. Settings

### Sidebar item design
Each item should contain:
- small icon on the left
- label text
- optional badge/count on the right

Active item style:
- accent background fill
- white or very dark readable text depending on accent choice
- rounded rectangle shape

Inactive item style:
- transparent background
- muted text
- hover state with light gray background

HTML-wise, think of it like:
- `aside.app-sidebar`
- `div.sidebar-brand`
- `nav.sidebar-nav`
- `a.sidebar-link.active`

---

## 5) Visual hierarchy in the content area
The reference does a good job of showing hierarchy clearly.

Order of attention:
1. page title
2. top summary metrics
3. primary visualization / content block
4. recent records / table block

That same structure works for your app.

Example for **Overview**:
- page title: `Overview`
- KPI row: applications sent, interviews, response rate, active pipelines
- middle row: activity chart + upcoming interviews / action queue
- bottom row: recent applications table

This matches the exact product-ready structure you described.

---

## 6) KPI cards design
The screenshot uses a row of compact summary cards.

Each card contains:
- small label at the top
- large primary number/value
- supporting subtext below
- optional trend badge or percentage change
- optional overflow menu icon in top-right

Design characteristics:
- white background
- soft border
- rounded corners
- generous inner padding
- big number is the visual anchor

For your app, useful KPI cards are:
- Applications Sent
- Response Rate
- Interviews Scheduled
- Tailored Resumes Generated

HTML structure example:

```html
<section class="kpi-grid">
  <article class="kpi-card">
    <div class="kpi-card__header">
      <span class="kpi-card__label">Applications Sent</span>
      <button class="icon-button">...</button>
    </div>
    <h3 class="kpi-card__value">128</h3>
    <p class="kpi-card__meta">+12% vs last week</p>
  </article>
</section>
```

---

## 7) Primary chart / analytics card style
The large middle card in the reference is a classic analytics panel.

Structure:
- card header with title + description
- top-right filter control (date range / dropdown)
- large visualization area below

Even if you do not use charts heavily everywhere, the **card framing** is useful.

For your app, this same component can become:
- application activity over time
- pipeline stage movement
- auto-apply runs over time
- interview conversion trend

Design notes:
- chart should sit inside a wide card
- keep gridlines soft and subtle
- never overuse colors
- use one primary accent and one secondary contrast line
- card should have plenty of empty space so it feels premium

---

## 8) Table card design
The lower section in the reference uses a simple data table inside a card.

This is important for your **Job Tracker** and **Library** pages.

Visual pattern:
- card title at top
- table underneath
- clean header row
- thin separators
- no heavy zebra striping
- text left-aligned
- important values slightly darker/bolder

For **Job Tracker**, a table view could include:
- Company
- Role
- Location
- Source
- Status
- Last Update
- Next Action

Design notes:
- keep row height comfortable
- use status pills for stage labels
- keep actions on far right
- allow the table card to switch with kanban view on tracker page

---

## 9) Card system
The whole interface should be built around reusable cards.

A card should usually have:
- white background
- `border: 1px solid` very light gray
- `border-radius: 14px` to `18px`
- padding around `20px` to `24px`
- optional header row

Recommended reusable card types:
- KPI card
- chart card
- table card
- queue card
- settings card
- detail panel card
- preview card

This makes the design scalable and easy to implement in HTML templates.

---

## 10) Suggested color system
The reference uses a restrained palette.

Recommended token approach:

```text
Background:        #F6F7F9 or similar
Surface:           #FFFFFF
Border:            #E7E9EE
Primary text:      #1E2430
Secondary text:    #6B7280
Muted text:        #9AA3AF
Accent:            deep teal / green / blue-green
Success:           soft green
Warning:           amber
Danger:            soft red
```

You do not need to copy the exact colors. What matters is the balance:
- mostly neutral UI
- one accent color
- status colors used sparingly

---

## 11) Typography
The reference relies on clean sans-serif typography with clear size contrast.

Suggested hierarchy:
- app/page title: bold, large
- section title: medium-bold
- card labels: small and muted
- KPI values: large and bold
- body text: regular, quiet, readable

Suggested feel:
- no decorative fonts
- tight, product-focused typography
- strong readability over style experimentation

---

## 12) Border radius, spacing, and density
The UI feels modern because the spacing is disciplined.

Recommended values:
- sidebar padding: `20px`
- content padding: `24px` to `32px`
- card padding: `20px` to `24px`
- card radius: `16px`
- button radius: `10px` to `12px`
- grid gap: `20px` to `24px`

Design rule:
- prefer fewer, larger blocks over many tiny blocks
- avoid cramped dashboards

---

## 13) Suggested HTML shell structure
This is the main structural interpretation of the screenshot for HTML.

```html
<body>
  <div class="app-shell">
    <aside class="app-sidebar">
      <div class="sidebar-brand">Your Product</div>

      <nav class="sidebar-nav">
        <a class="sidebar-link active" href="#">Overview</a>
        <a class="sidebar-link" href="#">Auto Apply</a>
        <a class="sidebar-link" href="#">Tailoring Studio</a>
        <a class="sidebar-link" href="#">Job Tracker</a>
        <a class="sidebar-link" href="#">Interview Prep</a>
        <a class="sidebar-link" href="#">Library</a>
        <a class="sidebar-link" href="#">Settings</a>
      </nav>
    </aside>

    <main class="app-main">
      <header class="topbar">
        <div class="topbar__spacer"></div>
        <div class="topbar__actions">
          <button class="icon-button">Theme</button>
          <button class="icon-button">Alerts</button>
          <button class="profile-button">Ayman</button>
        </div>
      </header>

      <section class="page-header">
        <div>
          <h1>Overview</h1>
          <p>Track applications, tailoring progress, and interview readiness.</p>
        </div>
        <div>
          <button class="button button--primary">New Application</button>
        </div>
      </section>

      <section class="kpi-grid">
        <!-- KPI cards -->
      </section>

      <section class="content-grid">
        <article class="card card--chart"></article>
        <article class="card card--queue"></article>
      </section>

      <section class="card card--table">
        <!-- Recent applications table -->
      </section>
    </main>
  </div>
</body>
```

---

## 14) How to map this design to your product pages

### Overview
Use the closest visual match to the screenshot.

Layout:
- KPI row on top
- activity chart + queue/interview snapshot in middle
- recent applications at bottom

### Auto Apply
Keep same shell, but main content should focus on execution status.

Suggested sections:
- run summary cards
- active job sources / rules
- queue of jobs to apply to
- recent auto-apply runs and failures

### Tailoring Studio
This page should break from the pure dashboard feel and become more of a workspace.

Recommended layout:
- left panel: job description, tailoring rules, profile controls
- right panel: live resume/cover letter preview
- sticky action bar: generate, regenerate, export

### Job Tracker
This should feel operational.

Recommended layout:
- top filters bar
- table / kanban toggle
- main tracker list
- right drawer or modal for item details

### Interview Prep
This can still use cards, but more editorial blocks.

Recommended sections:
- company brief
- likely interview questions
- STAR stories
- answer drafts
- notes / prep checklist

### Library
Use a clean table/grid mix.

Suggested content:
- resumes
- cover letters
- generated outputs
- saved job descriptions
- reusable story bank

### Settings
Use grouped settings cards.

Suggested groups:
- profile
- model/config
- file paths
- usage/preferences
- integrations

---

## 15) Interaction design notes
The reference UI is calm because interactions are understated.

Use:
- subtle hover states
- light transitions
- dropdowns and pills instead of heavy modals where possible
- compact icon buttons for secondary actions
- one clear primary CTA per page

Avoid:
- too many bright colors
- too many charts on one screen
- mixing tracker, generator, analytics, and prep on the same page

---

## 16) Responsive behavior
On smaller screens:
- collapse sidebar into icon rail or drawer
- stack KPI cards into 2 columns or 1 column
- stack split content sections vertically
- tables should scroll horizontally

Desktop should remain the main target for this product since it is a productivity application.

---

## 17) Implementation mindset
The main takeaway from the reference is not the rental-specific widgets.
The real takeaway is this:

- stable app shell
- clear navigation
- card-based layout
- calm premium admin styling
- one responsibility per page

That is exactly the right direction for your application platform.

If you implement this in HTML/CSS, the goal should be to create a **reusable app shell** first, then drop each product section into that shell instead of treating everything like one dashboard page.

---

## 18) Final design summary
This design should be interpreted as:

> a modern, light-theme SaaS admin shell with a fixed left sidebar, minimal topbar, white content cards, soft borders, large KPI tiles, spacious analytics blocks, and clean data tables.

For your product, keep the visual language, but replace the rental dashboard content with:
- job application workflow management
- resume and cover letter tailoring
- tracking and follow-up operations
- interview preparation
- reusable content library

That will make the product feel polished, scalable, and sellable.
