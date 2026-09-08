/** @type {import('tailwindcss').Config} */
export default {
  // ThemeProvider toggles a `dark` class on <html> for night-shoot / high-contrast,
  // so dark: variants resolve against the class, never the OS preference.
  darkMode: "class",
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    // Design-system components render inside this app and carry their own
    // utility classes, so their source must be scanned too or those utilities
    // would never be generated.
    "../../packages/design-system/src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
