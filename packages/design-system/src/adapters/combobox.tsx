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

  const filtered = options.filter((opt) =>
    opt.label.toLowerCase().includes(search.toLowerCase())
  );

  const selectedOption = options.find((opt) => opt.value === value);

  return (
    <div className="relative w-full">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={ariaLabel}
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 rounded-md bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
      >
        <span>{selectedOption ? selectedOption.label : placeholder}</span>
        <span className="text-xs text-slate-400">▼</span>
      </button>

      {isOpen && (
        <div
          role="listbox"
          className="absolute z-10 w-full mt-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-md shadow-lg max-h-60 overflow-auto"
        >
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter options..."
            className="w-full p-2 text-xs border-b border-slate-100 dark:border-slate-800 bg-transparent text-slate-900 dark:text-white"
          />
          {filtered.map((opt) => (
            <div
              key={opt.value}
              role="option"
              aria-selected={opt.value === value}
              onClick={() => {
                onChange(opt.value);
                setIsOpen(false);
              }}
              className="px-3 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
            >
              {opt.label}
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="p-3 text-xs text-slate-400 text-center">No results found</div>
          )}
        </div>
      )}
    </div>
  );
}
