import React, { useState, useMemo, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import type { 
  HeuristicExtractionResult, 
  PageAnalysisResult, 
  AssignmentSummary, 
  SummaryScores,
  PageAnalysis,
  HeuristicFragment,
  PageRole,
  RubricLevel
} from "../lib/types";


interface HeuristicInfo {
  number: number;
  name: string;
  description: string;
}

// Component to display structured page analysis
function StructuredAnalysisDisplay({ analysis }: { analysis: PageAnalysis }) {
  const roleLabels: Record<PageRole, string> = {
    intro: "Introduction",
    group_collab: "Group Collaboration",
    heuristic_explainer: "Heuristic Explainer",
    violation_detail: "Violation Detail",
    severity_summary: "Severity Summary",
    conclusion: "Conclusion",
    ai_opportunities: "AI Opportunities",
    other: "Other",
  };

  const levelColors: Record<RubricLevel, string> = {
    none: "bg-slate-100 text-slate-600",
    low: "bg-blue-100 text-blue-700",
    med: "bg-amber-100 text-amber-700",
    high: "bg-green-100 text-green-700",
  };

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-emerald-900 mb-1">
            Structured Analysis
          </h3>
          <div className="flex items-center gap-2 flex-wrap mt-1">
            <span className="text-xs px-2 py-1 rounded-full bg-purple-100 text-purple-800">
              {roleLabels[analysis.page_role] || analysis.page_role}
            </span>
            {analysis.main_heading && (
              <span className="text-xs text-emerald-700 italic">
                "{analysis.main_heading}"
              </span>
            )}
            {analysis.has_annotations !== "none" && (
              <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-800">
                Annotations: {analysis.has_annotations}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Rubric Relevance */}
      <div className="border-t border-emerald-200 pt-2">
        <p className="text-xs font-medium text-emerald-900 mb-1">Rubric Relevance:</p>
        <div className="grid grid-cols-2 gap-1 text-xs">
          <div className="flex justify-between">
            <span className="text-emerald-700">Coverage:</span>
            <span className={`px-1.5 py-0.5 rounded ${levelColors[analysis.rubric_relevance.coverage]}`}>
              {analysis.rubric_relevance.coverage}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-emerald-700">Violation Quality:</span>
            <span className={`px-1.5 py-0.5 rounded ${levelColors[analysis.rubric_relevance.violation_quality]}`}>
              {analysis.rubric_relevance.violation_quality}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-emerald-700">Severity Analysis:</span>
            <span className={`px-1.5 py-0.5 rounded ${levelColors[analysis.rubric_relevance.severity_analysis]}`}>
              {analysis.rubric_relevance.severity_analysis}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-emerald-700">Screenshots & Evidence:</span>
            <span className={`px-1.5 py-0.5 rounded ${levelColors[analysis.rubric_relevance.screenshots_evidence]}`}>
              {analysis.rubric_relevance.screenshots_evidence}
            </span>
          </div>
          <div className="flex justify-between col-span-2">
            <span className="text-emerald-700">Group Integration:</span>
            <span className={`px-1.5 py-0.5 rounded ${levelColors[analysis.rubric_relevance.group_integration]}`}>
              {analysis.rubric_relevance.group_integration}
            </span>
          </div>
        </div>
      </div>

      {/* Fragments */}
      {analysis.fragments && analysis.fragments.length > 0 && (
        <div className="border-t border-emerald-200 pt-2">
          <p className="text-xs font-medium text-emerald-900 mb-1">
            Heuristic Fragments ({analysis.fragments.length}):
          </p>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {analysis.fragments.map((frag, idx) => (
              <div key={idx} className="text-xs bg-white rounded border border-emerald-200 p-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-emerald-900">{frag.heuristic_id}</span>
                  <span className="text-emerald-600 italic">{frag.issue_key}</span>
                  {frag.severity_hint && (
                    <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-xs">
                      {frag.severity_hint}
                    </span>
                  )}
                </div>
                <p className="text-emerald-700 mb-1">{frag.text_summary}</p>
                {frag.fragment_role && frag.fragment_role.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {frag.fragment_role.map((role, rIdx) => (
                      <span key={rIdx} className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">
                        {role.replace("_", " ")}
                      </span>
                    ))}
                  </div>
                )}
                {frag.rubric_tags && frag.rubric_tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {frag.rubric_tags.map((tag, tIdx) => (
                      <span key={tIdx} className="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                        {tag}
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
      {analysis.severity_summary && (
        <div className="border-t border-emerald-200 pt-2">
          <p className="text-xs font-medium text-emerald-900 mb-1">Severity Summary:</p>
          <div className="text-xs bg-white rounded border border-emerald-200 p-2 space-y-1">
            <div className="flex justify-between">
              <span className="text-emerald-700">Visualization:</span>
              <span className="font-medium">{analysis.severity_summary.visualization}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-emerald-700">Coverage Scope:</span>
              <span className="font-medium">{analysis.severity_summary.coverage_scope}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-emerald-700">Mapping Clarity:</span>
              <span className={`font-medium ${
                analysis.severity_summary.mapping_clarity === "clear" ? "text-green-700" :
                analysis.severity_summary.mapping_clarity === "somewhat_clear" ? "text-amber-700" :
                "text-red-700"
              }`}>
                {analysis.severity_summary.mapping_clarity}
              </span>
            </div>
            {analysis.severity_summary.llm_note && (
              <p className="text-emerald-600 italic mt-1">{analysis.severity_summary.llm_note}</p>
            )}
          </div>
        </div>
      )}

      {analysis.fragments.length === 0 && !analysis.severity_summary && (
        <p className="text-xs text-emerald-600 italic">
          No specific heuristic violations or issues identified on this page.
        </p>
      )}
    </div>
  );
}

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzingProgress, setAnalyzingProgress] = useState<{ current: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HeuristicExtractionResult | null>(null);
  const [analysisResults, setAnalysisResults] = useState<PageAnalysisResult[] | null>(null);
  const [heuristicsInfo, setHeuristicsInfo] = useState<HeuristicInfo[]>([]);
  const [previousSubmissions, setPreviousSubmissions] = useState<Array<{
    jobId: string;
    fileName?: string;
    createdAt?: string;
    hasAnalysis?: boolean;
    hasOverrides?: boolean;
    hasFinalGrade?: boolean;
    status?: "ai_graded" | "ta_reviewed" | "final_graded";
  }>>([]);
  const [loadingPrevious, setLoadingPrevious] = useState(false);
  const [duplicateFile, setDuplicateFile] = useState<{
    jobId: string;
    fileName: string;
    hasAnalysis: boolean;
  } | null>(null);
  
  // Batch mode state
  const [batchMode, setBatchMode] = useState(false);
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [batchQueue, setBatchQueue] = useState<Array<{
    file: File;
    status: "pending" | "extracting" | "analyzing" | "completed" | "error";
    jobId?: string;
    error?: string;
    progress?: number;
  }>>([]);
  const [batchProcessing, setBatchProcessing] = useState(false);
  const [batchPaused, setBatchPaused] = useState(false);
  const [batchSize, setBatchSize] = useState(1); // Process 1 at a time by default
  const [showReviewerModeModal, setShowReviewerModeModal] = useState(false);
  const navigate = useNavigate();
  const prevAnalyzingRef = useRef(false);

  // Load heuristics info from rubric
  useEffect(() => {
    async function loadHeuristicsInfo() {
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
    }
    loadHeuristicsInfo();
  }, []);

  // Load previous submissions on mount
  useEffect(() => {
    async function loadPreviousSubmissions() {
      setLoadingPrevious(true);
      try {
        const res = await fetch("http://localhost:8000/api/list-jobs");
        if (res.ok) {
          const data = await res.json();
          const jobs = data.jobs || [];
          
          // Check which jobs have analysis results, overrides, and final grades
          const jobsWithAnalysis = await Promise.all(
            jobs.map(async (job: any) => {
              try {
                const analysisRes = await fetch(`http://localhost:8000/api/get-analysis-results?jobId=${job.jobId}`);
                const hasAnalysis = analysisRes.ok && (await analysisRes.json()).results?.length > 0;
                
                // Check for overrides (TA review)
                let hasOverrides = false;
                try {
                  const overridesRes = await fetch(`http://localhost:8000/api/get-overrides?jobId=${job.jobId}`);
                  if (overridesRes.ok) {
                    const overridesData = await overridesRes.json();
                    hasOverrides = overridesData.overrides && overridesData.overrides.length > 0;
                  }
                } catch {
                  // Ignore errors
                }
                
                // Check for final grade (final graded)
                let hasFinalGrade = false;
                try {
                  const finalGradeRes = await fetch(`http://localhost:8000/api/get-final-grade?jobId=${job.jobId}`);
                  if (finalGradeRes.ok) {
                    const finalGradeData = await finalGradeRes.json();
                    hasFinalGrade = finalGradeData.finalGrade !== undefined && finalGradeData.finalGrade !== null;
                  }
                } catch {
                  // Ignore errors
                }
                
                // Determine status
                let status: "ai_graded" | "ta_reviewed" | "final_graded" = "ai_graded";
                if (hasFinalGrade) {
                  status = "final_graded";
                } else if (hasOverrides) {
                  status = "ta_reviewed";
                } else if (hasAnalysis) {
                  status = "ai_graded";
                }
                
                return {
                  ...job,
                  hasAnalysis,
                  hasOverrides,
                  hasFinalGrade,
                  status,
                };
              } catch {
                return { 
                  ...job, 
                  hasAnalysis: false,
                  hasOverrides: false,
                  hasFinalGrade: false,
                  status: "ai_graded" as const,
                };
              }
            })
          );
          
          // Sort: ungraded (no analysis) first, then by date (newest first)
          jobsWithAnalysis.sort((a, b) => {
            if (a.hasAnalysis !== b.hasAnalysis) {
              return a.hasAnalysis ? 1 : -1; // ungraded first
            }
            const dateA = a.createdAt ? new Date(a.createdAt).getTime() : 0;
            const dateB = b.createdAt ? new Date(b.createdAt).getTime() : 0;
            return dateB - dateA; // newest first
          });
          
          setPreviousSubmissions(jobsWithAnalysis);
        }
      } catch (err) {
        console.error("Failed to load previous submissions:", err);
      } finally {
        setLoadingPrevious(false);
      }
    }
    loadPreviousSubmissions();
  }, []);


  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (batchMode) {
      const files = Array.from(e.target.files || []);
      const pdfFiles = files.filter(f => f.name.toLowerCase().endsWith(".pdf"));
      setBatchFiles(pdfFiles);
      
      // Refresh previous submissions to check for duplicates
      await refreshPreviousSubmissions();
      
      // Initialize queue
      setBatchQueue(pdfFiles.map(file => ({
        file,
        status: "pending" as const,
      })));
    } else {
      const f = e.target.files?.[0] ?? null;
      setFile(f);
      setError(null);
      setResult(null); // Clear previous result when selecting a new file
    }
  };

  // Load a previous submission
  const loadPreviousSubmission = async (jobId: string) => {
    setLoading(true);
    setError(null);
    try {
      // Load extraction result
      const pagesRes = await fetch(`http://localhost:8000/api/get-extraction-result?jobId=${jobId}`);
      if (!pagesRes.ok) throw new Error("Failed to load submission");

      const pagesData = await pagesRes.json();
      
      // Load analysis results if they exist
      const analysisRes = await fetch(`http://localhost:8000/api/get-analysis-results?jobId=${jobId}`);
      let analysisResults: PageAnalysisResult[] = [];
      
      if (analysisRes.ok) {
        const analysisData = await analysisRes.json();
        analysisResults = analysisData.results || [];
      }

      // Create extraction result
      const normalizedPages = (pagesData.pages || []).map(
        (page: { page_number: number; snippet: string; image_base64?: string }) => ({
          pageNumber: page.page_number,
          snippet: page.snippet,
          imageBase64: page.image_base64,
        }),
      );

      const extractionResult: HeuristicExtractionResult = {
        jobId: pagesData.jobId || jobId,
        fileName: pagesData.fileName,
        createdAt: pagesData.createdAt || new Date().toISOString(),
        pageCount: pagesData.pageCount || normalizedPages.length,
        pages: normalizedPages,
      };

      setResult(extractionResult);
      if (analysisResults.length > 0) {
        setAnalysisResults(analysisResults);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load previous submission");
    } finally {
      setLoading(false);
    }
  };

  // Delete a submission
  const deleteSubmission = async (jobId: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/delete-submission?jobId=${jobId}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        throw new Error("Failed to delete submission");
      }

      // Remove from previous submissions list
      setPreviousSubmissions(prev => prev.filter(s => s.jobId !== jobId));
      
      // If it was the duplicate file, clear it
      if (duplicateFile?.jobId === jobId) {
        setDuplicateFile(null);
      }
    } catch (err: any) {
      setError(err.message || "Failed to delete submission");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setDuplicateFile(null);

    if (!file) {
      setError("Please upload a PDF file.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }

    // Check for duplicate filename
    const existingSubmission = previousSubmissions.find(
      s => s.fileName?.toLowerCase() === file.name.toLowerCase()
    );

    if (existingSubmission) {
      setDuplicateFile({
        jobId: existingSubmission.jobId,
        fileName: file.name,
        hasAnalysis: existingSubmission.hasAnalysis || false,
      });
      return; // Stop here, show duplicate warning
    }

    // Use the helper function to perform upload
    await performUpload(file);
    
    // Refresh previous submissions list
    await refreshPreviousSubmissions();
  };

  // Batch processing functions
  const processBatchItem = async (item: typeof batchQueue[0], index: number) => {
    const file = item.file;
    
    // Update status to extracting
    setBatchQueue(prev => prev.map((q, i) => 
      i === index ? { ...q, status: "extracting", progress: 0 } : q
    ));

    try {
      // Step 1: Extract pages
      const formData = new FormData();
      formData.append("file", file);
      
      const extractRes = await fetch("http://localhost:8000/api/extract-heuristic-pages", {
        method: "POST",
        body: formData,
      });

      if (!extractRes.ok) {
        throw new Error(`Extraction failed: ${extractRes.statusText}`);
      }

      const extractData = await extractRes.json();
      const jobId = extractData.job_id || `job-${Date.now()}-${index}`;
      
      // Update status to analyzing
      setBatchQueue(prev => prev.map((q, i) => 
        i === index ? { ...q, status: "analyzing", jobId, progress: 50 } : q
      ));

      // Step 2: Analyze pages
      const pages = extractData.pages || [];
      const analysisResults: PageAnalysisResult[] = [];
      
      for (let i = 0; i < pages.length; i++) {
        const page = pages[i];
        const normalizedPage = {
          pageNumber: page.page_number,
          snippet: page.snippet,
          imageBase64: page.image_base64,
        };

        try {
          const analysisRes = await fetch("http://localhost:8000/api/analyze-single-page", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              page: normalizedPage,
              jobId,
            }),
          });

          if (analysisRes.ok) {
            const analysisData = await analysisRes.json();
            if (analysisData.status === "completed" && analysisData.result) {
              analysisResults.push(analysisData.result);
            }
          }

          // Update progress
          const progress = 50 + Math.floor((i + 1) / pages.length * 50);
          setBatchQueue(prev => prev.map((q, idx) => 
            idx === index ? { ...q, progress } : q
          ));
        } catch (err) {
          console.error(`Error analyzing page ${i + 1} of ${file.name}:`, err);
        }
      }

      // Mark as completed
      setBatchQueue(prev => prev.map((q, i) => 
        i === index ? { ...q, status: "completed", progress: 100 } : q
      ));

      // Refresh submissions list
      await refreshPreviousSubmissions();
    } catch (err: any) {
      setBatchQueue(prev => prev.map((q, i) => 
        i === index ? { 
          ...q, 
          status: "error", 
          error: err.message || "Processing failed" 
        } : q
      ));
    }
  };

  const processBatch = async () => {
    if (batchQueue.length === 0 || batchProcessing) return;

    setBatchProcessing(true);
    setBatchPaused(false);

    // Process items in batches
    let processedCount = 0;
    
    while (processedCount < batchQueue.length) {
      // Check if paused
      if (batchPaused) {
        setBatchProcessing(false);
        return;
      }

      // Get next batch of pending items
      const pendingItems = batchQueue
        .map((item, index) => ({ item, index }))
        .filter(({ item }) => item.status === "pending");

      if (pendingItems.length === 0) {
        // All items processed
        break;
      }

      const batch = pendingItems.slice(0, batchSize);
      
      // Process batch (sequentially or in parallel based on batchSize)
      if (batchSize === 1) {
        // Process one at a time
        for (const { item, index } of batch) {
          await processBatchItem(item, index);
          processedCount++;
        }
      } else {
        // Process batch in parallel
        await Promise.all(batch.map(({ item, index }) => processBatchItem(item, index)));
        processedCount += batch.length;
      }

      // Small delay between batches to avoid overwhelming the API
      if (pendingItems.length > batch.length) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }

    setBatchProcessing(false);
  };

  const pauseBatch = () => {
    setBatchPaused(true);
  };

  const resumeBatch = () => {
    setBatchPaused(false);
    processBatch();
  };

  const clearBatch = () => {
    setBatchFiles([]);
    setBatchQueue([]);
    setBatchProcessing(false);
    setBatchPaused(false);
  };

  // Helper function to refresh previous submissions list
  const refreshPreviousSubmissions = async () => {
    try {
      const jobsRes = await fetch("http://localhost:8000/api/list-jobs");
      if (jobsRes.ok) {
        const jobsData = await jobsRes.json();
        const jobs = jobsData.jobs || [];
        const jobsWithAnalysis = await Promise.all(
          jobs.map(async (job: any) => {
            try {
              const analysisRes = await fetch(`http://localhost:8000/api/get-analysis-results?jobId=${job.jobId}`);
              const hasAnalysis = analysisRes.ok && (await analysisRes.json()).results?.length > 0;
              return { ...job, hasAnalysis };
            } catch {
              return { ...job, hasAnalysis: false };
            }
          })
        );
        jobsWithAnalysis.sort((a, b) => {
          if (a.hasAnalysis !== b.hasAnalysis) {
            return a.hasAnalysis ? 1 : -1;
          }
          const dateA = a.createdAt ? new Date(a.createdAt).getTime() : 0;
          const dateB = b.createdAt ? new Date(b.createdAt).getTime() : 0;
          return dateB - dateA;
        });
        setPreviousSubmissions(jobsWithAnalysis);
      }
    } catch (err) {
      console.error("Failed to refresh submissions list:", err);
    }
  };

  // Handle duplicate file - user can choose to load existing or continue upload
  const handleDuplicateChoice = async (choice: "load" | "upload" | "delete") => {
    if (!duplicateFile || !file) return;

    if (choice === "load") {
      await loadPreviousSubmission(duplicateFile.jobId);
      // After loading an existing submission, immediately navigate to Reviewer Mode for that job
      setDuplicateFile(null);
      if (duplicateFile.jobId) {
        localStorage.setItem(
          "recentJobIds",
          JSON.stringify([{ jobId: duplicateFile.jobId, fileName: duplicateFile.fileName }]),
        );
        navigate(`/issue-reviewer?jobId=${duplicateFile.jobId}`);
      }
    } else if (choice === "delete") {
      if (window.confirm(`Are you sure you want to delete "${duplicateFile.fileName}"? This action cannot be undone.`)) {
        await deleteSubmission(duplicateFile.jobId);
        setDuplicateFile(null);
        // After deletion, proceed with upload
        await performUpload(file);
        await refreshPreviousSubmissions();
      }
    } else if (choice === "upload") {
      // Continue with upload anyway (will create a new submission with same filename)
      setDuplicateFile(null);
      await performUpload(file);
      await refreshPreviousSubmissions();
    }
  };

  // Helper function to perform upload
  const performUpload = async (fileToUpload: File) => {
    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", fileToUpload);

      const res = await fetch("http://localhost:8000/api/extract-heuristic-pages", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        const msg = data?.detail || `Request failed with status ${res.status}`;
        throw new Error(msg);
      }

      const data = await res.json();
      const normalizedPages = (data.pages || []).map(
        (page: { page_number: number; snippet: string; image_base64?: string }) => ({
          pageNumber: page.page_number,
          snippet: page.snippet,
          imageBase64: page.image_base64,
        }),
      );

      const jobId = data.job_id || `job-${Date.now()}`;
      const extractionResult: HeuristicExtractionResult = {
        jobId,
        fileName: fileToUpload.name,
        createdAt: new Date().toISOString(),
        pageCount: data.page_count ?? normalizedPages.length,
        pages: normalizedPages,
      };

      setResult(extractionResult);
      // Clear any previous analysis results when uploading a new file
      setAnalysisResults(null);
    } catch (err: any) {
      let errorMessage = err.message || "Something went wrong while parsing the PDF.";
      
      if (err.message?.includes("Failed to fetch") || err.message?.includes("NetworkError") || err.name === "TypeError") {
        errorMessage = "Cannot connect to backend server. Please ensure the backend is running:\n\n1. Run: npm start\n2. Or manually: cd backend && python -m uvicorn main:app --reload\n3. Backend should be available at http://localhost:8000";
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleRerunAnalysis = async () => {
    // Clear previous analysis results and rerun
    setAnalysisResults([]);
    setError(null);
    await handleAnalyze();
  };

  // Get missing pages that need analysis
  const getMissingPages = useMemo(() => {
    if (!result || !analysisResults) return [];
    const extractedPageNumbers = new Set(result.pages.map(p => p.pageNumber));
    const analyzedPageNumbers = new Set(
      analysisResults
        .filter(a => !a.skip_analysis)
        .map(a => a.page_number)
    );
    const missingPageNumbers = Array.from(extractedPageNumbers).filter(
      pn => !analyzedPageNumbers.has(pn)
    );
    return result.pages.filter(p => missingPageNumbers.includes(p.pageNumber));
  }, [result, analysisResults]);

  // Analyze only missing pages
  const handleAnalyzeMissingPages = async () => {
    const missingPages = getMissingPages;
    if (missingPages.length === 0) {
      setError("No missing pages to analyze.");
      return;
    }

    if (!result) {
      setError("No extraction result found.");
      return;
    }

    setAnalyzing(true);
    setError(null);
    setAnalyzingProgress({ current: 0, total: missingPages.length });

    const newResults: PageAnalysisResult[] = [];
    const existingResults = analysisResults || [];

    try {
      // Analyze missing pages with limited concurrency (2 at a time)
      const concurrency = 2;
      
      for (let i = 0; i < missingPages.length; i += concurrency) {
        const batch = missingPages.slice(i, i + concurrency);
        
        // Process batch concurrently
        const batchPromises = batch.map(async (page) => {
          try {
            const res = await fetch("http://localhost:8000/api/analyze-single-page", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                page: page,
                jobId: result.jobId,
              }),
            });

            if (!res.ok) {
              const data = await res.json().catch(() => null);
              const msg = data?.detail || `Request failed with status ${res.status}`;
              const errorStr = msg.toLowerCase();
              if (errorStr.includes("quota") || errorStr.includes("rate limit") || errorStr.includes("resource_exhausted") || 
                  errorStr.includes("429") || errorStr.includes("token") || errorStr.includes("billing") ||
                  errorStr.includes("api key") || errorStr.includes("authentication")) {
                setError(`⚠️ API Error (Page ${page.pageNumber}): ${msg}`);
              }
              throw new Error(msg);
            }

            const data = await res.json();
            if (data.status === "completed" && data.result) {
              if (data.result.error) {
                const errorStr = data.result.error.toLowerCase();
                if (errorStr.includes("quota") || errorStr.includes("rate limit") || errorStr.includes("resource_exhausted") || 
                    errorStr.includes("429") || errorStr.includes("token") || errorStr.includes("billing") ||
                    errorStr.includes("api key") || errorStr.includes("authentication")) {
                  setError(`⚠️ API Error (Page ${page.pageNumber}): ${data.result.error}`);
                }
              }
              return data.result;
            } else if (data.status === "error") {
              const errorStr = (data.result?.error || data.detail || "").toLowerCase();
              if (errorStr.includes("quota") || errorStr.includes("rate limit") || errorStr.includes("resource_exhausted") || 
                  errorStr.includes("429") || errorStr.includes("token") || errorStr.includes("billing") ||
                  errorStr.includes("api key") || errorStr.includes("authentication")) {
                setError(`⚠️ API Error (Page ${page.pageNumber}): ${data.result?.error || data.detail || "Token/quota issue"}`);
              }
              return data.result;
            }
            throw new Error("Unknown response status");
          } catch (err: any) {
            let errorMsg = err.message || "Failed to analyze this page";
            if (err.message?.includes("Failed to fetch") || err.message?.includes("NetworkError") || err.name === "TypeError") {
              errorMsg = "Cannot connect to backend server. Please ensure the backend is running.";
            }
            
            const errorStr = err.message?.toLowerCase() || "";
            if (errorStr.includes("quota") || errorStr.includes("rate limit") || errorStr.includes("resource_exhausted") || 
                errorStr.includes("429") || errorStr.includes("token") || errorStr.includes("billing") ||
                errorStr.includes("api key") || errorStr.includes("authentication")) {
              errorMsg = `API Error: ${err.message || "Token quota exhausted or API key issue. Please check your API key and billing status."}`;
              setError(`⚠️ API Error (Page ${page.pageNumber}): ${errorMsg}`);
            }
            
            return {
              page_number: page.pageNumber,
              error: errorMsg,
              feedback: `Error analyzing page ${page.pageNumber}: ${errorMsg}`,
            };
          }
        });

        const batchResults = await Promise.all(batchPromises);
        newResults.push(...batchResults);
        
        setAnalyzingProgress({ 
          current: Math.min(i + concurrency, missingPages.length), 
          total: missingPages.length 
        });
        setAnalysisResults([...existingResults, ...newResults]);
      }

      // Merge with existing results
      setAnalysisResults([...existingResults, ...newResults]);
    } catch (err: any) {
      setError(`Failed to analyze missing pages: ${err.message || "Unknown error"}`);
    } finally {
      setAnalyzing(false);
      setAnalyzingProgress({ current: 0, total: 0 });
    }
  };

  const handleAnalyze = async () => {
    if (!result || result.pages.length === 0) {
      setError("Please extract pages first before analyzing.");
      return;
    }

    setAnalyzing(true);
    setError(null);
    setAnalysisResults([]);
    setAnalyzingProgress({ current: 0, total: result.pages.length });

    const results: PageAnalysisResult[] = [];

    try {
      // Analyze pages with limited concurrency (2 at a time) to balance speed and API limits
      const concurrency = 2;
      const pages = result.pages;
      
      for (let i = 0; i < pages.length; i += concurrency) {
        const batch = pages.slice(i, i + concurrency);
        
        // Process batch concurrently
        const batchPromises = batch.map(async (page) => {
          try {
            const res = await fetch("http://localhost:8000/api/analyze-single-page", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                page: page,
                jobId: result.jobId,
              }),
            });

            if (!res.ok) {
              const data = await res.json().catch(() => null);
              const msg = data?.detail || `Request failed with status ${res.status}`;
              // Check for token/quota errors
              const errorStr = msg.toLowerCase();
              if (errorStr.includes("quota") || errorStr.includes("rate limit") || errorStr.includes("resource_exhausted") || 
                  errorStr.includes("429") || errorStr.includes("token") || errorStr.includes("billing") ||
                  errorStr.includes("api key") || errorStr.includes("authentication")) {
                setError(`⚠️ API Error (Page ${page.pageNumber}): ${msg}`);
              }
              throw new Error(msg);
            }

            const data = await res.json();
            if (data.status === "completed" && data.result) {
              // Check if result contains error related to tokens/quota
              if (data.result.error) {
                const errorStr = data.result.error.toLowerCase();
                if (errorStr.includes("quota") || errorStr.includes("rate limit") || errorStr.includes("resource_exhausted") || 
                    errorStr.includes("429") || errorStr.includes("token") || errorStr.includes("billing") ||
                    errorStr.includes("api key") || errorStr.includes("authentication")) {
                  setError(`⚠️ API Error (Page ${page.pageNumber}): ${data.result.error}`);
                }
              }
              return data.result;
            } else if (data.status === "error") {
              // Check for token/quota errors in error response
              const errorStr = (data.result?.error || data.detail || "").toLowerCase();
              if (errorStr.includes("quota") || errorStr.includes("rate limit") || errorStr.includes("resource_exhausted") || 
                  errorStr.includes("429") || errorStr.includes("token") || errorStr.includes("billing") ||
                  errorStr.includes("api key") || errorStr.includes("authentication")) {
                setError(`⚠️ API Error (Page ${page.pageNumber}): ${data.result?.error || data.detail || "Token/quota issue"}`);
              }
              return data.result;
            }
            throw new Error("Unknown response status");
          } catch (err: any) {
            // Check if it's a connection error
            let errorMsg = err.message || "Failed to analyze this page";
            if (err.message?.includes("Failed to fetch") || err.message?.includes("NetworkError") || err.name === "TypeError") {
              errorMsg = "Cannot connect to backend server. Please ensure the backend is running.";
            }
            
            // Check for token/quota errors
            const errorStr = err.message?.toLowerCase() || "";
            if (errorStr.includes("quota") || errorStr.includes("rate limit") || errorStr.includes("resource_exhausted") || 
                errorStr.includes("429") || errorStr.includes("token") || errorStr.includes("billing") ||
                errorStr.includes("api key") || errorStr.includes("authentication")) {
              errorMsg = `API Error: ${err.message || "Token quota exhausted or API key issue. Please check your API key and billing status."}`;
              // Set global error to display prominently
              setError(`⚠️ API Error (Page ${page.pageNumber}): ${errorMsg}`);
            }
            
            // Return error result
            return {
              page_number: page.pageNumber,
              error: errorMsg,
              feedback: `Error analyzing page ${page.pageNumber}: ${errorMsg}`,
            };
          }
        });

        // Wait for batch to complete
        const batchResults = await Promise.all(batchPromises);
        results.push(...batchResults);
        
        // Update progress and results
        setAnalyzingProgress({ current: Math.min(i + concurrency, pages.length), total: pages.length });
        setAnalysisResults([...results]);
      }
    } catch (err: any) {
      let errorMessage = err.message || "Something went wrong while analyzing with Gemini.";
      
      // Check if it's a connection error
      if (err.message?.includes("Failed to fetch") || err.message?.includes("NetworkError") || err.name === "TypeError") {
        errorMessage = "Cannot connect to backend server. Please ensure the backend is running:\n\n1. Run: npm start\n2. Or manually: cd backend && python -m uvicorn main:app --reload\n3. Backend should be available at http://localhost:8000";
      }
      
      setError(errorMessage);
    } finally {
      setAnalyzing(false);
      setAnalyzingProgress(null);
    }
  };

  // Track when analysis completes to show modal
  useEffect(() => {
    // Show modal when analysis transitions from analyzing to complete
    if (prevAnalyzingRef.current && !analyzing && analysisResults && analysisResults.length > 0 && !showReviewerModeModal) {
      // Small delay to ensure UI has updated
      setTimeout(() => {
        setShowReviewerModeModal(true);
      }, 500);
    }
    prevAnalyzingRef.current = analyzing;
  }, [analyzing, analysisResults, showReviewerModeModal]);

  // Calculate summary scores from all analyzed pages
  const assignmentSummary = useMemo((): AssignmentSummary | null => {
    if (!analysisResults || analysisResults.length === 0) {
      return null;
    }

    // Only consider pages that were actually analyzed (not skipped)
    const analyzedPages = analysisResults.filter(r => !r.skip_analysis && r.score_breakdown);
    const skippedPages = analysisResults.filter(r => r.skip_analysis).length;

    if (analyzedPages.length === 0) {
      return null;
    }

    // Initialize score accumulators
    const scoreSums: SummaryScores = {
      coverage: { points: 0, max: 15 },
      violation_quality: { points: 0, max: 20 },
      screenshots: { points: 0, max: 10 },
      severity_analysis: { points: 0, max: 10 },
      structure_navigation: { points: 0, max: 10 },
      professional_quality: { points: 0, max: 10 },
      writing_quality: { points: 0, max: 10 },
      group_integration: { points: 0, max: 15 },
      bonus_ai_opportunities: { points: 0, max: 3 },
      bonus_exceptional_quality: { points: 0, max: 2 },
    };

    // Sum up scores from all analyzed pages
    analyzedPages.forEach(page => {
      if (page.score_breakdown) {
        Object.entries(page.score_breakdown).forEach(([key, score]) => {
          if (key in scoreSums) {
            scoreSums[key as keyof SummaryScores].points += score.points;
          }
        });
      }
      if (page.bonus_scores) {
        Object.entries(page.bonus_scores).forEach(([key, score]) => {
          if (key in scoreSums) {
            scoreSums[key as keyof SummaryScores].points += score.points;
          }
        });
      }
    });

    // Average the scores (since multiple pages might contribute to same criteria)
    // For now, we'll take the maximum from any page for each criterion
    // This is a design choice - you might want to average instead
    const finalScores: SummaryScores = {
      coverage: { points: 0, max: 15, comment: undefined },
      violation_quality: { points: 0, max: 20, comment: undefined },
      screenshots: { points: 0, max: 10, comment: undefined },
      severity_analysis: { points: 0, max: 10, comment: undefined },
      structure_navigation: { points: 0, max: 10, comment: undefined },
      professional_quality: { points: 0, max: 10, comment: undefined },
      writing_quality: { points: 0, max: 10, comment: undefined },
      group_integration: { points: 0, max: 15, comment: undefined },
      bonus_ai_opportunities: { points: 0, max: 3, comment: undefined },
      bonus_exceptional_quality: { points: 0, max: 2, comment: undefined },
    };

    // Collect comments for each criterion (from the page with highest score)
    const scoreComments: Record<string, string> = {};

    // Take maximum score for each criterion across all pages, and collect comments
    analyzedPages.forEach(page => {
      if (page.score_breakdown) {
        Object.entries(page.score_breakdown).forEach(([key, score]) => {
          if (key in finalScores) {
            const current = finalScores[key as keyof SummaryScores];
            if (score.points > current.points) {
              current.points = score.points;
              // Store comment from the page with highest score
              if (score.comment) {
                scoreComments[key] = score.comment;
              }
            } else if (score.points === current.points && !scoreComments[key] && score.comment) {
              // If same score and no comment yet, use this one
              scoreComments[key] = score.comment;
            }
          }
        });
      }
      if (page.bonus_scores) {
        Object.entries(page.bonus_scores).forEach(([key, score]) => {
          if (key in finalScores) {
            const current = finalScores[key as keyof SummaryScores];
            if (score.points > current.points) {
              current.points = score.points;
              if (score.comment) {
                scoreComments[key] = score.comment;
              }
            } else if (score.points === current.points && !scoreComments[key] && score.comment) {
              scoreComments[key] = score.comment;
            }
          }
        });
      }
    });

    // Add comments to final scores
    Object.keys(finalScores).forEach(key => {
      if (scoreComments[key]) {
        (finalScores[key as keyof SummaryScores] as any).comment = scoreComments[key];
      }
    });

    // Calculate Coverage score based on total heuristics and violations count
    // Priority: Use extracted_violations array if available, especially for "Heuristic Violation Analysis" pages
    const allHeuristics = new Set<number>();
    let totalViolationsCount = 0;
    
    analyzedPages.forEach(page => {
      // Check if this page is a "Heuristic Violation Analysis" type page
      const isHeuristicAnalysisPage = page.page_type && 
        (page.page_type.toLowerCase().includes("heuristic violation analysis") ||
         page.page_type.toLowerCase().includes("violation analysis") ||
         page.page_type.toLowerCase().includes("heuristic analysis"));
      
      // Priority 1: Use extracted_violations if available (especially for analysis pages)
      if (page.extracted_violations && page.extracted_violations.length > 0) {
        page.extracted_violations.forEach((v: any) => {
          const hNum = v.heuristic_num || v.heuristic_number;
          if (hNum && hNum >= 1 && hNum <= 10) {
            allHeuristics.add(hNum);
          }
          // Count each violation
          if (v.description || v.heuristic_num) {
            totalViolationsCount += 1;
          }
        });
      } 
      // Priority 2: For analysis pages, also check feedback if extracted_violations is empty
      else if (isHeuristicAnalysisPage && page.feedback) {
        // Extract individual heuristic numbers from feedback
        const heuristicMatches = page.feedback.matchAll(/heuristic\s+(\d+)/gi);
        for (const match of heuristicMatches) {
          const hNum = parseInt(match[1], 10);
          if (hNum >= 1 && hNum <= 10) {
            allHeuristics.add(hNum);
          }
        }
        
        // Try to extract violations count from feedback
        if (page.feedback) {
          const violationsMatch = page.feedback.match(/identifies?\s+(\d+)\s+violations?/i);
          if (violationsMatch) {
            totalViolationsCount += parseInt(violationsMatch[1], 10);
          } else {
            // If no explicit count, estimate based on heuristic mentions (rough estimate)
            // Count distinct violations by looking for violation descriptions
            const violationPatterns = [
              /violation\s+\d+/gi,
              /issue\s+\d+/gi,
              /problem\s+\d+/gi
            ];
            let foundViolations = 0;
            violationPatterns.forEach(pattern => {
              const matches = page.feedback!.matchAll(pattern);
              foundViolations = Math.max(foundViolations, Array.from(matches).length);
            });
            if (foundViolations === 0 && allHeuristics.size > 0) {
              // If we found heuristics but no explicit violation count, assume at least 1 per heuristic
              totalViolationsCount += allHeuristics.size;
            } else {
              totalViolationsCount += foundViolations;
            }
          }
        }
      }
      // Priority 3: For non-analysis pages, still try to extract from feedback
      else if (page.feedback) {
        // Extract heuristics count: "covers [X] heuristics" or "covers [X] heuristics:"
        const heuristicsMatch = page.feedback.match(/covers\s+(\d+)\s+heuristics?/i);
        if (heuristicsMatch) {
          // Don't add to totalHeuristicsCount, just add individual numbers
        }
        
        // Extract violations count: "Identifies [Y] violations" or "identifies [Y] violations"
        const violationsMatch = page.feedback.match(/identifies?\s+(\d+)\s+violations?/i);
        if (violationsMatch) {
          totalViolationsCount += parseInt(violationsMatch[1], 10);
        }
        
        // Also try to extract individual heuristic numbers mentioned
        const heuristicMatches = page.feedback.matchAll(/heuristic\s+(\d+)/gi);
        for (const match of heuristicMatches) {
          const hNum = parseInt(match[1], 10);
          if (hNum >= 1 && hNum <= 10) {
            allHeuristics.add(hNum);
          }
        }
      }
    });

    // Calculate Coverage score: 15 points if 10 heuristics AND 12 violations are met
    const coverageScore = (allHeuristics.size >= 10 && totalViolationsCount >= 12) ? 15 : 0;
    const coverageComment = (allHeuristics.size >= 10 && totalViolationsCount >= 12) 
      ? "" 
      : `Only ${allHeuristics.size} heuristics covered (need 10) and ${totalViolationsCount} violations identified (need 12)`;
    
    // Update coverage score in finalScores
    finalScores.coverage.points = coverageScore;
    if (coverageComment) {
      finalScores.coverage.comment = coverageComment;
    }

    // Calculate totals
    // Base score (out of 100): coverage + violation_quality + screenshots + severity_analysis + structure_navigation + professional_quality + writing_quality + group_integration
    const baseScore = finalScores.coverage.points + 
                     finalScores.violation_quality.points + 
                     finalScores.screenshots.points + 
                     finalScores.severity_analysis.points + 
                     finalScores.structure_navigation.points + 
                     finalScores.professional_quality.points + 
                     finalScores.writing_quality.points + 
                     finalScores.group_integration.points;
    const baseMaxScore = 100; // 15+20+10+10+10+10+10+15 = 100
    
    // Bonus score (extra credit): bonus_ai_opportunities + bonus_exceptional_quality
    const bonusScore = finalScores.bonus_ai_opportunities.points + 
                      finalScores.bonus_exceptional_quality.points;
    const bonusMaxScore = 5; // 3+2 = 5
    
    // Total score includes bonus as extra credit
    const totalScore = baseScore + bonusScore;
    const maxScore = baseMaxScore; // Display as out of 100, bonus is extra
    const percentage = Math.round((baseScore / baseMaxScore) * 100);

    return {
      totalScore,
      maxScore,
      percentage,
      baseScore,
      bonusScore,
      scores: finalScores,
      analyzedPages: analyzedPages.length,
      skippedPages,
      totalHeuristicsCount: allHeuristics.size, // Use unique count as total
      totalViolationsCount,
      uniqueHeuristicsCount: allHeuristics.size,
    };
  }, [analysisResults]);

  // Navigate to issue reviewer mode
  const handleGoToReviewerMode = () => {
    if (result?.jobId) {
      // Store jobId in localStorage for reviewer mode
      localStorage.setItem("recentJobIds", JSON.stringify([{ jobId: result.jobId, fileName: result.fileName }]));
      navigate(`/issue-reviewer?jobId=${result.jobId}`);
    }
  };

  // Check if analysis is complete (all extracted pages have been analyzed)
  const isAnalysisComplete =
    !analyzing &&
    analysisResults &&
    analysisResults.length > 0 &&
    getMissingPages.length === 0;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center px-4 py-8">
      <div className="w-full max-w-7xl bg-white shadow rounded-2xl p-6 space-y-6">
        <h1 className="text-2xl font-semibold text-slate-900">
          Upload your heuristic evaluation PDF
        </h1>

        {/* Duplicate File Warning */}
        {duplicateFile && (
          <div className="border border-amber-300 rounded-lg p-4 bg-amber-50">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0">
                <svg className="w-5 h-5 text-amber-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-amber-900 mb-1">
                  File Already Exists
                </h3>
                <p className="text-sm text-amber-800 mb-3">
                  A submission with the filename <span className="font-medium">"{duplicateFile.fileName}"</span> already exists.
                  {duplicateFile.hasAnalysis ? " It has been graded." : " It has not been graded yet."}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => handleDuplicateChoice("load")}
                    className="px-3 py-1.5 text-sm bg-sky-600 text-white rounded-md hover:bg-sky-700"
                  >
                    Load Existing
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDuplicateChoice("upload")}
                    className="px-3 py-1.5 text-sm bg-slate-600 text-white rounded-md hover:bg-slate-700"
                  >
                    Upload Anyway
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDuplicateChoice("delete")}
                    className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700"
                  >
                    Delete & Upload New
                  </button>
                  <button
                    type="button"
                    onClick={() => setDuplicateFile(null)}
                    className="px-3 py-1.5 text-sm bg-slate-200 text-slate-700 rounded-md hover:bg-slate-300"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Previous Submissions Section */}
        {previousSubmissions.length > 0 && (
          <div className="border border-slate-200 rounded-lg p-4 bg-slate-50">
            <h2 className="text-sm font-semibold text-slate-700 mb-3">
              Previous Submissions
            </h2>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {previousSubmissions.map((submission) => {
                const getStatusBadge = () => {
                  if (submission.status === "final_graded") {
                    return (
                      <span className="text-xs bg-purple-100 text-purple-800 px-2 py-0.5 rounded font-medium">
                        Final Graded
                      </span>
                    );
                  } else if (submission.status === "ta_reviewed") {
                    return (
                      <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded font-medium">
                        TA Reviewed
                      </span>
                    );
                  } else if (submission.status === "ai_graded" && submission.hasAnalysis) {
                    return (
                      <span className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded font-medium">
                        AI extracted
                      </span>
                    );
                  } else {
                    return (
                      <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-medium">
                        Not Graded
                      </span>
                    );
                  }
                };

                return (
                  <div
                    key={submission.jobId}
                    className="flex items-center justify-between p-3 bg-white rounded border border-slate-200 hover:border-slate-300 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-slate-900 truncate">
                          {submission.fileName || submission.jobId}
                        </span>
                        {getStatusBadge()}
                      </div>
                      {submission.createdAt && (
                        <p className="text-xs text-slate-500 mt-1">
                          {new Date(submission.createdAt).toLocaleString()}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 ml-3 flex-shrink-0">
                      {submission.status === "final_graded" && (
                        <button
                          type="button"
                          onClick={() => {
                            navigate(`/final-detail?jobId=${submission.jobId}`);
                          }}
                          className="px-3 py-1.5 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700"
                          title="View final grade details"
                        >
                          View Details
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={async () => {
                          await loadPreviousSubmission(submission.jobId);
                          // After loading a previous submission from the list, jump directly to Reviewer Mode
                          localStorage.setItem(
                            "recentJobIds",
                            JSON.stringify([{ jobId: submission.jobId, fileName: submission.fileName }]),
                          );
                          navigate(`/issue-reviewer?jobId=${submission.jobId}`);
                        }}
                        disabled={loading}
                        className="px-3 py-1.5 text-sm bg-sky-600 text-white rounded-md hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {loading ? "Loading..." : "Load"}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`Are you sure you want to delete "${submission.fileName || submission.jobId}"? This action cannot be undone.`)) {
                            deleteSubmission(submission.jobId);
                          }
                        }}
                        className="px-2 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700"
                        title="Delete submission"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Batch Mode Toggle */}
        <div className="flex items-center gap-4 mb-4">
          <label className="relative inline-flex items-center cursor-pointer group">
            <input
              type="checkbox"
              checked={batchMode}
              onChange={(e) => {
                setBatchMode(e.target.checked);
                if (!e.target.checked) {
                  clearBatch();
                }
              }}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-slate-300 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-sky-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sky-600"></div>
            <span className="ml-3 text-sm font-medium text-slate-700 group-hover:text-slate-900">
              Batch Mode
            </span>
          </label>
          {batchMode && (
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <label>Batch Size:</label>
              <select
                value={batchSize}
                onChange={(e) => setBatchSize(parseInt(e.target.value, 10))}
                disabled={batchProcessing}
                className="px-2 py-1 border border-slate-300 rounded text-sm"
              >
                <option value={1}>1 at a time</option>
                <option value={2}>2 at a time</option>
                <option value={5}>5 at a time</option>
                <option value={10}>10 at a time</option>
              </select>
            </div>
          )}
        </div>

        {/* Batch Queue Display */}
        {batchMode && batchQueue.length > 0 && (
          <div className="border border-slate-200 rounded-lg p-4 bg-slate-50 mb-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-700">
                Batch Queue ({batchQueue.filter(q => q.status === "completed").length}/{batchQueue.length} completed)
              </h2>
              <div className="flex gap-2">
                {!batchProcessing && !batchPaused && (
                  <button
                    type="button"
                    onClick={processBatch}
                    className="px-3 py-1.5 text-sm bg-green-600 text-white rounded-md hover:bg-green-700"
                  >
                    Start Processing
                  </button>
                )}
                {batchProcessing && !batchPaused && (
                  <button
                    type="button"
                    onClick={pauseBatch}
                    className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded-md hover:bg-amber-700"
                  >
                    Pause
                  </button>
                )}
                {batchPaused && (
                  <button
                    type="button"
                    onClick={resumeBatch}
                    className="px-3 py-1.5 text-sm bg-sky-600 text-white rounded-md hover:bg-sky-700"
                  >
                    Resume
                  </button>
                )}
                <button
                  type="button"
                  onClick={clearBatch}
                  disabled={batchProcessing}
                  className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
            </div>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {batchQueue.map((item, index) => {
                // Check if this file matches a previous submission
                // Only show as duplicate if the item is NOT completed (completed items are expected to be in previous submissions)
                const duplicateSubmission = item.status !== "completed" 
                  ? previousSubmissions.find((sub) => sub.fileName === item.file.name)
                  : null;
                
                return (
                  <div
                    key={index}
                    className="p-2 bg-white rounded border border-slate-200"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-slate-900 truncate">
                            {item.file.name}
                          </span>
                          {duplicateSubmission && (
                            <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
                              Duplicate
                            </span>
                          )}
                          {item.status === "pending" && (
                            <span className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                              Pending
                            </span>
                          )}
                          {item.status === "extracting" && (
                            <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                              Extracting...
                            </span>
                          )}
                          {item.status === "analyzing" && (
                            <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
                              Analyzing... {item.progress}%
                            </span>
                          )}
                          {item.status === "completed" && (
                            <span className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded">
                              Completed
                            </span>
                          )}
                          {item.status === "error" && (
                            <span className="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded">
                              Error
                            </span>
                          )}
                        </div>
                        {duplicateSubmission && (
                          <p className="text-xs text-amber-600 mt-1">
                            Already exists: {duplicateSubmission.hasAnalysis ? "Graded" : "Not Graded"}
                          </p>
                        )}
                        {item.progress !== undefined && item.status !== "completed" && (
                          <div className="mt-1 w-full bg-slate-200 rounded-full h-1.5">
                            <div
                              className="bg-sky-600 h-1.5 rounded-full transition-all"
                              style={{ width: `${item.progress}%` }}
                            />
                          </div>
                        )}
                        {item.error && (
                          <p className="text-xs text-red-600 mt-1">{item.error}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 ml-3">
                        {duplicateSubmission && item.status === "pending" && (
                          <button
                            type="button"
                            onClick={async () => {
                              if (window.confirm(`Are you sure you want to delete the existing submission "${duplicateSubmission.fileName}"? This action cannot be undone.`)) {
                                await deleteSubmission(duplicateSubmission.jobId);
                                await refreshPreviousSubmissions();
                              }
                            }}
                            className="px-2 py-1 text-xs bg-red-600 text-white rounded-md hover:bg-red-700"
                            title="Delete existing submission"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        )}
                        {item.status === "pending" && (
                          <button
                            type="button"
                            onClick={() => {
                              setBatchQueue(prev => prev.filter((_, i) => i !== index));
                            }}
                            className="px-2 py-1 text-xs bg-slate-600 text-white rounded-md hover:bg-slate-700"
                            title="Remove from queue"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              {batchMode ? "Submission files (PDF) - Select multiple" : "Submission file (PDF)"}
            </label>
            <input
              type="file"
              accept="application/pdf"
              multiple={batchMode}
              onChange={handleFileChange}
              className="block w-full text-sm text-slate-700
                         file:mr-4 file:py-2 file:px-4
                         file:rounded-md file:border-0
                         file:text-sm file:font-semibold
                         file:bg-slate-100 file:text-slate-700
                         hover:file:bg-slate-200"
            />
            <p className="mt-1 text-xs text-slate-500">
              {batchMode 
                ? "Select multiple PDF files. They will be processed in batches."
                : "We will automatically extract the pages where you discuss Nielsen's heuristics (not pages that only describe the interface)."}
            </p>
            {batchMode && batchFiles.length > 0 && (
              <p className="mt-1 text-xs text-slate-600">
                {batchFiles.length} file(s) selected
              </p>
            )}
          </div>

          {!batchMode && (
            <button
              type="submit"
              disabled={!file || loading}
              className="inline-flex items-center justify-center rounded-md
                         bg-sky-600 px-4 py-2 text-sm font-medium text-white
                         hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Analyzing…" : "Upload & Extract Heuristic Pages"}
            </button>
          )}
          
          {batchMode && batchFiles.length > 0 && (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={processBatch}
                disabled={batchProcessing || batchQueue.length === 0}
                className="inline-flex items-center justify-center rounded-md
                           bg-sky-600 px-4 py-2 text-sm font-medium text-white
                           hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {batchProcessing ? "Processing..." : "Start Batch Processing"}
              </button>
            </div>
          )}

          {error && (
            <div className="border-2 border-red-300 rounded-lg p-4 bg-red-50 mt-2">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0">
                  <svg className="w-5 h-5 text-red-600" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-red-900 mb-1">
                    Error
                  </h3>
                  <p className="text-sm text-red-800 whitespace-pre-wrap">
                    {error}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setError(null)}
                  className="flex-shrink-0 text-red-600 hover:text-red-800"
                  title="Dismiss error"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </form>

        {loading && (
          <div className="border-t border-slate-200 pt-4">
            <p className="text-sm text-slate-600">Parsing PDF and extracting pages…</p>
          </div>
        )}

        {result && (
          <div className="border-t border-slate-200 pt-6 space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">
                    Extracted Heuristic Discussion Pages
                  </h2>
                  <p className="text-sm text-slate-600">
                    Uploaded file: <span className="font-semibold text-slate-800">{result.fileName}</span>
                  </p>
                  <p className="text-sm text-slate-600">
                    Total pages detected: <span className="font-semibold text-slate-800">{result.pageCount}</span>
                  </p>
                  {isAnalysisComplete && analysisResults && (
                    <div className="mt-2">
                      {(() => {
                        const extractedPageNumbers = new Set(result.pages.map(p => p.pageNumber));
                        const analyzedPageNumbers = new Set(
                          analysisResults
                            .filter(a => !a.skip_analysis)
                            .map(a => a.page_number)
                        );
                        const missingAnalysis = Array.from(extractedPageNumbers).filter(
                          pn => !analyzedPageNumbers.has(pn)
                        );
                        const extraAnalysis = Array.from(analyzedPageNumbers).filter(
                          pn => !extractedPageNumbers.has(pn)
                        );
                        const isMatch = missingAnalysis.length === 0 && extraAnalysis.length === 0;
                        
                        return (
                          <div className={`text-xs px-2 py-1 rounded ${
                            isMatch 
                              ? "bg-green-100 text-green-800" 
                              : "bg-yellow-100 text-yellow-800"
                          }`}>
                            {isMatch ? (
                              <span>✓ Pages match: {extractedPageNumbers.size} extracted = {analyzedPageNumbers.size} analyzed</span>
                            ) : (
                              <div>
                                <div>⚠ Page mismatch detected:</div>
                                {missingAnalysis.length > 0 && (
                                  <div className="mt-1">Missing analysis for pages: {missingAnalysis.sort((a, b) => a - b).join(", ")}</div>
                                )}
                                {extraAnalysis.length > 0 && (
                                  <div className="mt-1">Extra analysis for pages: {extraAnalysis.sort((a, b) => a - b).join(", ")}</div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  )}
                  {getMissingPages.length > 0 && isAnalysisComplete && (
                    <div className="mt-2">
                      <button
                        type="button"
                        onClick={handleAnalyzeMissingPages}
                        disabled={analyzing}
                        className="inline-flex items-center justify-center rounded-md
                                   bg-orange-600 px-3 py-1.5 text-xs font-medium text-white
                                   hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {analyzing ? `Analyzing ${getMissingPages.length} missing pages...` : `Analyze ${getMissingPages.length} Missing Page${getMissingPages.length > 1 ? 's' : ''}`}
                      </button>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {isAnalysisComplete ? (
                    <>
                      <button
                        type="button"
                        onClick={handleGoToReviewerMode}
                        className="inline-flex items-center justify-center rounded-md
                                   bg-purple-600 px-4 py-2 text-sm font-medium text-white
                                   hover:bg-purple-700 transition-colors"
                      >
                        Go to Reviewer Mode
                      </button>
                      <button
                        type="button"
                        onClick={handleRerunAnalysis}
                        disabled={analyzing}
                        className="inline-flex items-center justify-center rounded-md
                                   bg-emerald-600 px-4 py-2 text-sm font-medium text-white
                                   hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {analyzing ? "Re-analyzing with Gemini…" : "Rerun Analysis with Gemini"}
                      </button>
                    </>
                  ) : result && result.pages.length > 0 ? (
                    <button
                      type="button"
                      onClick={handleAnalyze}
                      disabled={analyzing}
                      className="inline-flex items-center justify-center rounded-md
                                 bg-emerald-600 px-4 py-2 text-sm font-medium text-white
                                 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {analyzing ? "Analyzing with Gemini…" : "Analyze with Gemini"}
                    </button>
                  ) : null}
                </div>
              </div>
            </div>

            {analyzing && analyzingProgress && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-blue-900">
                    Analyzing with Gemini AI...
                  </p>
                  <p className="text-sm text-blue-700">
                    {analyzingProgress.current} / {analyzingProgress.total}
                  </p>
                </div>
                <div className="w-full bg-blue-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                    style={{
                      width: `${(analyzingProgress.current / analyzingProgress.total) * 100}%`,
                    }}
                  />
                </div>
                <p className="text-xs text-blue-700 mt-2">
                  Currently analyzing page {analyzingProgress.current} of {analyzingProgress.total}...
                </p>
              </div>
            )}

            {/* Page-by-page Progress Display */}
            {result && result.pages.length > 0 && (
              <div className="rounded-lg border-2 border-slate-300 bg-slate-50 p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-bold text-slate-900">
                    Page Analysis Progress
                  </h2>
                  {analyzing && analyzingProgress && (
                    <span className="text-xs text-slate-600">
                      {analyzingProgress.current} / {analyzingProgress.total} analyzed
                    </span>
                  )}
                </div>
                <div className="space-y-4 max-h-[600px] overflow-y-auto">
                  {result.pages.map((page) => {
                    const analysis = analysisResults?.find(a => a.page_number === page.pageNumber);
                    const isAnalyzing = analyzing && !analysis;
                    const hasError = analysis?.error;
                    return (
                      <div
                        key={page.pageNumber}
                        className="rounded-xl border border-slate-200 bg-white p-4"
                      >
                        <div className="mb-2 flex items-center justify-between">
                          <span className="text-sm font-semibold text-slate-800">
                            Page {page.pageNumber}
                          </span>
                          {isAnalyzing ? (
                            <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-800">
                              Analyzing...
                            </span>
                          ) : hasError ? (
                            <span className="text-xs px-2 py-1 rounded-full bg-red-100 text-red-800">
                              Error
                            </span>
                          ) : analysis && (
                            <span className={`text-xs px-2 py-1 rounded-full ${
                              analysis.skip_analysis 
                                ? "bg-slate-100 text-slate-600" 
                                : "bg-emerald-100 text-emerald-800"
                            }`}>
                              {analysis.skip_analysis ? "Skipped" : "Analyzed"}
                            </span>
                          )}
                        </div>
                        {page.imageBase64 && (
                          <img
                            src={page.imageBase64}
                            alt={`Page ${page.pageNumber}`}
                            className="mb-3 w-full rounded-lg border border-slate-200 bg-white"
                          />
                        )}
                        {hasError && (
                          <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-2">
                            <div className="text-xs text-red-800 font-medium mb-1">
                              Error:
                            </div>
                            <div className="text-xs text-red-700">
                              {analysis.error}
                            </div>
                          </div>
                        )}
                        {analysis && !hasError && !analysis.skip_analysis && (
                          <div className="mt-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 space-y-2">
                            {/* Structured Analysis (new format) */}
                            {analysis.structured_analysis ? (
                              <>
                                <div className="text-xs font-semibold text-emerald-900 mb-2">
                                  Analysis Results:
                                </div>
                                <div className="space-y-1.5 text-xs">
                                  <div>
                                    <span className="font-medium text-emerald-800">Page Role:</span>{" "}
                                    <span className="text-emerald-700">{analysis.structured_analysis.page_role}</span>
                                  </div>
                                  {analysis.structured_analysis.main_heading && (
                                    <div>
                                      <span className="font-medium text-emerald-800">Main Heading:</span>{" "}
                                      <span className="text-emerald-700">{analysis.structured_analysis.main_heading}</span>
                                    </div>
                                  )}
                                  {analysis.structured_analysis.fragments && analysis.structured_analysis.fragments.length > 0 && (
                                    <div>
                                      <span className="font-medium text-emerald-800">Heuristic Fragments:</span>{" "}
                                      <span className="text-emerald-700">{analysis.structured_analysis.fragments.length} found</span>
                                      <div className="mt-1 ml-2 space-y-1">
                                        {analysis.structured_analysis.fragments.slice(0, 3).map((fragment, idx) => (
                                          <div key={idx} className="text-emerald-700">
                                            • {fragment.heuristic_id}: {fragment.text_summary.substring(0, 100)}
                                            {fragment.text_summary.length > 100 ? "..." : ""}
                                          </div>
                                        ))}
                                        {analysis.structured_analysis.fragments.length > 3 && (
                                          <div className="text-emerald-600 italic">
                                            + {analysis.structured_analysis.fragments.length - 3} more...
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                  {analysis.structured_analysis.severity_summary && (
                                    <div>
                                      <span className="font-medium text-emerald-800">Severity Summary:</span>{" "}
                                      <span className="text-emerald-700">
                                        {analysis.structured_analysis.severity_summary.visualization} - {
                                          analysis.structured_analysis.severity_summary.mapping_clarity
                                        }
                                      </span>
                                    </div>
                                  )}
                                </div>
                              </>
                            ) : (
                              /* Legacy format */
                              <>
                                <div className="text-xs font-semibold text-emerald-900 mb-2">
                                  Analysis Results:
                                </div>
                                <div className="space-y-1.5 text-xs">
                                  {analysis.page_type && (
                                    <div>
                                      <span className="font-medium text-emerald-800">Page Type:</span>{" "}
                                      <span className="text-emerald-700">{analysis.page_type}</span>
                                    </div>
                                  )}
                                  {analysis.extracted_violations && analysis.extracted_violations.length > 0 && (
                                    <div>
                                      <span className="font-medium text-emerald-800">Violations Found:</span>{" "}
                                      <span className="text-emerald-700">{analysis.extracted_violations.length}</span>
                                      <div className="mt-1 ml-2 space-y-1">
                                        {analysis.extracted_violations.slice(0, 3).map((violation, idx) => (
                                          <div key={idx} className="text-emerald-700">
                                            • {violation.heuristic_name || `H${violation.heuristic_num || violation.heuristic_number || "?"}`}: {
                                              violation.description?.substring(0, 80) || "No description"
                                            }
                                            {violation.description && violation.description.length > 80 ? "..." : ""}
                                          </div>
                                        ))}
                                        {analysis.extracted_violations.length > 3 && (
                                          <div className="text-emerald-600 italic">
                                            + {analysis.extracted_violations.length - 3} more...
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                  {analysis.feedback && (
                                    <div>
                                      <span className="font-medium text-emerald-800">Feedback:</span>{" "}
                                      <span className="text-emerald-700">
                                        {analysis.feedback.substring(0, 200)}
                                        {analysis.feedback.length > 200 ? "..." : ""}
                                      </span>
                                    </div>
                                  )}
                                </div>
                              </>
                            )}
                          </div>
                        )}
                        {analysis && analysis.skip_analysis && (
                          <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
                            <div className="text-xs text-slate-600">
                              Skipped: {analysis.skip_reason || "No reason provided"}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}


            {result && result.pages.length === 0 ? (
              <p className="text-sm text-slate-500">
                No pages matched the heuristics criteria. Try refining your submission.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
