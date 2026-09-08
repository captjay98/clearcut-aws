/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./src/**/*.{astro,html,ts,tsx,js,jsx,md,mdx}",
    // The design-system components share this site's utility vocabulary.
    "../../packages/design-system/src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
