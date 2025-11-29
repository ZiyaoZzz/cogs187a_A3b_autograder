import React, { useState, useMemo, useEffect } from "react";
import type { HeuristicExtractionResult, PageAnalysisResult, AssignmentSummary, SummaryScores } from "../lib/types";

// Types for Julian website analysis
interface HeuristicIssue {
  id: string;
  heuristic_number: number;
  heuristic_name: string;
  severity: number;
  severity_label: string;
  title: string;
  description: string;
  bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

interface JulianAnalysisData {
  overall_score?: number;
  issues: HeuristicIssue[];
  url?: string;
  image_path?: string;
  third_party_embeds?: string[];
  has_third_party_embeds?: boolean;
}

interface JulianPageMeta {
  id: string;
  title: string;
  url?: string;
}

interface HeuristicInfo {
  number: number;
  name: string;
  description: string;
}

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzingProgress, setAnalyzingProgress] = useState<{ current: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HeuristicExtractionResult | null>(null);
  const [analysisResults, setAnalysisResults] = useState<PageAnalysisResult[] | null>(null);
  const [julianPages, setJulianPages] = useState<JulianPageMeta[]>([]);
  const [compareAllJulianPages, setCompareAllJulianPages] = useState<boolean>(false);
  const [allJulianAnalyses, setAllJulianAnalyses] = useState<Map<string, JulianAnalysisData>>(new Map());
  const [comparisonResults, setComparisonResults] = useState<Array<{
    julianPageId: string;
    julianPageTitle: string;
    julianScore?: number;
    julianIssues: HeuristicIssue[];
    studentFeedback?: string;
    studentHeuristics: number[];
    studentViolations: number;
    similarityScore?: number;
    matchedIssues: Array<{ julian: HeuristicIssue; student: string }>;
  }>>([]);
  const [comparisonLoading, setComparisonLoading] = useState<boolean>(false);
  const [heuristicsInfo, setHeuristicsInfo] = useState<HeuristicInfo[]>([]);

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

  // Load Julian pages index on mount
  useEffect(() => {
    async function loadJulianPages() {
      try {
        const res = await fetch("/output_static/pages_index.json");
        if (res.ok) {
          const data = await res.json();
          const parsed: JulianPageMeta[] = data.map((item: any) => {
            const idStr = String(item.id).padStart(3, "0");
            const url = item.url || "";
            const urlPath = new URL(url).pathname.replace(/^\//, "").replace(/\/$/, "") || "index";
            const title = urlPath.split("/").pop()?.replace(/-/g, " ") || "Home";
            const titleCapitalized = title.split(" ").map((word: string) => 
              word.charAt(0).toUpperCase() + word.slice(1)
            ).join(" ");
            return {
              id: idStr,
              title: titleCapitalized,
              url: url,
            };
          });
          setJulianPages(parsed);
        }
      } catch (err) {
        console.error("Failed to load Julian pages:", err);
      }
    }
    loadJulianPages();
  }, []);


  // Load all Julian analyses when compareAllJulianPages is enabled
  useEffect(() => {
    async function loadAllJulianAnalyses() {
      if (!compareAllJulianPages || julianPages.length === 0) {
        setAllJulianAnalyses(new Map());
        return;
      }

      setComparisonLoading(true);
      const analysesMap = new Map<string, JulianAnalysisData>();
      
      try {
        const loadPromises = julianPages.map(async (page) => {
          try {
            const res = await fetch(`/output_static/desktop/analysis/${page.id}.json`);
            if (res.ok) {
              const data = await res.json();
              analysesMap.set(page.id, data);
            }
          } catch (err) {
            console.error(`Failed to load analysis for page ${page.id}:`, err);
          }
        });

        await Promise.all(loadPromises);
        setAllJulianAnalyses(analysesMap);
      } catch (err) {
        console.error("Failed to load all Julian analyses:", err);
      } finally {
        setComparisonLoading(false);
      }
    }

    loadAllJulianAnalyses();
  }, [compareAllJulianPages, julianPages]);

  // Compare student analysis with all Julian analyses
  useEffect(() => {
    if (!compareAllJulianPages || allJulianAnalyses.size === 0 || !analysisResults) {
      setComparisonResults([]);
      return;
    }

    const results: typeof comparisonResults = [];

    // Extract student violations with heuristics and severity
    interface StudentViolation {
      heuristic: number;
      description: string;
      severity?: string; // "Cosmetic", "Minor", "Major", "Critical" or "1", "2", "3", "4"
      pageNumber: number;
    }

    const extractStudentViolations = (feedback: string, pageNumber: number): StudentViolation[] => {
      const violations: StudentViolation[] = [];
      const text = feedback.toLowerCase();
      
      // Try to extract violations with heuristic and severity
      // Pattern: "Heuristic X ... violation ... severity: Y"
      const heuristicMatches = Array.from(feedback.matchAll(/heuristic\s+(\d+)/gi));
      
      heuristicMatches.forEach((heuristicMatch) => {
        const heuristicNum = parseInt(heuristicMatch[1], 10);
        const matchIndex = heuristicMatch.index || 0;
        
        // Find the text after this heuristic mention (next 200 chars)
        const context = feedback.substring(matchIndex, matchIndex + 300);
        
        // Try to extract severity
        let severity: string | undefined;
        const severityMatch = context.match(/severity[:\s]+(cosmetic|minor|major|critical|\d)/i);
        if (severityMatch) {
          severity = severityMatch[1];
        }
        
        // Extract violation description (text between heuristic and severity, or next sentence)
        const descMatch = context.match(/heuristic\s+\d+[^.]*?([^.]{10,100}?)(?:severity|$)/i);
        if (descMatch || context.length > 20) {
          const description = descMatch ? descMatch[1].trim() : context.substring(20, 100).trim();
          if (description.length > 5) {
            violations.push({
              heuristic: heuristicNum,
              description: description,
              severity: severity,
              pageNumber: pageNumber,
            });
          }
        }
      });
      
      return violations;
    };

    // Collect all student violations from all pages
    const allStudentViolations: StudentViolation[] = [];
    const allStudentAnalyses = analysisResults.filter(a => !a.skip_analysis && a.feedback);
    
    allStudentAnalyses.forEach(analysis => {
      if (analysis.feedback) {
        const violations = extractStudentViolations(analysis.feedback, analysis.page_number);
        allStudentViolations.push(...violations);
      }
    });

    if (allStudentViolations.length === 0) return;

    // Group violations by heuristic
    const violationsByHeuristic = new Map<number, StudentViolation[]>();
    allStudentViolations.forEach(v => {
      if (!violationsByHeuristic.has(v.heuristic)) {
        violationsByHeuristic.set(v.heuristic, []);
      }
      violationsByHeuristic.get(v.heuristic)!.push(v);
    });

    julianPages.forEach((julianPage) => {
      const julianAnalysis = allJulianAnalyses.get(julianPage.id);
      if (!julianAnalysis) return;

      // Match student violations with Julian issues
      const matchedIssues: Array<{ 
        julian: HeuristicIssue; 
        student: StudentViolation;
        matchScore: number; // 0-100 based on heuristic match + severity match + text similarity
      }> = [];
      
      julianAnalysis.issues.forEach((julianIssue) => {
        // Find student violations with same heuristic
        const studentViolations = violationsByHeuristic.get(julianIssue.heuristic_number) || [];
        
        studentViolations.forEach((studentViolation) => {
          let matchScore = 50; // Base score for heuristic match
          
          // Check severity match (if both have severity)
          if (studentViolation.severity && julianIssue.severity) {
            const studentSeverityNum = studentViolation.severity.match(/\d/) 
              ? parseInt(studentViolation.severity)
              : studentViolation.severity.toLowerCase().includes("cosmetic") ? 1
              : studentViolation.severity.toLowerCase().includes("minor") ? 2
              : studentViolation.severity.toLowerCase().includes("major") ? 3
              : studentViolation.severity.toLowerCase().includes("critical") ? 4
              : undefined;
            
            if (studentSeverityNum !== undefined) {
              const severityDiff = Math.abs(studentSeverityNum - julianIssue.severity);
              if (severityDiff === 0) {
                matchScore += 30; // Exact severity match
              } else if (severityDiff === 1) {
                matchScore += 15; // Close severity match
              }
            }
          }
          
          // Check text similarity
          const studentText = studentViolation.description.toLowerCase();
          const julianTitle = julianIssue.title.toLowerCase();
          const julianDesc = julianIssue.description.toLowerCase();
          
          const titleWords = julianTitle.split(/\s+/).filter(w => w.length > 3);
          const descWords = julianDesc.split(/\s+/).filter(w => w.length > 4).slice(0, 5);
          
          const hasSimilarText = titleWords.some(word => studentText.includes(word)) ||
                                 descWords.some(word => studentText.includes(word)) ||
                                 studentText.includes(julianTitle.substring(0, 15)) ||
                                 studentText.includes(julianDesc.substring(0, 30));
          
          if (hasSimilarText) {
            matchScore += 20; // Text similarity bonus
          }
          
          // Only include matches with score >= 50
          if (matchScore >= 50) {
            matchedIssues.push({
              julian: julianIssue,
              student: studentViolation,
              matchScore: matchScore,
            });
          }
        });
      });

      // Calculate overall match metrics
      const uniqueStudentHeuristics = new Set(allStudentViolations.map(v => v.heuristic));
      const matchedHeuristics = new Set(matchedIssues.map(m => m.julian.heuristic_number));
      const heuristicMatchRate = uniqueStudentHeuristics.size > 0
        ? (matchedHeuristics.size / uniqueStudentHeuristics.size) * 100
        : 0;
      
      // Average match score
      const avgMatchScore = matchedIssues.length > 0
        ? matchedIssues.reduce((sum, m) => sum + m.matchScore, 0) / matchedIssues.length
        : 0;

      results.push({
        julianPageId: julianPage.id,
        julianPageTitle: julianPage.title,
        julianScore: julianAnalysis.overall_score,
        julianIssues: julianAnalysis.issues,
        studentFeedback: allStudentAnalyses.map(a => a.feedback || "").join(" ").substring(0, 500),
        studentHeuristics: Array.from(uniqueStudentHeuristics),
        studentViolations: allStudentViolations.length,
        similarityScore: avgMatchScore,
        matchedIssues: matchedIssues.map(m => ({
          julian: m.julian,
          student: `Page ${m.student.pageNumber}: H${m.student.heuristic} - ${m.student.description}${m.student.severity ? ` (${m.student.severity})` : ""}`,
        })),
      });
    });

    // Sort by average match score (highest first), then by number of matches
    results.sort((a, b) => {
      if (Math.abs((b.similarityScore || 0) - (a.similarityScore || 0)) > 5) {
        return (b.similarityScore || 0) - (a.similarityScore || 0);
      }
      return b.matchedIssues.length - a.matchedIssues.length;
    });
    setComparisonResults(results);
  }, [compareAllJulianPages, allJulianAnalyses, analysisResults, julianPages]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setError(null);
    setResult(null); // Clear previous result when selecting a new file
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!file) {
      setError("Please upload a PDF file.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

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

      const jobId = `job-${Date.now()}`;
      const extractionResult: HeuristicExtractionResult = {
        jobId,
        fileName: file.name,
        createdAt: new Date().toISOString(),
        pageCount: data.page_count ?? normalizedPages.length,
        pages: normalizedPages,
      };

      setResult(extractionResult);
    } catch (err: any) {
      setError(err.message || "Something went wrong while parsing the PDF.");
    } finally {
      setLoading(false);
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
              throw new Error(msg);
            }

            const data = await res.json();
            if (data.status === "completed" && data.result) {
              return data.result;
            } else if (data.status === "error") {
              return data.result;
            }
            throw new Error("Unknown response status");
          } catch (err: any) {
            // Return error result
            return {
              page_number: page.pageNumber,
              error: err.message || "Failed to analyze this page",
              feedback: `Error analyzing page ${page.pageNumber}: ${err.message || "Unknown error"}`,
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
      setError(err.message || "Something went wrong while analyzing with Gemini.");
    } finally {
      setAnalyzing(false);
      setAnalyzingProgress(null);
    }
  };

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

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center px-4 py-8">
      <div className="w-full max-w-7xl bg-white shadow rounded-2xl p-6 space-y-6">
        <h1 className="text-2xl font-semibold text-slate-900">
          Upload your heuristic evaluation PDF
        </h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Submission file (PDF)
            </label>
            <input
              type="file"
              accept="application/pdf"
              onChange={handleFileChange}
              className="block w-full text-sm text-slate-700
                         file:mr-4 file:py-2 file:px-4
                         file:rounded-md file:border-0
                         file:text-sm file:font-semibold
                         file:bg-slate-100 file:text-slate-700
                         hover:file:bg-slate-200"
            />
            <p className="mt-1 text-xs text-slate-500">
              We will automatically extract the pages where you discuss Nielsen’s heuristics
              (not pages that only describe the interface).
            </p>
          </div>

          <button
            type="submit"
            disabled={!file || loading}
            className="inline-flex items-center justify-center rounded-md
                       bg-sky-600 px-4 py-2 text-sm font-medium text-white
                       hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Analyzing…" : "Upload & Extract Heuristic Pages"}
          </button>

          {error && (
            <p className="text-sm text-red-600 mt-2">
              {error}
            </p>
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
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {julianPages.length > 0 && (
                    <label className={`flex items-center gap-2 text-sm ${
                      analyzing || analysisResults ? "text-slate-500" : "text-slate-700"
                    }`}>
                      <input
                        type="checkbox"
                        checked={compareAllJulianPages}
                        onChange={(e) => setCompareAllJulianPages(e.target.checked)}
                        disabled={analyzing || analysisResults !== null}
                        className="rounded border-slate-300 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                      <span>Compare with Julian Site Analysis</span>
                    </label>
                  )}
                  <button
                    type="button"
                    onClick={handleAnalyze}
                    disabled={analyzing || result.pages.length === 0}
                    className="inline-flex items-center justify-center rounded-md
                               bg-emerald-600 px-4 py-2 text-sm font-medium text-white
                               hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {analyzing ? "Analyzing with Gemini…" : "Analyze with Gemini"}
                  </button>
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

            {/* Comparison Results Section - Overall Summary */}
            {!analyzing && compareAllJulianPages && comparisonResults.length > 0 && (
              <div className="rounded-lg border-2 border-blue-300 bg-blue-50 p-6 space-y-4">
                <h2 className="text-xl font-bold text-blue-900">
                  Comparison with Julian Site Analysis
                </h2>
                {comparisonLoading ? (
                  <p className="text-sm text-blue-700">Loading comparisons...</p>
                ) : (
                  (() => {
                    // Aggregate all Julian pages data
                    const totalJulianIssues = comparisonResults.reduce((sum, r) => sum + r.julianIssues.length, 0);
                    const totalJulianHeuristics = new Set(comparisonResults.flatMap(r => r.julianIssues.map(i => i.heuristic_number))).size;
                    const avgJulianScore = comparisonResults.reduce((sum, r) => sum + (r.julianScore || 0), 0) / comparisonResults.length;
                    const totalMatchedIssues = comparisonResults.reduce((sum, r) => sum + r.matchedIssues.length, 0);
                    const bestMatch = comparisonResults[0]; // Already sorted by match score
                    const avgMatchScore = comparisonResults.reduce((sum, r) => sum + (r.similarityScore || 0), 0) / comparisonResults.length;
                    const totalStudentHeuristics = new Set(comparisonResults.flatMap(r => r.studentHeuristics)).size;
                    const totalStudentViolations = comparisonResults[0]?.studentViolations || 0;
                    
                    return (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div className="rounded-lg border border-blue-200 bg-white p-4">
                            <h3 className="text-sm font-semibold text-blue-900 mb-3">Julian Site (Overall)</h3>
                            <div className="space-y-2 text-xs">
                              <div className="flex justify-between">
                                <span className="text-blue-700">Total Pages Analyzed:</span>
                                <span className="font-medium text-blue-900">{comparisonResults.length}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-blue-700">Total Issues Found:</span>
                                <span className="font-medium text-blue-900">{totalJulianIssues}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-blue-700">Heuristics Covered:</span>
                                <span className="font-medium text-blue-900">{totalJulianHeuristics} / 10</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-blue-700">Average Score:</span>
                                <span className="font-medium text-blue-900">{avgJulianScore.toFixed(2)}</span>
                              </div>
                            </div>
                          </div>
                          <div className="rounded-lg border border-blue-200 bg-white p-4">
                            <h3 className="text-sm font-semibold text-blue-900 mb-3">Student Submission</h3>
                            <div className="space-y-2 text-xs">
                              <div className="flex justify-between">
                                <span className="text-blue-700">Heuristics Covered:</span>
                                <span className="font-medium text-blue-900">{totalStudentHeuristics} / 10</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-blue-700">Violations Identified:</span>
                                <span className="font-medium text-blue-900">{totalStudentViolations}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-blue-700">Matched Issues:</span>
                                <span className="font-medium text-blue-900">{totalMatchedIssues}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-blue-700">Average Match Score:</span>
                                <span className={`font-medium ${
                                  avgMatchScore >= 70 ? "text-green-700" : avgMatchScore >= 50 ? "text-yellow-700" : "text-red-700"
                                }`}>
                                  {avgMatchScore.toFixed(0)}%
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                        {bestMatch && bestMatch.matchedIssues.length > 0 && (
                          <div className="rounded-lg border border-blue-200 bg-white p-4">
                            <h3 className="text-sm font-semibold text-blue-900 mb-2">
                              Best Match: {bestMatch.julianPageTitle} (Match Score: {bestMatch.similarityScore?.toFixed(0)}%)
                            </h3>
                            <p className="text-xs text-blue-700 mb-2">
                              {bestMatch.matchedIssues.length} issues matched out of {bestMatch.julianIssues.length} Julian issues
                            </p>
                            <div className="space-y-1 max-h-32 overflow-y-auto">
                              {bestMatch.matchedIssues.slice(0, 5).map((match, idx) => (
                                <div key={idx} className="text-xs text-blue-700 border-l-2 border-blue-300 pl-2">
                                  <span className="font-medium">H{match.julian.heuristic_number}: {match.julian.title}</span>
                                  <span className="text-blue-600"> ({match.julian.severity_label})</span>
                                </div>
                              ))}
                              {bestMatch.matchedIssues.length > 5 && (
                                <p className="text-xs text-blue-600 italic">
                                  ... and {bestMatch.matchedIssues.length - 5} more matches
                                </p>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })()
                )}
              </div>
            )}

            {/* Two-column layout: Report and Slide Analysis */}
            {result && result.pages.length > 0 && (
              <div className="grid grid-cols-2 gap-6">
                {/* Left Column: Slide Analysis - Always show in left half */}
                <div className="rounded-lg border-2 border-slate-300 bg-slate-50 p-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-bold text-slate-900">
                      Slide Analysis
                    </h2>
                    {analyzing && analyzingProgress && (
                      <span className="text-xs text-slate-600">
                        {analyzingProgress.current} / {analyzingProgress.total} analyzed
                      </span>
                    )}
                  </div>
                    <div className="space-y-4 max-h-[800px] overflow-y-auto">
                      {result.pages.map((page) => {
                        const analysis = analysisResults?.find(a => a.page_number === page.pageNumber);
                        const isAnalyzing = analyzing && !analysis;
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

                            {analysis && (
                              <div className={`mt-4 rounded-lg border p-4 space-y-3 ${
                                analysis.skip_analysis 
                                  ? "border-slate-200 bg-slate-50" 
                                  : "border-emerald-200 bg-emerald-50"
                              }`}>
                                <div className="flex items-start justify-between">
                                  <div>
                                    <h3 className={`text-sm font-semibold mb-1 ${
                                      analysis.skip_analysis 
                                        ? "text-slate-900" 
                                        : "text-emerald-900"
                                    }`}>
                                      Gemini Analysis
                                    </h3>
                                    {analysis.page_type && (
                                      <p className={`text-xs mb-2 ${
                                        analysis.skip_analysis 
                                          ? "text-slate-600" 
                                          : "text-emerald-700"
                                      }`}>
                                        Page Type: {analysis.page_type}
                                      </p>
                                    )}
                                    {analysis.skip_analysis && analysis.skip_reason && (
                                      <p className="text-xs text-slate-600 italic">
                                        {analysis.skip_reason}
                                      </p>
                                    )}
                                  </div>
                                  {!analysis.skip_analysis && analysis.compelling !== undefined && (
                                    <span className={`text-xs px-2 py-1 rounded-full ${
                                      analysis.compelling 
                                        ? "bg-green-100 text-green-800" 
                                        : "bg-amber-100 text-amber-800"
                                    }`}>
                                      {analysis.compelling ? "Compelling" : "Needs Improvement"}
                                    </span>
                                  )}
                                </div>

                                {!analysis.skip_analysis && analysis.feedback && (
                                  <div className={`text-sm ${
                                    analysis.skip_analysis 
                                      ? "text-slate-800" 
                                      : "text-emerald-800"
                                  }`}>
                                    <p className="font-medium mb-1">Feedback:</p>
                                    <p className="whitespace-pre-wrap text-xs">{analysis.feedback}</p>
                                  </div>
                                )}

                                {analysis.error && (
                                  <div className="mt-2 text-xs text-red-600">
                                    Error: {analysis.error}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                {/* Right Column: Assignment Summary & Final Score - Only show when analysis is complete */}
                <div className="rounded-lg border-2 border-emerald-300 bg-emerald-50 p-6 space-y-4">
                  {!analyzing && assignmentSummary ? (
                    <>
                    <div className="flex items-center justify-between">
                      <h2 className="text-xl font-bold text-emerald-900">
                        Assignment Summary & Final Score
                      </h2>
                      <div className="text-right">
                        <div className="text-3xl font-bold text-emerald-700">
                          {assignmentSummary.totalScore} / {assignmentSummary.maxScore}
                        </div>
                        {assignmentSummary.bonusScore > 0 && (
                          <div className="text-sm font-medium text-emerald-600">
                            ({assignmentSummary.baseScore} base + {assignmentSummary.bonusScore} bonus)
                          </div>
                        )}
                        <div className="text-sm text-emerald-600">
                          {assignmentSummary.percentage}%
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <h3 className="text-sm font-semibold text-emerald-900">Core Criteria:</h3>
                        <div className="space-y-2 text-xs">
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>Coverage:</span>
                              <span className="font-medium">{assignmentSummary.scores.coverage.points} / {assignmentSummary.scores.coverage.max}</span>
                            </div>
                            {assignmentSummary.scores.coverage.comment && assignmentSummary.scores.coverage.points < assignmentSummary.scores.coverage.max && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.coverage.comment}</p>
                            )}
                          </div>
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>Violation Quality:</span>
                              <span className="font-medium">{assignmentSummary.scores.violation_quality.points} / {assignmentSummary.scores.violation_quality.max}</span>
                            </div>
                            {assignmentSummary.scores.violation_quality.comment && assignmentSummary.scores.violation_quality.points < assignmentSummary.scores.violation_quality.max && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.violation_quality.comment}</p>
                            )}
                          </div>
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>Screenshots:</span>
                              <span className="font-medium">{assignmentSummary.scores.screenshots.points} / {assignmentSummary.scores.screenshots.max}</span>
                            </div>
                            {assignmentSummary.scores.screenshots.comment && assignmentSummary.scores.screenshots.points < assignmentSummary.scores.screenshots.max && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.screenshots.comment}</p>
                            )}
                          </div>
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>Severity Analysis:</span>
                              <span className="font-medium">{assignmentSummary.scores.severity_analysis.points} / {assignmentSummary.scores.severity_analysis.max}</span>
                            </div>
                            {assignmentSummary.scores.severity_analysis.comment && assignmentSummary.scores.severity_analysis.points < assignmentSummary.scores.severity_analysis.max && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.severity_analysis.comment}</p>
                            )}
                          </div>
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>Structure & Navigation:</span>
                              <span className="font-medium">{assignmentSummary.scores.structure_navigation.points} / {assignmentSummary.scores.structure_navigation.max}</span>
                            </div>
                            {assignmentSummary.scores.structure_navigation.comment && assignmentSummary.scores.structure_navigation.points < assignmentSummary.scores.structure_navigation.max && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.structure_navigation.comment}</p>
                            )}
                          </div>
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>Professional Quality:</span>
                              <span className="font-medium">{assignmentSummary.scores.professional_quality.points} / {assignmentSummary.scores.professional_quality.max}</span>
                            </div>
                            {assignmentSummary.scores.professional_quality.comment && assignmentSummary.scores.professional_quality.points < assignmentSummary.scores.professional_quality.max && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.professional_quality.comment}</p>
                            )}
                          </div>
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>Writing Quality:</span>
                              <span className="font-medium">{assignmentSummary.scores.writing_quality.points} / {assignmentSummary.scores.writing_quality.max}</span>
                            </div>
                            {assignmentSummary.scores.writing_quality.comment && assignmentSummary.scores.writing_quality.points < assignmentSummary.scores.writing_quality.max && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.writing_quality.comment}</p>
                            )}
                          </div>
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>Group Integration:</span>
                              <span className="font-medium">{assignmentSummary.scores.group_integration.points} / {assignmentSummary.scores.group_integration.max}</span>
                            </div>
                            {assignmentSummary.scores.group_integration.comment && assignmentSummary.scores.group_integration.points < assignmentSummary.scores.group_integration.max && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.group_integration.comment}</p>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <h3 className="text-sm font-semibold text-emerald-900">Bonus:</h3>
                        <div className="space-y-2 text-xs">
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>AI Opportunities:</span>
                              <span className="font-medium">{assignmentSummary.scores.bonus_ai_opportunities.points} / {assignmentSummary.scores.bonus_ai_opportunities.max}</span>
                            </div>
                            {assignmentSummary.scores.bonus_ai_opportunities.comment && assignmentSummary.scores.bonus_ai_opportunities.points === 0 && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.bonus_ai_opportunities.comment}</p>
                            )}
                          </div>
                          <div>
                            <div className="flex justify-between mb-1">
                              <span>Exceptional Quality:</span>
                              <span className="font-medium">{assignmentSummary.scores.bonus_exceptional_quality.points} / {assignmentSummary.scores.bonus_exceptional_quality.max}</span>
                            </div>
                            {assignmentSummary.scores.bonus_exceptional_quality.comment && assignmentSummary.scores.bonus_exceptional_quality.points === 0 && (
                              <p className="text-emerald-700 text-xs italic pl-2 border-l-2 border-emerald-300">{assignmentSummary.scores.bonus_exceptional_quality.comment}</p>
                            )}
                          </div>
                        </div>
                        <div className="mt-4 pt-3 border-t border-emerald-200">
                          <div className="text-xs text-emerald-700">
                            <div className="flex justify-between mb-1">
                              <span>Pages Analyzed:</span>
                              <span className="font-medium">{assignmentSummary.analyzedPages}</span>
                            </div>
                            {assignmentSummary.skippedPages > 0 && (
                              <div className="flex justify-between mb-1">
                                <span>Pages Skipped:</span>
                                <span className="font-medium">{assignmentSummary.skippedPages}</span>
                              </div>
                            )}
                            <div className="flex justify-between mb-1">
                              <span>Total Heuristics Covered:</span>
                              <span className="font-medium">{assignmentSummary.uniqueHeuristicsCount} / 10</span>
                            </div>
                            <div className="flex justify-between">
                              <span>Total Violations Identified:</span>
                              <span className="font-medium">{assignmentSummary.totalViolationsCount} / 12 (min)</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    </>
                  ) : (
                    <div className="text-center text-slate-500 py-8">
                      <p className="text-sm">
                        {analyzing ? "Analysis in progress..." : "Analysis results will appear here"}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Student Analysis Summary - List all heuristics and severity levels - MOVED TO BOTTOM */}
            {analysisResults && analysisResults.length > 0 && (
              <div className="rounded-lg border-2 border-purple-300 bg-purple-50 p-6 space-y-4">
                <h2 className="text-xl font-bold text-purple-900">
                  Student Analysis Summary
                </h2>
                <div className="space-y-3">
                  {analysisResults
                    .filter(a => !a.skip_analysis && (a.extracted_violations || a.feedback))
                    .map((analysis) => {
                      // Use extracted_violations if available, otherwise fallback to parsing feedback
                      const violations = analysis.extracted_violations || [];
                      
                      // Group violations by heuristic
                      const violationsByHeuristic = new Map<number, Array<{name: string, description: string, severity: string}>>();
                      violations.forEach((v: any) => {
                        const hNum = v.heuristic_num || v.heuristic_number;
                        if (hNum) {
                          if (!violationsByHeuristic.has(hNum)) {
                            violationsByHeuristic.set(hNum, []);
                          }
                          violationsByHeuristic.get(hNum)!.push({
                            name: v.heuristic_name || "",
                            description: v.description || "",
                            severity: v.severity || ""
                          });
                        }
                      });
                      
                      // Fallback: extract from feedback if no extracted_violations
                      if (violations.length === 0 && analysis.feedback) {
                        const heuristicMatches = Array.from((analysis.feedback || "").matchAll(/heuristic\s+(\d+)/gi));
                        const heuristics = new Set(heuristicMatches.map(m => parseInt(m[1], 10)));
                        heuristics.forEach(hNum => {
                          if (!violationsByHeuristic.has(hNum)) {
                            violationsByHeuristic.set(hNum, []);
                          }
                        });
                      }
                      
                      return (
                        <div key={analysis.page_number} className="rounded-lg border border-purple-200 bg-white p-3">
                          <div className="flex items-center justify-between mb-2">
                            <h3 className="text-sm font-semibold text-purple-900">
                              Page {analysis.page_number}
                            </h3>
                            {analysis.page_type && (
                              <span className="text-xs text-purple-600">
                                {analysis.page_type}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-purple-800 space-y-2">
                            <div>
                              <span className="font-medium">Heuristics & Violations:</span>
                              <div className="mt-1 space-y-2">
                                {Array.from(violationsByHeuristic.entries())
                                  .sort((a, b) => a[0] - b[0])
                                  .map(([hNum, violationsList]) => {
                                    const heuristic = heuristicsInfo.find((h: HeuristicInfo) => h.number === hNum);
                                    const heuristicName = violationsList[0]?.name || heuristic?.name || `Heuristic ${hNum}`;
                                    
                                    return (
                                      <div key={hNum} className="pl-2 border-l-2 border-purple-300">
                                        <div className="font-medium text-purple-900">
                                          H{hNum}: {heuristicName}
                                        </div>
                                        {heuristic?.description && (
                                          <div className="text-purple-600 italic text-xs mt-0.5 mb-1">
                                            {heuristic.description}
                                          </div>
                                        )}
                                        <div className="mt-1 space-y-1 ml-2">
                                          {violationsList.map((v, idx) => (
                                            <div key={idx} className="text-purple-700">
                                              <span className="font-medium">Violation {idx + 1}:</span>{" "}
                                              <span>{v.description || "No description"}</span>
                                              {v.severity && (
                                                <span className="ml-2 px-1.5 py-0.5 rounded bg-purple-100 text-purple-800 font-medium">
                                                  Severity: {v.severity}
                                                </span>
                                              )}
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    );
                                  })}
                              </div>
                            </div>
                            {analysis.feedback && (
                              <div className="mt-2 pt-2 border-t border-purple-200 text-purple-700 italic">
                                {analysis.feedback.substring(0, 300)}
                                {analysis.feedback.length > 300 ? "..." : ""}
                              </div>
                            )}
                          </div>
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
