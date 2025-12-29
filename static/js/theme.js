(() => {
  const root = document.documentElement;
  const button = document.querySelector("[data-theme-toggle]");
  if (!button) {
    return;
  }
  const storageKey = "theme";
  const getDefault = () => root.dataset.themeDefault || "auto";
  const prefersDark = () =>
    window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolve = (value) => {
    if (value === "auto") {
      return prefersDark() ? "dark" : "light";
    }
    return value === "dark" ? "dark" : "light";
  };
  const apply = (value) => {
    const mode = resolve(value);
    root.dataset.theme = mode;
    button.textContent = mode === "dark" ? "Light" : "Dark";
  };
  apply(localStorage.getItem(storageKey) || getDefault());
  button.addEventListener("click", () => {
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem(storageKey, next);
    apply(next);
  });
  const media = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");
  if (media) {
    media.addEventListener("change", () => {
      const stored = localStorage.getItem(storageKey);
      if (!stored || stored === "auto") {
        apply(getDefault());
      }
    });
  }
})();
