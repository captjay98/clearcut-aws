import React from "react";
import { FILTER_CATEGORY_LABELS } from "./itemPresentation";

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
 * see that a category was considered and came back empty. Values are unique
 * mock display labels (living/deceased people collapse to one chip).
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
        {["All", ...FILTER_CATEGORY_LABELS].map((category) => {
          const isSelected = selectedCategory === category;
          const count = category === "All" ? total : categoryCounts[category];
          return (
            <label className="choice" key={category}>
              {/* sr-only so the visible chip text is the click target rather than
                  the input the design system stretches over it. */}
              <input
                className="sr-only"
                type="radio"
                name="clearance-category"
                data-testid="category-filter-chip"
                value={category}
                checked={isSelected}
                onChange={() => onSelectCategory(category)}
              />
              <span>
                {category}
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
