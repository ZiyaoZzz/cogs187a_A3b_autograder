// src/App.tsx
import { Link, Route, Routes } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import UploadPage from "./pages/UploadPage";
import { JulianPagesPage } from "./pages/JulianPagesPage";
import LLMRecommendationsPage from "./pages/LLMRecommendationsPage";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b bg-white">
        <div className="mx-auto px-4 py-3 flex items-center justify-between">
          <Link to="/" className="text-sm font-semibold text-slate-900">
            COGS 187 Autograder
          </Link>
          <nav className="flex gap-4 text-sm">
            <Link to="/upload" className="text-slate-600 hover:text-slate-900">
              Grade PDF
            </Link>
            <Link
              to="/julian"
              className="text-slate-600 hover:text-slate-900"
            >
              Reference Site
            </Link>
            <Link
              to="/chatgpt-recommendations"
              className="text-slate-600 hover:text-slate-900"
            >
              LLM Recommendations
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Routes>
          <Route path="/julian" element={<JulianPagesPage />} />
          <Route
            path="/"
            element={
              <div className="mx-auto px-4 py-6">
                <HomePage />
              </div>
            }
          />
          <Route
            path="/upload"
            element={
              <div className="mx-auto px-4 py-6">
                <UploadPage />
              </div>
            }
          />
          <Route
            path="/chatgpt-recommendations"
            element={
              <div className="mx-auto px-4 py-6">
                <LLMRecommendationsPage />
              </div>
            }
          />
        </Routes>
      </main>

      <footer className="border-t bg-white">
        <div className="mx-auto px-4 py-3 text-xs text-slate-400">
          COGS 187 · LLM-based Heuristic Evaluation
        </div>
      </footer>
    </div>
  );
}
