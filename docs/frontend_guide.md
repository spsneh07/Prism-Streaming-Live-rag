# Frontend Guide

Welcome to the frontend of the Streaming Live RAG project! This guide explains how the user interface is built, how it communicates with the backend, and how to customize it.

## 1. What files make up the frontend
The entire frontend is built with pure, vanilla web technologies. There is no React, Angular, or build system (like Webpack or Vite) needed. 
It consists of just three files located in the `frontend/` directory:
- `index.html`: The structure and layout of the page.
- `style.css`: The visual design, colors, layout grids, and animations.
- `app.js`: The logic that connects to the backend and updates the HTML.

## 2. What each file does
- **`index.html`**: Contains the containers (like `<header>`, `<main>`, `<article>`) where the data will be injected. It defines the "Demo" buttons, the timeline area, the sub-queries list, and the final answer display area.
- **`style.css`**: Defines how everything looks. It uses CSS Variables (like `--bg`, `--accent`) at the top so you can easily change the color scheme. It also handles responsive layouts using CSS Grid.
- **`app.js`**: Contains JavaScript functions to:
  - Start a new session (`newSession()`)
  - Load the demo scenarios from the server (`loadScenarios()`)
  - Send the user's speech to the server and listen for real-time updates (`runTurn()`)
  - Update the screen whenever a new update arrives (`render()`)

## 3. How the page starts
When you visit `http://localhost:8000`, the FastAPI backend serves the `index.html` file. 
The browser then loads `style.css` and `app.js`. 
At the very bottom of `app.js`, it calls two functions: `newSession()` (to clear any old data and prepare a fresh session) and `loadScenarios()` (to fetch the demo configurations and create the numbered demo buttons at the top of the screen).

## 4. How it communicates with FastAPI
The frontend talks to the FastAPI backend using standard HTTP requests:
- **POST `/api/sessions`**: Creates a new, unique conversation session.
- **GET `/api/scenarios`**: Fetches the demo scenarios.
- **POST `/api/sessions/{id}/turns`**: Sends a "turn" (a piece of user speech) to the backend to be processed.

## 5. How streaming events reach the browser
Because this is a "Streaming Live" RAG, it doesn't wait for the whole answer to be ready before replying. 
When `app.js` calls `POST /api/sessions/{id}/turns`, the server responds with a continuous stream of text called **Server-Sent Events (SSE)**.
In `app.js`, the `runTurn()` function reads this stream as it arrives. Every time the server sends a new event (like `TRANSCRIPT_CHUNK` or `RETRIEVAL_STARTED`), `app.js` catches it and immediately passes it to the `render()` function to update the screen instantly.

## 6. How each demo scenario works
When you click a demo button (like "Early retrieval"), the `onclick` handler in `app.js`:
1. Resets the screen.
2. Loops through the predefined "chunks" of speech for that specific demo.
3. Feeds them into the `runTurn()` function exactly as if a user were speaking them into a microphone at a natural pace.

## 7. Where the UI gets its data
The UI does not store any data itself. All intelligence, searching, ranking, and answer generation happens on the FastAPI backend. The frontend simply takes the JSON events sent by the server and formats them into HTML.

## 8. Which API endpoints are called
- `POST /api/sessions`: Start session.
- `DELETE /api/sessions/{id}`: End session.
- `GET /api/scenarios`: Get demo configs.
- `POST /api/sessions/{id}/turns`: Send speech and get live stream.
- `GET /api/chunks/{id}`: Fetch the actual source text for a citation when the user clicks a citation button.

## 9. How I can modify text/layout/styles later
- **To change colors or fonts**: Open `style.css`. Look at the `:root` section at the very top. Changing `--accent` or `--bg` will instantly update the entire app.
- **To change where things are positioned**: Open `index.html` and move the `<article>` blocks around. The layout uses CSS Grid in `style.css` (`main { display: grid; ... }`), so it will automatically adapt.
- **To change the text of the events**: Open `app.js` and look inside the `render(ev)` function. You can change the HTML templates inside the backticks (` ` `) for any event type.
