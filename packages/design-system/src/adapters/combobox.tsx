import React, { useState } from "react";

export interface ComboboxOption {
  value: string;
  label: string;
}

export interface ComboboxProps {
  options: ComboboxOption[];
  value?: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
}

export function Combobox({
  options,
  value,
  onChange,
  placeholder = "Select option...",
  ariaLabel = "Select",
}: ComboboxProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");

  const filtered = options.filter((option) =>
    option.label.toLowerCase().includes(search.toLowerCase()),
  );
  const selectedOption = options.find((option) => option.value === value);

  // Positioning is inline: the stylesheet has no combobox rules, and inventing
  // class names it does not define would leave the panel unstyled.
  return (
    <div style={{ position: "relative" }}>
      <button
        className="button button-secondary"
        type="button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={ariaLabel}
        onClick={() => setIsOpen(!isOpen)}
      >
        <span>{selectedOption ? selectedOption.label : placeholder}</span>
        <span className="muted" aria-hidden="true">
          ▾
        </span>
      </button>

      {isOpen && (
        <div
          className="list"
          role="listbox"
          style={{
            position: "absolute",
            zIndex: 10,
            top: "calc(100% + var(--space-1))",
            left: 0,
            right: 0,
            maxHeight: "15rem",
            overflowY: "auto",
            padding: "var(--space-2)",
            boxShadow: "var(--shadow-md)",
          }}
        >
          <label className="field">
            <span className="sr-only">Filter options</span>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter options…"
            />
          </label>
          {filtered.map((option) => (
            <button
              className="list-row"
              type="button"
              key={option.value}
              role="option"
              aria-selected={option.value === value}
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
            >
              {option.label}
            </button>
          ))}
          {filtered.length === 0 && <p className="small muted">No results found</p>}
        </div>
      )}
    </div>
  );
}
