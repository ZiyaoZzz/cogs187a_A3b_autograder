import React, { useState, useEffect } from "react";

const API_BASE = "http://localhost:8000";

interface PromptVersion {
  id: string;
  version: number;
  prompt: string;
  aiModel: string;
  critique?: string;
  timestamp: string;
  type?: "critic" | "designed" | "final";
  label?: string; // P0, P1, P2, P3, P4, Best Prompt
  refinementSummary?: string;
  refinementReport?: string;
  problemAnalysis?: string;
  strengthsSummary?: string;
  scoringTable?: string;
  bestPromptLabel?: string;
  reasoning?: string;
}

interface RefinementSession {
  id: string;
  originalPrompt: string;
  versions: PromptVersion[];
  currentVersion: number;
  status: "idle" | "critiquing" | "refining" | "completed";
  iterations?: number;
  scoringTable?: string;
  bestPromptLabel?: string;
  judgeReasoning?: string;
}

export default function PromptRefinementPage() {
  const [originalPrompt, setOriginalPrompt] = useState<string>("");
  const [session, setSession] = useState<RefinementSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [iterations, setIterations] = useState(2); // Number of critique rounds
  const [finalPrompt, setFinalPrompt] = useState<string>("");
  const [refinementReport, setRefinementReport] = useState<string>("");
  const [autoFilledFromImprove, setAutoFilledFromImprove] = useState(false);
  const [savingPrompt, setSavingPrompt] = useState(false);

  // Load current prompt from backend or from localStorage (if coming from Improve Prompt)
  useEffect(() => {
    // Check if there's a prompt saved from Improve Prompt page
    const savedPrompt = localStorage.getItem("promptForRefinement");
    if (savedPrompt) {
      setOriginalPrompt(savedPrompt);
      setAutoFilledFromImprove(true);
      // Clear it so it doesn't persist
      localStorage.removeItem("promptForRefinement");
    } else {
      loadCurrentPrompt();
    }
  }, []);

  const loadCurrentPrompt = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/get-current-prompt`);
      if (res.ok) {
        const data = await res.json();
        setOriginalPrompt(data.prompt || "");
      }
    } catch (err) {
      console.error("Failed to load current prompt:", err);
    }
  };

  const startRefinement = async () => {
    if (!originalPrompt.trim()) {
      setError("Please provide an original prompt to refine.");
      return;
    }

    setLoading(true);
    setError(null);
    setFinalPrompt("");
    setRefinementReport("");

    try {
      const res = await fetch(`${API_BASE}/api/start-prompt-refinement`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          originalPrompt,
          iterations,
        }),
      });

      if (!res.ok) {
        throw new Error("Failed to start refinement process");
      }

      const data = await res.json();
      setSession(data.session);
      
      // Start the critique loop (loading will be set to false in runCritiqueLoop's finally)
      await runCritiqueLoop(data.session.id);
    } catch (err: any) {
      setError(err.message || "Failed to start refinement");
      setLoading(false); // Only set false on error, otherwise runCritiqueLoop handles it
    }
  };

  const runCritiqueLoop = async (sessionId: string) => {
    try {
      // Round 1: Critic B critiques P0, generates P1
      setSession(prev => prev ? { ...prev, status: "critiquing" } : null);
      const critiqueRes1 = await fetch(`${API_BASE}/api/critique-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId,
          round: 1,
          step: "critic_b_round1",
        }),
      });

      if (!critiqueRes1.ok) {
        const errorData = await critiqueRes1.json().catch(() => ({}));
        throw new Error(errorData.detail || "Round 1: Critic B critique failed");
      }
      const critiqueData1 = await critiqueRes1.json();
      setSession(critiqueData1.session);
      await new Promise(resolve => setTimeout(resolve, 500));

      // Round 2: Designer A compares P0 and P1, synthesizes P2
      setSession(prev => prev ? { ...prev, status: "refining" } : null);
      const refineRes = await fetch(`${API_BASE}/api/refine-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId,
          round: 2,
          step: "designer_a_round2",
        }),
      });

      if (!refineRes.ok) {
        const errorData = await refineRes.json().catch(() => ({}));
        throw new Error(errorData.detail || "Round 2: Designer A synthesis failed");
      }
      const refineData = await refineRes.json();
      setSession(refineData.session);
      await new Promise(resolve => setTimeout(resolve, 500));

      // Round 3: Critic B reviews P2, generates P3 if extended mode
      if (iterations >= 2) {
        setSession(prev => prev ? { ...prev, status: "critiquing" } : null);
        const critiqueRes3 = await fetch(`${API_BASE}/api/critique-prompt`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sessionId,
            round: 3,
            step: "critic_b_round3",
          }),
        });

        if (!critiqueRes3.ok) {
          const errorData = await critiqueRes3.json().catch(() => ({}));
          throw new Error(errorData.detail || "Round 3: Critic B review failed");
        }
        
        const critiqueData3 = await critiqueRes3.json();
        setSession(critiqueData3.session);
        await new Promise(resolve => setTimeout(resolve, 500));

        // Round 4: Designer A synthesizes P2 and P3 (if extended mode)
        if (iterations >= 3) {
          setSession(prev => prev ? { ...prev, status: "refining" } : null);
          const refineRes4 = await fetch(`${API_BASE}/api/refine-prompt`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              sessionId,
              round: 4,
              step: "designer_a_round4",
            }),
          });

          if (!refineRes4.ok) {
            const errorData = await refineRes4.json().catch(() => ({}));
            throw new Error(errorData.detail || "Round 4: Designer A synthesis failed");
          }
          
          const refineData4 = await refineRes4.json();
          setSession(refineData4.session);
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      }

      // Final: Judge selects Best Prompt from all candidates
      setSession(prev => prev ? { ...prev, status: "refining" } : null);
      const finalRes = await fetch(`${API_BASE}/api/generate-final-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId }),
      });

      if (!finalRes.ok) {
        const errorData = await finalRes.json().catch(() => ({}));
        throw new Error(errorData.detail || "Final: Judge selection failed");
      }
      const finalData = await finalRes.json();
      setFinalPrompt(finalData.finalPrompt);
      setRefinementReport(finalData.refinementReport || "");
      setSession(prev => {
        if (!prev) return null;
        return {
          ...prev,
          status: "completed",
          ...finalData.session,
          scoringTable: finalData.scoringTable,
          bestPromptLabel: finalData.bestPromptLabel,
          judgeReasoning: finalData.judgeReasoning,
        };
      });
    } catch (err: any) {
      setError(err.message || "Refinement process failed");
      setSession(prev => prev ? { ...prev, status: "idle" } : null);
    } finally {
      setLoading(false);
    }
  };

  const exportPrompt = () => {
    if (!finalPrompt) {
      alert("No final prompt to export");
      return;
    }

    const blob = new Blob([finalPrompt], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `refined_prompt_${new Date().toISOString().split("T")[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = () => {
    if (!finalPrompt) {
      alert("No final prompt to copy");
      return;
    }
    navigator.clipboard.writeText(finalPrompt);
    alert("Prompt copied to clipboard!");
  };

  const savePromptToBackend = async () => {
    if (!finalPrompt) {
      alert("No final prompt to save");
      return;
    }

    setSavingPrompt(true);
    try {
      const res = await fetch(`${API_BASE}/api/save-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: finalPrompt }),
      });

      if (res.ok) {
        alert("Prompt saved to backend successfully! It will be used as the default prompt for future analyses.");
      } else {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to save prompt");
      }
    } catch (err: any) {
      alert(`Failed to save prompt: ${err.message}`);
    } finally {
      setSavingPrompt(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Prompt Refinement Pipeline</h1>
      <p className="text-sm text-slate-600 mb-6">
        Use AI-to-AI critique to iteratively improve your grading prompt. Each AI critiques the other's prompt,
        then both refine their prompts based on the critiques. Finally, a best prompt is synthesized.
      </p>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md">
          <div className="text-red-800 font-medium mb-2">Error</div>
          <div className="text-red-700 text-sm">{error}</div>
        </div>
      )}

      {autoFilledFromImprove && (
        <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-md">
          <div className="flex items-start gap-3">
            <svg className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <div className="text-green-800 font-medium mb-1">Auto-filled Improved Prompt</div>
              <div className="text-green-700 text-sm">
                The prompt below has been automatically filled with the improved prompt from the "Improve Prompt" feature. 
                You can now use this as the starting point for AI-to-AI refinement.
              </div>
            </div>
            <button
              onClick={() => setAutoFilledFromImprove(false)}
              className="text-green-600 hover:text-green-800"
              aria-label="Dismiss"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Input and Control */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Original Prompt
            </label>
            <textarea
              value={originalPrompt}
              onChange={(e) => setOriginalPrompt(e.target.value)}
              placeholder="Paste your current grading prompt here..."
              className="w-full h-64 px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-xs"
              disabled={loading || (session !== null && session.status !== "idle" && session.status !== "completed")}
            />
            <button
              onClick={loadCurrentPrompt}
              className="mt-2 text-xs text-slate-600 hover:text-slate-900"
            >
              Load Current Prompt from Backend
            </button>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Iterations (Critique Rounds)
            </label>
            <select
              value={iterations}
              onChange={(e) => setIterations(parseInt(e.target.value, 10))}
              disabled={loading || (session !== null && session.status !== "idle" && session.status !== "completed")}
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value={2}>Basic (P0→P1→P2→Judge)</option>
              <option value={3}>Extended (P0→P1→P2→P3→P4→Judge)</option>
            </select>
          </div>

          <button
            onClick={startRefinement}
            disabled={loading || !originalPrompt.trim() || (session !== null && session.status !== "idle" && session.status !== "completed")}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Processing..." : session?.status === "completed" ? "Start New Refinement Process" : "Start Refinement Process"}
          </button>

          {session && (
            <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-medium text-slate-700">Session Status</div>
                {(session.status === "completed" || session.status === "idle") && (
                  <button
                    onClick={() => {
                      setSession(null);
                      setFinalPrompt("");
                      setRefinementReport("");
                    }}
                    className="text-xs text-slate-600 hover:text-slate-900 underline"
                  >
                    Clear Session
                  </button>
                )}
              </div>
              <div className="text-xs text-slate-600 space-y-1">
                <div>Status: <span className="font-medium">{session.status}</span></div>
                <div>Versions: {session.versions.length}</div>
                <div>Versions Generated: {session.versions.length}</div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Version History and Final Prompt */}
        <div className="space-y-4">
          {session && session.versions.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Version History ({session.versions.length} versions)
              </label>
              <div className="space-y-2 max-h-64 overflow-y-auto border border-slate-200 rounded-md p-3 bg-slate-50">
                {session.versions.map((version) => (
                  <div key={version.id} className="p-2 bg-white rounded border border-slate-200 text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium">
                        {version.label || `V${version.version}`} ({version.aiModel})
                        {version.type === "critic" && " - Critic B"}
                        {version.type === "designed" && " - Designer A"}
                        {version.type === "final" && " - Judge"}
                      </span>
                      <span className="text-slate-500">
                        {new Date(version.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    {version.problemAnalysis && (
                      <div className="text-amber-700 mt-1 p-1 bg-amber-50 rounded text-xs max-h-20 overflow-y-auto">
                        <div className="font-medium mb-0.5">Problem Analysis:</div>
                        {version.problemAnalysis.substring(0, 200)}
                        {version.problemAnalysis.length > 200 && "..."}
                      </div>
                    )}
                    {version.critique && !version.problemAnalysis && (
                      <div className="text-amber-700 mt-1 p-1 bg-amber-50 rounded text-xs max-h-20 overflow-y-auto">
                        <div className="font-medium mb-0.5">Critique:</div>
                        {version.critique.substring(0, 200)}
                        {version.critique.length > 200 && "..."}
                      </div>
                    )}
                    {version.type === "designed" && (
                      <div className="text-slate-600 mt-1 text-xs space-y-1">
                        <div>Prompt length: {version.prompt.length} chars</div>
                        {version.refinementSummary && (
                          <div className="text-blue-700 mt-1 p-1 bg-blue-50 rounded text-xs">
                            <div className="font-medium mb-0.5">Design Summary:</div>
                            {version.refinementSummary}
                          </div>
                        )}
                        {version.strengthsSummary && (
                          <div className="text-green-700 mt-1 p-1 bg-green-50 rounded text-xs">
                            <div className="font-medium mb-0.5">Strengths:</div>
                            {version.strengthsSummary.substring(0, 150)}
                            {version.strengthsSummary.length > 150 && "..."}
                          </div>
                        )}
                      </div>
                    )}
                    {version.type === "final" && (
                      <div className="text-purple-600 mt-1 text-xs space-y-1">
                        {version.scoringTable && (
                          <div className="p-1 bg-purple-50 rounded">
                            <div className="font-medium mb-0.5">Scoring:</div>
                            <div className="text-xs whitespace-pre-wrap">{version.scoringTable.substring(0, 200)}</div>
                          </div>
                        )}
                        {version.bestPromptLabel && (
                          <div className="font-semibold">Selected: {version.bestPromptLabel}</div>
                        )}
                        {version.reasoning && (
                          <div className="text-xs italic">{version.reasoning.substring(0, 150)}...</div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {finalPrompt && (
            <div>
              {/* Judge's Scoring Table and Reasoning */}
              {session?.scoringTable && (
                <div className="mb-4 p-4 bg-indigo-50 border border-indigo-200 rounded-lg">
                  <h4 className="text-sm font-semibold text-indigo-900 mb-2">Judge's Scoring Table</h4>
                  <div className="text-xs text-indigo-800 whitespace-pre-wrap font-mono">{session.scoringTable}</div>
                  {session.bestPromptLabel && (
                    <div className="mt-2 text-sm font-semibold text-indigo-900">
                      Best Prompt Selected: {session.bestPromptLabel}
                    </div>
                  )}
                  {session.judgeReasoning && (
                    <div className="mt-2 text-sm text-indigo-700 italic">
                      {session.judgeReasoning}
                    </div>
                  )}
                </div>
              )}
              
              {/* Refinement Report */}
              {refinementReport && (
                <div className="mb-4 p-4 bg-purple-50 border border-purple-200 rounded-lg">
                  <h4 className="text-sm font-semibold text-purple-900 mb-2">AI Refinement Report</h4>
                  <div className="text-xs text-purple-800 whitespace-pre-wrap">{refinementReport}</div>
                </div>
              )}
              
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-slate-700">
                  Final Refined Prompt (Best Prompt Selected by Judge)
                </label>
                <div className="flex gap-2">
                  <button
                    onClick={copyToClipboard}
                    className="px-3 py-1 text-xs bg-slate-600 text-white rounded-md hover:bg-slate-700"
                  >
                    Copy
                  </button>
                  <button
                    onClick={exportPrompt}
                    className="px-3 py-1 text-xs bg-green-600 text-white rounded-md hover:bg-green-700"
                  >
                    Export
                  </button>
                  <button
                    onClick={savePromptToBackend}
                    disabled={savingPrompt}
                    className="px-3 py-1 text-xs bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Save this prompt permanently to backend (will be used as default for future analyses)"
                  >
                    {savingPrompt ? "Saving..." : "Save to Backend"}
                  </button>
                </div>
              </div>
              <textarea
                value={finalPrompt}
                readOnly
                className="w-full h-96 px-3 py-2 border border-slate-300 rounded-md bg-slate-50 font-mono text-xs"
              />
              <div className="mt-2 text-xs text-slate-500">
                Prompt length: {finalPrompt.length} characters
              </div>
            </div>
          )}

          {loading && session && (
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <div className="text-sm font-medium text-blue-900 mb-2">
                Processing...
              </div>
              <div className="text-xs text-blue-700">
                {session.status === "critiquing" && "AI models are critiquing each other's prompts..."}
                {session.status === "refining" && "AI models are refining their prompts based on critiques..."}
              </div>
              {session.versions.length > 0 && (
                <div className="mt-2 text-xs text-blue-600">
                  Completed: {session.versions.length} versions
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

