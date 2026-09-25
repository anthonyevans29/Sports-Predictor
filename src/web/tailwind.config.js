// Tailwind build config for the local web UI. The UI used to load the
// Tailwind Play CDN at runtime; it now serves a pre-built stylesheet
// (static/css/tailwind.css) so no third-party script runs in the page.
//
// Rebuild after adding classes to templates (from the repo root):
//   npx tailwindcss@3.4.17 -c src/web/tailwind.config.js \
//     -i src/web/tailwind.input.css -o src/web/static/css/tailwind.css --minify
module.exports = {
  content: [
    "src/web/templates/**/*.html",
    "src/web/static/js/**/*.js",
    "src/web/**/*.py",
  ],
  // predictions.html builds these from a status->color map
  // (bg-{{color}}-100 text-{{color}}-800), which the scanner cannot see.
  safelist: [
    { pattern: /^bg-(green|cyan|amber|slate)-100$/ },
    { pattern: /^text-(green|cyan|amber|slate)-800$/ },
  ],
  theme: {
    extend: {
      colors: {
        arsenal: { red: "#EF0107", gold: "#9C824A" },
      },
    },
  },
};
