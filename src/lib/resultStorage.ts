import type { HeuristicExtractionResult } from "./types";

const RESULT_STORAGE_PREFIX = "heuristic-result:";

export const buildResultStorageKey = (jobId: string) =>
  `${RESULT_STORAGE_PREFIX}${jobId}`;

export const saveExtractionResult = (result: HeuristicExtractionResult) => {
  try {
    const key = buildResultStorageKey(result.jobId);
    const serialized = JSON.stringify(result);
    sessionStorage.setItem(key, serialized);
    localStorage.setItem(key, serialized);
  } catch (error) {
    console.warn("Failed to cache extraction result locally:", error);
  }
};

export const loadExtractionResult = (
  jobId: string,
): HeuristicExtractionResult | null => {
  try {
    const key = buildResultStorageKey(jobId);
    const rawSession = sessionStorage.getItem(key);
    if (rawSession) {
      return JSON.parse(rawSession) as HeuristicExtractionResult;
    }

    const rawLocal = localStorage.getItem(key);
    if (rawLocal) {
      sessionStorage.setItem(key, rawLocal);
      return JSON.parse(rawLocal) as HeuristicExtractionResult;
    }

    return null;
  } catch (error) {
    console.warn("Unable to read cached extraction result:", error);
    return null;
  }
};

