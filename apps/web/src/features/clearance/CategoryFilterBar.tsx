import React from "react";

export const PROTECTED_CATEGORIES = [
  "All",
  "Trademarks & Brand Names",
  "Real People & Living Persons",
  "Music & Lyrics",
  "Copyright & Creative Works",
  "Business & Corporate Entities",
  "Artwork & Protected Props",
  "Vehicles & Vessels",
  "Defamation & Sensitive Depictions",
  "Product Placement & Endorsements",
  "Government & Official Insignia",
] as const;

export interface CategoryFilterBarProps {
  selectedCategory: string;
  onSelectCategory: (category: string) => void;
  categoryCounts?: Record<string, number>;
  searchQuery: string;
  onSearchChange: (query: string) => void;
}

export function CategoryFilterBar({
  selectedCategory,
  onSelectCategory,
  categoryCounts = {},
  searchQuery,
  onSearchChange,
}: CategoryFilterBarProps) {
  return (
    <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 pb-2 border-b border-slate-800 shrink-0">
      {/* Search Input */}
      <div className="relative shrink-0">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter items..."
          className="w-full sm:w-44 px-2.5 py-1 text-xs bg-slate-900 border border-slate-700 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
        />
      </div>

      {/* Category Filter Chips */}
      <div className="flex items-center space-x-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-thin">
        {PROTECTED_CATEGORIES.map((cat) => {
          const isSelected = selectedCategory === cat || (cat === "Trademarks & Brand Names" && selectedCategory === "Trademarks");
          const count = categoryCounts[cat] ?? (cat === "All" ? Object.values(categoryCounts).reduce((a, b) => a + b, 0) : undefined);

          return (
            <button
              key={cat}
              type="button"
              data-testid="category-filter-chip"
              onClick={() => onSelectCategory(cat)}
              className={`inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500 ${
                isSelected
                  ? "bg-amber-500 text-slate-950 font-bold shadow-sm"
                  : "bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700"
              }`}
            >
              <span>{cat}</span>
              {count !== undefined && count > 0 && (
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-bold ${
                    isSelected ? "bg-slate-950/20 text-slate-950" : "bg-slate-800 text-slate-400"
                  }`}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default CategoryFilterBar;
