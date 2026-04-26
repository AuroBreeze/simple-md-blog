document.addEventListener('DOMContentLoaded', () => {
  const root = document.documentElement;
  const getTheme = () => root.dataset.theme === 'dark' ? 'dark' : 'default';
  
  mermaid.initialize({
    startOnLoad: true,
    theme: getTheme(),
    securityLevel: 'loose',
  });

  // Watch for theme changes
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'attributes' && mutation.attributeName === 'data-theme') {
        // Mermaid doesn't support easy re-rendering with a new theme without a page reload
        // or complex API calls. For now, we'll just let it be, or the user can refresh.
        // Most users don't flip themes back and forth while looking at one diagram.
      }
    });
  });

  observer.observe(root, { attributes: true });
});
