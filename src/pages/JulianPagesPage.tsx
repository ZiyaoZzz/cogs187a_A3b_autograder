import { useEffect, useState } from "react";

interface JulianPageMeta {
  id: string; // e.g., "001"
  title: string; // e.g., "Home"
  url?: string; // e.g., "https://visitjulian.com/"
  screenshot: string; // e.g., "001_index.png"
  screenshotPath: string; // e.g., "output_static/analysis/screens/001_index.png"
  overlayPath?: string;
  mobileImagePath?: string; // e.g., "output_static/analysis/screens_mobile/001__index_mobile.png"
  mobileOverlayPath?: string;
                      }

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

interface AnalysisData {
  overall_score?: number;
  issues: HeuristicIssue[];
  url?: string;
  image_path?: string;
  third_party_embeds?: string[];
  has_third_party_embeds?: boolean;
}

type LoadState = "idle" | "loading" | "error" | "ready";

export function JulianPagesPage() {
  const [pages, setPages] = useState<JulianPageMeta[]>([]);
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [useOverlay, setUseOverlay] = useState<boolean>(true);
  const [useMobileView, setUseMobileView] = useState<boolean>(false);
  const [desktopAnalysis, setDesktopAnalysis] = useState<AnalysisData | null>(
    null,
  );
  const [mobileAnalysis, setMobileAnalysis] = useState<AnalysisData | null>(
    null,
  );
  const [desktopAnalysisLoading, setDesktopAnalysisLoading] =
    useState<boolean>(false);
  const [mobileAnalysisLoading, setMobileAnalysisLoading] =
    useState<boolean>(false);
  const [hideThirdPartyIssues, setHideThirdPartyIssues] =
    useState<boolean>(false);

  useEffect(() => {
    async function load() {
      try {
        setState("loading");
        setError(null);
        const res = await fetch("/output_static/pages_index.json");
        if (!res.ok) {
          throw new Error(`Failed to load pages_index.json: ${res.status}`);
        }
        const data = await res.json();

        // Transform JSON data to match component interface
        const parsed: JulianPageMeta[] = data.map((item: any) => {
          // Extract filename from image_path (e.g., "output_static/screens/001_index.png" -> "001_index.png")
          const imagePath = item.image_path || "";
          const screenshot = imagePath.split("/").pop() || "";
          const normalizedImagePath =
            typeof imagePath === "string" && imagePath.length > 0
              ? imagePath
              : `output_static/desktop/screens/${screenshot}`;
          const overlayPath =
            typeof item.overlay_path === "string" && item.overlay_path.length > 0
              ? item.overlay_path
              : normalizedImagePath
                  .replace("/screens/", "/overlays/")
                  .replace(/\.png$/i, "_overlay.png");

          const mobileImagePath =
            typeof item.mobile_image_path === "string"
              ? item.mobile_image_path
              : "";
          const mobileOverlayPath =
            typeof item.mobile_overlay_path === "string"
              ? item.mobile_overlay_path
              : mobileImagePath
                  .replace("/screens/", "/overlays/")
                  .replace(/\.png$/i, "_overlay.png");
          
          // Convert numeric id to string with zero-padding (e.g., 1 -> "001")
          const idStr = String(item.id).padStart(3, "0");
          
          // Extract title from URL (e.g., "https://visitjulian.com/historic-julian/" -> "historic-julian")
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
            screenshot: screenshot,
            screenshotPath: normalizedImagePath,
            overlayPath,
            mobileImagePath,
            mobileOverlayPath,
          };
        });
        
        setPages(parsed);
        if (parsed.length > 0) {
          setSelectedId(parsed[0].id);
        }
        setState("ready");
      } catch (err) {
        console.error(err);
        setError((err as Error).message);
        setState("error");
      }
    }

    load();
  }, []);

  // Load desktop analysis data when selected page changes
  useEffect(() => {
    async function loadDesktopAnalysis() {
      if (!selectedId) {
        setDesktopAnalysis(null);
        return;
      }

      setDesktopAnalysisLoading(true);
      try {
        const res = await fetch(
          `/output_static/desktop/analysis/${selectedId}.json`,
        );
        if (!res.ok) {
          throw new Error(`Failed to load desktop analysis: ${res.status}`);
        }
        const data = await res.json();
        setDesktopAnalysis(data);
      } catch (err) {
        console.error("Failed to load desktop analysis:", err);
        setDesktopAnalysis(null);
      } finally {
        setDesktopAnalysisLoading(false);
      }
    }

    loadDesktopAnalysis();
  }, [selectedId]);

  const selectedPage = pages.find((p) => p.id === selectedId) ?? null;

  useEffect(() => {
    if (useMobileView && useOverlay && !selectedPage?.mobileOverlayPath) {
      setUseOverlay(false);
    }
  }, [useMobileView, useOverlay, selectedPage?.mobileOverlayPath]);

  // Load mobile analysis when mobile assets exist
  useEffect(() => {
    async function loadMobileAnalysis() {
      if (!selectedId || !selectedPage?.mobileImagePath) {
        setMobileAnalysis(null);
        return;
      }

      setMobileAnalysisLoading(true);
      try {
        const res = await fetch(
          `/output_static/mobile/analysis/${selectedId}_mobile.json`,
        );
        if (!res.ok) {
          throw new Error(`Failed to load mobile analysis: ${res.status}`);
        }
        const data = await res.json();
        setMobileAnalysis(data);
      } catch (err) {
        console.error("Failed to load mobile analysis:", err);
        setMobileAnalysis(null);
      } finally {
        setMobileAnalysisLoading(false);
      }
    }

    loadMobileAnalysis();
  }, [selectedId, selectedPage?.mobileImagePath]);

  const toPublicPath = (path: string) =>
    path.startsWith("/") ? path : `/${path}`;

  // Decide which image to show: overlay or original screenshot.
  const screenshotUrl =
    selectedPage && selectedPage.screenshotPath
      ? toPublicPath(selectedPage.screenshotPath)
      : "";
  const overlayUrl =
    selectedPage && selectedPage.overlayPath
      ? toPublicPath(selectedPage.overlayPath)
      : "";
  const mobileScreenshotUrl =
    selectedPage && selectedPage.mobileImagePath
      ? toPublicPath(selectedPage.mobileImagePath)
      : "";
  const mobileOverlayUrl =
    selectedPage && selectedPage.mobileOverlayPath
      ? toPublicPath(selectedPage.mobileOverlayPath)
      : "";

  const imageSrc = useMobileView
    ? useOverlay && mobileOverlayUrl
      ? mobileOverlayUrl
      : mobileScreenshotUrl
    : useOverlay && overlayUrl
    ? overlayUrl
    : screenshotUrl;
  const mobileAvailable = Boolean(mobileScreenshotUrl);
  const overlayToggleDisabled = useMobileView
    ? !mobileOverlayUrl
    : !overlayUrl;
  const viewDescription = useMobileView
    ? mobileAvailable
      ? useOverlay && mobileOverlayUrl
        ? "Showing mobile overlay image with heuristic annotations."
        : "Showing the mobile screenshot captured with a phone-sized viewport."
      : "Mobile screenshot not available for this page."
    : useOverlay && overlayUrl
    ? "Showing overlay image with heuristic-issue annotations. If the overlay image is not available, it will automatically fall back to the raw screenshot."
    : "Showing the raw screenshot captured from the Julian website for this page.";
  const currentAnalysis = useMobileView ? mobileAnalysis : desktopAnalysis;
  const currentAnalysisLoading = useMobileView
    ? mobileAnalysisLoading
    : desktopAnalysisLoading;
  const thirdPartyEmbeds = (currentAnalysis?.third_party_embeds || []).filter(
    (embed) => typeof embed === "string" && embed.trim().length > 0,
  );
  const showThirdPartyWarning =
    currentAnalysis?.has_third_party_embeds && thirdPartyEmbeds.length > 0;
