# ActionCount Project Structure

This document provides a comprehensive overview of the ActionCount codebase, explaining the directory structure, key files, and the responsibilities of each component.

ActionCount is an AI-powered fitness tracking platform that uses computer vision (MediaPipe/ST-GCN) to analyze exercise form, count repetitions in real-time, and provide an AI coaching experience. It features a dual-interface architecture: a Streamlit application and a FastAPI-driven modern web frontend.

---

## 📁 Root Directory
The root directory contains configuration files and the primary project folders.

- **`.env`**: Stores environment variables (e.g., API keys, database credentials, secrets).
- **`.gitignore`**: Specifies intentionally untracked files that Git should ignore.
- **`README.md`**: The main project documentation and setup instructions.
- **`muscle_map.svg`**: An interactive SVG graphic used in the frontend/Streamlit app to visualize muscle engagement (heatmaps).
- **`backend/`**: Contains all Python server-side code, ML model wrappers, and the Streamlit application.
- **`frontend/`**: Contains the vanilla web frontend (HTML/CSS/JS) assets.
- **`data/`**: Stores local mock data or local JSON databases for chats, users, and workouts (acting as a local store alongside MongoDB).

---

## 💻 Backend (`/backend`)
The backend is written in Python and is responsible for video processing, machine learning inference, API endpoints, database operations, and the Streamlit interface.

### 📄 Core Application Files
- **`app.py`**: The Streamlit application entry point. Provides a comprehensive UI for live tracking, video uploading, dashboard analytics, and AI chat.
- **`endpoint.py`**: The FastAPI application. Serves RESTful endpoints to the vanilla frontend for user authentication, workout saving, metrics retrieval, and chatbot interactions.
- **`requirements.txt`**: Lists all Python dependencies required to run the backend.

### 🧮 Counters (`/backend/counters`)
Contains the logic for analyzing human pose landmarks and counting repetitions for specific exercises.
- **`BaseCounter.py`**: The base class defining the standard interface and shared logic (state machine, angle calculations) for all exercise counters.
- **`*Counter.py`** (e.g., `BicepCurlCounter.py`, `PushupCounter.py`, `SquatCounter.py`): Inherit from `BaseCounter`. Each file implements the specific biomechanical rules, angle thresholds, and state transitions to accurately count a specific exercise and provide real-time form feedback.

### 👁️ Detector (`/backend/detector`)
Handles raw pose estimation from images/video frames.
- **`PoseDetector.py`**: Wraps MediaPipe Pose (33-keypoint standard) or similar models to extract pose landmarks from frames efficiently, passing the data to the counters.

### 📷 Reader (`/backend/reader`)
Handles secondary computer vision tasks.
- **`code_reader.py`**: Utilizes YOLO object detection and `pyzbar` to detect and decode barcodes from video frames. This is designed for scanning gym equipment barcodes to automatically identify the exercise context.

### 🛠️ Utilities (`/backend/utils`)
Helper modules and core services used across the backend.
- **`db.py`**: Manages all database interactions (MongoDB). Handles user profiles, workout history persistence, and data retrieval for metrics.
- **`chatbot.py`**: Integrates with the Gemini LLM to provide the "AI Coach" functionality, analyzing user data to give customized fitness and dietary advice.
- **`session_manager.py`**: Handles user session lifecycle, JWT generation, and secure authentication flows (integrated with email-based auth).
- **`validation.py`**: Contains utility functions to validate incoming data requests.
- **`singleton.py`**: Implements the Singleton design pattern, likely used to ensure only one instance of the database client or ML model is loaded into memory.

### 📈 Logger (`/backend/logger`)
- **`metrics.py`**: Responsible for calculating, formatting, and logging user performance metrics and trends over time.

---

## 🌐 Frontend (`/frontend`)
The custom web interface for users who prefer a traditional web app over the Streamlit interface. It interacts heavily with `backend/endpoint.py`.

- **`index.html`**: The landing page introducing the platform.
- **`login.html`**: Handles user authentication (Sign In / Sign Up) via email.
- **`dashboard.html`**: The main user hub showing recent workouts, progress, and interactive visualizations.
- **`metrics.html`**: Detailed analytics page featuring longitudinal body metrics tracking and radar charts.
- **`chatbot.html`**: Dedicated interface for the Gemini-powered AI fitness coach.
- **`app.js`**: Core JavaScript logic handling API requests to the FastAPI backend, state management, and UI interactivity.
- **`styles.css`**: Vanilla CSS (and potentially Tailwind CSS) for global styling, responsive design, and UI aesthetics.
- **`css/` & `js/`**: Directories containing modularized stylesheets and supplementary JavaScript files.

---

## 💾 Data (`/data`)
Used for local data storage, caching, or mock data when the primary database is disconnected.
- **`chats/`**: Stores raw chat histories or logs from the AI Coach.
- **`workouts/`**: Stores local backups or cached workout session data.
- **`users.json`**: A local JSON file serving as a lightweight user database or fallback for user credentials and profiles.
