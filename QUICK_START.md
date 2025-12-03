## Quick Start (Professor-Friendly)

Follow these steps to run the autograder locally without any manual setup.

### 1. Prerequisites
- **Node.js 18+** (https://nodejs.org/)
- **Python 3.10+**
- (Optional) **Git** if you plan to pull updates

### 2. Prepare the Environment
1. Open a terminal in this folder.
2. Run `npm install` once (or just run the main start command in step 3 and it will do this for you).
3. Copy `env.template` to `.env` (the `npm start` script will do this automatically on the first run) and paste your Gemini API key:
   ```bash
   cp env.template .env
   # then edit .env and set GEMINI_API_KEY=YOUR_REAL_KEY
   ```

### 3. Start Everything Automatically
```bash
npm start
```
This command:
1. Installs missing frontend dependencies.
2. Creates & populates a Python virtual environment, then installs backend dependencies from `requirements.txt`.
3. Ensures `.env` exists (copies `env.template` if needed).
4. Warns you if `GEMINI_API_KEY` is missing or still the placeholder.
5. Launches **both** backend (`http://localhost:8000`) and frontend (`http://localhost:5173`) using `concurrently`.

You can stop both servers with `Ctrl + C`.

### 4. Alternative Commands
If you prefer separate terminals:
- `npm run frontend` – starts the Vite dev server only.
- `npm run backend` – starts the FastAPI backend using the virtual environment (if present).
- `npm run dev:full` – runs both via `concurrently`, same as `npm start` but without the dependency checks.

### 5. Troubleshooting
| Symptom | Fix |
| --- | --- |
| `GEMINI_API_KEY not configured` | Open `.env` and paste the key your TA gave you, then restart `npm start`. |
| `python3: command not found` | Install Python 3.10+ or use pyenv/Anaconda; ensure `python3` is on your PATH. |
| `npm start` complains about permissions | If you're on macOS/Linux, run `chmod +x start.sh` once, then retry. |
| Port already in use | Close other apps using ports 5173 or 8000, or edit `vite.config.ts` / backend port settings. |

That’s it! Once you see “Frontend ready” and “Backend running” in the terminal, open http://localhost:5173 in your browser and start grading. 

