/* =========================================================================
   Ratshie UI — shared interaction layer
   Toasts · popups/dropdowns · modals · drawers.
   Exposes a global `RUI` namespace used by the public site and the admin
   command centre. Supports prefers-reduced-motion and keyboard access.
   ========================================================================= */
(function (window) {
  "use strict";

  var RUI = {};

  /* ---------------- Toast controller ---------------- */

  var AUTO_CLOSE = { success: 3800, info: 4200, warning: 5200, error: 6500 };
  var ICONS = {
    success: "i-check",
    info: "i-info",
    warning: "i-bell",
    error: "i-alert",
  };

  function stack() {
    var s = document.querySelector(".toast-stack");
    if (!s) {
      s = document.createElement("div");
      s.className = "toast-stack";
      s.setAttribute("role", "region");
      s.setAttribute("aria-label", "Notifications");
      document.body.appendChild(s);
    }
    return s;
  }

  function svgUse(id) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "toast__icon");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#" + id);
    svg.appendChild(use);
    return svg;
  }

  function toast(message, kind, opts) {
    kind = kind || "info";
    if (AUTO_CLOSE[kind] == null) kind = "info";
    opts = opts || {};

    var el = document.createElement("div");
    el.className = "toast toast--" + kind;
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");

    var icon = document.createElement("span");
    icon.appendChild(svgUse(ICONS[kind] || "i-info"));

    var body = document.createElement("span");
    body.className = "toast__body";
    body.textContent = message;

    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "toast__close";
    closeBtn.setAttribute("aria-label", "Dismiss notification");
    closeBtn.setAttribute("data-toast-close", "");

    el.appendChild(icon);
    el.appendChild(body);
    el.appendChild(closeBtn);

    var s = stack();
    s.appendChild(el);
    wireToast(el, kind, opts);
    return el;
  }

  var wired = new WeakSet();

  function dismiss(el) {
    if (el.getAttribute("data-leaving") != null) return;
    el.setAttribute("data-leaving", "1");
    el.classList.add("is-leaving");
    window.setTimeout(function () { el.remove(); }, 300);
  }

  function wireToast(el, kind, opts) {
    if (wired.has(el)) return;
    wired.add(el);
    opts = opts || {};
    var close = el.querySelector("[data-toast-close]");
    if (close) {
      close.addEventListener("click", function (e) {
        e.stopPropagation();
        dismiss(el);
      });
    }
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    void reduce;
    var delay = opts.sticky ? 0 : AUTO_CLOSE[kind || "info"];
    if (delay) window.setTimeout(function () { dismiss(el); }, delay);
  }

  function enhanceAllToasts() {
    document.querySelectorAll(".toast").forEach(function (el) {
      var kind = "info";
      ["success", "error", "warning", "info"].some(function (k) {
        if (el.classList.contains("toast--" + k)) { kind = k; return true; }
        return false;
      });
      wireToast(el, kind);
    });
  }

  RUI.toast = toast;
  RUI.toast.dismiss = dismiss;

  /* ---------------- Popup controller ---------------- */
  /* [data-popup-wrap] > trigger([data-popup-toggle]) + [data-popup]
     Opening a popup closes sibling popups. Clicking inside never closes it.
     Outside click and Escape close it. Kept within the viewport. */

  function closeAllPopups(exceptWrap) {
    document.querySelectorAll("[data-popup].open").forEach(function (pop) {
      var wrap = pop.closest("[data-popup-wrap]");
      if (exceptWrap && wrap === exceptWrap) return;
      pop.classList.remove("open");
      var trigger = wrap ? wrap.querySelector("[data-popup-toggle]") : null;
      if (trigger) trigger.setAttribute("aria-expanded", "false");
    });
  }

  function togglePopup(wrap) {
    var pop = wrap.querySelector("[data-popup]");
    var trigger = wrap.querySelector("[data-popup-toggle]");
    var isOpen = pop && pop.classList.contains("open");
    closeAllPopups(wrap);
    if (pop && !isOpen) {
      pop.classList.add("open");
      if (trigger) trigger.setAttribute("aria-expanded", "true");
      clampToViewport(pop);
    } else if (trigger) {
      trigger.setAttribute("aria-expanded", "false");
    }
  }

  function clampToViewport(el) {
    if (!el) return;
    var r = el.getBoundingClientRect();
    var pad = 12;
    if (r.bottom > window.innerHeight - pad) {
      el.style.maxHeight = window.innerHeight - r.top - pad + "px";
      el.style.overflowY = "auto";
    } else if (el.style.maxHeight) {
      el.style.maxHeight = "";
      el.style.overflowY = "";
    }
    if (r.right > window.innerWidth - pad) {
      el.style.right = "0";
    }
  }

  document.addEventListener("click", function (e) {
    var wrap = e.target.closest("[data-popup-wrap]");
    if (wrap) {
      var trigger = e.target.closest("[data-popup-toggle]");
      if (trigger) {
        e.stopPropagation();
        togglePopup(wrap);
        return;
      }
      // Clicking elsewhere inside a popup wrapper must NOT close the popup.
      return;
    }
    closeAllPopups();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeAllPopups();
  });

  document.addEventListener("htmx:afterSwap", function () {
    document.querySelectorAll("[data-popup]").forEach(clampToViewport);
    enhanceAllToasts();
  });

  document.addEventListener("DOMContentLoaded", enhanceAllToasts);
  if (document.readyState === "interactive" || document.readyState === "complete") {
    enhanceAllToasts();
  }

  /* ---------------- Modal / drawer controller ---------------- */

  function openModal(el) {
    if (!el) return;
    el.classList.add("open");
    document.body.style.overflow = "hidden";
    var focusable = el.querySelector('[data-modal-focus], button, a[href], input, select, textarea');
    if (focusable) focusable.focus();
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    void reduce;
  }

  function closeModal(el) {
    if (!el) return;
    el.classList.remove("open");
    if (!document.querySelector(".dui-modal.open, .member-modal.open")) {
      document.body.style.overflow = "";
    }
  }

  RUI.openModal = openModal;
  RUI.closeModal = closeModal;

  /* Click + Escape close for any `.dui-modal`. */
  document.addEventListener("click", function (e) {
    var closer = e.target.closest('.dui-modal [data-modal-close], .dui-modal__backdrop');
    if (closer) closeModal(closer.closest(".dui-modal"));
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".dui-modal.open").forEach(function (m) {
      closeModal(m);
    });
  });

  /* Drawer helpers: `[data-drawer-open][data-drawer-target]` etc. */
  function openDrawer(el) {
    el.classList.add("open");
    var backdrop = document.getElementById(el.getAttribute("data-drawer-backdrop"));
    if (backdrop) backdrop.classList.add("open");
    document.body.style.overflow = "hidden";
  }

  function closeDrawer(el) {
    el.classList.remove("open");
    var backdrop = document.getElementById(el.getAttribute("data-drawer-backdrop"));
    if (backdrop) backdrop.classList.remove("open");
    if (!document.querySelector(".dui-drawer.open")) {
      document.body.style.overflow = "";
    }
  }

  RUI.openDrawer = openDrawer;
  RUI.closeDrawer = closeDrawer;

  document.addEventListener("click", function (e) {
    var openBtn = e.target.closest("[data-drawer-open]");
    if (openBtn) {
      e.preventDefault();
      var target = document.getElementById(openBtn.getAttribute("data-drawer-target"));
      if (target) openDrawer(target);
      return;
    }
    var closer = e.target.closest('.dui-drawer [data-drawer-close], .dui-drawer__backdrop');
    if (closer) {
      closeDrawer(closer.closest(".dui-drawer, .dui-drawer__backdrop").closest(".dui-drawer"));
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".dui-drawer.open").forEach(function (d) {
      closeDrawer(d);
    });
  });

  /* ---------------- HTMX toast partials ---------------- */
  /* A swapped fragment may carry `data-toast-message` (and optional
     data-toast-kind / data-toast-sticky) to surface a toast with no refresh. */
  document.addEventListener("htmx:afterSwap", function (e) {
    var root = e.detail && e.detail.target ? e.detail.target : null;
    if (!root) return;
    var node = root.querySelector
      ? root.matches("[data-toast-message]") ? root : root.querySelector("[data-toast-message]")
      : null;
    if (!node) return;
    toast(
      node.getAttribute("data-toast-message"),
      node.getAttribute("data-toast-kind") || "info",
      { sticky: node.getAttribute("data-toast-sticky") != null }
    );
    node.remove();
  });

  window.RUI = RUI;
})(window);