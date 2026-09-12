import React, { useMemo, useState } from "react";
import { FILTER_CATEGORY_LABELS } from "./itemPresentation";

export interface CategoryFilterBarProps {
  selectedCategory: string;
  onSelectCategory: (category: string) => void;
  categoryCounts?: Record<string, number>;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  /** Compact chips for the workspace side rail (smaller hit targets). */
  compact?: boolean;
}

/**
 * Filter controls for the flag list. By default only categories that actually
 * have flags appear (plus All) — empty categories would otherwise stack into a
 * tall chip wall. "More" reveals the rest so a reader can still see an empty
 * category was considered.
 */
export function CategoryFilterBar({
  selectedCategory,
  onSelectCategory,
  categoryCounts = {},
  searchQuery,
  onSearchChange,
  compact = false,
}: CategoryFilterBarProps) {
  const [showEmpty, setShowEmpty] = useState(false);
  const total = Object.values(categoryCounts).reduce((sum, value) => sum + value, 0);

  const nonEmpty = useMemo(
    () => FILTER_CATEGORY_LABELS.filter((label) => (categoryCounts[label] ?? 0) > 0),
    [categoryCounts],
  );
  const empty = useMemo(
    () => FILTER_CATEGORY_LABELS.filter((label) => (categoryCounts[label] ?? 0) === 0),
    [categoryCounts],
  );

  // Always include the active chip even if its count is 0, so the filter
  // doesn't silently drop the selection.
  const visible = useMemo(() => {
    const list = [...nonEmpty];
    if (selectedCategory !== "All" && !list.includes(selectedCategory)) {
      list.unshift(selectedCategory);
    }
    if (showEmpty) {
      for (const label of empty) {
        if (!list.includes(label)) list.push(label);
      }
    }
    return list;
  }, [nonEmpty, empty, showEmpty, selectedCategory]);

  return (
    <div className={`stack-sm category-filter ${compact ? "is-compact" : ""}`.trim()}>
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
        <label className="choice">
          <input
            className="sr-only"
            type="radio"
            name="clearance-category"
            data-testid="category-filter-chip"
            value="All"
            checked={selectedCategory === "All"}
            onChange={() => onSelectCategory("All")}
          />
          <span>All{total > 0 ? ` (${total})` : ""}</span>
        </label>
        {visible.map((category) => {
          const count = categoryCounts[category] ?? 0;
          return (
            <label className="choice" key={category}>
              <input
                className="sr-only"
                type="radio"
                name="clearance-category"
                data-testid="category-filter-chip"
                value={category}
                checked={selectedCategory === category}
                onChange={() => onSelectCategory(category)}
              />
              <span>
                {category}
                {count > 0 ? ` (${count})` : ""}
              </span>
            </label>
          );
        })}
        {empty.length > 0 && (
          <button
            type="button"
            className="button button-quiet button-sm category-filter-more"
            onClick={() => setShowEmpty((v) => !v)}
            aria-expanded={showEmpty}
          >
            {showEmpty ? "Fewer" : `More (${empty.length})`}
          </button>
        )}
      </div>
    </div>
  );
}

export default CategoryFilterBar;
