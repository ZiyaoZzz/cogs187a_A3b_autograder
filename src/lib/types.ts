export interface HeuristicExtractionPage {
  pageNumber: number;
  snippet: string;
  imageBase64?: string;
}

export interface HeuristicExtractionResult {
  jobId: string;
  fileName?: string;
  createdAt: string;
  pageCount: number;
  pages: HeuristicExtractionPage[];
}

export type PageRole =
  | "intro"
  | "group_collab"
  | "heuristic_explainer"
  | "violation_detail"
  | "severity_summary"
  | "conclusion"
  | "ai_opportunities"
  | "other";

export type RubricLevel = "none" | "low" | "med" | "high";

export interface HeuristicFragment {
  heuristic_id: string; // e.g. "H1", "H3", "H7"
  issue_key: string;    // short slug within this submission, e.g. "search_bar_mobile_hidden"
  fragment_role: (
    | "problem_description"
    | "impact"
    | "evidence"
    | "design_rationale"
    | "fix_idea"
  )[];
  text_summary: string; // 1–2 sentences: what this page says about this heuristic/issue
  severity_hint?: "minor" | "major" | "critical";
  rubric_tags?: (
    | "coverage"
    | "violation_quality"
    | "severity_analysis"
    | "screenshots_evidence"
  )[];
}

export interface SeveritySummaryInfo {
  is_summary: true;
  visualization: "table" | "plot" | "mixed" | "text_only";
  coverage_scope: "all_issues" | "major_issues_only" | "unclear";
  mapping_clarity: "clear" | "somewhat_clear" | "unclear";
  llm_note: string; // 1–2 sentences describing what the summary visualization is trying to convey and how clear it is
}

export interface AiOpportunitiesInfo {
  present: true;
  raw_text_excerpt: string;        // short excerpt (3–6 sentences max)
  llm_summary: string;             // 2–3 sentence summary of what AI is supposed to do
  relevance_to_violations: "low" | "med" | "high";
  specificity: "generic" | "somewhat_specific" | "very_specific";
}

export interface PageAnalysis {
  page_id: string;      // internal ID, like "p01", "p02"
  page_number: number;  // original page index (1-based)
  page_role: PageRole;
  main_heading?: string; // main title text on the slide, if any
  has_annotations: "none" | "low" | "medium" | "high";
  // how much this page matters for each rubric component
  rubric_relevance: {
    coverage: RubricLevel;
    violation_quality: RubricLevel;
    severity_analysis: RubricLevel;
    screenshots_evidence: RubricLevel;
    group_integration: RubricLevel;
    professional_quality: RubricLevel;
    writing_quality: RubricLevel;
  };
  // ID connecting pages that share the same screenshot image
  screenshot_cluster_id?: string; // e.g. "ss_1"
  fragments: HeuristicFragment[];
  severity_summary?: SeveritySummaryInfo; // only present when page_role === "severity_summary"
  ai_opportunities_info?: AiOpportunitiesInfo; // only present when page_role === "ai_opportunities"
  ta_review?: {
    override_reason?: string;
    ta_comment?: string;
  };
}

// Legacy types for backward compatibility
export interface ExtractedViolation {
  heuristic_num?: number;
  heuristic_number?: number;
  heuristic_name?: string;
  description?: string;
  severity?: string;
}

export interface PageAnalysisResult {
  page_number: number;
  skip_analysis?: boolean;
  page_type?: string;
  skip_reason?: string;
  extracted_violations?: ExtractedViolation[];
  feedback?: string;
  compelling?: boolean;
  score_breakdown?: {
    [key: string]: {
      points: number;
      max: number;
      comment: string;
    };
  };
  bonus_scores?: {
    [key: string]: {
      points: number;
      max: number;
      comment: string;
    };
  };
  overall_assessment?: string;
  error?: string;
  // New structured analysis (optional for backward compatibility)
  structured_analysis?: PageAnalysis;
}

export interface SummaryScores {
  coverage: { points: number; max: number; comment?: string };
  violation_quality: { points: number; max: number; comment?: string };
  screenshots: { points: number; max: number; comment?: string };
  severity_analysis: { points: number; max: number; comment?: string };
  structure_navigation: { points: number; max: number; comment?: string };
  professional_quality: { points: number; max: number; comment?: string };
  writing_quality: { points: number; max: number; comment?: string };
  group_integration: { points: number; max: number; comment?: string };
  bonus_ai_opportunities: { points: number; max: number; comment?: string };
  bonus_exceptional_quality: { points: number; max: number; comment?: string };
}

export interface AssignmentSummary {
  totalScore: number;
  maxScore: number;
  percentage: number;
  baseScore: number;
  bonusScore: number;
  scores: SummaryScores;
  analyzedPages: number;
  skippedPages: number;
  totalHeuristicsCount: number;
  totalViolationsCount: number;
  uniqueHeuristicsCount: number;
}

