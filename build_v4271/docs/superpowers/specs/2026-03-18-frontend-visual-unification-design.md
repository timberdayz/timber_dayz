# Frontend Visual Unification Design

**Date:** 2026-03-18

## Goal

Unify the XiHong ERP frontend into one coherent PC-first product while preserving the strengths of existing dashboard pages and improving the efficiency of administrator-facing configuration and control pages.

## Key Decision

Adopt a dual-style system under one shared shell:
- dashboard and business overview pages use a modern data-platform style
- administrator and configuration pages use a high-density operations-console style
- both styles share one global layout, one token system, one navigation model, and one component grammar

## Why

The current frontend is functional, but it does not yet behave like one intentionally designed ERP product.

The codebase currently mixes:
- global tokens and ad hoc inline styling
- dashboard-style cards and control-panel-style forms without explicit page-family rules
- repeated page headers, inconsistent filter bars, and page-local layout decisions
- a global shell that is visually stable in some places and improvised in others

This creates three practical problems:
- visual inconsistency reduces trust and perceived quality
- admin pages are less efficient than they should be for heavy operators
- future frontend work will keep diverging unless page families and shell rules are made explicit

## Scope

In scope:
- global shell alignment for sidebar, header, content frame, footer, and page header behavior
- a shared frontend token system for color, spacing, radius, shadow, border, typography, and state colors
- explicit page-family definitions for dashboard pages vs administrator control pages
- reusable page sections for page headers, filter bars, KPI cards, tables, forms, and detail dialogs
- phased migration of the highest-value frontend pages

Out of scope:
- backend API redesign
- route or permission model redesign beyond visual/navigation clarity improvements
- a mobile-first redesign
- a full rewrite of already-successful business overview pages
- replacing Vue 3, Element Plus, Pinia, or Vite

## Product Direction

### Shared Product Tone

The product should feel:
- professional
- stable
- operationally credible
- data-driven
- efficient without feeling chaotic

The frontend should no longer look like many independently styled pages. It should feel like one ERP product with clear visual rules.

### Page Family A: Data Platform / Business Dashboards

This family is for:
- business overview
- analytics
- report summaries
- KPI and ranking dashboards

Style characteristics:
- more breathing room
- stronger card framing
- clearer visual grouping
- higher emphasis on KPIs, trends, rankings, and summary modules
- more modern presentation while remaining enterprise-safe

Primary intent:
- support reading, monitoring, comparison, and decision-making

Important constraint:
- existing strong pages such as `BusinessOverview.vue` should be preserved conceptually and refined rather than redesigned from scratch

### Page Family B: High-Density Operations Console

This family is for:
- target setting
- permissions
- account and role management
- system configuration
- maintenance and operational admin screens
- any page primarily used to configure, approve, or execute repeated management tasks

Style characteristics:
- denser information layout
- stronger table and form emphasis
- tighter spacing than dashboard pages
- less decorative card treatment
- more immediate action visibility

Primary intent:
- reduce operator effort
- shorten scan paths
- expose controls and state quickly

Important constraint:
- density must improve efficiency, not create clutter; hierarchy still needs to be explicit

## Global Shell Rules

One shell should serve both page families.

### Sidebar

The sidebar should:
- remain the primary navigation surface on PC
- use one visual language for group headers, active states, and submenu depth
- reduce visual noise in the current grouped navigation
- make current location clearer through stronger active indicators

The sidebar should not:
- visually compete with page content
- rely on color shifts alone to show state

### Header

The global header should:
- show stable page identity and context
- stop acting like a dashboard-specific toolbar on every route
- reserve global actions for truly global concerns such as account, notifications, and environment context

The global refresh pattern should change:
- page-local refresh belongs inside the page
- the shell should not expose one refresh action that implies universal meaning across all routes

### Page Header

Every page should use a standard page-header structure:
- page title
- short page description or context line when needed
- primary page actions
- optional secondary actions

This removes current duplication where some pages rely on the shell title while others build a completely separate hero/header block.

### Content Frame

The content frame should define:
- standard max-width behavior
- standard vertical rhythm
- standard section spacing
- consistent table and form container widths

