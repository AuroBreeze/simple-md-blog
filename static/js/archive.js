(() => {
  const views = document.querySelector(".archive-views");
  const buttons = document.querySelectorAll(".archive-toggle");
  if (!views || !buttons.length) {
    return;
  }
  views.classList.add("is-js");

  const setView = (view) => {
    views.querySelectorAll(".archive-view").forEach((section) => {
      section.classList.toggle("is-active", section.dataset.view === view);
    });
    buttons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.view === view);
    });
  };

  buttons.forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });

  setView("archive");
})();
