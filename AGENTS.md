# AGENTS.md

## 🚀 Project Overview
This repository contains a full-stack application for "Sheepshead." It consists of two main parts: a modern frontend built with Angular (TypeScript) and a backend API implemented using FastAPI/Python. The goal is to connect the user interface provided by the Angular client with the business logic exposed by the Python API.

## 🛠️ Tech Stack
*   **Frontend:** Angular (v21+), TypeScript, JavaScript. Dependencies managed via `npm`. Key libraries include `@angular/*` packages and Express for SSR functionality.
*   **Backend:** Python (FastAPI). Uses `uv` for virtual environment and dependency management.
*   **Package Managers/Tools:** `npm`, `pip`, `uv`.

## ⚙️ Setup Commands
To get a working development environment, follow these steps:

1.  **Get Environment Variables:** Obtain the required `.env` file from Caleb.
2.  **Backend Dependencies (API):** Install dependencies using `pip install uv`.
3.  **Start Backend Server:** Run the FastAPI application using `uv run fastapi dev`.
4.  **Frontend Dependencies (Angular):** Navigate to the `angular/` directory and install node modules (`npm install`).
5.  **Start Frontend Server:** Use `ng serve --open` from the root or within the `angular/` directory.

## 🏗️ Build, Test, and Lint Commands
### Angular Frontend
*   **Development Serve (Run):** `npm start` (or `ng serve --open`)
*   **Build Production Bundle:** `npm run build` (Generates optimized assets in `dist/`).
*   **Testing (Unit):** `ng test` (Runs unit tests using Vitest).
*   **E2e Testing:** `ng e2e` (End-to-end testing).

### Backend API
*   (No dedicated build/lint commands were found for the backend.)

## 📁 Project Structure Map
*   `angular/`: Contains all frontend source code. This is an Angular workspace with components, services, and modules defined in TypeScript.
*   `api/`: Houses the backend API logic, written in Python (FastAPI).
*   `.vscode/`: VS Code workspace configuration files.

## 🎨 Code Style Conventions
*   **Frontend:** Follows standard Angular conventions using TypeScript and RxJS patterns.
*   **Formatting:** Prettier is listed as a dependency (`devDependencies`), implying it should be used for code formatting consistency across the project.
*   **Naming:** Standard PascalCase/camelCase conventions are followed, typical of Angular development.

## 🧪 Testing Conventions
*   **Frameworks:** Angular utilizes **Vitest** (via `ng test`) for unit testing.
*   **Location:** Test files generally follow the pattern defined by the CLI and should be co-located or imported into the component/module being tested.

## 🔐 Environment Variables & Secrets
*   **Required Vars:** The backend requires an environment file (`.env`) to operate, containing necessary credentials (e.g., database URLs, external service keys).
*   **Example Location:** Look for example variable files provided by the team. *Note: No explicit secret examples were found in the codebase.*

## ⚠️ Gotchas / Non-obvious Things
1.  **Two-Part Execution:** The frontend and backend run independently. Both services must be started, and cross-service communication (like CORS) must be verified.
2.  **Dependency Management:** Use `npm` for Angular dependencies and `pip`/`uv` for Python dependencies.
3.  **API Backend Setup:** Initial setup requires obtaining the `.env` file from Caleb before running the API development server.