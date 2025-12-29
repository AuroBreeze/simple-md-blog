(() => {
  const tabSets = document.querySelectorAll(".sidebar-tabs");
  tabSets.forEach((tabs) => {
    const buttons = tabs.querySelectorAll(".sidebar-tab");
    const panels = tabs.querySelectorAll(".sidebar-tabpanel");
    if (!buttons.length) {
      return;
    }
    const activate = (targetId) => {
      buttons.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.tab === targetId);
      });
      panels.forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.tab === targetId);
      });
    };
    tabs.classList.add("is-js");
    buttons.forEach((button) => {
      button.addEventListener("click", () => activate(button.dataset.tab));
    });
  });
})();
