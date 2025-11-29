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
