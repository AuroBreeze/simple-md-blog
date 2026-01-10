(() => {
  const copyText = async (text) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();

    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      ok = false;
    }

    document.body.removeChild(textarea);
    return ok;
  };

  const getCodeText = (pre) => {
    const code = pre.querySelector("code");
    const text = (code || pre).innerText;
    return text.replace(/\n$/, "");
  };

  const setButtonState = (button, state, label) => {
    button.dataset.state = state;
    button.textContent = label;
  };

  const addCopyButton = (pre) => {
    let container = pre.parentElement;
    if (!container) {
      return;
    }

    if (container.classList.contains("code-block")) {
      // Already wrapped.
    } else if (container.classList.contains("codehilite")) {
      container.classList.add("code-block");
    } else {
      const wrapper = document.createElement("div");
      wrapper.className = "code-block";
      container.insertBefore(wrapper, pre);
      wrapper.appendChild(pre);
      container = wrapper;
    }

    if (container.querySelector(".code-copy")) {
      return;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "code-copy";
    button.textContent = "Copy";
    button.setAttribute("aria-label", "Copy code to clipboard");
    button.dataset.state = "idle";

    container.appendChild(button);

    let resetTimer = null;
    button.addEventListener("click", async () => {
      if (resetTimer) {
        window.clearTimeout(resetTimer);
        resetTimer = null;
      }

      const text = getCodeText(pre);
      if (!text) {
        setButtonState(button, "error", "Empty");
        resetTimer = window.setTimeout(() => {
          setButtonState(button, "idle", "Copy");
        }, 1500);
        return;
      }

      button.disabled = true;
      let ok = false;
      try {
        ok = await copyText(text);
      } catch (err) {
        ok = false;
      }

      setButtonState(button, ok ? "copied" : "error", ok ? "Copied" : "Failed");
      resetTimer = window.setTimeout(() => {
        setButtonState(button, "idle", "Copy");
        button.disabled = false;
      }, 1600);
    });
  };

  const init = () => {
    const blocks = document.querySelectorAll(".post-body pre");
    if (!blocks.length) {
      return;
    }

    blocks.forEach(addCopyButton);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();