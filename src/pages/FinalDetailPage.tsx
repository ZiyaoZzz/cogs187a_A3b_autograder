import React, { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type {
  HeuristicExtractionResult,
  PageAnalysisResult,
  OverrideRecord,
} from "../lib/types";
import { API_BASE } from "../lib/api";

interface FinalGradeData {
  finalGrade: number;
  maxGrade: number;
  overallFeedback?: string;
  timestamp?: string;
}

export default function FinalDetailPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const jobId = searchParams.get("jobId") || "";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [extractionResult, setExtractionResult] = useState<HeuristicExtractionResult | null>(null);
  const [analysisResults, setAnalysisResults] = useState<PageAnalysisResult[]>([]);
  const [overrides, setOverrides] = useState<OverrideRecord[]>([]);
  const [finalGrade, setFinalGrade] = useState<FinalGradeData | null>(null);

  useEffect(() => {
    if (jobId) {
      loadData();
    } else {
      setError("No job ID provided");
      setLoading(false);
    }
  }, [jobId]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Load extraction result
      const pagesRes = await fetch(`${API_BASE}/api/get-extraction-result?jobId=${jobId}`);
      if (!pagesRes.ok) throw new Error("Failed to load extraction result");
      const pagesData = await pagesRes.json();
      setExtractionResult(pagesData);

      // Load analysis results
      const analysisRes = await fetch(`${API_BASE}/api/get-analysis-results?jobId=${jobId}`);
      if (analysisRes.ok) {
        const analysisData = await analysisRes.json();
        setAnalysisResults(analysisData.results || []);
      }

      // Load overrides
      const overridesRes = await fetch(`${API_BASE}/api/get-overrides?jobId=${jobId}`);
      if (overridesRes.ok) {
        const overridesData = await overridesRes.json();
        setOverrides(overridesData.overrides || []);
      }

      // Load final grade
      const finalGradeRes = await fetch(`${API_BASE}/api/get-final-grade?jobId=${jobId}`);
      if (finalGradeRes.ok) {
        const finalGradeData = await finalGradeRes.json();
        setFinalGrade(finalGradeData);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-600 mx-auto mb-4"></div>
          <p className="text-slate-600">Loading final grade details...</p>
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

  return (
    <div className="min-h-screen bg-slate-50 py-8">
      <div className="max-w-7xl mx-auto px-4">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 mb-2">Final Grade Details</h1>
            <p className="text-slate-600">
              {extractionResult?.fileName || jobId}
            </p>
          </div>
          <button
            onClick={() => navigate("/upload")}
            className="px-4 py-2 bg-slate-600 text-white rounded-md hover:bg-slate-700"
          >
            Back to Upload
          </button>
        </div>

        {/* Final Grade Summary */}
        {finalGrade && (
          <div className="bg-white rounded-lg shadow-lg p-6 mb-6 border-2 border-purple-300">
            <h2 className="text-2xl font-bold text-purple-900 mb-4">Final Grade</h2>
            <div className="flex items-baseline gap-4 mb-4">
              <div className="text-5xl font-bold text-purple-700">
                {finalGrade.finalGrade} / {finalGrade.maxGrade}
              </div>
              <div className="text-2xl text-purple-600">
                ({((finalGrade.finalGrade / finalGrade.maxGrade) * 100).toFixed(1)}%)
              </div>
            </div>
            {finalGrade.overallFeedback && (
              <div className="mt-4 p-4 bg-purple-50 rounded-lg">
                <h3 className="font-semibold text-purple-900 mb-2">Overall Feedback:</h3>
                <p className="text-purple-800 whitespace-pre-wrap">{finalGrade.overallFeedback}</p>
              </div>
            )}
            {finalGrade.timestamp && (
              <p className="text-sm text-slate-500 mt-4">
                Finalized on: {new Date(finalGrade.timestamp).toLocaleString()}
              </p>
            )}
          </div>
        )}

        {/* TA Review Summary */}
        {overrides.length > 0 && (
          <div className="bg-white rounded-lg shadow-lg p-6 mb-6 border-2 border-blue-300">
            <h2 className="text-2xl font-bold text-blue-900 mb-4">TA Review Summary</h2>
            <div className="hidden">
              {/* helper values computed inline to avoid useMemo clutter */}
            </div>
            {(() => {
              const uniquePages = new Set(overrides.map((o) => o.pageNumber)).size;
              const scoreAdjustments = overrides.filter(
                (o) =>
                  typeof o.overrideValue === "number" ||
                  /score/i.test(o.field)
              ).length;
              return (
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-blue-50 p-4 rounded-lg">
                <div className="text-sm text-blue-700 mb-1">Total Overrides</div>
                <div className="text-2xl font-bold text-blue-900">{overrides.length}</div>
              </div>
              <div className="bg-blue-50 p-4 rounded-lg">
                <div className="text-sm text-blue-700 mb-1">Pages Reviewed</div>
                <div className="text-2xl font-bold text-blue-900">
                  {uniquePages}
                </div>
              </div>
              <div className="bg-blue-50 p-4 rounded-lg">
                <div className="text-sm text-blue-700 mb-1">Score Adjustments</div>
                <div className="text-2xl font-bold text-blue-900">
                  {scoreAdjustments}
                </div>
              </div>
            </div>
              );
            })()}
          </div>
        )}

        {/* Page-by-Page Results */}
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-4">Page-by-Page Results</h2>
          <div className="space-y-6">
            {extractionResult?.pages.map((page) => {
              const analysis = analysisResults.find(a => a.page_number === page.pageNumber);
              const pageOverrides = overrides.filter(o => o.pageNumber === page.pageNumber);
              
              return (
                <div key={page.pageNumber} className="border border-slate-200 rounded-lg p-4">
                  <div className="flex items-start justify-between mb-4">
                    <h3 className="text-lg font-semibold text-slate-900">
                      Page {page.pageNumber}
                    </h3>
                    {analysis && (
                      <div className="flex items-center gap-2">
                        {analysis.skip_analysis ? (
                          <span className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded">
                            Skipped
                          </span>
                        ) : (
                          <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                            Analyzed
                          </span>
                        )}
                        {pageOverrides.length > 0 && (
                          <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                            {pageOverrides.length} Override{pageOverrides.length > 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {page.imageBase64 && (
                    <img
                      src={page.imageBase64}
                      alt={`Page ${page.pageNumber}`}
                      className="mb-4 w-full max-w-2xl rounded-lg border border-slate-200"
                    />
                  )}

                  {analysis && !analysis.skip_analysis && (
                    <div className="mb-4 p-4 bg-emerald-50 rounded-lg border border-emerald-200">
                      <h4 className="font-semibold text-emerald-900 mb-2">AI Analysis</h4>
                      {analysis.page_type && (
                        <p className="text-sm text-emerald-700 mb-2">
                          Page Type: {analysis.page_type}
                        </p>
                      )}
                      {analysis.feedback && (
                        <p className="text-sm text-emerald-800 whitespace-pre-wrap">
                          {analysis.feedback}
                        </p>
                      )}
                      {analysis.score_breakdown && (
                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                          {Object.entries(analysis.score_breakdown).map(([key, value]: [string, any]) => (
                            <div key={key} className="flex justify-between">
                              <span className="text-emerald-700">{key.replace(/_/g, " ")}:</span>
                              <span className="font-medium text-emerald-900">
                                {value.points} / {value.max}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {pageOverrides.length > 0 && (
                    <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                      <h4 className="font-semibold text-blue-900 mb-2">TA Overrides</h4>
                      <div className="space-y-3">
                        {pageOverrides.map((override, idx) => {
                          const displayValue = (value: any) => {
                            if (value === null || value === undefined) return "—";
                            if (typeof value === "object") {
                              try {
                                return JSON.stringify(value, null, 2);
                              } catch {
                                return String(value);
                              }
                            }
                            return String(value);
                          };

                          const formatField = (field: string) =>
                            field
                              .replace(/\./g, " › ")
                              .replace(/_/g, " ")
                              .replace(/\b\w/g, (char) => char.toUpperCase());

                          return (
                            <div key={override.id || idx} className="text-sm border-b border-blue-100 pb-3 last:border-b-0 last:pb-0">
                              <div className="mb-1">
                                <span className="text-blue-700">Field: </span>
                                <span className="font-medium text-blue-900">{formatField(override.field)}</span>
                              </div>
                              <div className="mb-1">
                                <span className="text-blue-700">Original: </span>
                                <span className="text-blue-900 whitespace-pre-wrap">{displayValue(override.originalValue)}</span>
                              </div>
                              <div className="mb-1">
                                <span className="text-blue-700">Override: </span>
                                <span className="text-blue-900 whitespace-pre-wrap">{displayValue(override.overrideValue)}</span>
                              </div>
                              {override.reviewerNotes && (
                                <div className="mb-1">
                                  <span className="text-blue-700">TA Notes: </span>
                                  <span className="text-blue-900 whitespace-pre-wrap">{override.reviewerNotes}</span>
                                </div>
                              )}
                              {override.reviewerName && (
                                <div className="text-xs text-blue-600">
                                  Reviewer: {override.reviewerName}
                                </div>
                              )}
                              {override.timestamp && (
                                <div className="text-xs text-blue-600">
                                  {new Date(override.timestamp).toLocaleString()}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

