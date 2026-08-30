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
  claims?: ClaimRecord[];
}

export function ClaimTable({ claims = [] }: ClaimTableProps) {
  const defaultClaims: ClaimRecord[] = [
    {
      claimId: "c1",
      claimText: "Registered US trademark for carbonated beverages",
      stance: "supports",
      authorityTier: "primary_official",
      sourceUrl: "https://tsdr.uspto.gov/#caseNumber=8850142",
      sourceDomain: "tsdr.uspto.gov",
      excerpt: "The mark consists of standard characters without claim to any particular font.",
    },
    {
      claimId: "c2",
      claimText: "Historical registration in class 009 for motion-picture equipment",
      stance: "supports",
      authorityTier: "reputable_news",
      sourceUrl: "https://variety.com/archives",
      sourceDomain: "variety.com",
      excerpt: "Camera manufacturer active in 1968 production era.",
    },
  ];

  const displayClaims = claims && claims.length > 0 ? claims : defaultClaims;

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
          {displayClaims.map((c) => (
            <tr key={c.claimId} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
              <td className="p-3 font-medium text-slate-900 dark:text-white max-w-xs">
                {c.claimText}
              </td>
              <td className="p-3">
                <Badge label={c.stance} variant={stanceBadges[c.stance] || "neutral"} />
              </td>
              <td className="p-3 text-slate-600 dark:text-slate-300">
                {c.authorityTier?.replace("_", " ") || "Primary Official"}
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
                <p className="mt-1 text-slate-500 italic text-[11px]">&ldquo;{c.excerpt}&rdquo;</p>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
