// API utility functions and constants
const API_BASE = "http://localhost:8000";

export { API_BASE };

async function parseError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data === "string") return data;
    if (data?.detail) return data.detail;
    return JSON.stringify(data);
  } catch {
    try {
      return await response.text();
    } catch {
      return `Request failed with status ${response.status}`;
    }
  }
}

async function apiFetch<T>(endpoint: string, init?: RequestInit): Promise<T> {
  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE}${endpoint}`;
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json") || contentType.includes("text/json")) {
    return response.json() as Promise<T>;
  }
  return (response.text() as unknown) as T;
}

/**
 * Check job status (analysis, overrides, final grade)
 */
export async function checkJobStatus(jobId: string): Promise<{
  hasAnalysis: boolean;
  hasOverrides: boolean;
  hasFinalGrade: boolean;
  status?: "ai_graded" | "ta_reviewed" | "final_graded" | undefined;
}> {
  try {
    // Check for analysis results
    const analysisRes = await fetch(`${API_BASE}/api/get-analysis-results?jobId=${jobId}`);
    const hasAnalysis = analysisRes.ok && (await analysisRes.json()).results?.length > 0;
    
    // Check for overrides (TA review)
    let hasOverrides = false;
    try {
      const overridesRes = await fetch(`${API_BASE}/api/get-overrides?jobId=${jobId}`);
      if (overridesRes.ok) {
        const overridesData = await overridesRes.json();
        hasOverrides = overridesData.overrides && overridesData.overrides.length > 0;
      }
    } catch {
      // Ignore errors
    }
    
    // Only check for final grade if there's analysis or overrides (to avoid unnecessary 404s)
    let hasFinalGrade = false;
    if (hasAnalysis || hasOverrides) {
      try {
        const finalGradeRes = await fetch(`${API_BASE}/api/get-final-grade?jobId=${jobId}`);
        if (finalGradeRes.ok) {
          const finalGradeData = await finalGradeRes.json();
          hasFinalGrade = finalGradeData.finalGrade !== undefined && finalGradeData.finalGrade !== null;
        }
      } catch {
        // Ignore errors (404 is normal if no final grade exists)
      }
    }
    
    // Determine status
    let status: "ai_graded" | "ta_reviewed" | "final_graded" | undefined = undefined;
    if (hasFinalGrade) {
      status = "final_graded";
    } else if (hasOverrides) {
      status = "ta_reviewed";
    } else if (hasAnalysis) {
      status = "ai_graded";
    }
    
    return {
      hasAnalysis,
      hasOverrides,
      hasFinalGrade,
      status,
    };
  } catch {
    return {
      hasAnalysis: false,
      hasOverrides: false,
      hasFinalGrade: false,
      status: undefined,
    };
  }
}

/**
 * Load all jobs with their status information
 */
export async function loadJobsWithStatus(): Promise<Array<{
  jobId: string;
  fileName?: string;
  createdAt?: string;
  hasAnalysis?: boolean;
  hasOverrides?: boolean;
  hasFinalGrade?: boolean;
  status?: "ai_graded" | "ta_reviewed" | "final_graded" | undefined;
}>> {
  const res = await fetch(`${API_BASE}/api/list-jobs`);
  if (!res.ok) {
    return [];
  }
  
  const data = await res.json();
  const jobs = data.jobs || [];
  
  // Check status for each job
  const jobsWithStatus = await Promise.all(
    jobs.map(async (job: any) => {
      const status = await checkJobStatus(job.jobId);
      return {
        ...job,
        ...status,
      };
    })
  );
  
  // Sort: ungraded (no analysis) first, then by date (newest first)
  jobsWithStatus.sort((a, b) => {
    if (a.hasAnalysis !== b.hasAnalysis) {
      return a.hasAnalysis ? 1 : -1; // ungraded first
    }
    const dateA = a.createdAt ? new Date(a.createdAt).getTime() : 0;
    const dateB = b.createdAt ? new Date(b.createdAt).getTime() : 0;
    return dateB - dateA; // newest first
  });
  
  return jobsWithStatus;
}

export async function listJobs(): Promise<any[]> {
  const data = await apiFetch<{ jobs?: any[] }>("/api/list-jobs");
  return data.jobs || [];
}

export async function getIssues(jobId: string): Promise<{ jobId: string; issues: any[] }> {
  return apiFetch(`/api/get-issues?jobId=${encodeURIComponent(jobId)}`);
}

export async function getPages(jobId: string): Promise<{ jobId: string; pages: any[] }> {
  return apiFetch(`/api/get-pages?jobId=${encodeURIComponent(jobId)}`);
}

export async function getExtractionResult(jobId: string): Promise<{ pages: any[] }> {
  return apiFetch(`/api/get-extraction-result?jobId=${encodeURIComponent(jobId)}`);
}

export async function getRubricComments(jobId: string): Promise<{ comments: Record<string, string> } | null> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/rubric-comments`);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function saveRubricComments(jobId: string, comments: Record<string, string>) {
  await apiFetch(`/api/jobs/${jobId}/rubric-comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comments }),
  });
}

export async function getScoringOutput(jobId: string): Promise<{ scoring: any } | null> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/scoring`);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function calculateGradingScores(jobId: string): Promise<{ scores: any }> {
  return apiFetch(`/api/calculate-grading-scores?jobId=${encodeURIComponent(jobId)}`);
}

export async function saveGradingScores(jobId: string, scores: any) {
  await apiFetch("/api/save-grading-scores", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobId, scores }),
  });
}

export async function getIssueScores(jobId: string): Promise<Record<string, any>> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/issue-scores`);
  if (response.status === 404) {
    return {};
  }
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  const data = await response.json();
  return data.issues || {};
}

export async function saveIssueScores(jobId: string, issueId: string, scores: any) {
  await apiFetch("/api/save-issue-scores", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobId, issueId, scores }),
  });
}

export async function updatePageMetadata(jobId: string, pageId: string, updates: Record<string, any>) {
  await apiFetch("/api/update-page-metadata", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobId, pageId, ...updates }),
  });
}

export async function updateIssueReview(jobId: string, issueId: string, taReview: any) {
  await apiFetch("/api/update-issue-review", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobId, issueId, ta_review: taReview }),
  });
}

export async function getCurrentPrompt(): Promise<any> {
  return apiFetch("/api/get-current-prompt");
}

export async function startPromptRefinement(payload: { originalPrompt: string; iterations: number }): Promise<any> {
  return apiFetch("/api/start-prompt-refinement", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function critiquePrompt(payload: Record<string, any>): Promise<any> {
  return apiFetch("/api/critique-prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function refinePrompt(payload: Record<string, any>): Promise<any> {
  return apiFetch("/api/refine-prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function generateFinalPrompt(payload: Record<string, any>): Promise<any> {
  return apiFetch("/api/generate-final-prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function savePrompt(prompt: string): Promise<any> {
  return apiFetch("/api/save-prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
}

export async function runRuthlessAuditRequest(payload: Record<string, any>): Promise<any> {
  return apiFetch("/api/ruthless-audit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function runEnhancedPromptRefinement(payload: Record<string, any>): Promise<any> {
  return apiFetch("/api/enhanced-prompt-refinement", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