// Reviewer Mode (HITL) types
export interface OverrideRecord {
  id: string;
  jobId: string;
  pageNumber: number;
  field: string; // e.g., "score_breakdown.violation_quality.points", "feedback", "extracted_violations[0].severity"
  originalValue: any;
  overrideValue: any;
  reviewerName?: string;
  reviewerNotes?: string;
  timestamp: string;
}

export interface PageAnalysisWithOverride extends PageAnalysisResult {
  overrides?: OverrideRecord[];
  hasOverrides?: boolean;
}

export interface ReviewerSubmission {
  jobId: string;
  fileName?: string;
  createdAt: string;
  pages: HeuristicExtractionPage[];
  analysisResults: PageAnalysisWithOverride[];
  totalOverrides?: number;
}

export interface AICorrection {
  id: string;
  jobId: string;
  pageNumber: number;
  component: string;
  reason: string;
  originalValue: any;
  correctedValue: any;
  reviewerNotes?: string;
  timestamp: string;
}

export interface AIRiskPage {
  pageNumber: number;
  notes?: string;
  timestamp?: string;
  // Legacy fields (for backward compatibility, but not used for manual flags)
  riskScore?: number;
  flags?: string[];
}

export interface AIFlags {
  jobId: string;
  flags: any[];
  riskPages: AIRiskPage[];
  totalRiskPages: number;
}

// Issue-level model for TA review
export interface Issue {
  issue_id: string;       // generated ID, e.g. "issue_001" (unique per submission)
  heuristic_id: string;   // "H1".."H10"
  issue_key: string;      // carries over from fragments, e.g. "search_bar_mobile_hidden"

  title: string;                // short human-readable title
  combined_description: string; // combined description from fragments

  pages_involved: string[];         // page_ids like ["p03","p04","p05"]
  screenshot_cluster_ids: string[]; // e.g. ["ss_2"]

  ai_proposed_severity: "minor" | "major" | "critical";
  ai_severity_rationale: string;

  ta_review?: {
    final_severity: "minor" | "major" | "critical";
    final_score_0_4: number;      // TA's final score for this issue (0–4)
    override_reason?: string;
    ta_comment?: string;
  };
}

// Scoring types for LLM-based final scoring
export interface IssueRubricScores {
  coverage?: number;
  violation_quality?: number;
  severity_analysis?: number;
  screenshots_evidence?: number;
  structure_navigation?: number;
  professional_quality?: number;
  writing_quality?: number;
  group_integration?: number;
}

export interface ScoringIssueForLLM {
  issue_id: string;
  heuristic_id: string;
  title: string;
  combined_description: string;
  pages_involved: string[];
  ai_proposed_severity: "minor" | "major" | "critical";
  ai_rubric_scores?: IssueRubricScores;
  ta_review?: {
    final_severity: "minor" | "major" | "critical";
    final_issue_score_0_4: number;
    rubric_overrides?: IssueRubricScores;
    override_reason?: string;
    ta_comment?: string;
  };
}

export interface ScoringInput {
  job_id: string;
  rubric_brief: string;
  submission_meta?: {
    num_pages: number;
    num_issues: number;
  };
  issues: ScoringIssueForLLM[];
  ai_opportunities_pages?: {
    page_id: string;
    llm_summary: string;
    raw_text_excerpt: string;
    relevance_to_violations: "low" | "med" | "high";
    specificity: "generic" | "somewhat_specific" | "very_specific";
  }[];
}

export interface ScoringOutput {
  overall_score_0_100: number;
  rubric_scores: {
    coverage: { points: number; max: number; explanation: string };             // max: 15, based on count of heuristics/violations
    violation_quality: { points: number; max: number; explanation: string };    // max: 20, evaluated on heuristic pages
    severity_analysis: { points: number; max: number; explanation: string };    // max: 10, evaluated on heuristic pages
    screenshots_evidence: { points: number; max: number; explanation: string }; // max: 10, evaluated on heuristic pages
    structure_navigation: { points: number; max: number; explanation: string }; // max: 10, evaluated on heuristic pages
    professional_quality: { points: number; max: number; explanation: string }; // max: 10, evaluated on intro/group pages and overall
    writing_quality: { points: number; max: number; explanation: string };      // max: 10, evaluated on intro/group pages and overall
    group_integration: { points: number; max: number; explanation: string };    // max: 15, evaluated on intro/group pages only
  };
  bonus_scores?: {
    bonus_ai_opportunities: { points: number; max: number; explanation?: string }; // max: 3
    bonus_exceptional_quality: { points: number; max: number; explanation?: string }; // max: 1
  };
  summary_comment: string;              // 2–4 sentences
  ai_vs_ta_notes?: string;
}
