import React from "react";
import { humanizeCategory } from "./itemPresentation";

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

/**
 * Filter controls for the flag list, using the mock's search-field plus choice
 * chips. Categories with no detected items are still offered so the reader can
 * see that a category was considered and came back empty.
 */
export function CategoryFilterBar({
  selectedCategory,
  onSelectCategory,
  categoryCounts = {},
  searchQuery,
  onSearchChange,
}: CategoryFilterBarProps) {
  const total = Object.values(categoryCounts).reduce((sum, value) => sum + value, 0);

  return (
    <div className="stack-sm">
      <label className="search-field" htmlFor="flag-filter">
        <span className="sr-only">Filter flags</span>
        <span className="search-icon" aria-hidden="true">
          ⌕
        </span>
        <input
          id="flag-filter"
          type="search"
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Filter flags…"
        />
      </label>

      <div className="choice-row" role="group" aria-label="Filter flags by category">
        {PROTECTED_CATEGORIES.map((category) => {
          const isSelected = selectedCategory === category;
          const count = category === "All" ? total : categoryCounts[category];
          return (
            <label className="choice" key={category}>
              <input
                type="radio"
                name="clearance-category"
                data-testid="category-filter-chip"
                value={category}
                checked={isSelected}
                onChange={() => onSelectCategory(category)}
              />
              <span>
                {humanizeCategory(category)}
                {count !== undefined && count > 0 ? ` (${count})` : ""}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

export default CategoryFilterBar;
