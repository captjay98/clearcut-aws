import React, { createContext, useContext, useMemo, useState } from "react";

/**
 * The mock's header carries a context chip naming the current project and the
 * version being read, plus a live position readout. Those values belong to the
 * project layer but render in the shell above it, so the shell owns the state
 * and the project layer publishes into it.
 */
interface ShellContextValue {
  projectTitle: string | null;
  setProjectTitle: (title: string | null) => void;
  /** e.g. "Scene 3 · Page 2 of 43", announced politely when it changes. */
  scriptPosition: string | null;
  setScriptPosition: (position: string | null) => void;
}

const ShellContext = createContext<ShellContextValue | undefined>(undefined);

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const [projectTitle, setProjectTitle] = useState<string | null>(null);
  const [scriptPosition, setScriptPosition] = useState<string | null>(null);

  const value = useMemo(
    () => ({ projectTitle, setProjectTitle, scriptPosition, setScriptPosition }),
    [projectTitle, scriptPosition],
  );

  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}

export function useShell(): ShellContextValue {
  const context = useContext(ShellContext);
  if (!context) {
    throw new Error("useShell must be used within a ShellProvider");
  }
  return context;
}
