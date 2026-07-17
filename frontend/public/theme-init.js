// Applied before first paint to avoid a light->dark flash (mirrors useTheme's
// storage key + Tailwind darkMode:["class"]). External, not inline, so the CSP
// can be script-src 'self' with NO 'unsafe-inline'. Referenced from index.html
// <head> as a plain (render-blocking) script, which runs before <body> paints.
(function () {
  try {
    if (localStorage.getItem("theme") === "dark") {
      document.documentElement.classList.add("dark");
    }
  } catch (e) {}
})();
