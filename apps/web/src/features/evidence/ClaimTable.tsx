import React from "react";
import { Badge } from "@clearcut/design-system";

export interface ClaimRecord {
  claimId: string;
  claimText: string;
  stance: "supports" | "disagrees" | "context";
  authorityTier: "primary_official" | "reputable_news" | "secondary_informal";
  sourceUrl: string;
  sourceDomain: string;
  excerpt: string;
}

export interface ClaimTableProps {
  claims: ClaimRecord[];
}

export function ClaimTable({ claims }: ClaimTableProps) {
  if (claims.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 rounded-lg">
        Zero claims admitted. Evidence is unresolved.
      </div>
    );
  }

  const stanceBadges: Record<string, "success" | "danger" | "neutral"> = {
    supports: "success",
    disagrees: "danger",
    context: "neutral",
  };

  return (
    <div className="overflow-x-auto border border-slate-200 dark:border-slate-800 rounded-lg">
      <table className="w-full text-left text-xs">
        <thead className="bg-slate-50 dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
          <tr>
            <th className="p-3">Claim</th>
            <th className="p-3">Stance</th>
            <th className="p-3">Authority Tier</th>
            <th className="p-3">Source Citation & Provenance</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {claims.map((c) => (
            <tr key={c.claimId} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
              <td className="p-3 font-medium text-slate-900 dark:text-white max-w-xs">
                {c.claimText}
              </td>
              <td className="p-3">
                <Badge label={c.stance} variant={stanceBadges[c.stance]} />
              </td>
              <td className="p-3 text-slate-600 dark:text-slate-300">
                {c.authorityTier.replace("_", " ")}
              </td>
              <td className="p-3 max-w-md">
                <a
                  href={c.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 dark:text-blue-400 hover:underline font-mono"
                >
                  {c.sourceDomain}
                </a>
                <p className="mt-1 text-slate-500 italic text-[11px]">"{c.excerpt}"</p>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