const thirdPartyIssueKeywords = [
  "empty",
  "blank",
  "missing",
  "failed",
  "fails",
  "loading",
  "unavailable",
  "not visible",
  "not rendering",
  "did not load",
  "doesn't load",
];
const nielsenHeuristics = [
  "Visibility of System Status",
  "Match Between System and the Real World",
  "User Control and Freedom",
  "Consistency and Standards",
  "Error Prevention",
  "Recognition Rather Than Recall",
  "Flexibility and Efficiency of Use",
  "Aesthetic and Minimalist Design",
  "Help Users Recognize, Diagnose, and Recover from Errors",
  "Help and Documentation",
];
const isIssueAffectedByThirdParty = (issue: HeuristicIssue) => {
  if (!showThirdPartyWarning) {
    return false;
  }
  const issueText = (
    `${issue.title ?? ""} ${issue.description ?? ""}`
  ).toLowerCase();
  return thirdPartyIssueKeywords.some((keyword) =>
    issueText.includes(keyword),
  );
};
const baseIssues = currentAnalysis?.issues ?? [];
const filteredIssues =
  hideThirdPartyIssues && showThirdPartyWarning
    ? baseIssues.filter((issue) => !isIssueAffectedByThirdParty(issue))
    : baseIssues;
const totalIssues = baseIssues.length;
const filteredIssueCount = filteredIssues.length;
const filteredOverallScore =
  currentAnalysis?.overall_score !== undefined && totalIssues > 0
    ? Number(
        (
          (currentAnalysis.overall_score * filteredIssueCount) /
          totalIssues
        ).toFixed(2),
      )
    : undefined;

  const heuristicCounts = Array.from({ length: 10 }, (_, index) =>
    filteredIssues.filter((issue) => issue.heuristic_number === index + 1)
      .length,
  );
  const maxHeuristicCount = Math.max(1, ...heuristicCounts);

  const severityGroups = [
    { level: 1, label: "Cosmetic" },
    { level: 2, label: "Minor" },
    { level: 3, label: "Major" },
    { level: 4, label: "Critical" },
  ];
  const severityCounts = severityGroups.map(
    ({ level }) =>
      filteredIssues.filter((issue) => issue.severity === level).length,
  );
  const maxSeverityCount = Math.max(1, ...severityCounts);

  return (
    <div className="space-y-6 px-4 py-6">
      <header className="space-y-2">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-slate-900">
              Julian Site Pages & Overlays
            </h1>
            <p className="text-base text-slate-600 max-w-2xl">
              This viewer shows the pages crawled from{" "}
              <span className="font-mono text-sm">visitjulian.com</span> along with
              their screenshots and heuristic-issue overlays generated by the
              autograder pipeline.
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              id="hideThirdPartyGlobal"
              className="h-4 w-4 rounded border-slate-300 text-slate-900"
              checked={hideThirdPartyIssues}
              onChange={(e) => setHideThirdPartyIssues(e.target.checked)}
            />
            <label htmlFor="hideThirdPartyGlobal" className="cursor-pointer">
              Hide issues possibly affected by external widgets
            </label>
          </div>
        </div>
      </header>

      {/* Loading / error messages */}
      {state === "loading" && (
        <p className="text-base text-slate-500">Loading page list…</p>
      )}
      {state === "error" && (
        <p className="text-base text-red-600">
          Failed to load pages_index.json: {error}
        </p>
      )}

      {state === "ready" && pages.length === 0 && (
        <p className="text-base text-slate-500">No pages found.</p>
      )}

      {state === "ready" && pages.length > 0 && (
        <div className="grid gap-8 md:grid-cols-[minmax(0,0.9fr)_minmax(0,2fr)]">
          {/* Left: list of pages */}
          <aside className="rounded-lg border bg-white p-5 text-base">
            <div className="mb-4 flex items-center justify-between gap-3">
              <span className="text-lg font-semibold text-slate-900">
                Crawled pages
              </span>
              <span className="text-sm text-slate-500">
                {pages.length} page{pages.length > 1 ? "s" : ""}
              </span>
            </div>
            <ul className="space-y-2 max-h-[600px] overflow-auto pr-2">
              {pages.map((page) => {
                const isActive = page.id === selectedId;
                return (
                  <li key={page.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedId(page.id);

                        if (!useMobileView) {
                          setUseOverlay(true); // default to overlay when switching pages
                        }
                      }}
                      className={[
                        "w-full text-left rounded-md px-4 py-3 text-sm",
                        isActive
                          ? "bg-slate-900 text-white"
                          : "hover:bg-slate-100 text-slate-800",
                      ].join(" ")}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium">
                          {page.id} · {page.title}
                        </span>
                      </div>
                      {page.url && (
                        <span
                          className={
                            isActive
                              ? "text-xs text-slate-200 mt-1"
                              : "text-xs text-slate-500 mt-1"
                          }
                        >
                          {page.url}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          {/* Right: selected page preview and heuristics */}
          <section className="space-y-4">
            {selectedPage ? (
              <>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-semibold text-slate-900">
                      {selectedPage.id} · {selectedPage.title}
                    </h2>
                    {selectedPage.url && (
                      <a
                        href={selectedPage.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm text-slate-500 underline decoration-slate-300 hover:text-slate-700 mt-1 inline-block"
                      >
                        {selectedPage.url}
                      </a>
                    )}
                  </div>

                  <div className="flex flex-col gap-3 sm:items-end">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-slate-500">Device:</span>
                      <button
                        type="button"
                        onClick={() => setUseMobileView(false)}
                        className={[
                          "rounded-full px-4 py-2 text-sm font-medium",
                          !useMobileView
                            ? "bg-slate-900 text-white"
                            : "bg-slate-100 text-slate-700",
                        ].join(" ")}
                      >
                        Desktop
                      </button>
                      <button
                        type="button"
                        disabled={!mobileAvailable}
                        onClick={() => mobileAvailable && setUseMobileView(true)}
                        className={[
                          "rounded-full px-4 py-2 text-sm font-medium",
                          useMobileView
                            ? "bg-slate-900 text-white"
                            : "bg-slate-100 text-slate-700",
                          !mobileAvailable ? "opacity-50 cursor-not-allowed" : "",
                        ].join(" ")}
                      >
                        Phone
                      </button>
                    </div>
                    {!mobileAvailable && (
                      <p className="text-xs text-slate-500">
                        Phone screenshot not captured yet.
                      </p>
                    )}

                    <div className="flex items-center gap-2">
                      <span className="text-sm text-slate-500">
                        View mode:
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setUseOverlay(false);
                        }}
                        className={[
                          "rounded-full px-4 py-2 text-sm font-medium",
                          !useOverlay
                            ? "bg-slate-900 text-white"
                            : "bg-slate-100 text-slate-700",
                        ].join(" ")}
                      >
                        Screenshot
                      </button>
                      <button
                        type="button"
                        disabled={overlayToggleDisabled}
                        onClick={() => {
                          if (overlayToggleDisabled) return;
                          setUseOverlay(true);
                        }}
                        className={[
                          "rounded-full px-4 py-2 text-sm font-medium",
                          useOverlay
                            ? "bg-slate-900 text-white"
                            : "bg-slate-100 text-slate-700",
                          overlayToggleDisabled
                            ? "opacity-50 cursor-not-allowed"
                            : "",
                        ].join(" ")}
                      >
                        Overlay
                      </button>
                    </div>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  {/* Image preview */}
                  <div className="rounded-lg border bg-white p-5">
                    <div className="overflow-auto max-h-[70vh] rounded-md border border-slate-200 bg-slate-50">
                      {imageSrc ? (
                        <img
                          src={imageSrc}
                          alt={
                            useOverlay
                              ? `Overlay for ${selectedPage.title}`
                              : `Screenshot for ${selectedPage.title}`
                          }
                          className="block w-full h-auto"
                          onError={() => {
                            // If overlay is missing, automatically fall back to screenshot.
                            const fallbackScreenshot = useMobileView
                              ? mobileScreenshotUrl
                              : screenshotUrl;
                            if (useOverlay && fallbackScreenshot) {
                              setUseOverlay(false);
                            }
                          }}
                        />
                      ) : (
                        <p className="p-6 text-sm text-slate-500">
                          No image available for this page.
                        </p>
                      )}
                    </div>
                    <p className="mt-3 text-sm text-slate-500">
                      {viewDescription}
                    </p>
                    {showThirdPartyWarning && (
                      <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
                        <span className="font-semibold">Heads-up:</span>{" "}
                        This page contains third-party embeds. They sometimes fail to
                        render in automated screenshots, so scoring may under-represent
                        those sections. Focus feedback on the shell around those widgets
                        rather than the missing live content.
                      </div>
                    )}
                  </div>

                  {/* Heuristics info */}
                  <div className="rounded-lg border bg-white p-5">
                    <div className="mb-4">
                      <h3 className="text-lg font-semibold text-slate-900 mb-2">
                        Heuristic Issues
                      </h3>
                      {currentAnalysisLoading ? (
                        <p className="text-sm text-slate-500">Loading analysis...</p>
                      ) : currentAnalysis && filteredIssues.length > 0 ? (
                        <>
                          <div className="mb-4 p-3 bg-slate-50 rounded-md">
                            <p className="text-sm text-slate-600">
                              <span className="font-semibold text-slate-900">
                                {filteredIssueCount}
                              </span>{" "}
                              issue{filteredIssueCount !== 1 ? "s" : ""} found
                            </p>
                            {filteredIssueCount !== totalIssues && (
                              <p className="text-[11px] text-slate-500">
                                Showing {filteredIssueCount} of {totalIssues} issues
                                (external-widget issues hidden)
                              </p>
                            )}
                            {currentAnalysis?.overall_score !== undefined && (
                              <p className="mt-1 text-[11px] text-slate-500">
                                Overall Score (LLM):{" "}
                                <span className="font-semibold text-slate-900">
                                  {currentAnalysis.overall_score.toFixed(1)}
                                </span>
                                {hideThirdPartyIssues &&
                                  filteredOverallScore !== undefined &&
                                  filteredOverallScore !==
                                    currentAnalysis.overall_score && (
                                    <>
                                      {" "}
                                      · Filtered:{" "}
                                      <span className="font-semibold text-slate-900">
                                        {filteredOverallScore.toFixed(2)}
                                      </span>
                                    </>
                                  )}
                              </p>
                            )}
                          </div>
                          <div className="space-y-4 max-h-[60vh] overflow-auto pr-2">
                            {filteredIssues.map((issue, index) => {
                              const isThirdPartyIssue =
                                showThirdPartyWarning &&
                                isIssueAffectedByThirdParty(issue);

                              return (
                                <div
                                  key={issue.id || index}
                                  className="border border-slate-200 rounded-md p-4 bg-slate-50"
                                >
                                  <div className="mb-2">
                                    <div className="flex items-center gap-2 mb-1">
                                      <span className="text-xs font-medium text-slate-500">
                                        #{issue.heuristic_number}
                                      </span>
                                      <span className="text-sm font-semibold text-slate-900">
                                        {issue.heuristic_name}
                                      </span>
                                      <span
                                        className={`text-xs px-2 py-0.5 rounded-full ${
                                          issue.severity === 3
                                            ? "bg-red-100 text-red-700"
                                            : issue.severity === 2
                                            ? "bg-yellow-100 text-yellow-700"
                                            : "bg-blue-100 text-blue-700"
                                        }`}
                                      >
                                        {issue.severity_label}
                                      </span>
                                    </div>
                                    <h4 className="text-sm font-medium text-slate-900 mb-2">
                                      {issue.title}
                                    </h4>
                                    {isThirdPartyIssue && (
                                      <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
                                        Possibly affected by external widget
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-sm text-slate-700 leading-relaxed">
                                    {issue.description}
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-slate-500">
                          No analysis data available for this page.
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-base text-slate-500">
                Select a page on the left to view its screenshot and overlay.
              </p>
            )}
          </section>
          {/* Global summary */}
          <section className="space-y-4">
            <div className="rounded-lg border bg-white p-5 space-y-4">
              <h3 className="text-lg font-semibold text-slate-900">
                Global Summary
              </h3>

              <div>
                <p className="text-sm font-medium text-slate-700 mb-2">
                  Heuristic Coverage (Filtered View)
                </p>
                <div className="space-y-2">
                  {heuristicCounts.map((count, index) => (
                    <div key={index} className="text-xs text-slate-600">
                      <div className="flex items-center justify-between mb-1">
                        <span>
                          Heuristic {index + 1} · {nielsenHeuristics[index] ?? ""}
                        </span>
                        <span>{count}</span>
                      </div>
                      <div className="h-2 rounded bg-slate-100">
                        <div
                          className="h-2 rounded bg-slate-900"
                          style={{
                            width: `${Math.min(
                              100,
                              (count / maxHeuristicCount) * 100 || 0,
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <p className="text-sm font-medium text-slate-700 mb-2">
                  Severity Distribution
                </p>
                <div className="space-y-2">
                  {severityGroups.map(({ level, label }, idx) => (
                    <div key={level} className="text-xs text-slate-600">
                      <div className="flex items-center justify-between mb-1">
                        <span>
                          Severity {level} · {label}
                        </span>
                        <span>{severityCounts[idx]}</span>
                      </div>
                      <div className="h-2 rounded bg-slate-100">
                        <div
                          className="h-2 rounded bg-slate-500"
                          style={{
                            width: `${Math.min(
                              100,
                              (severityCounts[idx] / maxSeverityCount) * 100 || 0,
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