This should replace the current mix of:
- inline width values
- page-specific spacing guesses
- repeated `padding: 20px`

## Design System Decisions

### Tokens

The token system should become the single visual source of truth for:
- primary and neutral colors
- semantic status colors
- spacing scale
- radius scale
- shadow scale
- typography sizes and weights
- border treatment

Raw hex values and page-level one-off gradients should be reduced sharply.

### Typography

Typography should separate:
- shell/navigation text
- page titles
- card titles
- body text
- dense table/form text

Dashboard pages may use more expressive title contrast, but admin pages should prioritize legibility and density discipline.

### Cards

Cards should split into explicit variants:
- dashboard-card
- panel-card
- compact-control-card

Today, one generic card idea is stretched across incompatible page types.

### Tables

Tables should adopt one ERP-friendly standard:
- consistent toolbar region
- standard density modes
- standard fixed-column treatment
- standard empty/loading states
- standard action-column behavior

Admin pages should default to the dense table variant.

### Forms And Dialogs

Admin forms should follow one compact control grammar:
- consistent label width
- grouped settings blocks
- stable action placement
- predictable helper text and warnings

Dialogs should use standard size tiers:
- compact
- detail
- wide

Hard-coded dialog widths should be replaced by shared dialog classes or props derived from the design system.

## Navigation And Information Hierarchy

Navigation should continue to use grouped menus, but with clearer intent:
- business reading and monitoring pages remain in data-oriented groups
- admin-only configuration pages are visually treated as operator tools
- current-page identity should be reinforced by both shell state and page header structure

This is not a route model rewrite. It is a hierarchy clarification and a visual cleanup of the current information architecture.

## Migration Strategy

Use phased migration, not a big-bang redesign.

### Wave 1: Shell And Tokens

Target files:
- `frontend/src/App.vue`
- `frontend/src/components/common/Header.vue`
- `frontend/src/components/common/GroupedSidebar.vue`
- `frontend/src/components/common/IcpFooter.vue`
- `frontend/src/assets/styles/variables.css`
- `frontend/src/assets/styles/base.css`
- `frontend/src/assets/erp-layout.css`

Deliverables:
- shared shell behavior
- revised visual tokens
- standard page frame
- standard header and content spacing

### Wave 2: Reference Pages

Target pages:
- `frontend/src/views/BusinessOverview.vue`
- `frontend/src/views/system/SystemConfig.vue`
- `frontend/src/views/InventoryManagement.vue`
- `frontend/src/views/SalesDashboard.vue`
- selected admin configuration pages after standards prove stable

Deliverables:
- one strong dashboard example
- one strong dense admin example
- one list-heavy management example
- one legacy dashboard aligned to the new system

### Wave 3: Broad Rollout

After the first wave proves stable:
- migrate additional dashboard pages to the data-platform family
- migrate additional admin/config pages to the operations-console family
- reduce remaining inline styling and one-off layout decisions

## Non-Breaking Constraint

This redesign should not make already-usable pages unusable.

The practical rule is:
- preserve working business behavior
- preserve route and permission behavior unless a change is explicitly approved
- preserve the conceptual success of strong pages such as the current business overview
- change presentation and structure incrementally, with page-by-page verification

## Risks And Trade-offs

### Risk: Over-standardizing dashboards

If dashboard pages are forced into the same density and structure as admin pages, they will lose readability.

Mitigation:
- keep explicit page-family rules
- use dashboards as summary-and-reading surfaces, not compact control panels

### Risk: Keeping too much of the old visual debt

If migration avoids touching shell and tokens first, page-level updates will remain inconsistent.

Mitigation:
- complete shell and token work before broad page migration

### Risk: Dense admin style becomes visually harsh

If density is pursued without hierarchy, admin pages will feel stressful rather than efficient.

Mitigation:
- preserve strong title, section, and action hierarchy
- use compact spacing with disciplined grouping, not visual compression everywhere

## Open Items For Implementation

- define the final neutral palette and accent behavior for both page families
- decide whether the global header keeps any page title responsibility or delegates fully to page headers
- define standard component classes or wrappers for page-header, filter-bar, dashboard-card, admin-panel, and dialog sizes
- identify the first administrator-only pages to serve as the dense-style reference set
