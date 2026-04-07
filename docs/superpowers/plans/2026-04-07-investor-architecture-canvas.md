# Investor Architecture Canvas Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an Obsidian canvas that explains XiHong ERP to investors through a visual architecture and decision-support graph.

**Architecture:** The canvas will use a central left-to-right flow for the data-to-decision path, with supporting trees for pain points, business modules, and investor value. Text stays short and node-sized so the result reads like a relationship map instead of a document.

**Tech Stack:** Obsidian Canvas JSON, Markdown text nodes

---

### Task 1: Lock the investor narrative

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-investor-architecture-canvas-design.md`
- Modify: `findings.md`

- [ ] Summarize the investor-facing story in one sentence.
- [ ] Confirm the main flow is `痛点 -> 数据 -> 指标 -> 决策 -> 价值`.
- [ ] Keep technical details only where they prove scalability or trustworthiness.

### Task 2: Draft the canvas node map

**Files:**
- Create: `docs/投资人架构与决策支撑.canvas`

- [ ] Define compact nodes for pain points.
- [ ] Define the central architecture chain.
- [ ] Define the A/B/C closed loop node.
- [ ] Define business capability tree nodes.
- [ ] Define management output and investor value nodes.

### Task 3: Validate the file

**Files:**
- Modify: `docs/投资人架构与决策支撑.canvas`

- [ ] Ensure the canvas is valid JSON.
- [ ] Ensure every node id used by edges exists.
- [ ] Ensure text stays compact enough for a visual explanation.

### Task 4: Handoff

**Files:**
- Modify: `progress.md`

- [ ] Record what was created.
- [ ] Prepare a short explanation of how to use and adjust the canvas in Obsidian.
