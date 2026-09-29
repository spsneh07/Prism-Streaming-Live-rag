# Frontend Customization Guide

This guide explains how to tweak the new AI dashboard UI.

## Where colors are defined
Colors are defined at the very top of `frontend/style.css` inside the `:root` block using CSS variables. 
- `--bg-app`: The very back layer color.
- `--bg-panel`: The color of the cards/panels.
- `--accent`: The primary blue color for buttons and highlights.
- `--wait`, `--ret`, `--sup`, `--bad`: The semantic colors used for Controller states (Wait, Retrieve, Suppress, Error).
Change any of these hex codes and the entire application will update instantly.

## Where typography is defined
Typography is also defined in `:root` inside `style.css`:
- `--font-sans`: Used for almost all text. It defaults to 'Inter' (fetched via Google Fonts in index.html).
- `--font-mono`: Used for session IDs, event timestamps, and chunk IDs to align numbers neatly.

## Where cards are defined
The dashboard layout is a CSS Grid.
Look for `.dashboard-grid` in `style.css`.
The physical HTML for the panels (like Controller Status, Trust & Grounding, Evidence) is in `frontend/index.html` inside `<main class="dashboard">`. 
Each panel is wrapped in a `<section class="panel">`. 

## Where demo controls are defined
The demo buttons are generated dynamically!
In `frontend/app.js`, the `loadScenarios()` function fetches the demo configuration from the backend (`GET /api/scenarios`) and creates a `<button>` for each scenario. It injects them into the `<div id="scenarioButtons">` div located in the `<nav class="demo-controls">` of `index.html`.

## Where API/SSE handling is defined
The communication with the backend happens inside `frontend/app.js`, primarily in the `runTurn(chunks, endT)` function.
- It uses `fetch` to POST to `/api/sessions/{sessionId}/turns`.
- It uses a `TextDecoder` and a `while` loop to read the Server-Sent Events stream chunk by chunk.
- It routes the parsed JSON data to the `render(ev)` function.

## How to add a new demo
You do NOT need to touch the frontend to add a new demo!
1. Open `configs/demo_scenarios.json` in the backend.
2. Add a new scenario object with a `title` and `turns` (which contain the text chunks).
3. The frontend `loadScenarios()` will automatically discover it and render a new button on the dashboard.

## How to change dashboard labels
If you want to change the text "Streaming Live RAG" or "Controller State" to something else:
1. Open `frontend/index.html`.
2. Look for the `<h2>` tags inside the `.panel-header` divs.
3. Edit the text directly. No build step is required. Just refresh the browser!
