import React, { useState, useEffect, useMemo, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { Issue, PageAnalysis, HeuristicExtractionPage, ScoringOutput } from "../lib/types";
import {
  API_BASE,
  listJobs,
  getIssues,
  getPages,
  getExtractionResult,
  getRubricComments as fetchRubricComments,
  getScoringOutput as fetchScoringOutput,
  calculateGradingScores as fetchGradingScores,
  saveGradingScores as postGradingScores,
  getIssueScores as fetchIssueScores,
  saveIssueScores as postIssueScores,
  updatePageMetadata as patchPageMetadata,
  updateIssueReview as patchIssueReview,
} from "../lib/api";

interface HeuristicInfo {
  number: number;
  name: string;
  description: string;
}

export default function IssueReviewerPage() {
  const navigateBase = useNavigate();
  const [searchParams] = useSearchParams();
  const [jobId, setJobId] = useState<string>(searchParams.get("jobId") || "");
  const [availableJobs, setAvailableJobs] = useState<Array<{jobId: string; fileName?: string; createdAt?: string}>>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [pages, setPages] = useState<PageAnalysis[]>([]);
  const [extractionPages, setExtractionPages] = useState<HeuristicExtractionPage[]>([]);
  const [selectedIssueIndex, setSelectedIssueIndex] = useState<number>(0);
  const [selectedPageIndex, setSelectedPageIndex] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<"issue" | "page">("issue");
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [heuristicsInfo, setHeuristicsInfo] = useState<HeuristicInfo[]>([]);
  const [gradingScores, setGradingScores] = useState<Record<string, {points: number; max: number; comment: string; ta_points?: number; ta_comment?: string}>>({});
  const [loadingScores, setLoadingScores] = useState(false);
  const [recomputing, setRecomputing] = useState(false);
  const [scoringOutput, setScoringOutput] = useState<ScoringOutput | null>(null);
  const [issueScores, setIssueScores] = useState<Record<string, Record<string, {points: number; max: number; ta_points?: number; ta_comment?: string}>>>({});
  const [reanalyzingPage, setReanalyzingPage] = useState<string | null>(null);
  const [editingPageMetadata, setEditingPageMetadata] = useState<string | null>(null); // pageId being edited
  const [savingPageMetadata, setSavingPageMetadata] = useState(false);
  const currentJobIdRef = useRef<string>("");
  
  // Rubric component comments
  const rubricComponents = [
    { key: "coverage", label: "Coverage", max: 15 },
    { key: "violation_quality", label: "Violation Quality", max: 20 },
    { key: "severity_analysis", label: "Severity Analysis", max: 10 },
    { key: "screenshots_evidence", label: "Screenshots & Evidence", max: 10 },
    { key: "structure_navigation", label: "Structure & Navigation", max: 10 },
    { key: "professional_quality", label: "Professional Quality", max: 10 },
    { key: "writing_quality", label: "Writing Quality", max: 10 },
    { key: "group_integration", label: "Group Integration", max: 15 },
    { key: "bonus_ai_opportunities", label: "Bonus: AI Opportunities", max: 3 },
    { key: "bonus_exceptional_quality", label: "Bonus: Exceptional Quality", max: 2 },
  ];
  const [rubricComments, setRubricComments] = useState<Record<string, string>>({}); // Saved comments (for display in summary)
  const evaluateRubricComment = (comment: string) => {
    const length = comment.trim().length;
    if (length >= 60) {
      return {
        badge: "Included in re-run",
        badgeClass: "bg-green-100 text-green-800",
        detail: "This detailed comment is fed into the re-run scoring prompt as-is.",
      };
    }
    if (length >= 25) {
      return {
        badge: "Included (concise)",
        badgeClass: "bg-blue-100 text-blue-800",
        detail: "Comment is included in the scoring input, though adding more specifics will strengthen future runs.",
      };
    }
    return {
      badge: "Needs more detail",
      badgeClass: "bg-amber-100 text-amber-800",
      detail: "Comment is logged for reference but is too short to influence the scoring input. Consider elaborating.",
    };
  };

  const handleGeneratePromptAnalysis = async () => {
    if (!jobId) return;
    setGeneratingPromptAnalysis(true);
    setSaveStatus(null);
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${jobId}/comment-prompt-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Failed to generate prompt analysis" }));
        throw new Error(errorData.detail || "Failed to generate prompt analysis");
      }
      const data = await response.json();
      if (data.ok && data.analysis) {
        setCommentPromptAnalysis(data.analysis);
        setSaveStatus("✅ Generated prompt analysis from TA comments.");
        setTimeout(() => setSaveStatus(null), 4000);
      }
    } catch (err: any) {
      setSaveStatus(`❌ Error: ${err.message}`);
    } finally {
      setGeneratingPromptAnalysis(false);
    }
  };
  const [editingRubricComment, setEditingRubricComment] = useState<string>(""); // Currently editing comment (temporary, not saved yet)
  const [savingRubricComments, setSavingRubricComments] = useState(false);
  const [selectedRubricComponent, setSelectedRubricComponent] = useState<string>("");

  useEffect(() => {
    loadAvailableJobs();
    loadHeuristicsInfo();
  }, []);

  const loadHeuristicsInfo = async () => {
    try {
      const res = await fetch("/rubrics/a3_rubric.json");
      if (res.ok) {
        const data = await res.json();
        if (data.heuristics && Array.isArray(data.heuristics)) {
          setHeuristicsInfo(data.heuristics);
        }
      }
    } catch (err) {
      console.error("Failed to load heuristics info:", err);
    }
  };

  useEffect(() => {
    if (jobId) {
      // Update ref to track current jobId
      currentJobIdRef.current = jobId;
      
      // Check for timestamp parameter to force refresh (e.g., after rerun)
      const timestamp = searchParams.get("t");
      const isFromRerun = !!timestamp;
      
      // Reset all state when jobId changes or when timestamp is present (force refresh)
      setIssues([]);
      setPages([]);
      setExtractionPages([]);
      setScoringOutput(null);
      setIssueScores({});
      setRubricComments({});
      setSelectedIssueIndex(0);
      setSelectedPageIndex(null);
      setError(null);
      setLoading(true); // Ensure loading state is shown
      
      // Load heuristics info first (needed for display)
      loadHeuristicsInfo();
      
      // If coming from rerun, wait a bit for backend to process, then load data
      if (isFromRerun) {
        // Wait 2 seconds for backend to finish processing analysis results
        setTimeout(() => {
          loadData();
          loadGradingScores();
          loadScoringOutput();
          loadRubricComments();
          checkBackupExists();
          
          // After loading, wait a bit more then refresh to ensure all data is up to date
          setTimeout(() => {
            if (currentJobIdRef.current === jobId) {
              loadData();
              loadGradingScores();
              loadScoringOutput();
            }
          }, 1000);
        }, 2000);
      } else {
        // Normal load
        loadData();
        loadGradingScores();
        loadScoringOutput();
        loadRubricComments();
        checkBackupExists();
      }
      
      // Remove timestamp from URL after loading to avoid confusion
      if (timestamp) {
        const newSearchParams = new URLSearchParams(searchParams);
        newSearchParams.delete("t");
        const newUrl = `${window.location.pathname}?${newSearchParams.toString()}`;
        window.history.replaceState({}, "", newUrl);
      }
    } else {
      currentJobIdRef.current = "";
      setLoading(false);
    }
  }, [jobId, searchParams]);

  // Check if backup exists
  const checkBackupExists = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/check-backup-exists`);
      if (response.ok) {
        const data = await response.json();
        setBackupExists(data.backup_exists || false);
      }
    } catch (err) {
      console.error("Failed to check backup:", err);
    }
  };

  // Track if we've auto-triggered recompute to avoid infinite loops
  const hasAutoRecomputedRef = useRef(false);
  
  // Reset auto-recompute flag when jobId changes
  useEffect(() => {
    hasAutoRecomputedRef.current = false;
  }, [jobId]);

  // Load saved issue scores
  const loadIssueScores = async () => {
    if (!jobId) return;
    try {
      const data = await fetchIssueScores(jobId);
      if (Object.keys(data).length > 0) {
        setIssueScores(data);
        return;
      }
    } catch {
      console.log("No saved issue scores found");
    }
    
    // If no saved scores, calculate from pages
    if (issues.length > 0 && pages.length > 0) {
      calculateIssueScores();
    }
  };

  // Calculate issue-level scores from pages
  const calculateIssueScores = () => {
    if (issues.length === 0 || pages.length === 0) return;
    
    const newIssueScores: Record<string, Record<string, {points: number; max: number; ta_points?: number; ta_comment?: string}>> = {};
    
    issues.forEach((issue) => {
      const issuePages = pages.filter((p) => issue.pages_involved.includes(p.page_id));
      if (issuePages.length === 0) {
        // If no pages match, try to find pages by heuristic_id
        const heuristicPages = pages.filter((p) => {
          // Check if any fragment in the page matches this issue's heuristic_id
          return p.fragments?.some((f: any) => f.heuristic_id === issue.heuristic_id);
        });
        if (heuristicPages.length > 0) {
          issuePages.push(...heuristicPages);
        }
      }
      if (issuePages.length === 0) return;
      
      // Prefer violation_detail pages, but also use other pages if available
      const violationPages = issuePages.filter((p) => p.page_role === "violation_detail");
      const pagesToUse = violationPages.length > 0 ? violationPages : issuePages;
      
      const scores: Record<string, {points: number; max: number}> = {};
      
      // Convert rubric_relevance levels to points
      const levelToPoints = (level: string, max: number): number => {
        switch (level) {
          case "high": return max;
          case "med": return Math.round(max * 0.7);
          case "low": return Math.round(max * 0.4);
          default: return 0;
        }
      };
      
      // Violation Quality (max 20)
      const violationQualityLevels = pagesToUse.map((p) => p.rubric_relevance?.violation_quality || "none");
      const avgViolationQuality = violationQualityLevels.length > 0
        ? Math.round(violationQualityLevels.reduce((sum, level) => sum + levelToPoints(level, 20), 0) / violationQualityLevels.length)
        : 0;
      scores["violation_quality"] = { points: avgViolationQuality, max: 20 };
      
      // Severity Analysis (max 10)
      const severityLevels = pagesToUse.map((p) => p.rubric_relevance?.severity_analysis || "none");
      const avgSeverity = severityLevels.length > 0
        ? Math.round(severityLevels.reduce((sum, level) => sum + levelToPoints(level, 10), 0) / severityLevels.length)
        : 0;
      scores["severity_analysis"] = { points: avgSeverity, max: 10 };
      
      // Screenshots & Evidence (max 10)
      const screenshotsLevels = pagesToUse.map((p) => {
        const annotationLevel = p.has_annotations;
        if (annotationLevel === "high") return "high";
        if (annotationLevel === "medium") return "med";
        if (annotationLevel === "low") return "low";
        return "none";
      });
      const avgScreenshots = screenshotsLevels.length > 0
        ? Math.round(screenshotsLevels.reduce((sum, level) => sum + levelToPoints(level, 10), 0) / screenshotsLevels.length)
        : 0;
      scores["screenshots_evidence"] = { points: avgScreenshots, max: 10 };
      
      // Structure & Navigation (max 10) - use violation_quality as proxy if structure_navigation not available
      const structureLevels = pagesToUse.map((p) => {
        // Try structure_navigation first, fallback to violation_quality
        const rubric = p.rubric_relevance;
        if (rubric && "structure_navigation" in rubric) {
          return (rubric as any).structure_navigation || "none";
        }
        return rubric?.violation_quality || "none";
      });
      const avgStructure = structureLevels.length > 0
        ? Math.round(structureLevels.reduce((sum, level) => sum + levelToPoints(level, 10), 0) / structureLevels.length)
        : 0;
      scores["structure_navigation"] = { points: avgStructure, max: 10 };
      
      newIssueScores[issue.issue_id] = scores;
    });
    
    setIssueScores(newIssueScores);
  };

  useEffect(() => {
    if (issues.length > 0 && pages.length > 0 && jobId) {
      loadIssueScores();
    }
  }, [issues, pages, jobId]);

  const loadScoringOutput = async () => {
    const currentJobId = currentJobIdRef.current;
    if (!currentJobId) return;
    try {
      const data = await fetchScoringOutput(currentJobId);
      if (currentJobIdRef.current === currentJobId && data?.scoring) {
        setScoringOutput(data.scoring);
      }
    } catch {
      console.log("No scoring output found yet");
    }
  };

  const loadRubricComments = async () => {
    const currentJobId = currentJobIdRef.current;
    if (!currentJobId) return;
    try {
      const data = await fetchRubricComments(currentJobId);
      if (currentJobIdRef.current === currentJobId && data?.comments) {
        const loadedComments = data.comments || {};
        setRubricComments(loadedComments);
        if (selectedRubricComponent && loadedComments[selectedRubricComponent]) {
          setEditingRubricComment(loadedComments[selectedRubricComponent]);
        }
      }
    } catch {
      setRubricComments({});
      setEditingRubricComment("");
    }
  };

  const loadGradingScores = async () => {
    const currentJobId = currentJobIdRef.current;
    if (!currentJobId) return;
    setLoadingScores(true);
    try {
      const data = await fetchGradingScores(currentJobId);
      if (currentJobIdRef.current === currentJobId) {
        setGradingScores(data.scores || {});
      }
    } catch (err) {
      console.error("Failed to load grading scores:", err);
    } finally {
      // Only set loading to false if jobId hasn't changed
      if (currentJobIdRef.current === currentJobId) {
        setLoadingScores(false);
      }
    }
  };

  const handleSaveGradingScores = async () => {
    if (!jobId) return;
    setSaving(true);
    try {
      await postGradingScores(jobId, gradingScores);
      setSaveStatus("Grading scores saved successfully!");
      setTimeout(() => setSaveStatus(null), 2000);
    } catch (err: any) {
      // Error messages should persist - don't auto-clear
      setSaveStatus(`Error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRerunWithModifiedRubric = () => {
    navigate(`/upload?jobId=${jobId}&rerun=true`);
  };

  const [changesSummary, setChangesSummary] = useState<any>(null);
  const [commentPromptAnalysis, setCommentPromptAnalysis] = useState<any>(null);
  const [showChangesModal, setShowChangesModal] = useState(false);
  const [updatingPrompt, setUpdatingPrompt] = useState(false);
  const [generatingPromptAnalysis, setGeneratingPromptAnalysis] = useState(false);
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string>("");
  const [backupExists, setBackupExists] = useState<boolean>(false);
  const [backingUp, setBackingUp] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [showNavigationConfirm, setShowNavigationConfirm] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null);

  // Wrapped navigate function that intercepts navigation when recomputing or generating analysis
  const navigate = React.useCallback((to: string | number, options?: any) => {
    if ((recomputing || generatingPromptAnalysis) && typeof to === "string" && to.startsWith("/")) {
      setPendingNavigation(() => () => {
        navigateBase(to as string, options);
      });
      setShowNavigationConfirm(true);
      return;
    }
    if (typeof to === "number") {
      navigateBase(to);
    } else {
      navigateBase(to, options);
    }
  }, [recomputing, generatingPromptAnalysis, navigateBase]);

  // Intercept navigation when recomputing or generating analysis
  useEffect(() => {
    if (!recomputing && !generatingPromptAnalysis) return;

    // Intercept browser navigation (back button, refresh, etc.)
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      const message = recomputing
        ? "Re-run grading is in progress. If you leave, changes will not be saved. Are you sure you want to leave?"
        : "Analysis generation is in progress. If you leave, changes will not be saved. Are you sure you want to leave?";
      e.returnValue = message;
      return e.returnValue;
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    // Intercept React Router navigation by wrapping navigate
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const link = target.closest("a[href]");
      if (link) {
        const href = link.getAttribute("href");
        if (href && href.startsWith("/") && href !== window.location.pathname) {
          e.preventDefault();
          e.stopPropagation();
          setPendingNavigation(() => () => {
            navigate(href);
          });
          setShowNavigationConfirm(true);
        }
      }
    };

    document.addEventListener("click", handleClick, true);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      document.removeEventListener("click", handleClick, true);
    };
  }, [recomputing, generatingPromptAnalysis, navigate]);

  // Clean up analysis summary/recs when backend falls back to raw JSON text
  const { cleanedAnalysisSummary, cleanedRecommendations } = useMemo(() => {
    const rawSummary = (commentPromptAnalysis?.analysis_summary as string) || "";
    const rawRecs = (commentPromptAnalysis?.recommendations as string[]) || [];

    const normalize = (text: string) =>
      text
        .replace(/\\n/g, " ")
        .replace(/\\+/g, "")
        .replace(/\s+/g, " ")
        .trim();

    if (!rawSummary) {
      return {
        cleanedAnalysisSummary: "",
        cleanedRecommendations: rawRecs.map((r) => normalize(r)),
      };
    }

    const marker = "LLM returned non-strict JSON. Showing raw text instead:";

    // Case 1: backend fallback前綴 + 嵌套 JSON，一起出現在 summary 內
    if (rawSummary.includes('"analysis_summary"') && rawSummary.includes('"recommendations"')) {
      const start = rawSummary.indexOf("{");
      const end = rawSummary.lastIndexOf("}");
      if (start !== -1 && end !== -1 && end > start) {
        const jsonFragment = rawSummary.slice(start, end + 1);
        try {
          const obj = JSON.parse(jsonFragment);
          const summaryText =
            typeof obj.analysis_summary === "string" && obj.analysis_summary.trim().length > 0
              ? obj.analysis_summary.trim()
              : rawSummary;
          const recs =
            Array.isArray(obj.recommendations) && obj.recommendations.length > 0
              ? obj.recommendations
              : rawRecs;
          return {
            cleanedAnalysisSummary: normalize(summaryText),
            cleanedRecommendations: recs.map((r: string) => normalize(r)),
          };
        } catch {
          // 解析失敗就繼續往下走
        }
      }
    }

    // Case 2: 只有 fallback 前綴，沒有 JSON 結構
    if (rawSummary.startsWith(marker)) {
      return {
        cleanedAnalysisSummary: normalize(rawSummary.slice(marker.length)),
        cleanedRecommendations: rawRecs.map((r) => normalize(r)),
      };
    }

    // 正常情況：直接使用後端給的值，但去掉多餘符號
    return {
      cleanedAnalysisSummary: normalize(rawSummary),
      cleanedRecommendations: rawRecs.map((r) => normalize(r)),
    };
  }, [commentPromptAnalysis]);

  const handleRecomputeScores = async () => {
    if (!jobId) return;
    setRecomputing(true);
    setSaveStatus(null);
    setChangesSummary(null);
    
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${jobId}/review/recompute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Re-run grading ONLY with the current rubric/prompt.
        // Do NOT clear TA reviews or modify underlying issues/pages.
        body: JSON.stringify({ clear_reviews: false }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Failed to recompute scores" }));
        throw new Error(errorData.detail || "Failed to recompute scores");
      }
      const data = await response.json();
      if (data.ok && data.scoring) {
        // Only update scoring output and changes summary.
        // Do NOT reload issues/pages or touch TA reviews.
        setScoringOutput(data.scoring);
        setChangesSummary(data.changes || null);
        
        // Clear all rubric comments after rerun
        try {
          const clearResponse = await fetch(`${API_BASE}/api/jobs/${jobId}/rubric-comments`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              comments: {},
            }),
          });
          if (clearResponse.ok) {
            setRubricComments({});
            setEditingRubricComment("");
            // Reload to ensure UI is in sync
            await loadRubricComments();
          }
        } catch (clearErr) {
          console.error("Failed to clear rubric comments:", clearErr);
          // Still continue even if clearing fails
        }
        
        // Mark that we've manually recomputed, so auto-recompute won't trigger
        hasAutoRecomputedRef.current = true;
        
        // Show changes modal if there are changes or improvements
        if (data.changes || data.improvement_analysis) {
          setShowChangesModal(true);
        }
        
        setSaveStatus("✅ Recomputed scores; TA reviews cleared. Click to view changes and improvements.");
        setTimeout(() => setSaveStatus(null), 8000);
        
        // Reload grading scores to show updated values
        await loadGradingScores();
      } else {
        throw new Error("Invalid response from server");
      }
    } catch (err: any) {
      // Error messages should persist until manually cleared or next action
      setSaveStatus(`❌ Error: ${err.message}`);
      // Don't auto-clear error messages - let them persist
    } finally {
      setRecomputing(false);
    }
  };

  // Auto-recompute scores when pages/issues are loaded but scoring is missing or outdated
  useEffect(() => {
    const checkAndRecompute = async () => {
      // Only check if we have pages and issues loaded, but no scoring output
      // And we haven't already auto-triggered for this jobId
      if (pages.length > 0 && issues.length > 0 && !scoringOutput && !loading && !recomputing && jobId && !hasAutoRecomputedRef.current) {
        console.log("[DEBUG] Pages and issues loaded but no scoring found. Auto-triggering recompute...");
        hasAutoRecomputedRef.current = true;
        // Small delay to ensure all data is loaded
        setTimeout(async () => {
          if (currentJobIdRef.current === jobId && pages.length > 0 && issues.length > 0 && !scoringOutput && !recomputing) {
            try {
              await handleRecomputeScores();
            } catch (err) {
              console.error("[DEBUG] Auto-recompute failed:", err);
              hasAutoRecomputedRef.current = false; // Reset on error so user can retry
            }
          }
        }, 1000);
      }
    };
    
    checkAndRecompute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pages.length, issues.length, scoringOutput, loading, recomputing, jobId]);

  const loadAvailableJobs = async () => {
    try {
      const jobs = await listJobs();
      setAvailableJobs(jobs);
      if (!jobId) {
        const stored = localStorage.getItem("recentJobIds");
        if (stored) {
          try {
            const storedJobs = JSON.parse(stored);
            if (storedJobs.length > 0) {
              setJobId(storedJobs[0].jobId);
              return;
            }
          } catch {
            // ignore JSON errors
          }
        }
        if (jobs.length > 0) {
          setJobId(jobs[0].jobId);
        }
      }
    } catch (err) {
      console.error("Failed to load jobs:", err);
    }
  };

  const loadData = async () => {
    // Use ref to get the current jobId to avoid stale closures
    const currentJobId = currentJobIdRef.current;
    
    if (!currentJobId) {
      console.log("[DEBUG] loadData: No jobId provided, skipping");
      setLoading(false);
      return;
    }
    
    console.log(`[DEBUG] loadData: Loading data for jobId: ${currentJobId}`);
    setLoading(true);
    setError(null);
    // Clear old data immediately when switching jobs
    setIssues([]);
    setPages([]);
    setExtractionPages([]);
    setScoringOutput(null);
    setIssueScores({});
    setSelectedIssueIndex(0);
    setSelectedPageIndex(null);
    
    try {
      const issuesData = await getIssues(currentJobId);
      console.log(`[DEBUG] loadData: Loaded ${issuesData.issues?.length || 0} issues for jobId ${currentJobId}, response jobId: ${issuesData.jobId}`);
      
      // Verify jobId hasn't changed before setting state
      if (currentJobIdRef.current !== currentJobId) {
        console.log(`[DEBUG] loadData: JobId changed during load (${currentJobId} -> ${currentJobIdRef.current}), discarding issues`);
        return;
      }
      
      // Verify we got data for the correct jobId
      if (issuesData.jobId && issuesData.jobId !== currentJobId) {
        console.warn(`[DEBUG] loadData: JobId mismatch! Requested ${currentJobId}, got ${issuesData.jobId}`);
      }
      setIssues(issuesData.issues || []);

      const pagesData = await getPages(currentJobId);
        console.log(`[DEBUG] loadData: Loaded ${pagesData.pages?.length || 0} pages for jobId ${currentJobId}, response jobId: ${pagesData.jobId}`);
        
        // Verify jobId hasn't changed before setting state
        if (currentJobIdRef.current !== currentJobId) {
          console.log(`[DEBUG] loadData: JobId changed during load (${currentJobId} -> ${currentJobIdRef.current}), discarding pages`);
          return;
        }
        
        // Verify we got data for the correct jobId
        if (pagesData.jobId && pagesData.jobId !== currentJobId) {
          console.warn(`[DEBUG] loadData: JobId mismatch! Requested ${currentJobId}, got ${pagesData.jobId}`);
        }
        setPages(pagesData.pages || []);
      const extractionData = await getExtractionResult(currentJobId);
        
        // Verify jobId hasn't changed before setting state
        if (currentJobIdRef.current !== currentJobId) {
          console.log(`[DEBUG] loadData: JobId changed during load (${currentJobId} -> ${currentJobIdRef.current}), discarding extraction pages`);
          return;
        }
        
        const extractionPagesData = (extractionData.pages || []).map((page: any) => ({
          ...page,
          // Normalize pageNumber - backend might return page_number or pageNumber
          pageNumber: page.pageNumber || page.page_number || parseInt(page.pageNumber || page.page_number || "0", 10),
          // Normalize imageBase64 - backend might return image_base64 or imageBase64
          imageBase64: page.imageBase64 || page.image_base64,
        }));
      setExtractionPages(extractionPagesData);
      console.log(`[DEBUG] loadData: Loaded ${extractionPagesData.length} extraction pages for job ${currentJobId}`);
    } catch (err: any) {
      // Only set error if jobId hasn't changed
      if (currentJobIdRef.current === currentJobId) {
        setError(err.message || "Failed to load data");
      }
    } finally {
      // Only set loading to false if jobId hasn't changed
      if (currentJobIdRef.current === currentJobId) {
        setLoading(false);
      }
    }
  };

  const handlePageRoleUpdated = async () => {
    // Reload pages and issues after page role is updated
    await loadData();
  };

  const handleSavePageMetadata = async (pageId: string, updates: {
    main_heading?: string | null;
    has_annotations?: string;
    rubric_relevance?: Record<string, string>;
  }) => {
    if (!jobId) return;
    setSavingPageMetadata(true);
    try {
      await patchPageMetadata(jobId, pageId, updates);
      // Reload pages to get updated data
      await loadData();
      setEditingPageMetadata(null);
      setSaveStatus("✅ Page metadata updated successfully");
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (err: any) {
      setSaveStatus(`❌ Error: ${err.message}`);
      setTimeout(() => setSaveStatus(null), 5000);
    } finally {
      setSavingPageMetadata(false);
    }
  };

  const handleSaveIssueReview = async (issue: Issue) => {
    setSaving(true);
    setSaveStatus(null);
    try {
      await patchIssueReview(jobId, issue.issue_id, issue.ta_review);

      // Save issue scores if they exist
      if (issueScores[issue.issue_id]) {
        try {
          await postIssueScores(jobId, issue.issue_id, issueScores[issue.issue_id]);
        } catch (err) {
          console.warn("Error saving issue scores:", err);
        }
      }

      setSaveStatus("Saved successfully!");
      setTimeout(() => setSaveStatus(null), 2000);

      // Reload data to show saved review
      await loadData();
    } catch (err: any) {
      // Error messages should persist - don't auto-clear
      setSaveStatus(`Error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const updateIssueReview = (
    issueId: string,
    field: keyof NonNullable<Issue["ta_review"]>,
    value: any
  ) => {
    const updatedIssues = issues.map((issue) => {
      if (issue.issue_id === issueId) {
        return {
          ...issue,
          ta_review: {
            ...issue.ta_review,
            [field]: value,
          } as Issue["ta_review"],
        };
      }
      return issue;
    });
    setIssues(updatedIssues);
  };

  const getPageImage = (pageId: string): string | undefined => {
    // First, try to find the page in pages array to get the actual page_number
    const pageData = pages.find((p) => p.page_id === pageId);
    if (pageData && pageData.page_number) {
      // Use the page_number from PageAnalysis
      const extractionPage = extractionPages.find((p) => p.pageNumber === pageData.page_number);
      if (extractionPage) {
        return extractionPage.imageBase64;
      }
    }
    
    // Fallback: try to parse pageId directly
    const pageNumber = parseInt(pageId.replace(/^p0*/, ""), 10);
    if (!isNaN(pageNumber)) {
      const extractionPage = extractionPages.find((p) => p.pageNumber === pageNumber);
      if (extractionPage) {
        return extractionPage.imageBase64;
      }
    }
    
    // Debug: log available pageNumbers only if we have extraction pages
    if (extractionPages.length > 0) {
      const availablePageNumbers = extractionPages.map(p => p.pageNumber).sort((a, b) => a - b);
      const pageNumbersInPages = pages.map(p => p.page_number).sort((a, b) => a - b);
      console.warn(`No extraction page found for pageId: ${pageId}. Available extraction pageNumbers:`, availablePageNumbers, `Page numbers in pages:`, pageNumbersInPages);
    }
    
    return undefined;
  };

  const getScreenshotImages = (issue: Issue): string[] => {
    const images: string[] = [];
    for (const clusterId of issue.screenshot_cluster_ids) {
      // Find pages with this screenshot cluster ID
      const pagesWithCluster = pages.filter(
        (p) => p.screenshot_cluster_id === clusterId
      );
      for (const page of pagesWithCluster) {
        const image = getPageImage(page.page_id);
        if (image) {
          images.push(image);
          break; // Only add one image per cluster
        }
      }
    }
    return images;
  };

  // Group issues by heuristic_id - MUST be before any conditional returns
  // Filter out Hx_unknown and invalid heuristic IDs
  const validIssues = useMemo(() => {
    return issues.filter((issue) => {
      const heuristicId = issue.heuristic_id;
      // Only include H1-H10 (valid Nielsen heuristics)
      if (!heuristicId || heuristicId.startsWith("Hx") || heuristicId === "Hx_unknown") {
        return false;
      }
      // Validate heuristic number (1-10)
      const heuristicNumStr = heuristicId.replace(/^H/i, "").split("_")[0];
      const heuristicNum = parseInt(heuristicNumStr, 10);
      return !isNaN(heuristicNum) && heuristicNum >= 1 && heuristicNum <= 10;
    });
  }, [issues]);

  const issuesByHeuristic = useMemo(() => {
    const grouped: Record<string, Issue[]> = {};
    validIssues.forEach((issue) => {
      const key = issue.heuristic_id;
      if (!grouped[key]) {
        grouped[key] = [];
      }
      grouped[key].push(issue);
    });
    return grouped;
  }, [validIssues]);

  // Get pages by type - MUST be before any conditional returns
  const severitySummaryPages = useMemo(() => {
    return pages.filter((page) => page.page_role === "severity_summary");
  }, [pages]);

  const introPages = useMemo(() => {
    return pages.filter((page) => page.page_role === "intro");
  }, [pages]);

  const conclusionPages = useMemo(() => {
    return pages.filter((page) => page.page_role === "conclusion");
  }, [pages]);

  const aiOpportunitiesPages = useMemo(() => {
    return pages.filter((page) => page.page_role === "ai_opportunities");
  }, [pages]);

  const otherPages = useMemo(() => {
    return pages.filter(
      (page) =>
        page.page_role === "group_collab" ||
        page.page_role === "heuristic_explainer" ||
        page.page_role === "other"
    );
  }, [pages]);

  // Legacy: nonViolationPages for backward compatibility with existing code
  const nonViolationPages = useMemo(() => {
    return [...severitySummaryPages, ...introPages, ...conclusionPages, ...aiOpportunitiesPages, ...otherPages];
  }, [severitySummaryPages, introPages, conclusionPages, aiOpportunitiesPages, otherPages]);

  // Get all pages (including violation_detail pages) for navigation
  const allPagesForView = useMemo(() => {
    return pages; // All pages can be viewed
  }, [pages]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-600 mx-auto mb-4"></div>
          <p className="text-slate-600">Loading issues...</p>
        </div>
      </div>
    );
  }

  // Show job selection if no jobId
  if (!jobId && !loading) {
    return (
      <div className="min-h-screen bg-slate-50 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <div className="bg-white rounded-lg shadow-lg p-6">
            <h1 className="text-2xl font-bold text-slate-900 mb-4">Select a Submission</h1>
            {availableJobs.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-slate-600 mb-4">No submissions found. Please upload and analyze a PDF first.</p>
                <button
                  onClick={() => navigate("/upload")}
                  className="px-4 py-2 bg-sky-600 text-white rounded-md hover:bg-sky-700"
                >
                  Go to Upload
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {availableJobs.map((job) => (
                  <button
                    key={job.jobId}
                    onClick={() => {
                      setJobId(job.jobId);
                      navigate(`/issue-reviewer?jobId=${job.jobId}`, { replace: true });
                    }}
                    className="w-full text-left p-4 border border-slate-200 rounded-lg hover:border-sky-300 hover:bg-sky-50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-slate-900">{job.fileName || job.jobId}</p>
                        {job.createdAt && (
                          <p className="text-sm text-slate-500">
                            {new Date(job.createdAt).toLocaleString()}
                          </p>
                        )}
                      </div>
                      <span className="text-sky-600">→</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-4">{error}</p>
          <button
            onClick={() => navigate("/upload")}
            className="px-4 py-2 bg-sky-600 text-white rounded-md hover:bg-sky-700"
          >
            Back to Upload
          </button>
        </div>
      </div>
    );
  }

  // Determine what to show based on selection
  const currentIssue = viewMode === "issue" && validIssues.length > 0 ? validIssues[selectedIssueIndex] : null;
  const currentPage = viewMode === "page" && selectedPageIndex !== null 
    ? (selectedPageIndex < 10000
        ? nonViolationPages[selectedPageIndex] 
        : allPagesForView[selectedPageIndex - 10000])
    : null;
  const screenshotImages = currentIssue ? getScreenshotImages(currentIssue) : [];

  if (validIssues.length === 0 && pages.length === 0 && !loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-slate-600 mb-4">No issues or pages found. Please run analysis first.</p>
          <button
            onClick={() => navigate("/upload")}
            className="px-4 py-2 bg-sky-600 text-white rounded-md hover:bg-sky-700"
          >
            Back to Upload
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 py-8">
      <div className="max-w-7xl mx-auto px-4">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 mb-2">Issue-Level Reviewer Mode</h1>
            <div className="flex items-center gap-3">
              <p className="text-slate-600">Job ID: {jobId}</p>
              {availableJobs.length > 1 && (
                <select
                  value={jobId}
                  onChange={(e) => {
                    const newJobId = e.target.value;
                    console.log(`[DEBUG] Document selector: Switching from ${jobId} to ${newJobId}`);
                    // Clear all state immediately
                    setIssues([]);
                    setPages([]);
                    setExtractionPages([]);
                    setScoringOutput(null);
                    setIssueScores({});
                    setSelectedIssueIndex(0);
                    setSelectedPageIndex(null);
                    setError(null);
                    // Update jobId - this will trigger useEffect to reload data
                    setJobId(newJobId);
                    navigate(`/issue-reviewer?jobId=${newJobId}`, { replace: true });
                  }}
                  className="px-3 py-1 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  {availableJobs.map((job) => (
                    <option key={job.jobId} value={job.jobId}>
                      {job.fileName || job.jobId}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {saveStatus && (
              <div className="flex items-center gap-2">
                <span className={`text-sm font-medium ${saveStatus.includes("Error") || saveStatus.includes("❌") ? "text-red-600" : "text-green-600"}`}>
                  {saveStatus}
                </span>
                {(saveStatus.includes("Error") || saveStatus.includes("❌")) && (
                  <button
                    onClick={() => setSaveStatus(null)}
                    className="text-red-600 hover:text-red-800 text-xs font-bold"
                    title="Dismiss error"
                  >
                    ✕
                  </button>
                )}
              </div>
            )}
            <button
              onClick={() => navigate("/upload")}
              className="px-4 py-2 bg-slate-600 text-white rounded-md hover:bg-slate-700"
            >
              Back to Upload
            </button>
          </div>
        </div>

        {/* AI Final Grading Section - At the top */}
        {!scoringOutput && !recomputing && issues.length > 0 && (
          <div className="bg-blue-50 rounded-lg shadow-lg p-6 mb-6 border-2 border-blue-200">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-blue-900 mb-2">AI Final Grading</h2>
                <p className="text-sm text-blue-700">
                  Run AI grading based on all issues and pages. This will calculate the final overall score and rubric component scores.
                </p>
              </div>
              <button
                onClick={handleRecomputeScores}
                disabled={recomputing || !jobId}
                className="px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold text-lg"
              >
                {recomputing ? "Running AI Grading..." : "Run AI Grading"}
              </button>
            </div>
          </div>
        )}

        {/* Loading Indicator for AI Grading */}
        {recomputing && (
          <div className="bg-blue-50 rounded-lg shadow-lg p-6 mb-6 border-2 border-blue-200">
            <div className="flex items-center justify-center space-x-3">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <div>
                <h3 className="text-lg font-semibold text-blue-900">Running AI Grading...</h3>
                <p className="text-sm text-blue-700">Analyzing all issues and calculating final scores. This may take a moment.</p>
              </div>
            </div>
          </div>
        )}

        {/* Changes Summary Modal */}
        {showChangesModal && changesSummary && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
              <div className="sticky top-0 bg-white border-b border-slate-200 p-6 flex items-center justify-between">
                <h2 className="text-2xl font-bold text-slate-900">Re-run Grading Results</h2>
                <button
                  onClick={() => setShowChangesModal(false)}
                  className="text-slate-500 hover:text-slate-700"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="p-6 space-y-6">
                {changesSummary && (
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900 mb-2">What Changed After Re-run</h3>
                    <p className="text-sm text-slate-600 mb-4">
                      The section below summarizes how the scores moved in this re-run compared to the previous grading output.
                    </p>
                    <h4 className="text-md font-semibold text-slate-900 mb-3">Score Changes</h4>
                    {changesSummary.overall_score_change && (
                      <div className="bg-blue-50 rounded-lg p-4 mb-4 border border-blue-200">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-blue-900">Overall Score</span>
                          <div className="flex items-center gap-2">
                            <span className="text-blue-700">{changesSummary.overall_score_change.old}</span>
                            <span className="text-blue-500">→</span>
                            <span className="text-blue-900 font-bold">{changesSummary.overall_score_change.new}</span>
                            <span className={`font-semibold ${changesSummary.overall_score_change.delta >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                              ({changesSummary.overall_score_change.delta > 0 ? '+' : ''}{changesSummary.overall_score_change.delta})
                            </span>
                          </div>
                        </div>
                      </div>
                    )}
                    {changesSummary.component_changes && changesSummary.component_changes.length > 0 && (
                      <div className="space-y-2 mb-4">
                        <h4 className="font-semibold text-slate-700">Component Changes:</h4>
                        {changesSummary.component_changes.map((change: any, idx: number) => (
                          <div key={idx} className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                            <div className="flex items-center justify-between">
                              <span className="text-sm font-medium text-slate-700 capitalize">{change.component.replace(/_/g, " ")}</span>
                              <div className="flex items-center gap-2">
                                <span className="text-slate-600">{change.old}</span>
                                <span className="text-slate-400">→</span>
                                <span className="font-semibold text-slate-900">{change.new}</span>
                                <span className={`text-sm font-semibold ${change.delta >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                  ({change.delta > 0 ? '+' : ''}{change.delta})
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {changesSummary.bonus_changes && changesSummary.bonus_changes.length > 0 && (
                      <div className="space-y-2">
                        <h4 className="font-semibold text-slate-700">Bonus Changes:</h4>
                        {changesSummary.bonus_changes.map((change: any, idx: number) => (
                          <div key={idx} className="bg-amber-50 rounded-lg p-3 border border-amber-200">
                            <div className="flex items-center justify-between">
                              <span className="text-sm font-medium text-amber-700 capitalize">{change.component.replace(/_/g, " ")}</span>
                              <div className="flex items-center gap-2">
                                <span className="text-amber-600">{change.old}</span>
                                <span className="text-amber-400">→</span>
                                <span className="font-semibold text-amber-900">{change.new}</span>
                                <span className={`text-sm font-semibold ${change.delta >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                  ({change.delta > 0 ? '+' : ''}{change.delta})
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {rubricComponents.some(comp => rubricComments[comp.key]?.trim()) && (
                  <div className="bg-white rounded-lg border border-slate-200 p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-lg font-semibold text-slate-900">TA Rubric Comments (This Run)</h3>
                      <span className="text-xs text-slate-500">
                        Loaded from {jobId}_rubric_comments.json before re-run
                      </span>
                    </div>
                    <p className="text-xs text-slate-600">
                      Each entry mirrors what you saved under “Rubric Component Comments”, along with how the system handled it for the current scoring run.
                    </p>
                    <div className="space-y-3">
                      {rubricComponents
                        .filter(component => rubricComments[component.key]?.trim())
                        .map(component => {
                          const comment = rubricComments[component.key];
                          const evaluation = evaluateRubricComment(comment);
                          return (
                            <div key={component.key} className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                              <div className="flex items-center justify-between mb-1">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm font-semibold text-slate-800">{component.label}</span>
                                  <span className="text-xs text-slate-500">(Max: {component.max})</span>
                                </div>
                                <span className={`px-2 py-1 rounded text-xs font-semibold ${evaluation.badgeClass}`}>
                                  {evaluation.badge}
                                </span>
                              </div>
                              <p className="text-sm text-slate-800 whitespace-pre-wrap bg-white p-2 rounded border border-slate-200">
                                {comment}
                              </p>
                              <p className="text-xs text-slate-600 mt-2">{evaluation.detail}</p>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                )}

                {/* Prompt analysis from TA comments (intentionally removed - only show score changes here) */}
                
                <div className="flex justify-end pt-4 border-t border-slate-200">
                  <button
                    onClick={() => setShowChangesModal(false)}
                    className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Scoring Output Display - At the top */}
        {scoringOutput && (
          <div className="bg-gradient-to-r from-purple-50 to-indigo-50 rounded-lg shadow-lg p-6 mb-6 border-2 border-purple-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-purple-900">AI Final Grading Results</h2>
              <div className="flex items-center gap-2">
                {changesSummary && (
                  <button
                    onClick={() => setShowChangesModal(true)}
                    className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 text-sm"
                  >
                    View Changes
                  </button>
                )}
                <button
                  onClick={handleRecomputeScores}
                  disabled={recomputing || !jobId}
                  className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  {recomputing ? "Recomputing..." : "Re-run Grading"}
                </button>
                <button
                  onClick={() => setScoringOutput(null)}
                  className="text-purple-600 hover:text-purple-800"
                  title="Close"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <div className="space-y-4">
              <div className="bg-white rounded-lg p-4 border border-purple-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold text-purple-700">Overall Score</span>
                  <span className="text-3xl font-bold text-purple-900">{scoringOutput.overall_score_0_100} / 100</span>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-3">
                {Object.entries(scoringOutput.rubric_scores).map(([key, score]) => {
                  const scoreValue = typeof score === "object" && "points" in score ? score.points : score;
                  const maxValue = typeof score === "object" && "max" in score ? score.max : 
                    (key === "coverage" ? 15 : key === "violation_quality" ? 20 : 
                     key === "group_integration" ? 15 : 10);
                  const explanation = typeof score === "object" && "explanation" in score ? score.explanation : "";
                  return (
                    <div key={key} className="bg-white rounded-lg p-4 border border-purple-200">
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm font-semibold text-purple-700 capitalize">
                          {key.replace(/_/g, " ")}
                        </div>
                        <div className="text-lg font-bold text-purple-900">{scoreValue} / {maxValue}</div>
                      </div>
                      {explanation && (
                        <div className="text-xs text-slate-600 mt-2 pl-2 border-l-2 border-purple-300">
                          {explanation}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              {scoringOutput.bonus_scores && (
                <div className="bg-amber-50 rounded-lg p-4 border border-amber-200">
                  <h3 className="text-sm font-semibold text-amber-700 mb-3">Bonus Scores</h3>
                  <div className="grid grid-cols-1 gap-3">
                    {Object.entries(scoringOutput.bonus_scores).map(([key, score]) => {
                      const scoreValue = typeof score === "object" && "points" in score ? score.points : score;
                      const maxValue = typeof score === "object" && "max" in score ? score.max : 
                        (key === "bonus_ai_opportunities" ? 3 : 2);
                      const explanation = typeof score === "object" && "explanation" in score ? score.explanation : "";
                      // Show bonus_ai_opportunities even if 0, but hide other bonuses if 0
                      if (scoreValue === 0 && key !== "bonus_ai_opportunities") return null;
                      return (
                        <div key={key} className="bg-white rounded-lg p-4 border border-amber-200">
                          <div className="flex items-center justify-between mb-2">
                            <div className="text-sm font-semibold text-amber-700 capitalize">
                              {key === "bonus_ai_opportunities" ? "AI Opportunities" : key.replace(/_/g, " ").replace(/bonus /i, "")}
                            </div>
                            <div className="text-lg font-bold text-amber-900">{scoreValue} / {maxValue}</div>
                          </div>
                          {explanation && (
                            <div className="text-xs text-slate-600 mt-2 pl-2 border-l-2 border-amber-300">
                              {explanation}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              <div className="bg-white rounded-lg p-4 border border-purple-200">
                <h3 className="text-sm font-semibold text-purple-700 mb-2">Summary Comment</h3>
                {scoringOutput.summary_comment ? (
                  <p className="text-sm text-slate-700">{scoringOutput.summary_comment}</p>
                ) : (
                  <p className="text-sm text-slate-400 italic">No summary comment available.</p>
                )}
              </div>
              {scoringOutput.ai_vs_ta_notes && (
                <div className="bg-white rounded-lg p-4 border border-amber-200">
                  <h3 className="text-sm font-semibold text-amber-700 mb-2">AI vs TA Notes</h3>
                  <p className="text-sm text-slate-700">{scoringOutput.ai_vs_ta_notes}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Issue List Sidebar */}
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-3">
            <div className="bg-white rounded-lg shadow-lg p-6">
              <h2 className="text-xl font-bold text-slate-900 mb-4">
                Content
              </h2>
              <div className="space-y-3 max-h-[calc(100vh-180px)] overflow-y-auto">
                {/* Issues grouped by heuristic */}
                {Object.entries(issuesByHeuristic).map(([heuristicId, heuristicIssues]) => (
                  <div key={heuristicId} className="border border-slate-200 rounded-lg p-2">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-bold text-purple-700">{heuristicId}</span>
                      <span className="text-xs text-slate-500">
                        {heuristicIssues.length} issue{heuristicIssues.length > 1 ? "s" : ""}
                      </span>
                    </div>
                    <div className="space-y-1">
                      {heuristicIssues.map((issue, idx) => {
                        const globalIndex = validIssues.findIndex((i) => i.issue_id === issue.issue_id);
                        return (
                          <button
                            key={issue.issue_id}
                            onClick={() => {
                              setViewMode("issue");
                              setSelectedIssueIndex(globalIndex);
                              setSelectedPageIndex(null);
                            }}
                            className={`w-full text-left p-2 rounded border transition-colors ${
                              viewMode === "issue" && globalIndex === selectedIssueIndex
                                ? "border-purple-500 bg-purple-50"
                                : "border-slate-200 bg-white hover:border-slate-300"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium text-slate-700">
                                {issue.title}
                              </span>
                              {issue.ta_review && (
                                <span className="text-xs bg-green-100 text-green-800 px-1.5 py-0.5 rounded">
                                  ✓
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-slate-500">
                              {issue.pages_involved.length} page(s)
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}

                {/* Severity Summary Pages */}
                {severitySummaryPages.length > 0 && (
                  <div className="border-t border-slate-300 pt-3 mt-3">
                    <h3 className="text-sm font-semibold text-slate-700 mb-2">
                      Severity Summary Pages ({severitySummaryPages.length})
                    </h3>
                    <div className="space-y-1">
                      {severitySummaryPages.map((page, idx) => {
                        const globalIdx = nonViolationPages.findIndex((p) => p.page_id === page.page_id);
                        return (
                          <button
                            key={page.page_id}
                            onClick={() => {
                              setViewMode("page");
                              setSelectedPageIndex(globalIdx);
                              setSelectedIssueIndex(-1);
                            }}
                            className={`w-full text-left p-2 rounded border transition-colors ${
                              viewMode === "page" && globalIdx === selectedPageIndex
                                ? "border-blue-500 bg-blue-50"
                                : "border-slate-200 bg-white hover:border-slate-300"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium text-slate-700">
                                Page {page.page_number}
                              </span>
                              <div className="flex items-center gap-1">
                                {page.ta_review && (page.ta_review.override_reason || page.ta_review.ta_comment) && (
                                  <span className="text-xs bg-green-100 text-green-800 px-1.5 py-0.5 rounded">
                                    ✓
                                  </span>
                                )}
                                <span className="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">
                                  severity_summary
                                </span>
                              </div>
                            </div>
                            {page.main_heading && (
                              <div className="text-xs text-slate-500 line-clamp-1">
                                {page.main_heading}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Intro Pages */}
                {introPages.length > 0 && (
                  <div className="border-t border-slate-300 pt-3 mt-3">
                    <h3 className="text-sm font-semibold text-slate-700 mb-2">
                      Introduction Pages ({introPages.length})
                    </h3>
                    <div className="space-y-1">
                      {introPages.map((page, idx) => {
                        const globalIdx = nonViolationPages.findIndex((p) => p.page_id === page.page_id);
                        return (
                          <button
                            key={page.page_id}
                            onClick={() => {
                              setViewMode("page");
                              setSelectedPageIndex(globalIdx);
                              setSelectedIssueIndex(-1);
                            }}
                            className={`w-full text-left p-2 rounded border transition-colors ${
                              viewMode === "page" && globalIdx === selectedPageIndex
                                ? "border-blue-500 bg-blue-50"
                                : "border-slate-200 bg-white hover:border-slate-300"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium text-slate-700">
                                Page {page.page_number}
                              </span>
                              <div className="flex items-center gap-1">
                                {page.ta_review && (page.ta_review.override_reason || page.ta_review.ta_comment) && (
                                  <span className="text-xs bg-green-100 text-green-800 px-1.5 py-0.5 rounded">
                                    ✓
                                  </span>
                                )}
                                <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                                  intro
                                </span>
                              </div>
                            </div>
                            {page.main_heading && (
                              <div className="text-xs text-slate-500 line-clamp-1">
                                {page.main_heading}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Conclusion Pages */}
                {conclusionPages.length > 0 && (
                  <div className="border-t border-slate-300 pt-3 mt-3">
                    <h3 className="text-sm font-semibold text-slate-700 mb-2">
                      Conclusion Pages ({conclusionPages.length})
                    </h3>
                    <div className="space-y-1">
                      {conclusionPages.map((page, idx) => {
                        const globalIdx = nonViolationPages.findIndex((p) => p.page_id === page.page_id);
                        return (
                          <button
                            key={page.page_id}
                            onClick={() => {
                              setViewMode("page");
                              setSelectedPageIndex(globalIdx);
                              setSelectedIssueIndex(-1);
                            }}
                            className={`w-full text-left p-2 rounded border transition-colors ${
                              viewMode === "page" && globalIdx === selectedPageIndex
                                ? "border-blue-500 bg-blue-50"
                                : "border-slate-200 bg-white hover:border-slate-300"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium text-slate-700">
                                Page {page.page_number}
                              </span>
                              <div className="flex items-center gap-1">
                                {page.ta_review && (page.ta_review.override_reason || page.ta_review.ta_comment) && (
                                  <span className="text-xs bg-green-100 text-green-800 px-1.5 py-0.5 rounded">
                                    ✓
                                  </span>
                                )}
                                <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
                                  conclusion
                                </span>
                              </div>
                            </div>
                            {page.main_heading && (
                              <div className="text-xs text-slate-500 line-clamp-1">
                                {page.main_heading}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* AI Opportunities Pages */}
                {aiOpportunitiesPages.length > 0 && (
                  <div className="border-t border-slate-300 pt-3 mt-3">
                    <h3 className="text-sm font-semibold text-slate-700 mb-2">
                      AI Opportunities Pages ({aiOpportunitiesPages.length})
                    </h3>
                    <div className="space-y-1">
                      {aiOpportunitiesPages.map((page, idx) => {
                        const globalIdx = nonViolationPages.findIndex((p) => p.page_id === page.page_id);
                        return (
                          <button
                            key={page.page_id}
                            onClick={() => {
                              setViewMode("page");
                              setSelectedPageIndex(globalIdx);
                              setSelectedIssueIndex(-1);
                            }}
                            className={`w-full text-left p-2 rounded border transition-colors ${
                              viewMode === "page" && globalIdx === selectedPageIndex
                                ? "border-blue-500 bg-blue-50"
                                : "border-slate-200 bg-white hover:border-slate-300"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium text-slate-700">
                                Page {page.page_number}
                              </span>
                              <div className="flex items-center gap-1">
                                {page.ta_review && (page.ta_review.override_reason || page.ta_review.ta_comment) && (
                                  <span className="text-xs bg-green-100 text-green-800 px-1.5 py-0.5 rounded">
                                    ✓
                                  </span>
                                )}
                                <span className="text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">
                                  ai_opportunities
                                </span>
                              </div>
                            </div>
                            {page.main_heading && (
                              <div className="text-xs text-slate-500 line-clamp-1">
                                {page.main_heading}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Other Pages */}
                {otherPages.length > 0 && (
                  <div className="border-t border-slate-300 pt-3 mt-3">
                    <h3 className="text-sm font-semibold text-slate-700 mb-2">
                      Other Pages ({otherPages.length})
                    </h3>
                    <div className="space-y-1">
                      {otherPages.map((page, idx) => {
                        const globalIdx = nonViolationPages.findIndex((p) => p.page_id === page.page_id);
                        return (
                          <button
                            key={page.page_id}
                            onClick={() => {
                              setViewMode("page");
                              setSelectedPageIndex(globalIdx);
                              setSelectedIssueIndex(-1);
                            }}
                            className={`w-full text-left p-2 rounded border transition-colors ${
                              viewMode === "page" && globalIdx === selectedPageIndex
                                ? "border-blue-500 bg-blue-50"
                                : "border-slate-200 bg-white hover:border-slate-300"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium text-slate-700">
                                Page {page.page_number}
                              </span>
                              <div className="flex items-center gap-1">
                                {page.ta_review && (page.ta_review.override_reason || page.ta_review.ta_comment) && (
                                  <span className="text-xs bg-green-100 text-green-800 px-1.5 py-0.5 rounded">
                                    ✓
                                  </span>
                                )}
                                <span className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                                  {page.page_role}
                                </span>
                              </div>
                            </div>
                            {page.main_heading && (
                              <div className="text-xs text-slate-500 line-clamp-1">
                                {page.main_heading}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Main Content: Two Columns */}
          <div className="col-span-9">
            {viewMode === "issue" && currentIssue ? (
              <div>
                {/* Issue Overview */}
                <div className="bg-white rounded-lg shadow-lg p-6">
                  <h2 className="text-xl font-bold text-slate-900 mb-4">Issue Overview</h2>
                
                <div className="space-y-4">
                  {/* Issue Name */}
                  <div>
                    <label className="text-sm font-semibold text-slate-700 block mb-1">
                      Issue Name
                    </label>
                    <p className="text-base text-slate-900">
                      {(() => {
                        // Extract heuristic number from heuristic_id (e.g., "H3" -> 3)
                        const heuristicNum = parseInt(currentIssue.heuristic_id.replace(/^H/i, "").split("_")[0], 10);
                        const heuristic = heuristicsInfo.find((h) => h.number === heuristicNum);
                        const heuristicName = heuristic ? heuristic.name : currentIssue.heuristic_id;
                        return `${currentIssue.heuristic_id}: ${heuristicName}`;
                      })()}
                    </p>
                  </div>

                  {/* Heuristic */}
                  <div>
                    <label className="text-sm font-semibold text-slate-700 block mb-1">
                      Heuristic
                    </label>
                    <span className="inline-block px-3 py-1 bg-purple-100 text-purple-800 rounded-md font-medium">
                      {currentIssue.heuristic_id}
                    </span>
                  </div>

                  {/* Pages that contributed */}
                  <div>
                    <label className="text-sm font-semibold text-slate-700 block mb-2">
                      Pages that contributed to this issue
                    </label>
                    <div className="space-y-3">
                      {currentIssue.pages_involved.map((pageId) => {
                        // Handle different pageId formats: "p01", "p1", "p03", etc.
                        const pageNumber = parseInt(pageId.replace(/^p0*/, ""), 10) || parseInt(pageId.replace("p", ""), 10);
                        const pageImage = getPageImage(pageId);
                        const pageData = pages.find((p) => p.page_id === pageId);
                        return (
                          <div
                            key={pageId}
                            className="border border-slate-200 rounded-lg p-3 bg-slate-50"
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-sm font-medium text-slate-900">
                                Page {pageNumber}
                              </span>
                              {pageData && (
                                <div className="flex items-center gap-2">
                                  <span className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                                    {pageData.page_role}
                                  </span>
                                  <EditPageRoleButton
                                    jobId={jobId}
                                    pageId={pageData.page_id}
                                    currentRole={pageData.page_role}
                                    isReanalyzing={reanalyzingPage === pageData.page_id}
                                    onReanalyzingChange={setReanalyzingPage}
                                    onRoleUpdated={handlePageRoleUpdated}
                                  />
                                </div>
                              )}
                            </div>
                            <div className="w-full">
                              {pageImage ? (
                                <img
                                  src={pageImage}
                                  alt={`Page ${pageNumber}`}
                                  className="w-full rounded-lg border border-slate-200 bg-white"
                                  onError={(e) => {
                                    console.error(`Failed to load image for page ${pageNumber}`, e);
                                    e.currentTarget.style.display = 'none';
                                  }}
                                />
                              ) : (
                                <div className="w-full h-48 bg-slate-100 rounded-lg border border-slate-200 flex items-center justify-center">
                                  <div className="text-center">
                                    <p className="text-sm text-slate-500 mb-1">No image available</p>
                                    <p className="text-xs text-slate-400">Page {pageNumber} (ID: {pageId})</p>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Page Analysis Details */}
                  {currentIssue.pages_involved.length > 0 && (
                    <div>
                      <label className="text-sm font-semibold text-slate-700 block mb-2">
                        Page Analysis Details
                      </label>
                      <div className="space-y-3 max-h-96 overflow-y-auto">
                        {currentIssue.pages_involved.map((pageId) => {
                          const pageData = pages.find((p) => p.page_id === pageId);
                          if (!pageData) return null;

                          return (
                            <div key={pageId} className="border border-slate-200 rounded-lg p-3 bg-slate-50">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-sm font-medium text-slate-900">
                                  Page {pageData.page_number}
                                </span>
                                <div className="flex items-center gap-2">
                                  <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                                    {pageData.page_role}
                                  </span>
                                  <EditPageRoleButton
                                    jobId={jobId}
                                    pageId={pageData.page_id}
                                    currentRole={pageData.page_role}
                                    isReanalyzing={reanalyzingPage === pageData.page_id}
                                    onReanalyzingChange={setReanalyzingPage}
                                    onRoleUpdated={handlePageRoleUpdated}
                                  />
                                </div>
                              </div>

                              {/* Fragments */}
                              {pageData.fragments && pageData.fragments.length > 0 && (
                                <div className="mb-2">
                                  <label className="text-xs font-semibold text-slate-600 block mb-1">
                                    Fragments ({pageData.fragments.length})
                                  </label>
                                  <div className="space-y-1">
                                    {pageData.fragments
                                      .filter((f) => f.heuristic_id === currentIssue.heuristic_id)
                                      .map((fragment, idx) => (
                                        <div key={idx} className="p-2 bg-white rounded border border-slate-200">
                                          <div className="flex items-center gap-2 mb-1">
                                            <span className="text-xs font-medium text-purple-700">
                                              {fragment.heuristic_id}
                                            </span>
                                            {fragment.severity_hint && (
                                              <span className="text-xs bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded">
                                                {fragment.severity_hint}
                                              </span>
                                            )}
                                          </div>
                                          <p className="text-xs text-slate-800">{fragment.text_summary}</p>
                                          {fragment.fragment_role && fragment.fragment_role.length > 0 && (
                                            <div className="mt-1 flex flex-wrap gap-1">
                                              {fragment.fragment_role.map((role, roleIdx) => (
                                                <span
                                                  key={roleIdx}
                                                  className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded"
                                                >
                                                  {role}
                                                </span>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      ))}
                                  </div>
                                </div>
                              )}

                              {/* Severity Summary */}
                              {pageData.severity_summary && (
                                <div className="mb-2">
                                  <label className="text-xs font-semibold text-slate-600 block mb-1">
                                    Severity Summary
                                  </label>
                                  <div className="p-2 bg-white rounded border border-slate-200 text-xs">
                                    <p>
                                      <span className="font-medium">Visualization:</span>{" "}
                                      {pageData.severity_summary.visualization}
                                    </p>
                                    <p>
                                      <span className="font-medium">Coverage:</span>{" "}
                                      {pageData.severity_summary.coverage_scope}
                                    </p>
                                    <p>
                                      <span className="font-medium">Clarity:</span>{" "}
                                      {pageData.severity_summary.mapping_clarity}
                                    </p>
                                    {pageData.severity_summary.llm_note && (
                                      <p className="mt-1 text-slate-700">
                                        {pageData.severity_summary.llm_note}
                                      </p>
                                    )}
                                  </div>
                                </div>
                              )}

                              {/* Page Metadata */}
                              <div>
                                <div className="flex items-center justify-between mb-1">
                                  <label className="text-xs font-semibold text-slate-600 block">
                                    Page Metadata
                                  </label>
                                  {editingPageMetadata !== pageData.page_id ? (
                                    <button
                                      onClick={() => setEditingPageMetadata(pageData.page_id)}
                                      className="text-xs text-blue-600 hover:text-blue-800 underline"
                                    >
                                      Edit
                                    </button>
                                  ) : (
                                    <div className="flex gap-1">
                                      <button
                                        onClick={() => setEditingPageMetadata(null)}
                                        className="text-xs text-slate-600 hover:text-slate-800"
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  )}
                                </div>
                                {editingPageMetadata === pageData.page_id ? (
                                  <PageMetadataEditor
                                    pageData={pageData}
                                    onSave={(updates) => handleSavePageMetadata(pageData.page_id, updates)}
                                    onCancel={() => setEditingPageMetadata(null)}
                                    saving={savingPageMetadata}
                                    size="small"
                                  />
                                ) : (
                                  <div className="space-y-1 text-xs">
                                    {/* Main Heading */}
                                    {pageData.main_heading && (
                                      <div className="flex justify-between">
                                        <span className="text-slate-600">Main Heading:</span>
                                        <span className="font-medium text-slate-800 max-w-[60%] text-right truncate" title={pageData.main_heading}>
                                          {pageData.main_heading}
                                        </span>
                                      </div>
                                    )}

                                    {/* Screenshot Annotations - Only for violation_detail pages */}
                                    {pageData.page_role === "violation_detail" && (
                                      <div className="flex justify-between items-center">
                                        <span className="text-slate-600">Screenshot Annotations:</span>
                                        <span className={`font-medium px-2 py-0.5 rounded ${
                                          pageData.has_annotations === "high" ? "bg-green-100 text-green-800" :
                                          pageData.has_annotations === "medium" ? "bg-amber-100 text-amber-800" :
                                          pageData.has_annotations === "low" ? "bg-yellow-100 text-yellow-800" :
                                          "bg-red-100 text-red-800"
                                        }`}>
                                          {pageData.has_annotations === "high" ? "Highly Annotated" :
                                           pageData.has_annotations === "medium" ? "Moderately Annotated" :
                                           pageData.has_annotations === "low" ? "Minimally Annotated" :
                                           "No Annotations"}
                                        </span>
                                      </div>
                                    )}

                                    {/* Rubric Relevance (excluding coverage) */}
                                    <div className="pt-1 border-t border-slate-200 mt-1">
                                      <div className="text-slate-600 font-semibold mb-1">Rubric Relevance:</div>
                                      <div className="space-y-0.5">
                                        {Object.entries(pageData.rubric_relevance)
                                          .filter(([key]) => key !== "coverage")
                                          .map(([key, value]) => (
                                            <div key={key} className="flex justify-between">
                                              <span className="text-slate-600 capitalize">{key.replace(/_/g, " ")}:</span>
                                              <span className={`font-medium ${
                                                value === "high" ? "text-green-700" :
                                                value === "med" ? "text-amber-700" :
                                                value === "low" ? "text-blue-700" :
                                                "text-slate-500"
                                              }`}>
                                                {value}
                                              </span>
                                            </div>
                                          ))}
                                      </div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
            ) : viewMode === "page" && currentPage ? (
              <div className="bg-white rounded-lg shadow-lg p-6">
                <h2 className="text-xl font-bold text-slate-900 mb-4">
                  Page {currentPage.page_number} - {currentPage.page_role}
                </h2>
                
                <div className="space-y-4">
                  {/* Page Screenshot - Show at top */}
                  {getPageImage(currentPage.page_id) && (
                    <div>
                      <label className="text-sm font-semibold text-slate-700 block mb-2">
                        Page Screenshot
                      </label>
                      <img
                        src={getPageImage(currentPage.page_id)}
                        alt={`Page ${currentPage.page_number}`}
                        className="w-full rounded-lg border border-slate-200 shadow-sm"
                      />
                    </div>
                  )}

                  {currentPage.main_heading && (
                    <div>
                      <label className="text-sm font-semibold text-slate-700 block mb-1">
                        Main Heading
                      </label>
                      <p className="text-base text-slate-900">{currentPage.main_heading}</p>
                    </div>
                  )}

                  <div>
                    <label className="text-sm font-semibold text-slate-700 block mb-1">
                      Page Role
                    </label>
                    <div className="flex items-center gap-2">
                      <span className="inline-block px-3 py-1 bg-blue-100 text-blue-800 rounded-md font-medium">
                        {currentPage.page_role}
                      </span>
                      <EditPageRoleButton
                        jobId={jobId}
                        pageId={currentPage.page_id}
                        currentRole={currentPage.page_role}
                        isReanalyzing={reanalyzingPage === currentPage.page_id}
                        onReanalyzingChange={setReanalyzingPage}
                        onRoleUpdated={handlePageRoleUpdated}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-sm font-semibold text-slate-700 block mb-1">
                      Annotations Level
                    </label>
                    <span className="inline-block px-3 py-1 bg-slate-100 text-slate-800 rounded-md font-medium">
                      {currentPage.has_annotations}
                    </span>
                  </div>

                  {currentPage.fragments && currentPage.fragments.length > 0 && (
                    <div>
                      <label className="text-sm font-semibold text-slate-700 block mb-2">
                        Fragments ({currentPage.fragments.length})
                      </label>
                      <div className="space-y-2">
                        {currentPage.fragments.map((fragment, idx) => (
                          <div key={idx} className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-medium text-purple-700">
                                {fragment.heuristic_id}
                              </span>
                              {fragment.severity_hint && (
                                <span className="text-xs bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded">
                                  {fragment.severity_hint}
                                </span>
                              )}
                            </div>
                            <p className="text-sm text-slate-800">{fragment.text_summary}</p>
                            {fragment.fragment_role && fragment.fragment_role.length > 0 && (
                              <div className="mt-1 flex flex-wrap gap-1">
                                {fragment.fragment_role.map((role, roleIdx) => (
                                  <span
                                    key={roleIdx}
                                    className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded"
                                  >
                                    {role}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {currentPage.severity_summary && (
                    <div>
                      <label className="text-sm font-semibold text-slate-700 block mb-2">
                        Severity Summary
                      </label>
                      <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                        <div className="space-y-1 text-sm">
                          <p>
                            <span className="font-medium">Visualization:</span>{" "}
                            {currentPage.severity_summary.visualization}
                          </p>
                          <p>
                            <span className="font-medium">Coverage:</span>{" "}
                            {currentPage.severity_summary.coverage_scope}
                          </p>
                          <p>
                            <span className="font-medium">Clarity:</span>{" "}
                            {currentPage.severity_summary.mapping_clarity}
                          </p>
                          {currentPage.severity_summary.llm_note && (
                            <p className="mt-2 text-slate-700">
                              {currentPage.severity_summary.llm_note}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-sm font-semibold text-slate-700 block">
                        Page Metadata
                      </label>
                      {editingPageMetadata !== currentPage.page_id ? (
                        <button
                          onClick={() => setEditingPageMetadata(currentPage.page_id)}
                          className="text-sm text-blue-600 hover:text-blue-800 underline"
                        >
                          Edit
                        </button>
                      ) : (
                        <div className="flex gap-1">
                          <button
                            onClick={() => setEditingPageMetadata(null)}
                            className="text-sm text-slate-600 hover:text-slate-800"
                          >
                            Cancel
                          </button>
                        </div>
                      )}
                    </div>
                    {editingPageMetadata === currentPage.page_id ? (
                      <PageMetadataEditor
                        pageData={currentPage}
                        onSave={(updates) => handleSavePageMetadata(currentPage.page_id, updates)}
                        onCancel={() => setEditingPageMetadata(null)}
                        saving={savingPageMetadata}
                        size="normal"
                      />
                    ) : (
                      <div className="space-y-2 text-sm">
                        {/* Main Heading */}
                        {currentPage.main_heading && (
                          <div className="flex justify-between">
                            <span className="text-slate-600">Main Heading:</span>
                            <span className="font-medium text-slate-800 max-w-[60%] text-right truncate" title={currentPage.main_heading}>
                              {currentPage.main_heading}
                            </span>
                          </div>
                        )}

                        {/* Screenshot Annotations - Only for violation_detail pages */}
                        {currentPage.page_role === "violation_detail" && (
                          <div className="flex justify-between items-center">
                            <span className="text-slate-600">Screenshot Annotations:</span>
                            <span className={`font-medium px-3 py-1 rounded ${
                              currentPage.has_annotations === "high" ? "bg-green-100 text-green-800" :
                              currentPage.has_annotations === "medium" ? "bg-amber-100 text-amber-800" :
                              currentPage.has_annotations === "low" ? "bg-yellow-100 text-yellow-800" :
                              "bg-red-100 text-red-800"
                            }`}>
                              {currentPage.has_annotations === "high" ? "Highly Annotated" :
                               currentPage.has_annotations === "medium" ? "Moderately Annotated" :
                               currentPage.has_annotations === "low" ? "Minimally Annotated" :
                               "No Annotations"}
                            </span>
                          </div>
                        )}

                        {/* Rubric Relevance (excluding coverage) */}
                        <div className="pt-2 border-t border-slate-200">
                          <div className="text-slate-600 font-semibold mb-2">Rubric Relevance:</div>
                          <div className="grid grid-cols-2 gap-2">
                            {Object.entries(currentPage.rubric_relevance)
                              .filter(([key]) => key !== "coverage")
                              .map(([key, value]) => (
                                <div key={key} className="flex justify-between">
                                  <span className="text-slate-600 capitalize">{key.replace(/_/g, " ")}:</span>
                                  <span className={`font-medium ${
                                    value === "high" ? "text-green-700" :
                                    value === "med" ? "text-amber-700" :
                                    value === "low" ? "text-blue-700" :
                                    "text-slate-500"
                                  }`}>
                                    {value}
                                  </span>
                                </div>
                              ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* TA Review Section for Pages */}
                <div className="mt-6 pt-6 border-t border-slate-200">
                  <h3 className="text-lg font-bold text-slate-900 mb-4">TA Review</h3>
                  
                  <div className="space-y-4">
                    {/* Override Reason */}
                    <div>
                      <label className="text-sm font-semibold text-slate-700 block mb-1">
                        Override Reason
                      </label>
                      <textarea
                        value={currentPage.ta_review?.override_reason || ""}
                        onChange={(e) => {
                          const updatedPages = pages.map((p) =>
                            p.page_id === currentPage.page_id
                              ? { ...p, ta_review: { ...p.ta_review, override_reason: e.target.value || undefined } }
                              : p
                          );
                          setPages(updatedPages);
                        }}
                        rows={3}
                        className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                        placeholder="Explain any overrides or corrections for this page..."
                      />
                    </div>

                    {/* Save Button */}
                    <button
                      onClick={async () => {
                        try {
                          setSaving(true);
                          const response = await fetch(
                            `${API_BASE}/api/update-page-review?jobId=${jobId}&pageId=${currentPage.page_id}`,
                            {
                              method: "PATCH",
                              headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({
                                override_reason: currentPage.ta_review?.override_reason,
                                ta_comment: currentPage.ta_review?.ta_comment,
                              }),
                            }
                          );
                          if (!response.ok) {
                            const errorData = await response.json().catch(() => ({ detail: "Failed to save page review" }));
                            throw new Error(errorData.detail || `HTTP ${response.status}: Failed to save page review`);
                          }
                          setSaveStatus("Page review saved successfully!");
                          setTimeout(() => setSaveStatus(null), 2000);
                          // Reload pages to get updated ta_review from backend
                          await loadData();
                        } catch (err: any) {
                          // Error messages should persist - don't auto-clear
                          setSaveStatus(`Error: ${err.message}`);
                          console.error("Error saving page review:", err);
                        } finally {
                          setSaving(false);
                        }
                      }}
                      disabled={saving}
                      className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                    >
                      {saving ? "Saving..." : "Save Page Review"}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-white rounded-lg shadow-lg p-6 text-center">
                <p className="text-slate-600">Please select an issue or page from the sidebar</p>
              </div>
            )}

          </div>
        </div>

        {/* Prompt analysis from TA comments */}
        <div className="mt-8 bg-white rounded-lg shadow-lg p-6 mb-6 border border-slate-200">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-xl font-bold text-slate-900 mb-2">Regenerate Prompt Based on TA Feedback</h2>
              <p className="text-sm text-slate-700 leading-relaxed">
                If you are not satisfied with the current automatic grading results, you can use this tool to refine the grading prompt based on your rubric component comments. After you have added your review comments in the "Rubric Component Comments" section below, click "Generate analysis" to:
              </p>
              <ul className="text-sm text-slate-700 mt-2 ml-4 list-disc space-y-1">
                <li>Analyze how your comments should be incorporated into the grading prompt</li>
                <li>Generate a descriptive summary of the changes needed</li>
                <li>Produce a draft of the updated prompt that you can review and save</li>
                <li>Optionally re-run grading to see how the updated prompt affects the scores</li>
              </ul>
            </div>
            <button
              onClick={handleGeneratePromptAnalysis}
              disabled={generatingPromptAnalysis || !jobId || !rubricComponents.some(comp => rubricComments[comp.key]?.trim())}
              className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold"
              title={!rubricComponents.some(comp => rubricComments[comp.key]?.trim()) ? "Please add rubric component comments first" : ""}
            >
              {generatingPromptAnalysis ? "Generating..." : "Generate analysis"}
            </button>
          </div>

          {commentPromptAnalysis ? (
            <div className="mt-4 space-y-4">
              {cleanedAnalysisSummary && (
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-slate-800 mb-1">Analysis summary</h3>
                  <p className="text-sm text-slate-700 whitespace-pre-wrap">{cleanedAnalysisSummary}</p>
                </div>
              )}

              {cleanedRecommendations && cleanedRecommendations.length > 0 && (
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-slate-800 mb-2">Recommendations</h3>
                  <ul className="list-disc list-inside text-sm text-slate-700 space-y-1">
                    {cleanedRecommendations.map((rec: string, idx: number) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}

              {commentPromptAnalysis.modified_prompt && (
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between mb-2">
                    <h3 className="text-sm font-semibold text-slate-800">Draft prompt (ready to save)</h3>
                    <div className="flex gap-2">
                      <button
                        onClick={async () => {
                          if (!commentPromptAnalysis.modified_prompt) return;
                          setUpdatingPrompt(true);
                          try {
                            const response = await fetch(`${API_BASE}/api/update-grading-prompt`, {
                              method: "POST",
                              headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ prompt: commentPromptAnalysis.modified_prompt }),
                            });
                            if (!response.ok) {
                              const errorData = await response.json().catch(() => ({ detail: "Failed to save prompt" }));
                              throw new Error(errorData.detail || "Failed to save prompt");
                            }
                            setSaveStatus("✅ Prompt saved to grading_prompt.txt");
                            setTimeout(() => setSaveStatus(null), 4000);
                            // Show feedback modal
                            setFeedbackMessage("✅ Prompt saved to grading_prompt.txt");
                            setShowFeedbackModal(true);
                          } catch (err: any) {
                            setSaveStatus(`❌ Error: ${err.message}`);
                            // Show error feedback modal
                            setFeedbackMessage(`❌ Failed to save prompt: ${err.message}`);
                            setShowFeedbackModal(true);
                          } finally {
                            setUpdatingPrompt(false);
                          }
                        }}
                        disabled={updatingPrompt}
                        className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 text-sm font-semibold disabled:opacity-50"
                      >
                        {updatingPrompt ? "Saving..." : "Save to grading_prompt.txt"}
                      </button>
                      <button
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(commentPromptAnalysis.modified_prompt);
                            setSaveStatus("✅ Prompt copied to clipboard!");
                            setTimeout(() => setSaveStatus(null), 3000);
                            // Show feedback modal
                            setFeedbackMessage("✅ Prompt copied to clipboard!");
                            setShowFeedbackModal(true);
                          } catch (err: any) {
                            setSaveStatus(`❌ Error: ${err.message}`);
                            // Show error feedback modal
                            setFeedbackMessage(`❌ Failed to copy prompt: ${err.message}`);
                            setShowFeedbackModal(true);
                          }
                        }}
                        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-semibold"
                      >
                        Copy Prompt
                      </button>
                    </div>
                  </div>
                  <pre className="text-xs text-slate-800 whitespace-pre-wrap font-mono overflow-x-auto max-h-[40vh] overflow-y-auto bg-white p-3 rounded border border-slate-200">
                    {commentPromptAnalysis.modified_prompt}
                  </pre>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-600 mt-4 bg-slate-50 border border-slate-200 rounded-lg p-3">
              <strong>No analysis generated yet.</strong> To use this feature:
              <ol className="list-decimal list-inside mt-2 space-y-1 ml-2">
                <li>First, add your review comments in the "Rubric Component Comments" section below</li>
                <li>Then click "Generate analysis" to see how your comments can improve the grading prompt</li>
                <li>Review the generated prompt and optionally save it or re-run grading</li>
              </ol>
            </p>
          )}
        </div>

        {/* Rubric Component Comments Section */}
        <div className="mt-8 bg-white rounded-lg shadow-lg p-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-4">Rubric Component Comments</h2>
          <p className="text-sm text-slate-600 mb-4">
            Select a rubric component and add your comment. These will be saved and displayed in TA Reviews Summary.
          </p>
          
          <div className="space-y-4">
            {/* Dropdown to select rubric component */}
            <div>
              <label className="text-sm font-semibold text-slate-700 block mb-2">
                Select Rubric Component
              </label>
              <select
                value={selectedRubricComponent}
                onChange={(e) => {
                  const newComponent = e.target.value;
                  setSelectedRubricComponent(newComponent);
                  // Load existing comment for the selected component, or empty string
                  setEditingRubricComment(newComponent ? (rubricComments[newComponent] || "") : "");
                }}
                className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
              >
                <option value="">-- Select a component --</option>
                {rubricComponents.map((component) => (
                  <option key={component.key} value={component.key}>
                    {component.label} (Max: {component.max})
                  </option>
                ))}
              </select>
            </div>

            {/* Textarea for selected component */}
            {selectedRubricComponent && (
              <div>
                <label className="text-sm font-semibold text-slate-700 block mb-2">
                  Comment for {rubricComponents.find(c => c.key === selectedRubricComponent)?.label}
                </label>
                <textarea
                  value={editingRubricComment}
                  onChange={(e) => {
                    setEditingRubricComment(e.target.value);
                  }}
                  rows={4}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none text-sm"
                  placeholder={`Add your comment for ${rubricComponents.find(c => c.key === selectedRubricComponent)?.label}...`}
                />
              </div>
            )}
            
            <div className="flex justify-end pt-2">
              <button
                onClick={async () => {
                  if (!jobId) {
                    setSaveStatus("❌ Error: No job ID selected");
                    return;
                  }
                  
                  if (!selectedRubricComponent) {
                    setSaveStatus("❌ Please select a rubric component first");
                    return;
                  }
                  
                  setSavingRubricComments(true);
                  try {
                    // Update the saved comments with the current editing comment
                    const updatedComments = {
                      ...rubricComments,
                      [selectedRubricComponent]: editingRubricComment,
                    };
                    
                    const response = await fetch(`${API_BASE}/api/jobs/${jobId}/rubric-comments`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        comments: updatedComments,
                      }),
                    });
                    if (!response.ok) {
                      const errorData = await response.json().catch(() => ({ detail: "Failed to save rubric comments" }));
                      throw new Error(errorData.detail || "Failed to save rubric comments");
                    }
                    
                    // Update saved comments state (this will trigger display in summary)
                    setRubricComments(updatedComments);
                    
                    setSaveStatus("✅ Rubric component comments saved successfully!");
                    setTimeout(() => setSaveStatus(null), 3000);
                  } catch (err: any) {
                    setSaveStatus(`❌ Error: ${err.message}`);
                  } finally {
                    setSavingRubricComments(false);
                  }
                }}
                disabled={savingRubricComments}
                className="px-6 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
              >
                {savingRubricComments ? "Saving..." : "Save Rubric Comments"}
              </button>
            </div>
          </div>
        </div>

        {/* TA Reviews Summary Section - At the bottom */}
        <div className="mt-8 bg-white rounded-lg shadow-lg p-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-4">TA Reviews Summary</h2>
          
          {/* Rubric Component Comments */}
          {(() => {
            const hasComments = rubricComponents.some(comp => rubricComments[comp.key]?.trim());
            if (!hasComments) return null;
            
            return (
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-slate-700 mb-3">Rubric Component Comments</h3>
                <div className="space-y-4">
                  {rubricComponents
                    .filter(comp => rubricComments[comp.key]?.trim())
                    .map((component) => (
                      <div key={component.key} className="bg-slate-50 rounded-lg p-4 border border-slate-200">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-1 bg-purple-100 text-purple-800 rounded text-xs font-semibold">
                              {component.label}
                            </span>
                            <span className="text-xs text-slate-500">(Max: {component.max})</span>
                          </div>
                          <button
                            onClick={async () => {
                              if (window.confirm(`Are you sure you want to delete the comment for ${component.label}? This action cannot be undone.`)) {
                                try {
                                  // Remove this component's comment
                                  const updatedComments = { ...rubricComments };
                                  delete updatedComments[component.key];
                                  
                                  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/rubric-comments`, {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({
                                      comments: updatedComments,
                                    }),
                                  });
                                  
                                  if (response.ok) {
                                    setRubricComments(updatedComments);
                                    // If this was the selected component, clear the editing state
                                    if (selectedRubricComponent === component.key) {
                                      setEditingRubricComment("");
                                    }
                                    setSaveStatus(`✅ Comment for ${component.label} deleted successfully!`);
                                    setTimeout(() => setSaveStatus(null), 3000);
                                  } else {
                                    throw new Error("Failed to delete comment");
                                  }
                                } catch (err: any) {
                                  setSaveStatus(`❌ Error: ${err.message}`);
                                }
                              }
                            }}
                            className="px-3 py-1.5 text-sm text-red-600 hover:text-red-800 font-medium rounded-md hover:bg-red-50 border border-red-200 hover:border-red-300 transition-colors"
                            title={`Delete comment for ${component.label}`}
                          >
                            Delete
                          </button>
                        </div>
                        <p className="text-sm text-slate-800 whitespace-pre-wrap bg-white p-3 rounded border border-slate-200">
                          {rubricComments[component.key]}
                        </p>
                        {(() => {
                          const evaluation = evaluateRubricComment(rubricComments[component.key]);
                          return (
                            <div className="mt-3 bg-white p-3 rounded border border-dashed border-slate-200">
                              <div className="flex items-center justify-between">
                                <span className={`px-2 py-1 rounded text-xs font-semibold ${evaluation.badgeClass}`}>
                                  {evaluation.badge}
                                </span>
                                <span className="text-xs text-slate-500">
                                  System decision shown during re-run
                                </span>
                              </div>
                              <p className="text-xs text-slate-600 mt-2">{evaluation.detail}</p>
                            </div>
                          );
                        })()}
                      </div>
                    ))}
                </div>

                <div className="mt-3 bg-slate-100 border border-slate-200 rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-slate-700 mb-1">How your comments are processed</h4>
                  <ol className="list-decimal list-inside text-xs text-slate-600 space-y-1">
                    <li>Every saved comment is stored in <code>{jobId}_rubric_comments.json</code>.</li>
                    <li>During <strong>Re-run Grading</strong>, detailed comments (60+ chars) are injected directly into the scoring prompt.</li>
                    <li>Concise comments (25–59 chars) are still included but flagged for potential elaboration.</li>
                    <li>Very short comments are logged for your reference but called out as “Needs more detail” so you can decide whether to expand them.</li>
                  </ol>
                </div>
              </div>
            );
          })()}
          

          {/* Issue Reviews */}
          {validIssues.filter(issue => issue.ta_review && (issue.ta_review.override_reason || issue.ta_review.ta_comment)).length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold text-slate-700 mb-3">Issue Reviews</h3>
              <div className="space-y-4">
                {validIssues
                  .filter(issue => issue.ta_review && (issue.ta_review.override_reason || issue.ta_review.ta_comment))
                  .map((issue) => {
                    const heuristicName = heuristicsInfo.find(h => h.number === parseInt(issue.heuristic_id.replace(/^H/i, "")))?.name || issue.heuristic_id;
                    return (
                      <div key={issue.issue_id} className="bg-slate-50 rounded-lg p-4 border border-slate-200">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="px-2 py-1 bg-purple-100 text-purple-800 rounded text-xs font-semibold">
                            {issue.heuristic_id}
                          </span>
                          <span className="text-sm font-semibold text-slate-700">{heuristicName}</span>
                          <span className="text-xs text-slate-500">({issue.pages_involved.length} page{issue.pages_involved.length !== 1 ? 's' : ''})</span>
                        </div>
                        {issue.ta_review?.override_reason && (
                          <div className="mb-2">
                            <label className="text-xs font-semibold text-slate-600 block mb-1">Override Reason</label>
                            <p className="text-sm text-slate-800 whitespace-pre-wrap bg-white p-2 rounded border border-slate-200">
                              {issue.ta_review.override_reason}
                            </p>
                          </div>
                        )}
                        {issue.ta_review?.ta_comment && (
                          <div>
                            <label className="text-xs font-semibold text-slate-600 block mb-1">TA Comment</label>
                            <p className="text-sm text-slate-800 whitespace-pre-wrap bg-white p-2 rounded border border-slate-200">
                              {issue.ta_review.ta_comment}
                            </p>
                          </div>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
          )}

          {/* Page Reviews */}
          {pages.filter(page => page.ta_review && (page.ta_review.override_reason || page.ta_review.ta_comment)).length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-slate-700 mb-3">Page Reviews</h3>
              <div className="space-y-4">
                {pages
                  .filter(page => page.ta_review && (page.ta_review.override_reason || page.ta_review.ta_comment))
                  .map((page) => (
                    <div key={page.page_id} className="bg-slate-50 rounded-lg p-4 border border-slate-200">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-semibold">
                          Page {page.page_number}
                        </span>
                        <span className="text-sm font-semibold text-slate-700 capitalize">{page.page_role}</span>
                        {page.main_heading && (
                          <span className="text-xs text-slate-500">- {page.main_heading}</span>
                        )}
                      </div>
                      {page.ta_review?.override_reason && (
                        <div className="mb-2">
                          <label className="text-xs font-semibold text-slate-600 block mb-1">Override Reason</label>
                          <p className="text-sm text-slate-800 whitespace-pre-wrap bg-white p-2 rounded border border-slate-200">
                            {page.ta_review.override_reason}
                          </p>
                        </div>
                      )}
                      {page.ta_review?.ta_comment && (
                        <div>
                          <label className="text-xs font-semibold text-slate-600 block mb-1">TA Comment</label>
                          <p className="text-sm text-slate-800 whitespace-pre-wrap bg-white p-2 rounded border border-slate-200">
                            {page.ta_review.ta_comment}
                          </p>
                        </div>
                      )}
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* No reviews message */}
          {validIssues.filter(issue => issue.ta_review && (issue.ta_review.override_reason || issue.ta_review.ta_comment)).length === 0 &&
           pages.filter(page => page.ta_review && (page.ta_review.override_reason || page.ta_review.ta_comment)).length === 0 &&
           Object.keys(rubricComments).filter(key => rubricComments[key]?.trim()).length === 0 && (
            <div className="text-center py-8 text-slate-500">
              <p>No TA reviews saved yet. Reviews will appear here after you save them.</p>
            </div>
          )}
        </div>

        {/* Prompt Backup & Restore - After TA Reviews Summary */}
        <div className="mt-8 bg-gradient-to-r from-amber-50 to-orange-50 border-2 border-amber-300 rounded-lg p-4 shadow-md">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                <h2 className="text-lg font-bold text-slate-900">Prompt Backup & Restore</h2>
              </div>
              <p className="text-sm text-slate-700">
                {backupExists 
                  ? "✅ Original prompt backup exists. If you think the current prompt is worse than the original, you can restore the original prompt."
                  : "⚠️ Create a backup of the current prompt as the original version. If you later think the current prompt is worse than the original, you can restore it. This backup will never be modified automatically."}
              </p>
            </div>
            <div className="flex gap-2 flex-shrink-0">
              <button
                onClick={async () => {
                  setBackingUp(true);
                  try {
                    const response = await fetch(`${API_BASE}/api/backup-grading-prompt`, {
                      method: "POST",
                    });
                    if (!response.ok) {
                      const errorData = await response.json().catch(() => ({ detail: "Failed to backup prompt" }));
                      throw new Error(errorData.detail || "Failed to backup prompt");
                    }
                    const data = await response.json();
                    setBackupExists(true);
                    setSaveStatus(`✅ ${data.message}`);
                    setTimeout(() => setSaveStatus(null), 4000);
                    setFeedbackMessage(`✅ ${data.message}`);
                    setShowFeedbackModal(true);
                  } catch (err: any) {
                    setSaveStatus(`❌ Error: ${err.message}`);
                    setFeedbackMessage(`❌ Failed to backup prompt: ${err.message}`);
                    setShowFeedbackModal(true);
                  } finally {
                    setBackingUp(false);
                  }
                }}
                disabled={backingUp}
                className="px-5 py-2.5 bg-amber-600 text-white rounded-md hover:bg-amber-700 text-sm font-semibold disabled:opacity-50 shadow-sm transition-colors"
              >
                {backingUp ? "Backing up..." : "💾 Backup Original Prompt"}
              </button>
              {backupExists && (
                <button
                  onClick={async () => {
                    if (!window.confirm("Are you sure you want to restore the prompt from backup? This will overwrite the current prompt.")) {
                      return;
                    }
                    setRestoring(true);
                    try {
                      const response = await fetch(`${API_BASE}/api/restore-grading-prompt`, {
                        method: "POST",
                      });
                      if (!response.ok) {
                        const errorData = await response.json().catch(() => ({ detail: "Failed to restore prompt" }));
                        throw new Error(errorData.detail || "Failed to restore prompt");
                      }
                      const data = await response.json();
                      setSaveStatus(`✅ ${data.message}`);
                      setTimeout(() => setSaveStatus(null), 4000);
                      setFeedbackMessage(`✅ ${data.message}`);
                      setShowFeedbackModal(true);
                    } catch (err: any) {
                      setSaveStatus(`❌ Error: ${err.message}`);
                      setFeedbackMessage(`❌ Failed to restore prompt: ${err.message}`);
                      setShowFeedbackModal(true);
                    } finally {
                      setRestoring(false);
                    }
                  }}
                  disabled={restoring}
                  className="px-5 py-2.5 bg-orange-600 text-white rounded-md hover:bg-orange-700 text-sm font-semibold disabled:opacity-50 shadow-sm transition-colors"
                >
                  {restoring ? "Restoring..." : "🔄 Restore from Backup"}
                </button>
              )}
            </div>
          </div>
        </div>

      </div>

      {/* Feedback Modal */}
      {showFeedbackModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-900">Feedback</h3>
              <button
                onClick={() => setShowFeedbackModal(false)}
                className="text-slate-500 hover:text-slate-700"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="text-slate-700 mb-4">{feedbackMessage}</p>
            <div className="flex justify-end">
              <button
                onClick={() => setShowFeedbackModal(false)}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-semibold"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Navigation Confirmation Modal */}
      {showNavigationConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 mb-4">
              <svg className="w-8 h-8 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <h3 className="text-lg font-semibold text-slate-900">
                {recomputing ? "Re-run Grading in Progress" : "Analysis Generation in Progress"}
              </h3>
            </div>
            <p className="text-slate-700 mb-6">
              {recomputing 
                ? "Re-run grading is currently running. If you navigate away, changes will not be saved."
                : "Analysis generation is currently running. If you navigate away, changes will not be saved."}
            </p>
            <p className="text-sm text-slate-600 mb-6 font-semibold">
              Are you sure you want to leave this page?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowNavigationConfirm(false);
                  setPendingNavigation(null);
                }}
                className="px-4 py-2 bg-slate-200 text-slate-700 rounded-md hover:bg-slate-300 text-sm font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setShowNavigationConfirm(false);
                  if (pendingNavigation) {
                    pendingNavigation();
                  }
                  setPendingNavigation(null);
                }}
                className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 text-sm font-semibold"
              >
                Leave Page
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Component for editing page role
interface EditPageRoleButtonProps {
  jobId: string;
  pageId: string;
  currentRole: string;
  isReanalyzing: boolean;
  onReanalyzingChange: (pageId: string | null) => void;
  onRoleUpdated: () => void;
}

// Component for editing page metadata
interface PageMetadataEditorProps {
  pageData: PageAnalysis;
  onSave: (updates: { main_heading?: string | null; has_annotations?: string; rubric_relevance?: Record<string, string> }) => void;
  onCancel: () => void;
  saving: boolean;
  size?: "small" | "normal";
}

function PageMetadataEditor({ pageData, onSave, onCancel, saving, size = "normal" }: PageMetadataEditorProps) {
  const [mainHeading, setMainHeading] = useState(pageData.main_heading || "");
  const [hasAnnotations, setHasAnnotations] = useState<"none" | "low" | "medium" | "high">(
    (pageData.has_annotations as "none" | "low" | "medium" | "high") || "none"
  );
  const [rubricRelevance, setRubricRelevance] = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries(pageData.rubric_relevance || {}).filter(([key]) => key !== "coverage")
    )
  );

  const textSize = size === "small" ? "text-xs" : "text-sm";
  const inputSize = size === "small" ? "px-2 py-0.5" : "px-3 py-1.5";

  const handleSave = () => {
    const updates: any = {};
    if (mainHeading !== (pageData.main_heading || "")) {
      updates.main_heading = mainHeading || null;
    }
    if (pageData.page_role === "violation_detail" && hasAnnotations !== (pageData.has_annotations || "none")) {
      updates.has_annotations = hasAnnotations;
    }
    // Check if any rubric_relevance changed
    const originalRelevance = Object.fromEntries(
      Object.entries(pageData.rubric_relevance || {}).filter(([key]) => key !== "coverage")
    );
    const hasChanges = Object.keys(rubricRelevance).some(
      key => rubricRelevance[key] !== originalRelevance[key]
    );
    if (hasChanges) {
      updates.rubric_relevance = rubricRelevance;
    }
    onSave(updates);
  };

  const rubricLevels = ["none", "low", "med", "high"];
  const annotationLevels = ["none", "low", "medium", "high"];

  return (
    <div className={`space-y-2 ${textSize}`}>
      {/* Main Heading */}
      <div>
        <label className="text-slate-600 block mb-1">Main Heading:</label>
        <input
          type="text"
          value={mainHeading}
          onChange={(e) => setMainHeading(e.target.value)}
          className={`w-full ${inputSize} border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500`}
          placeholder="Enter main heading..."
        />
      </div>

      {/* Screenshot Annotations - Only for violation_detail pages */}
      {pageData.page_role === "violation_detail" && (
        <div>
          <label className="text-slate-600 block mb-1">Screenshot Annotations:</label>
          <select
            value={hasAnnotations}
            onChange={(e) => setHasAnnotations(e.target.value as "none" | "low" | "medium" | "high")}
            className={`w-full ${inputSize} border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500`}
          >
            {annotationLevels.map((level) => (
              <option key={level} value={level}>
                {level === "high" ? "Highly Annotated" :
                 level === "medium" ? "Moderately Annotated" :
                 level === "low" ? "Minimally Annotated" :
                 "No Annotations"}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Rubric Relevance */}
      <div className="pt-2 border-t border-slate-200">
        <div className="text-slate-600 font-semibold mb-1">Rubric Relevance:</div>
        <div className="space-y-1">
          {Object.keys(rubricRelevance).map((key) => (
            <div key={key} className="flex items-center justify-between">
              <span className="text-slate-600 capitalize">{key.replace(/_/g, " ")}:</span>
              <select
                value={rubricRelevance[key]}
                onChange={(e) => setRubricRelevance({ ...rubricRelevance, [key]: e.target.value })}
                className={`${inputSize} border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500`}
              >
                {rubricLevels.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </div>

      {/* Save/Cancel buttons */}
      <div className="flex gap-2 pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className={`${inputSize} bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 font-semibold`}
        >
          {saving ? "Saving..." : "Save"}
        </button>
        <button
          onClick={onCancel}
          disabled={saving}
          className={`${inputSize} bg-slate-200 text-slate-700 rounded-md hover:bg-slate-300 disabled:opacity-50`}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function EditPageRoleButton({ jobId, pageId, currentRole, isReanalyzing, onReanalyzingChange, onRoleUpdated }: EditPageRoleButtonProps) {
  const [showModal, setShowModal] = useState(false);
  const [selectedRole, setSelectedRole] = useState<string>(currentRole);
  const [selectedHeuristic, setSelectedHeuristic] = useState<string>("H1");
  const [error, setError] = useState<string | null>(null);

  const pageRoles: Array<{ value: string; label: string }> = [
    { value: "intro", label: "Introduction" },
    { value: "group_collab", label: "Group Collaboration" },
    { value: "heuristic_explainer", label: "Heuristic Explainer" },
    { value: "violation_detail", label: "Violation Detail" },
    { value: "severity_summary", label: "Severity Summary" },
    { value: "conclusion", label: "Conclusion" },
    { value: "ai_opportunities", label: "AI Opportunities" },
    { value: "other", label: "Other" },
  ];

  const heuristics = Array.from({ length: 10 }, (_, i) => ({
    value: `H${i + 1}`,
    label: `H${i + 1}`,
  }));

  const handleSave = async () => {
    if (selectedRole === currentRole && (selectedRole !== "heuristic_explainer" || !selectedHeuristic)) {
      setShowModal(false);
      return;
    }

    setError(null);
    onReanalyzingChange(pageId);

    try {
      const requestBody: any = {
        jobId,
        pageId,
        page_role: selectedRole,
      };

      // If switching to heuristic_explainer, include the heuristic_id
      if (selectedRole === "heuristic_explainer") {
        requestBody.heuristic_id = selectedHeuristic;
      }

      const res = await fetch(`${API_BASE}/api/reanalyze-page-with-role`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: "Failed to reanalyze page" }));
        throw new Error(errorData.detail || "Failed to reanalyze page");
      }

      setShowModal(false);
      onRoleUpdated();
    } catch (err: any) {
      setError(err.message || "Failed to reanalyze page");
    } finally {
      onReanalyzingChange(null);
    }
  };

  return (
    <>
      <button
        onClick={() => setShowModal(true)}
        disabled={isReanalyzing}
        className="px-2 py-1 text-xs bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
        title="Edit page role and reanalyze"
      >
        {isReanalyzing ? "Reanalyzing..." : "Edit Role"}
      </button>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-900">Edit Page Role</h3>
              <button
                onClick={() => {
                  setShowModal(false);
                  setError(null);
                }}
                className="text-slate-500 hover:text-slate-700"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Current Role: <span className="font-semibold">{currentRole}</span>
              </label>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                New Role:
              </label>
              <select
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 mb-3"
              >
                {pageRoles.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </select>

              {/* Show heuristic selector when switching to heuristic_explainer */}
              {selectedRole === "heuristic_explainer" && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Select Heuristic:
                  </label>
                  <select
                    value={selectedHeuristic}
                    onChange={(e) => setSelectedHeuristic(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {heuristics.map((h) => (
                      <option key={h.value} value={h.value}>
                        {h.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {error && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="text-sm text-slate-600 mb-4">
              <p className="font-medium">Note:</p>
              <p>Changing the page role will trigger a reanalysis of this page with the new role. The page will be re-analyzed using AI, and issues will be regenerated.</p>
            </div>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowModal(false);
                  setError(null);
                }}
                className="px-4 py-2 bg-slate-200 text-slate-700 rounded-md hover:bg-slate-300 text-sm font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isReanalyzing || selectedRole === currentRole}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold"
              >
                {isReanalyzing ? "Reanalyzing..." : "Save & Reanalyze"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

