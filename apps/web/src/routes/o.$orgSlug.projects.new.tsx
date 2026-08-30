import React, { useState } from "react";
import { ImportStep } from "../features/ingestion/import-step.tsx";
import { ParseReview } from "../features/ingestion/parse-review.tsx";
import { AnalysisProgress } from "../features/ingestion/analysis-progress.tsx";

interface NewProjectRouteProps {
  orgSlug: string;
}

export function NewProjectRoute({ orgSlug }: NewProjectRouteProps) {
  const [step, setStep] = useState<"import" | "review" | "analysis">("import");
  const [scriptTitle, setScriptTitle] = useState("Screenplay Draft");

  const handleFile = (_file: File) => {
    setScriptTitle(_file.name.replace(/\.[^/.]+$/, ""));
    setStep("review");
  };

  const handlePaste = (_text: string) => {
    setScriptTitle("Pasted Screenplay");
    setStep("review");
  };

  return (
    <div className="max-w-3xl mx-auto p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">New Clearance Project</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">Workspace: {orgSlug}</p>
      </div>

      {step === "import" && (
        <ImportStep onFileSelected={handleFile} onPasteSubmitted={handlePaste} />
      )}

      {step === "review" && (
        <ParseReview
          title={scriptTitle}
          sceneCount={12}
          elementCount={84}
          onConfirm={() => setStep("analysis")}
          onCancel={() => setStep("import")}
        />
      )}

      {step === "analysis" && (
        <AnalysisProgress status="running" progressPercent={45} />
      )}
    </div>
  );
}
