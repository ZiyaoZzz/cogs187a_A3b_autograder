import React, { useState, useEffect, useMemo, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import type {
  HeuristicExtractionPage,
  PageAnalysisWithOverride,
  OverrideRecord,
  ReviewerSubmission,
  AICorrection,
} from "../lib/types";

// Use the same API base as UploadPage
const API_BASE = "http://localhost:8000";

export default function ReviewerModePage() {
  const navigate = useNavigate();
  const [submission, setSubmission] = useState<ReviewerSubmission | null>(null);
  const [currentPageIndex, setCurrentPageIndex] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [availableJobs, setAvailableJobs] = useState<Array<{jobId: string; fileName?: string; createdAt?: string}>>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [showErrorReport, setShowErrorReport] = useState(false);
  const [errorReportComponent, setErrorReportComponent] = useState("");
  const [errorReportReason, setErrorReportReason] = useState("");
  const [errorReportCorrectedValue, setErrorReportCorrectedValue] = useState("");
  const [errorReportNotes, setErrorReportNotes] = useState("");
  const [corrections, setCorrections] = useState<AICorrection[]>([]);
  const [showPromptImprovement, setShowPromptImprovement] = useState(false);
  const [improvedPrompt, setImprovedPrompt] = useState("");
  const [promptModificationNotes, setPromptModificationNotes] = useState("");
  const [generatingPrompt, setGeneratingPrompt] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [showFlagAdded, setShowFlagAdded] = useState(false);
  const autoSavedPages = useRef<Set<string>>(new Set());

  useEffect(() => {
    loadAvailableJobs();
  }, []);

  const loadAvailableJobs = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/list-jobs`);
      if (!res.ok) {
        // If endpoint doesn't exist, try to get from localStorage
        const stored = localStorage.getItem("recentJobIds");
        if (stored) {
          const jobs = JSON.parse(stored);
          setAvailableJobs(jobs);
          if (jobs.length > 0) {
            setSelectedJobId(jobs[0].jobId);
            loadSubmission(jobs[0].jobId);
          }
        }
        return;
      }
      const data = await res.json();
      setAvailableJobs(data.jobs || []);
      if (data.jobs && data.jobs.length > 0) {
        setSelectedJobId(data.jobs[0].jobId);
        loadSubmission(data.jobs[0].jobId);
      }
    } catch (err: any) {
      // Backend might not be running
      const errorMsg = err.message || "Failed to load jobs";
      if (errorMsg.includes("fetch") || errorMsg.includes("Failed to fetch") || err.name?.includes("TypeError")) {
        // Network error - backend is likely not running
        setError("Backend server is not running. Please start it:\n1. Run: npm start\n2. Or manually: cd backend && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000");
      } else {
        setError(errorMsg);
      }
      // Try localStorage as fallback
      const stored = localStorage.getItem("recentJobIds");
      if (stored) {
        try {
          const jobs = JSON.parse(stored);
          setAvailableJobs(jobs);
          if (jobs.length > 0) {
            setSelectedJobId(jobs[0].jobId);
            loadSubmission(jobs[0].jobId);
          }
        } catch (parseErr) {
          // Ignore parse errors
        }
      }
    }
  };

  const loadSubmission = async (jobId: string) => {
    setLoading(true);
    setError(null);
    try {
      // Load pages from extraction result
      const pagesRes = await fetch(`${API_BASE}/api/get-extraction-result?jobId=${jobId}`);
      if (!pagesRes.ok) {
        if (pagesRes.status === 0 || pagesRes.status === 500) {
          throw new Error("Cannot connect to backend server. Please ensure the backend service is running (http://localhost:8000)");
        }
        throw new Error(`Failed to load pages: ${pagesRes.statusText}`);
      }

      const pagesData = await pagesRes.json();
      
      // Load analysis results
      const analysisRes = await fetch(`${API_BASE}/api/get-analysis-results?jobId=${jobId}`);
      let analysisResults: PageAnalysisWithOverride[] = [];
      
      if (analysisRes.ok) {
        const analysisData = await analysisRes.json();
        analysisResults = analysisData.results || [];
      } else {
      }

      // Load overrides
      const overridesRes = await fetch(`${API_BASE}/api/get-overrides?jobId=${jobId}`);
      let overrides: OverrideRecord[] = [];
      
      if (overridesRes.ok) {
        const overridesData = await overridesRes.json();
        overrides = overridesData.overrides || [];
      }

      // Merge overrides into analysis results
      const analysisWithOverrides = analysisResults.map((result) => {
        const pageOverrides = overrides.filter((o) => o.pageNumber === result.page_number);
        return {
          ...result,
          overrides: pageOverrides,
          hasOverrides: pageOverrides.length > 0,
        };
      });

      setSubmission({
        jobId,
        fileName: pagesData.fileName,
        createdAt: pagesData.createdAt || new Date().toISOString(),
        pages: pagesData.pages || [],
        analysisResults: analysisWithOverrides,
        totalOverrides: overrides.length,
      });

      // Load corrections
      await loadCorrections(jobId);

      // Save to localStorage for future use
      const recentJobs = availableJobs.length > 0 ? availableJobs : [];
      const jobExists = recentJobs.some(j => j.jobId === jobId);
      if (!jobExists) {
        recentJobs.unshift({ jobId, fileName: pagesData.fileName, createdAt: pagesData.createdAt });
        localStorage.setItem("recentJobIds", JSON.stringify(recentJobs.slice(0, 10))); // Keep last 10
      }
    } catch (err: any) {
      const errorMsg = err.message || "Failed to load submission";
      // Only show error if it's not a network/fetch error
      if (!errorMsg.includes("fetch") && !errorMsg.includes("Failed to fetch") && !err.name?.includes("TypeError")) {
        setError(errorMsg);
      } else {
        // For network errors, just log and don't show error message
        setError(null); // Clear any previous errors
      }
    } finally {
      setLoading(false);
    }
  };

  const saveOverride = async (
    pageNumber: number,
    field: string,
    originalValue: any,
    overrideValue: any,
    notes?: string
  ): Promise<void> => {
    if (!submission) {
      return;
    }
    
    // For auto-saves, check backend availability and suppress errors
    if (notes && notes.includes("Auto-set:")) {
      // Silently skip if backend is not available
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1000);
        await fetch(`${API_BASE}/api/list-jobs`, { 
          method: "GET", 
          signal: controller.signal 
        });
        clearTimeout(timeoutId);
      } catch (err) {
        // Silently skip auto-save if backend is not available
        return;
      }
    }

    setSaving(true);
    try {
      const override: Omit<OverrideRecord, "id" | "timestamp"> = {
        jobId: submission.jobId,
        pageNumber,
        field,
        originalValue,
        overrideValue,
        reviewerName: "Reviewer",
        reviewerNotes: notes,
      };

      const res = await fetch(`${API_BASE}/api/save-override`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(override),
      });

      if (!res.ok) {
        const errorText = await res.text().catch(() => "Failed to save override");
        throw new Error(errorText);
      }

      const savedOverride = await res.json();

      // Update local state immediately for real-time display
      const updatedResults = submission.analysisResults.map((result) => {
        if (result.page_number === pageNumber) {
          const existingOverrides = result.overrides || [];
          // Check if this override already exists to avoid duplicates
          const overrideExists = existingOverrides.some(
            (o) => o.field === field && o.originalValue === originalValue && o.overrideValue === overrideValue
          );
          
          if (!overrideExists) {
            return {
              ...result,
              overrides: [...existingOverrides, savedOverride.override],
              hasOverrides: true,
            };
          } else {
            // Update existing override
            return {
              ...result,
              overrides: existingOverrides.map(o => 
                (o.field === field && o.originalValue === originalValue && o.overrideValue === overrideValue)
                  ? savedOverride.override
                  : o
              ),
              hasOverrides: true,
            };
          }
        }
        return result;
      });

      const totalOverridesCount = updatedResults.reduce((sum, result) => {
        return sum + (result.overrides?.length || 0);
      }, 0);

      const updatedSubmission: ReviewerSubmission = {
        ...submission,
        pages: [...submission.pages],
        analysisResults: [...updatedResults],
        totalOverrides: totalOverridesCount,
      };
      
      setSubmission(updatedSubmission);
      
      // Update corrections from overrides with notes (excluding auto-set)
      const autoSetKeywords = ["Auto-set:", "auto-set:", "Auto-generated", "auto-generated"];
      const overridesWithNotes = updatedResults
        .flatMap(r => (r.overrides || []).map(o => ({ ...o, _pageNumber: r.page_number })))
        .filter(o => o.reviewerNotes?.trim() && !autoSetKeywords.some(k => o.reviewerNotes.includes(k)));
      
      const newCorrections = overridesWithNotes.map((o, idx) => ({
        id: o.id || `correction_${Date.now()}_${idx}`,
        jobId: submission.jobId,
        pageNumber: o.pageNumber ?? o._pageNumber ?? 0,
        component: o.field.split('.')[1] || o.field,
        reason: `TA override: Changed ${o.field}`,
        originalValue: o.originalValue,
        correctedValue: o.overrideValue,
        reviewerNotes: o.reviewerNotes,
        timestamp: o.timestamp || new Date().toISOString(),
      } as AICorrection));
      
      setCorrections(newCorrections);
      setRefreshTrigger(prev => prev + 1);
      
      // Show flag added notification if notes were provided (creates a risk flag)
      if (notes && notes.trim() && !notes.includes("Auto-set:") && !notes.includes("auto-set:")) {
        setShowFlagAdded(true);
        // Hide notification after 3 seconds
        setTimeout(() => {
          setShowFlagAdded(false);
        }, 3000);
      }
      
      // Refresh from backend in background to sync
      setTimeout(() => {
        loadCorrections(submission.jobId, true).catch(() => {});
      }, 1000);
    } catch (err: any) {
      // Only show error if it's not a network error
      if (!err.message?.includes("fetch") && !err.message?.includes("Failed to fetch") && !err.name?.includes("TypeError")) {
        setError(err.message || "Failed to save override");
      } else {
        // For network errors, just log and don't show error
      }
    } finally {
      setSaving(false);
    }
  };

  const currentPage = submission?.pages[currentPageIndex];
  // Try to match by page_number (from analysis) with pageNumber (from extraction) or page_number (from extraction)
  // Use refreshTrigger to force recalculation when overrides change
  const currentAnalysis = useMemo(() => {
    if (!submission || !currentPage) return undefined;
    const pageNum = currentPage?.pageNumber || (currentPage as any)?.page_number;
    return submission.analysisResults.find(r => r.page_number === pageNum);
  }, [submission, currentPage, refreshTrigger]);

  const loadCorrections = async (jobId: string, mergeWithLocal: boolean = false) => {
    try {
      const res = await fetch(`${API_BASE}/api/get-corrections?jobId=${jobId}`);
      if (res.ok) {
        const data = await res.json();
        const correctionsList = data.corrections || [];
        // Ensure all corrections have pageNumber
        const validCorrections = correctionsList.map((c: AICorrection) => ({
          ...c,
          pageNumber: c.pageNumber ?? 0, // Fallback to 0 if missing
        }));
        
        if (mergeWithLocal) {
          // Merge with existing corrections, avoiding duplicates
          setCorrections(prev => {
            const existingIds = new Set(prev.map((c: AICorrection) => c.id));
            const newOnes = validCorrections.filter((c: AICorrection) => !existingIds.has(c.id));
            return [...prev, ...newOnes];
          });
        } else {
          setCorrections(validCorrections);
        }
      }
    } catch (err) {
      // Silently handle network errors
    }
  };

  const reportAIError = async (component: string, reason: string, originalValue: any, correctedValue: any, notes: string) => {
    if (!submission || !currentAnalysis || !currentPage) return;

    try {
      const res = await fetch(`${API_BASE}/api/report-ai-error`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jobId: submission.jobId,
          pageNumber: currentPage.pageNumber,
          component,
          reason,
          originalValue,
          correctedValue,
          reviewerNotes: notes,
        }),
      });

      if (res.ok) {
        await loadCorrections(submission.jobId);
        setShowErrorReport(false);
        setErrorReportComponent("");
        setErrorReportReason("");
        setErrorReportCorrectedValue("");
        setErrorReportNotes("");
        alert("AI error reported successfully!");
      } else {
        throw new Error("Failed to report AI error");
      }
    } catch (err: any) {
      setError(err.message || "Failed to report AI error");
    }
  };

  const generateImprovedPrompt = async () => {
    if (!submission || corrections.length === 0) return;
    
    setGeneratingPrompt(true);
    setError(null);
    
    try {
      // Collect page images and score changes for corrections
      const correctionsWithImages = corrections.map(correction => {
        // Find the page that matches this correction
        const matchingPage = submission.pages.find(p => p.pageNumber === correction.pageNumber);
        const pageImage = matchingPage ? ((matchingPage as any).imageBase64 || (matchingPage as any).image_base64) : null;
        
        return {
          ...correction,
          pageImage: pageImage, // Include page image if available
        };
      });

      const res = await fetch(`${API_BASE}/api/generate-prompt-from-corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          limit: 50,
          corrections: correctionsWithImages,
          // Include score change details
          scoreChanges: corrections.map(c => ({
            pageNumber: c.pageNumber,
            component: c.component,
            originalValue: c.originalValue,
            correctedValue: c.correctedValue,
            change: `${c.originalValue} → ${c.correctedValue}`,
            notes: c.reviewerNotes,
          })),
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setImprovedPrompt(data.improvedPrompt);
        setPromptModificationNotes(data.modificationNotes || "");
        setShowPromptImprovement(true);
      } else {
        throw new Error("Failed to generate improved prompt");
      }
    } catch (err: any) {
      setError(err.message || "Failed to generate improved prompt");
    } finally {
      setGeneratingPrompt(false);
    }
  };

  const exportSubmission = () => {
    if (!submission) return;

    const exportData = {
      jobId: submission.jobId,
      fileName: submission.fileName,
      createdAt: submission.createdAt,
      totalPages: submission.pages.length,
      totalOverrides: submission.totalOverrides || 0,
      totalCorrections: corrections.length,
      analysisResults: submission.analysisResults,
      corrections: corrections,
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `review_${submission.jobId}_${new Date().toISOString().split("T")[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getEffectiveValue = useMemo(() => {
    return (field: string, defaultValue: any): any => {
      if (!currentAnalysis?.overrides) return defaultValue;
      
      const override = currentAnalysis.overrides.find((o) => o.field === field);
      return override ? override.overrideValue : defaultValue;
    };
  }, [currentAnalysis]);

  return (
    <>
      {/* Full-screen success notification for flag added */}
      {showFlagAdded && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 backdrop-blur-sm">
          <div className="bg-white rounded-lg shadow-2xl p-8 max-w-md w-full mx-4 transform transition-all">
            <div className="flex flex-col items-center text-center">
              <div className="mb-4">
                <svg className="w-16 h-16 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              </div>
              <h3 className="text-2xl font-bold text-green-800 mb-2">Flag Added Successfully!</h3>
              <p className="text-slate-600 mb-6">The page has been flagged and added to AI Risk Flags.</p>
              <button
                onClick={() => setShowFlagAdded(false)}
                className="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}

    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 mb-4">Reviewer Mode</h1>
        
        <div className="flex gap-4 items-end mb-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Select Submission
            </label>
            <select
              value={selectedJobId}
              onChange={(e) => {
                setSelectedJobId(e.target.value);
                if (e.target.value) {
                  loadSubmission(e.target.value);
                }
              }}
              disabled={loading || availableJobs.length === 0}
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {availableJobs.length === 0 ? (
                <option value="">No submissions available</option>
              ) : (
                availableJobs.map((job) => (
                  <option key={job.jobId} value={job.jobId}>
                    {job.fileName || job.jobId} {job.createdAt ? `(${new Date(job.createdAt).toLocaleDateString()})` : ""}
                  </option>
                ))
              )}
            </select>
          </div>
          <button
            onClick={loadAvailableJobs}
            disabled={loading}
            className="px-4 py-2 bg-slate-600 text-white rounded-md hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Refresh
          </button>
        </div>

        {submission && (
          <div className="flex items-center justify-between">
            <div className="text-sm text-slate-600">
              <span className="font-medium">File:</span> {submission.fileName || "N/A"} ·{" "}
              <span className="font-medium">Pages:</span> {submission.pages.length}{" "}
              {corrections.length > 0 && (
                <> · <span className="font-medium">Overrides:</span> {corrections.length}</>
              )}
            </div>
            <div className="flex gap-2">
              <button
                onClick={generateImprovedPrompt}
                disabled={corrections.length === 0 || generatingPrompt}
                className="px-3 py-1.5 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                title={`Generate improved prompt from ${corrections.length} correction(s) (auto-collected from overrides)`}
              >
                {generatingPrompt ? (
                  <>
                    <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Generating...
                  </>
                ) : (
                  `Improve Prompt (${corrections.length})`
                )}
              </button>
              <button
                onClick={exportSubmission}
                disabled={!submission}
                className="px-3 py-1.5 text-sm bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Export Review
              </button>
            </div>
          </div>
        )}


        {/* AI Flags & Risk Pages (User-manually-marked) - Use corrections data directly */}
        {corrections.length > 0 && (
          <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-amber-900">
                ⚠️ AI Risk Flags ({corrections.length} corrections)
              </h3>
            </div>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {corrections.map((correction) => {
                // Format component name (e.g., "violation_quality" -> "Violation Quality")
                const componentName = correction.component
                  .replace(/_/g, " ")
                  .replace(/\b\w/g, (l) => l.toUpperCase());
                
                return (
                  <div
                    key={correction.id}
                    className="text-xs bg-white p-2 rounded border border-amber-200 cursor-pointer hover:bg-amber-100"
                    onClick={() => {
                      const pageIndex = submission?.pages.findIndex(p => p.pageNumber === correction.pageNumber) ?? -1;
                      if (pageIndex >= 0) setCurrentPageIndex(pageIndex);
                    }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">

                        <span className="font-medium text-amber-800">{componentName}</span>
                      </div>
                      {correction.timestamp && (
                        <span className="text-xs text-amber-600">
                          {new Date(correction.timestamp).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                    <div className="text-amber-800 mb-1">
                      <span className="font-medium">Score:</span>{" "}
                      <span className="line-through text-amber-600">{correction.originalValue}</span>{" "}
                      <span className="font-semibold">→ {correction.correctedValue}</span>
                    </div>
                    {correction.reviewerNotes && (
                      <div className="mt-1 text-amber-700 text-xs italic border-l-2 border-amber-300 pl-2">
                        {correction.reviewerNotes}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Bonus Scores - Assignment Summary */}
        {submission && (() => {
          // Bonus scores are assignment-level, not page-level
          // Find the page with bonus scores (usually only one page has them, or take the first one)
          // If multiple pages have bonus scores, take the maximum value for each
          const bonusScores: { [key: string]: { original: number; current: number; max: number; hasOverride: boolean; pageNumber: number; comment: string } } = {};
          
          submission.analysisResults.forEach((result) => {
            if (result.bonus_scores && !result.skip_analysis) {
              Object.entries(result.bonus_scores).forEach(([key, score]) => {
                // Get effective value (with override if exists)
                const override = result.overrides?.find(o => o.field === `bonus_scores.${key}.points`);
                const effectivePoints = override ? override.overrideValue : score.points;
                const hasOverride = !!override;
                
                // For assignment-level bonus, take the maximum value across all pages
                // (in case multiple pages have bonus scores, we want the highest)
                if (!bonusScores[key]) {
                  bonusScores[key] = {
                    original: score.points,
                    current: effectivePoints,
                    max: score.max,
                    hasOverride: hasOverride,
                    pageNumber: result.page_number,
                    comment: score.comment || ""
                  };
                } else {
                  // Take maximum if multiple pages have bonus scores
                  if (score.points > bonusScores[key].original) {
                    bonusScores[key].original = score.points;
                    bonusScores[key].pageNumber = result.page_number;
                    bonusScores[key].comment = score.comment || "";
                  }
                  if (effectivePoints > bonusScores[key].current) {
                    bonusScores[key].current = effectivePoints;
                  }
                  if (hasOverride) {
                    bonusScores[key].hasOverride = true;
                  }
                }
              });
            }
          });
          
          const hasBonusScores = Object.keys(bonusScores).length > 0;
          
          return hasBonusScores ? (
            <div className="mt-4 p-4 bg-purple-50 border border-purple-200 rounded-lg">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-purple-900">
                  ✨ Bonus Scores (Assignment Level)
                </h3>
              </div>
              <div className="space-y-3">
                {Object.entries(bonusScores).map(([key, scoreData]) => {
                  const displayLabel = key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
                  
                  // Find the page with this bonus score for editing
                  const pageWithBonus = submission.analysisResults.find(r => 
                    r.page_number === scoreData.pageNumber && 
                    r.bonus_scores && 
                    r.bonus_scores[key]
                  );
                  
                  const pageBonusScore = pageWithBonus?.bonus_scores?.[key];
                  const pageOverride = pageWithBonus?.overrides?.find(o => o.field === `bonus_scores.${key}.points`);
                  
                  return (
                    <div key={key} className="bg-white border border-purple-200 rounded-lg p-3">
                      <EditableScoreField
                        key={`${key}_assignment_${scoreData.hasOverride ? 'modified' : 'original'}_${refreshTrigger}`}
                        label={displayLabel}
                        points={scoreData.current}
                        max={scoreData.max}
                        originalPoints={scoreData.original}
                        comment={pageBonusScore?.comment || scoreData.comment}
                        field={`bonus_scores.${key}.points`}
                        pageNumber={scoreData.pageNumber}
                        onSave={(value, notes) => {
                          if (pageWithBonus) {
                            saveOverride(
                              scoreData.pageNumber,
                              `bonus_scores.${key}.points`,
                              pageBonusScore?.points || scoreData.original,
                              value,
                              notes
                            );
                          }
                        }}
                        hasOverride={scoreData.hasOverride}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null;
        })()}
      </div>

      {error && !error.includes("fetch") && !error.includes("Failed to fetch") && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md">
          <div className="text-red-800 font-medium mb-2">Error</div>
          <div className="text-red-700 text-sm whitespace-pre-line">{error}</div>
        </div>
      )}

      {submission && currentPage && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: PDF Page - Detailed View */}
          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <div className="flex justify-between items-center mb-4">
              <div>
                {currentAnalysis && (
                  <div className="text-xs text-slate-500">
                    {currentAnalysis.skip_analysis ? (
                      <span className="text-amber-600">Skipped</span>
                    ) : (
                      <span className="text-green-600">Analyzed</span>
                    )}
                    {currentAnalysis.hasOverrides && (
                      <span className="ml-2 text-blue-600">• Has Overrides</span>
                    )}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setCurrentPageIndex(Math.max(0, currentPageIndex - 1))}
                  disabled={currentPageIndex === 0}
                  className="px-3 py-1 text-sm border border-slate-300 rounded hover:bg-slate-50 disabled:opacity-50"
                >
                  ← Previous
                </button>
                <span className="text-sm font-medium text-slate-700">
                  Page {currentPageIndex + 1} of {submission.pages.length}
                  {currentPage && (
                    <span className="text-slate-500 ml-1">
                      (Page {currentPage.pageNumber})
                    </span>
                  )}
                </span>
                <button
                  onClick={() =>
                    setCurrentPageIndex(
                      Math.min(submission.pages.length - 1, currentPageIndex + 1)
                    )
                  }
                  disabled={currentPageIndex === submission.pages.length - 1}
                  className="px-3 py-1 text-sm border border-slate-300 rounded hover:bg-slate-50 disabled:opacity-50"
                >
                  Next →
                </button>
              </div>
            </div>

            {((currentPage as any).imageBase64 || (currentPage as any).image_base64) && (
              <div className="mb-4 bg-slate-50 p-2 rounded-lg">
                <img
                  src={(currentPage as any).imageBase64 || (currentPage as any).image_base64}
                  alt={`Page ${currentPage.pageNumber}`}
                  className="w-full border border-slate-200 rounded shadow-sm"
                  style={{ maxHeight: "70vh", objectFit: "contain" }}
                />
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Page Text Content
                </label>
                <div className="text-sm text-slate-600 bg-slate-50 p-3 rounded max-h-48 overflow-y-auto border border-slate-200">
                  {currentPage.snippet || "No text content available"}
                </div>
              </div>
              
              {currentAnalysis && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Page Information
                  </label>
                  <div className="text-xs text-slate-600 bg-slate-50 p-2 rounded space-y-1">
                    <div><span className="font-medium">Type:</span> {currentAnalysis.page_type || "N/A"}</div>
                    {currentAnalysis.skip_analysis && (
                      <div><span className="font-medium">Skip Reason:</span> {currentAnalysis.skip_reason || "N/A"}</div>
                    )}
                    {currentAnalysis.extracted_violations && (
                      <div><span className="font-medium">Violations Found:</span> {currentAnalysis.extracted_violations.length}</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right: Detailed Review Results */}
          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Review Results & Override</h2>
              {currentAnalysis && currentAnalysis.hasOverrides && (
                <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                  Modified
                </span>
              )}
            </div>

            {currentAnalysis ? (
              <div className="space-y-4 max-h-[calc(100vh-150px)] overflow-y-auto">
                {/* Summary Card */}
                <div className="bg-gradient-to-r from-slate-50 to-slate-100 p-3 rounded-lg border border-slate-200">
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <span className="text-slate-600">Status:</span>{" "}
                      <span className={`font-medium ${
                        currentAnalysis.skip_analysis ? "text-amber-600" : "text-green-600"
                      }`}>
                        {currentAnalysis.skip_analysis ? "Skipped" : "Analyzed"}
                      </span>
                    </div>
                    {currentAnalysis.extracted_violations &&
                      currentAnalysis.extracted_violations.length > 0 &&
                      currentAnalysis.page_type &&
                      !currentAnalysis.page_type.toLowerCase().includes("introduction") &&
                      !currentAnalysis.page_type.toLowerCase().includes("conclusion") &&
                      !currentAnalysis.page_type.toLowerCase().includes("severity summary") && (
                        <div>
                          <span className="text-slate-600">Violations:</span>{" "}
                          <span className="font-medium text-slate-900">
                            {currentAnalysis.extracted_violations.length}
                          </span>
                        </div>
                      )}
                  </div>
                </div>
                

                {/* Feedback */}
                <EditableField
                  label="Feedback"
                  value={getEffectiveValue("feedback", currentAnalysis.feedback || "")}
                  originalValue={currentAnalysis.feedback || ""}
                  field="feedback"
                  pageNumber={currentPage.pageNumber}
                  onSave={(value, notes) =>
                    saveOverride(
                      currentPage.pageNumber,
                      "feedback",
                      currentAnalysis.feedback,
                      value,
                      notes
                    )
                  }
                  hasOverride={!!currentAnalysis.overrides?.find((o) => o.field === "feedback")}
                />

                {/* Score Breakdown - Only show if not skipped */}
                {currentAnalysis.score_breakdown && !currentAnalysis.skip_analysis && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Score Breakdown
                    </label>
                    <div className="space-y-2">
                      {Object.entries(currentAnalysis.score_breakdown).map(([key, score]) => {
                        // Skip Group Integration if not an introduction/group collaboration page
                        const pageType = currentAnalysis.page_type?.toLowerCase() || "";
                        const isIntroductionPage = pageType.includes("introduction");
                        const isGroupIntegrationPage = isIntroductionPage || pageType.includes("group") || pageType.includes("collaboration");
                        
                        if (key === "group_integration" && !isGroupIntegrationPage) {
                          return null; // Don't display Group Integration for non-introduction pages
                        }
                        
                        const effectivePoints = getEffectiveValue(
                          `score_breakdown.${key}.points`,
                          score.points
                        );
                        const hasOverride = !!currentAnalysis.overrides?.find(
                          (o) => o.field === `score_breakdown.${key}.points`
                        );
                        
                        // Special handling for coverage: show heuristic count
                        let displayLabel = key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
                        let additionalInfo = null;
                        
                        // Special handling for coverage
                        let coveragePoints = effectivePoints;
                        
                        if (key === "coverage") {
                          // Count unique heuristics covered across all pages
                          const allHeuristics = new Set<number>();
                          submission?.analysisResults.forEach((result) => {
                            if (result.extracted_violations) {
                              result.extracted_violations.forEach((violation) => {
                                const heuristicNum = violation.heuristic_num || violation.heuristic_number;
                                if (heuristicNum) {
                                  allHeuristics.add(heuristicNum);
                                }
                              });
                            }
                          });
                          const totalHeuristics = 10; // Nielsen's 10 heuristics
                          const coveredCount = allHeuristics.size;
                          
                          // If all 10 heuristics are covered, auto-set to max (15 points)
                          if (coveredCount === totalHeuristics) {
                            coveragePoints = score.max;
                            // Auto-save if not already at max and no override exists
                            // Use a unique key to track if we've already auto-saved for this page/field
                            const autoSaveKey = `${submission?.jobId}_${currentPage?.pageNumber}_${key}`;
                            if (effectivePoints < score.max && !hasOverride && submission && currentPage && !autoSavedPages.current.has(autoSaveKey)) {
                              // Mark as auto-saved to prevent duplicate saves
                              autoSavedPages.current.add(autoSaveKey);
                              // Auto-save the score (with delay to ensure state is ready)
                              setTimeout(() => {
                                // Double-check submission is still available and hasn't been manually overridden
                                if (submission && currentPage) {
                                  const currentHasOverride = currentAnalysis?.overrides?.find(
                                    (o) => o.field === `score_breakdown.${key}.points`
                                  );
                                }
                              }, 500);
                            }
                          }
                          
                          additionalInfo = (
                            <span className="text-xs text-slate-500 ml-2">
                              ({coveredCount} / {totalHeuristics} heuristics covered)
                            </span>
                          );
                        }
                        
                        return (
                          <div key={key} className={key === "coverage" ? "mb-3" : ""}>
                            {key === "coverage" && additionalInfo && (
                              <div className="mb-1 text-xs text-slate-600">
                                {additionalInfo}
                              </div>
                            )}
                            <EditableScoreField
                              key={`${key}_${currentPage.pageNumber}_${hasOverride ? 'modified' : 'original'}_${refreshTrigger}`}
                              label={displayLabel}
                              points={key === "coverage" ? coveragePoints : effectivePoints}
                              max={score.max}
                              originalPoints={score.points}
                              comment={score.comment}
                              field={`score_breakdown.${key}.points`}
                              pageNumber={currentPage.pageNumber}
                              onSave={(value, notes) =>
                                saveOverride(
                                  currentPage.pageNumber,
                                  `score_breakdown.${key}.points`,
                                  score.points,
                                  value,
                                  notes
                                )
                              }
                              hasOverride={hasOverride}
                            />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Violations - Detailed View - Only show for violation analysis pages */}
                {currentAnalysis.extracted_violations &&
                  currentAnalysis.extracted_violations.length > 0 &&
                  currentAnalysis.page_type &&
                  !currentAnalysis.page_type.toLowerCase().includes("introduction") &&
                  !currentAnalysis.page_type.toLowerCase().includes("conclusion") &&
                  !currentAnalysis.page_type.toLowerCase().includes("severity summary") && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-2">
                        Heuristic Violations ({currentAnalysis.extracted_violations.length})
                      </label>
                      <div className="space-y-3 max-h-96 overflow-y-auto">
                        {currentAnalysis.extracted_violations.map((violation, idx) => (
                          <div
                            key={idx}
                            className="p-3 bg-slate-50 rounded-lg text-sm border border-slate-200 hover:border-slate-300 transition-colors"
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="font-semibold text-slate-900">
                                H{violation.heuristic_num || violation.heuristic_number}:{" "}
                                {violation.heuristic_name || "N/A"}
                              </div>
                              {violation.severity && (
                                <span className={`text-xs px-2 py-1 rounded font-medium ${
                                  violation.severity.toLowerCase() === "critical" || violation.severity.toLowerCase() === "high"
                                    ? "bg-red-100 text-red-800"
                                    : violation.severity.toLowerCase() === "medium"
                                    ? "bg-amber-100 text-amber-800"
                                    : "bg-blue-100 text-blue-800"
                                }`}>
                                  {violation.severity}
                                </span>
                              )}
                            </div>
                            {violation.description && (
                              <div className="text-slate-700 text-sm mt-2 leading-relaxed">
                                {violation.description}
                              </div>
                            )}
                            {(violation as any).location && (
                              <div className="text-slate-500 text-xs mt-2">
                                <span className="font-medium">Location:</span> {(violation as any).location}
                              </div>
                            )}
                            {(violation as any).suggestion && (
                              <div className="text-blue-700 text-xs mt-2 bg-blue-50 p-2 rounded">
                                <span className="font-medium">Suggestion:</span> {(violation as any).suggestion}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                {/* Override History - Detailed View */}
                {currentAnalysis.overrides && currentAnalysis.overrides.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Override History ({currentAnalysis.overrides.length})
                    </label>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {currentAnalysis.overrides.map((override) => (
                        <div
                          key={override.id}
                          className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs"
                        >
                          <div className="flex items-center justify-between mb-1">
                            <div className="font-semibold text-amber-900">
                              {override.field.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
                            </div>
                            <div className="text-amber-600 text-xs">
                              {override.reviewerName || "Anonymous"}
                              {override.timestamp && (
                                <span className="ml-1">
                                  • {new Date(override.timestamp).toLocaleString()}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="text-amber-800 mt-2 p-2 bg-white rounded border border-amber-100">
                            <div className="flex items-center gap-2">
                              <span className="line-through text-slate-500">
                                {String(override.originalValue)}
                              </span>
                              <span className="text-amber-600">→</span>
                              <span className="font-semibold text-amber-900">
                                {String(override.overrideValue)}
                              </span>
                            </div>
                          </div>
                          {override.reviewerNotes && 
                           !override.reviewerNotes.includes("Auto-set") && 
                           !override.reviewerNotes.includes("auto-set") && (
                            <div className="text-amber-700 mt-2 italic bg-amber-100 p-2 rounded">
                              <span className="font-medium">Note:</span> {override.reviewerNotes}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-slate-500 text-sm">No analysis available for this page.</div>
            )}
          </div>
        </div>
      )}

      {!submission && !loading && availableJobs.length === 0 && (
        <div className="text-center py-12">
          <div className="text-slate-500 mb-2">No submissions available</div>
          <div className="text-sm text-slate-400">
            Please upload and analyze a PDF on the <a href="/upload" className="text-blue-600 hover:underline">Grade PDF</a> page first
          </div>
        </div>
      )}

      {/* Report AI Error Dialog */}
      {showErrorReport && currentAnalysis && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold mb-4">Report AI Error</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Component (What did the AI get wrong?)
                </label>
                <select
                  value={errorReportComponent}
                  onChange={(e) => setErrorReportComponent(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md"
                >
                  <option value="">Select component...</option>
                  <option value="violation_quality">Violation Quality</option>
                  <option value="coverage">Coverage</option>
                  <option value="screenshots">Screenshots</option>
                  <option value="severity_analysis">Severity Analysis</option>
                  <option value="structure_navigation">Structure/Navigation</option>
                  <option value="professional_quality">Professional Quality</option>
                  <option value="writing_quality">Writing Quality</option>
                  <option value="group_integration">Group Integration</option>
                  <option value="feedback">Feedback</option>
                  <option value="extracted_violations">Extracted Violations</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Reason (Why was the AI wrong?)
                </label>
                <textarea
                  value={errorReportReason}
                  onChange={(e) => setErrorReportReason(e.target.value)}
                  placeholder="Describe what the AI got wrong and why..."
                  className="w-full px-3 py-2 border border-slate-300 rounded-md h-24"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Original AI Value
                </label>
                <textarea
                  value={JSON.stringify(errorReportComponent && currentAnalysis.score_breakdown?.[errorReportComponent] || currentAnalysis.feedback || "", null, 2)}
                  readOnly
                  className="w-full px-3 py-2 border border-slate-300 rounded-md bg-slate-50 h-20 font-mono text-xs"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Corrected Value
                </label>
                <textarea
                  value={errorReportCorrectedValue}
                  onChange={(e) => setErrorReportCorrectedValue(e.target.value)}
                  placeholder="Enter the corrected value..."
                  className="w-full px-3 py-2 border border-slate-300 rounded-md h-24"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Additional Notes (Optional)
                </label>
                <textarea
                  value={errorReportNotes}
                  onChange={(e) => setErrorReportNotes(e.target.value)}
                  placeholder="Any additional context..."
                  className="w-full px-3 py-2 border border-slate-300 rounded-md h-20"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-6">
              <button
                onClick={() => {
                  if (errorReportComponent && errorReportReason) {
                    const originalValue = errorReportComponent && currentAnalysis.score_breakdown?.[errorReportComponent] || currentAnalysis.feedback || "";
                    reportAIError(errorReportComponent, errorReportReason, originalValue, errorReportCorrectedValue, errorReportNotes);
                  } else {
                    alert("Please fill in Component and Reason");
                  }
                }}
                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
              >
                Report Error
              </button>
              <button
                onClick={() => {
                  setShowErrorReport(false);
                  setErrorReportComponent("");
                  setErrorReportReason("");
                  setErrorReportCorrectedValue("");
                  setErrorReportNotes("");
                }}
                className="flex-1 px-4 py-2 bg-slate-300 text-slate-700 rounded-md hover:bg-slate-400"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Prompt Improvement Dialog */}
      {showPromptImprovement && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-5xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold mb-4">Improved Prompt Generated from Corrections</h3>
            <div className="mb-4 text-sm text-slate-600">
              Based on {corrections.length} correction(s). Review and copy the improved prompt below.
            </div>
            
            {/* Modification Notes */}
            {promptModificationNotes && (
              <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h4 className="text-sm font-semibold text-blue-900 mb-2">How the Prompt Was Modified:</h4>
                <div className="text-sm text-blue-800 whitespace-pre-wrap">{promptModificationNotes}</div>
              </div>
            )}
            
            <div className="mb-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">Improved Prompt:</label>
              <textarea
                value={improvedPrompt}
                readOnly
                className="w-full h-96 px-3 py-2 border border-slate-300 rounded-md font-mono text-xs"
              />
            </div>
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(improvedPrompt);
                  alert("Prompt copied to clipboard!");
                }}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                Copy to Clipboard
              </button>
              <button
                onClick={() => {
                  const blob = new Blob([improvedPrompt], { type: "text/plain" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `improved_prompt_${new Date().toISOString().split("T")[0]}.txt`;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                }}
                className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
              >
                Export as File
              </button>
              <button
                onClick={() => {
                  // Save improved prompt to localStorage so refine page can use it
                  localStorage.setItem("promptForRefinement", improvedPrompt);
                  // Navigate to refine page
                  navigate("/prompt-refinement");
                  // Close dialog
                  setShowPromptImprovement(false);
                  setImprovedPrompt("");
                  setPromptModificationNotes("");
                }}
                className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 flex items-center gap-2"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Continue with AI Refine
              </button>
              <button
                onClick={() => {
                  setShowPromptImprovement(false);
                  setImprovedPrompt("");
                  setPromptModificationNotes("");
                }}
                className="px-4 py-2 bg-slate-300 text-slate-700 rounded-md hover:bg-slate-400"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Generating Prompt Loading Overlay */}
      {generatingPrompt && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-8 max-w-md w-full mx-4">
            <div className="flex flex-col items-center gap-4">
              <svg className="animate-spin h-12 w-12 text-purple-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <div className="text-lg font-semibold text-slate-900">Generating Improved Prompt...</div>
              <div className="text-sm text-slate-600 text-center">
                Analyzing {corrections.length} correction(s) and page images to improve the grading prompt.
                This may take a moment.
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
    </>
  );
}

// Editable Field Component
function EditableField({
  label,
  value,
  originalValue,
  field,
  pageNumber,
  onSave,
  hasOverride,
}: {
  label: string;
  value: string;
  originalValue: string;
  field: string;
  pageNumber: number;
  onSave: (value: string, notes?: string) => void;
  hasOverride: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(value);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    setEditValue(value);
  }, [value]);

  const handleSave = async () => {
    if (editValue !== originalValue || notes.trim()) {
      await onSave(editValue, notes);
      // Update local state immediately
      setEditValue(editValue);
    }
    setEditing(false);
    setNotes(""); // Clear notes after save
  };

  const handleCancel = () => {
    setEditValue(value);
    setNotes("");
    setEditing(false);
  };

  if (editing) {
    return (
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
        <textarea
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          rows={4}
        />
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Override notes (optional)"
          className="w-full mt-2 px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
        />
        <div className="flex gap-2 mt-2">
          <button
            onClick={handleSave}
            className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Save Override
          </button>
          <button
            onClick={handleCancel}
            className="px-3 py-1 text-sm border border-slate-300 rounded hover:bg-slate-50"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <label className="block text-sm font-medium text-slate-700">{label}</label>
        {hasOverride && (
          <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
            Overridden
          </span>
        )}
      </div>
      <div className="text-sm text-slate-600 bg-slate-50 p-2 rounded relative group">
        {value || "N/A"}
        <button
          onClick={() => setEditing(true)}
          className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Edit
        </button>
      </div>
    </div>
  );
}

// Editable Score Field Component
function EditableScoreField({
  label,
  points,
  max,
  originalPoints,
  comment,
  field,
  pageNumber,
  onSave,
  hasOverride,
}: {
  label: string;
  points: number;
  max: number;
  originalPoints: number;
  comment: string;
  field: string;
  pageNumber: number;
  onSave: (value: number, notes?: string) => void;
  hasOverride: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(points.toString());
  const [notes, setNotes] = useState("");

  useEffect(() => {
    // Always sync with points prop when not editing
    // This ensures the displayed value updates when parent state changes
    if (!editing) {
      const newValue = points.toString();
      if (editValue !== newValue) {
        setEditValue(newValue);
      }
    }
  }, [points, editing]);

  const handleSave = async () => {
    const numValue = parseFloat(editValue);
    if (!isNaN(numValue) && numValue >= 0 && numValue <= max) {
      // Save if value changed OR if notes were added
      if (numValue !== originalPoints || notes.trim()) {
        // Close editing mode first
        setEditing(false);
        setNotes(""); // Clear notes after save
        // Then save (this will update parent state and trigger re-render)
        await onSave(numValue, notes);
      } else {
        setEditing(false);
        setNotes("");
      }
    } else {
      setEditing(false);
      setNotes("");
    }
  };

  const handleCancel = () => {
    setEditValue(points.toString());
    setNotes("");
    setEditing(false);
  };

  if (editing) {
    return (
      <div className={`p-2 rounded border ${
        hasOverride 
          ? "bg-green-50 border-green-300" 
          : "bg-slate-50 border-slate-200"
      }`}>
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium">{label}</span>
          {hasOverride && (
            <span className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded">
              Modified
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            min={0}
            max={max}
            className="w-20 px-2 py-1 border border-slate-300 rounded text-sm"
          />
          <span className="text-sm text-slate-600">/ {max}</span>
        </div>
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Override notes (optional)"
          className="w-full mt-2 px-2 py-1 border border-slate-300 rounded text-sm"
        />
        <div className="flex gap-2 mt-2">
          <button
            onClick={handleSave}
            className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Save
          </button>
          <button
            onClick={handleCancel}
            className="px-2 py-1 text-xs border border-slate-300 rounded hover:bg-slate-50"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`p-2 rounded border relative group ${
      hasOverride 
        ? "bg-green-50 border-green-300" 
        : "bg-slate-50 border-slate-200"
    }`}>
      <div className="flex justify-between items-center">
        <span className="text-sm font-medium">{label}</span>
        {hasOverride && (
          <span className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded">
            Modified
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 mt-1">
        <span className={`text-sm font-semibold ${
          hasOverride ? "text-green-700" : "text-slate-900"
        }`}>
          {points} / {max}
        </span>
        {comment && <span className="text-xs text-slate-500">({comment})</span>}
        <button
          onClick={() => setEditing(true)}
          className="ml-auto opacity-0 group-hover:opacity-100 px-2 py-0.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Edit
        </button>
      </div>
    </div>
  );
}

