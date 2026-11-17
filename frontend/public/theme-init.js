// Applied before first paint to avoid a light->dark flash (mirrors useTheme's
// storage key + Tailwind darkMode:["class"]). External, not inline, so the CSP
// can be script-src 'self' with NO 'unsafe-inline'. Referenced from index.html
// <head> as a plain (render-blocking) script, which runs before <body> paints.
(function () {
  try {
    // Una scelta salvata vince; senza, si segue il sistema (E-28): un
    // telefono in modo scuro non deve aprire l'app con un lampo bianco.
    var salvato = localStorage.getItem("theme");
    var scuro = salvato
      ? salvato === "dark"
      : window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (scuro) document.documentElement.classList.add("dark");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", scuro ? "#121212" : "#ffffff");
  } catch (e) {}
})();
