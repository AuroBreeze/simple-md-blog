document.addEventListener("DOMContentLoaded", () => {
  const body = document.body;
  let dialog = null;

  function initializeDialog() {
    if (document.querySelector(".code-dialog")) {
      return;
    }
    
    dialog = document.createElement("div");
    dialog.className = "code-dialog";
    
    dialog.innerHTML = `
      <div class="code-dialog-header">
        <span class="code-dialog-title">Code Viewer</span>
        <button class="panel-close-btn" type="button">&times;</button>
      </div>
      <div class="panel-code-container"></div>
      <div class="code-dialog-resize-handle"></div>
    `;
    
    body.appendChild(dialog);

    const closeBtn = dialog.querySelector(".panel-close-btn");
    closeBtn.addEventListener("click", hideDialog);

    dragElement(dialog);
    resizeElement(dialog);
  }

  function showDialog(target) {
    if (!dialog) {
      initializeDialog();
    }
    
    const codeContainer = dialog.querySelector(".panel-code-container");
    const title = dialog.querySelector(".code-dialog-title");

    codeContainer.innerHTML = target.dataset.code;
    title.textContent = target.textContent;
    
    dialog.classList.add("is-visible");

    // Don't reset position if it has been moved
    if (!dialog.style.top || dialog.style.top === '50%') {
        dialog.style.top = '50%';
        dialog.style.left = '50%';
        dialog.style.transform = 'translate(-50%, -50%)';
    }


    // Scroll to the highlighted line
    const highlightedLine = codeContainer.querySelector(".hll");
    if (highlightedLine) {
      setTimeout(() => {
        highlightedLine.scrollIntoView({ block: "center", behavior: "auto" });
      }, 50);
    }
  }

  function hideDialog() {
    if (dialog) {
      dialog.classList.remove("is-visible");
    }
  }

  function dragElement(elmnt) {
    let offsetX = 0, offsetY = 0;

    const header = elmnt.querySelector(".code-dialog-header");
    if (header) {
      header.onmousedown = dragMouseDown;
    }

    function dragMouseDown(e) {
      e.preventDefault();

      // If centered with transform, convert to pixel values first
      if (elmnt.style.transform) {
        const rect = elmnt.getBoundingClientRect();
        elmnt.style.transform = 'none';
        elmnt.style.left = rect.left + 'px';
        elmnt.style.top = rect.top + 'px';
      }

      // calculate the mouse offset inside the header
      offsetX = e.clientX - elmnt.offsetLeft;
      offsetY = e.clientY - elmnt.offsetTop;

      document.onmouseup = closeDragElement;
      document.onmousemove = elementDrag;
    }

    function elementDrag(e) {
      e.preventDefault();
      
      // set the element's new position
      let newLeft = e.clientX - offsetX;
      let newTop = e.clientY - offsetY;

      // Ensure the dialog stays within the viewport
      const doc = document.documentElement;
      const bounds = elmnt.getBoundingClientRect();
      
      newLeft = Math.max(0, newLeft);
      newTop = Math.max(0, newTop);
      newLeft = Math.min(newLeft, doc.clientWidth - bounds.width);
      newTop = Math.min(newTop, doc.clientHeight - bounds.height);

      elmnt.style.left = newLeft + "px";
      elmnt.style.top = newTop + "px";
    }

    function closeDragElement() {
      // stop moving when mouse button is released:
      document.onmouseup = null;
      document.onmousemove = null;
    }
  }

  function resizeElement(elmnt) {
    const handle = elmnt.querySelector(".code-dialog-resize-handle");
    let original_width = 0;
    let original_height = 0;
    let original_x = 0;
    let original_y = 0;
    let original_mouse_x = 0;
    let original_mouse_y = 0;

    handle.onmousedown = resizeMouseDown;

    function resizeMouseDown(e) {
      e.preventDefault();
      original_width = parseFloat(getComputedStyle(elmnt, null).getPropertyValue('width').replace('px', ''));
      original_height = parseFloat(getComputedStyle(elmnt, null).getPropertyValue('height').replace('px', ''));
      original_x = elmnt.offsetLeft;
      original_y = elmnt.offsetTop;
      original_mouse_x = e.pageX;
      original_mouse_y = e.pageY;
      document.onmousemove = resizeMouseMove;
      document.onmouseup = stopResize;
    }

    function resizeMouseMove(e) {
      const width = original_width + (e.pageX - original_mouse_x);
      const height = original_height + (e.pageY - original_mouse_y);
      const minWidth = 300;
      const minHeight = 200;

      if (width > minWidth) {
        elmnt.style.width = width + 'px';
      }
      if (height > minHeight) {
        elmnt.style.height = height + 'px';
      }
    }

    function stopResize() {
      document.onmousemove = null;
      document.onmouseup = null;
    }
  }


  body.addEventListener("click", (e) => {
    const target = e.target.closest(".code-link");
    if (target) {
      e.preventDefault();
      showDialog(target);
    }
  });

  initializeDialog();
});