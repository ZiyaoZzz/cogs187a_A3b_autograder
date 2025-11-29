export function HomePage() {
    return (
      <div className="space-y-4">
        <h1 className="text-3xl font-semibold text-slate-900">
          COGS 187 · LLM Autograder for A3a
        </h1>
        <p className="text-base text-slate-600 max-w-2xl">
          Upload a heuristic evaluation PDF for{" "}
          <span className="font-mono text-sm">visitjulian.com</span>. The system is
          designed to call LLMs to analyze your findings, check coverage of Nielsen&apos;s
          10 heuristics, and generate structured feedback.
        </p>
  
        <div className="flex gap-3">
          <a
            href="/upload"
            className="inline-flex items-center rounded-md bg-slate-900 px-4 py-2.5 text-base font-medium text-white hover:bg-slate-800"
          >
            Start by uploading a PDF
          </a>
        </div>
  
        <div className="mt-6 rounded-lg border bg-white p-4 text-base text-slate-600">
          <h2 className="text-base font-semibold text-slate-900 mb-1">
            For students / TAs
          </h2>
          <p>
            Upload a submission to eventually get per-heuristic feedback, severity
            suggestions, and a summary of strengths and missing issues.
          </p>
        </div>
      </div>
    );
  }
  