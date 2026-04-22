# ActionCount Personalization & History Tracking (Dual Implementation)

The goal is to enhance the existing ActionCount application with user authentication, personalized tracking, historical workout data, and AI-driven dietary planning. As requested, these features will be implemented in **both** the Streamlit app and the traditional HTML/CSS/JS frontend.

## Current Directory Structure & File Roles

Currently, the project is a hybrid of a legacy FastAPI/HTML stack and a new Streamlit implementation. 

*   `backend/app.py`: The main Streamlit application script containing the UI, WebRTC video processing logic, and routing. **(Primary entry point for Streamlit)**
*   `backend/endpoint.py`: The FastAPI entry point which handles the APIs for the web frontend.
*   `backend/PoseDetector.py`: The core MediaPipe pose estimation logic.
*   `backend/session_manager.py`: Session management for the FastAPI server.
*   `backend/counters/`: Contains the logic for counting reps for various exercises.
    *   `BaseCounter.py`: Abstract base class for exercise counters, providing common state machine logic.
    *   `*Counter.py`: Individual exercise logic files (e.g., `BicepCurlCounter.py`, `PushupCounter.py`).
*   `frontend/`: Contains the HTML/JS/CSS frontend implementation.
    *   `index.html`: The current tracker landing page.
    *   `app.js`: Connects to FastAPI WebSockets for live video and pose skeleton rendering.
    *   `styles.css`: Current base styles.
*   `requirements.txt`: Python dependencies.

## Separation of Concerns

### Backend Responsibilities (FastAPI in `endpoint.py` & Data Store)
- **Data Layer**: Manage persistent JSON storage for users (`data/users.json`), workouts (`data/workouts/<username>.json`), and chat history (`data/chats/<username>.json`).
- **Auth API**: `/api/auth/login`, `/api/auth/signup`
- **Profile API**: `/api/user/profile` (GET/POST for onboarding info)
- **Workout API**: `/api/workout/save` (POST reps/sets), `/api/workout/history` (GET calendar data), `/api/workout/stats` (GET monthly muscle aggregations)
- **Chatbot API**: `/api/chat` (POST message, returns Gemini response based on user profile context)

### Web Frontend (`frontend/`)
- Acts as a pure client calling the FastAPI endpoints.
- **Routing**: We will use **separate HTML files** for navigation.
- **Aesthetics**: Modern, dynamic design utilizing **TailwindCSS** for layout and styling, combined with custom CSS for rich animations (glassmorphism, smooth hover effects, slide-in panels).

### Streamlit Frontend (`backend/app.py`)
- Acts as a monolithic client using Streamlit widgets.
- It will read/write directly to the JSON data store.
- **Pages**: Login, Dashboard (Calendar + Stats), Live Tracking, Diet Chatbot.

---

## Proposed Changes: Backend (FastAPI & Data)

### 1. Data Models & Storage (`backend/models.py` & `backend/db.py`)
- Create standard Pydantic models for User, Workout, and Chat messages.
- Create a simple JSON-based database manager to handle read/writes to the `data/` directory.

### 2. Extending `endpoint.py`
- **Single File Architecture**: All new backend REST APIs will be exposed directly from the existing `endpoint.py` script to maintain a straightforward, monolithic API structure.
- Add routes for `/api/auth/login`, `/api/auth/signup`, `/api/user/profile`, `/api/workout/save`, `/api/workout/history`, and `/api/workout/stats` directly in `endpoint.py`.
- The `/api/chat` endpoint will utilize `langchain-google-genai` to initialize an agent with the user's saved profile (weight, target, dietary restrictions) and stream or return the response.

---

## Proposed Changes: Web Frontend (`frontend/`)

### 1. File Structure Update
```
frontend/
├── login.html        (Landing / Auth / Onboarding)
├── dashboard.html    (Calendar & Stats)
├── index.html        (The current live rep counter / Tracker)
├── chatbot.html      (Dietary AI)
├── css/
│   ├── main.css      (Tailwind directives & custom animations)
└── js/
    ├── api.js        (Centralized fetch calls)
    ├── auth.js
    ├── dashboard.js
    ├── tracker.js    (Adapted from current app.js)
    └── chat.js
```

### 2. Aesthetics & TailwindCSS Integration
- **Tailwind Framework**: Use TailwindCSS via CDN (or local build) for rapid UI development and consistent styling.
- **Theme**: Dark mode, vibrant accent colors (e.g., Tailwind's `emerald-500` for success, `indigo-500` for primary actions).
- **Animations**:
  - Extend Tailwind with custom keyframes in `main.css`: `fade-in-up`, `pulse`, `slide-in-right`.
  - Apply backdrop-filter classes (`backdrop-blur-md bg-white/5`) to achieve the glassmorphism aesthetic for stat cards.

### 3. Feature Implementations
- **Auth/Onboarding**: A sleek login card built with Tailwind that flips/transitions to a signup/onboarding form (asking for weight, height, age, target).
- **Dashboard**: A CSS Grid-based calendar styled with Tailwind. Clicking a date triggers a Tailwind modal showing the exercises done. A Chart.js canvas for the monthly muscle group distribution.
- **Chatbot**: A modern chat UI built with Tailwind utility classes, resembling iMessage/WhatsApp web, fetching AI responses from the backend.

---

## Proposed Changes: Streamlit Frontend (`app.py`)

- **State Management**: Use `st.session_state` to track the logged-in user.
- **Navigation**: Use `st.sidebar` to navigate between "Tracking", "Dashboard", and "Diet AI".
- **Dashboard**: Use `streamlit-calendar` for the calendar UI and `st.dialog` for the popup. Use `st.bar_chart` for muscle group stats.
- **Chatbot**: Use `st.chat_message` and `st.chat_input` connected to the same Langchain logic.

---

## User Review Required

> [!IMPORTANT]
> The plan now includes the current project structure at the top, and explicitly outlines the use of **TailwindCSS** and **separate HTML files** for the web frontend. If you approve of this final architecture, we can begin the implementation phase!
