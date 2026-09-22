/* Ratshie Command Centre — premium light admin.
   Sidebar, mobile drawer, notification bell, toasts, modals, drawers,
   and HTMX interaction guards. */
(function () {
  "use strict";

  function getCookie(name) {
    var value = "; " + document.cookie;
    var parts = value.split("; " + name + "=");
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  var COLLAPSE_KEY = "ratshie.admin.sidebarCollapsed";
  var sidebar = document.getElementById("ruiSidebar");
  var mainEl = document.getElementById("ruiMain");

  /* ---------------- Sidebar ----------------
     Desktop collapse -> icon rail, persisted. Mobile -> off-canvas drawer. */
  function isDesktop() { return window.matchMedia("(min-width: 901px)").matches; }

  function applyCollapsedState() {
    if (!sidebar) return;
    if (localStorage.getItem(COLLAPSE_KEY) === "1") {
      sidebar.classList.add("rui-collapsed");
      if (mainEl) mainEl.classList.remove("rui-shifted");
    } else {
      sidebar.classList.remove("rui-collapsed");
      if (mainEl) mainEl.classList.add("rui-shifted");
    }
  }

  var collapseBtn = document.getElementById("ruiSidebarCollapse");
  if (collapseBtn) {
    collapseBtn.addEventListener("click", function () {
      var isCollapsed = sidebar.classList.toggle("rui-collapsed");
      localStorage.setItem(COLLAPSE_KEY, isCollapsed ? "1" : "0");
      if (mainEl) mainEl.classList.toggle("rui-shifted", !isCollapsed);
    });
  }
  applyCollapsedState();

  var toggleBtn = document.getElementById("ruiSidebarToggle");
  var backdrop = document.getElementById("ruiSidebarBackdrop");
  function openDrawer() {
    if (sidebar) { sidebar.classList.add("rui-open"); sidebar.setAttribute("aria-hidden", "false"); }
    if (backdrop) backdrop.classList.add("rui-open");
    document.body.style.overflow = "hidden";
  }
  function closeDrawer() {
    if (sidebar) { sidebar.classList.remove("rui-open"); }
    if (backdrop) backdrop.classList.remove("rui-open");
    document.body.style.overflow = "";
  }
  if (toggleBtn) toggleBtn.addEventListener("click", openDrawer);
  if (backdrop) backdrop.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeDrawer();
  });
  /* Close mobile drawer when a sidebar link is followed. */
  document.addEventListener("click", function (e) {
    if (e.target.closest(".rui-sidebar-link")) closeDrawer();
  });

  /* Tooltips for collapsed rail. */
  document.addEventListener("mouseover", function (e) {
    var t = e.target.closest("[data-tip]");
    if (!t) return;
    var el = document.getElementById("rui-tip");
    if (!el) {
      el = document.createElement("div");
      el.id = "rui-tip";
      el.className = "rui-tip";
      document.body.appendChild(el);
    }
    el.textContent = t.getAttribute("data-tip");
    var r = t.getBoundingClientRect();
    el.style.top = r.top + r.height / 2 - el.offsetHeight / 2 + "px";
    el.style.left = r.right + 10 + "px";
    el.classList.add("show");
  });
  document.addEventListener("mouseout", function (e) {
    if (e.target.closest("[data-tip]")) {
      var el = document.getElementById("rui-tip");
      if (el) el.classList.remove("show");
    }
  });

  /* ---------------- Toast ----------------
     Self-contained (no dependency on public ui.css). */
  function toast(message, kind) {
    var region = document.getElementById("rui-toast-region");
    if (!region) {
      region = document.createElement("div");
      region.id = "rui-toast-region";
      region.className = "rui-toast-region";
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    var t = document.createElement("div");
    t.className = "rui-toast rui-toast--" + (kind || "info");
    var p = document.createElement("span");
    p.textContent = message;
    var close = document.createElement("button");
    close.setAttribute("aria-label", "Dismiss");
    close.innerHTML = "×";
    close.addEventListener("click", function () { t.remove(); });
    t.appendChild(p); t.appendChild(close);
    region.appendChild(t);
    setTimeout(function () { t.classList.add("rui-toast--hide"); setTimeout(function () { t.remove(); }, 300); }, 4200);
  }
  window.RATSHIE_ADMIN = { toast: toast };

  /* Convert Django server messages to toasts. */
  function convertDjangoMessages() {
    var holder = document.getElementById("rui-django-messages");
    if (!holder) return;
    var data;
    try { data = JSON.parse(holder.getAttribute("data-messages")); } catch (e) { return; }
    (data || []).forEach(function (m) {
      var kind = { success: "success", error: "error", warning: "warning", info: "info" }[m.tags] || "info";
      toast(m.msg, kind);
    });
    holder.remove();
  }
  convertDjangoMessages();

  /* ---------------- Notification bell ----------------
     Mark read on open of an item; mark-all clears badge; badge refresh. */
  function refreshBadge(count) {
    var btn = document.querySelector('[data-popup-toggle][aria-label*="Notification"], [aria-label="Notifications"]');
    var badge = btn ? btn.querySelector(".rui-bell-dot") : null;
    if (count > 0) {
      if (badge) badge.textContent = count;
      else if (btn) {
        var b = document.createElement("span");
        b.className = "rui-bell-dot";
        b.textContent = count;
        btn.appendChild(b);
      }
    } else if (badge) {
      badge.remove();
    }
  }

  function wireNotifications() {
    document.querySelectorAll("[data-mark-read]").forEach(function (a) {
      a.addEventListener("click", function () {
        a.classList.remove("rui-notif-unread");
        var dot = a.querySelector(".rounded-full");
        if (dot) dot.classList.remove("bg-brand-500");
        if (dot) dot.classList.add("bg-ink-200");
        var pk = a.getAttribute("data-mark-read");
        fetch("/admin/notifications/" + pk + "/read/", {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
        });
      });
    });

    var markAll = document.querySelector("[data-mark-all-read]");
    if (markAll) {
      markAll.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation();
        fetch("/admin/notifications/read-all/", {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
        }).then(function () {
          document.querySelectorAll(".rui-notif-unread").forEach(function (a) {
            a.classList.remove("rui-notif-unread");
            var dot = a.querySelector(".rounded-full");
            if (dot) { dot.classList.remove("bg-brand-500"); dot.classList.add("bg-ink-200"); }
          });
          refreshBadge(0);
          toast("All notifications marked as read.", "success");
        }).catch(function () {
          toast("Something went wrong. Please try again.", "error");
        });
      });
    }
  }
  wireNotifications();

  /* ---------------- Modals ---------------- */
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-open-modal]");
    if (!opener) return;
    var body = document.body;
    var id = opener.getAttribute("data-open-modal");
    var existing = document.getElementById(id);
    if (existing) { body.appendChild(existing); existing.classList.add("open"); return; }
    var modal = document.createElement("div");
    modal.id = id;
    modal.className = "rui-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.innerHTML =
      '<div class="rui-modal__backdrop" data-modal-close></div>' +
      '<div class="rui-modal__panel">' +
        '<button type="button" class="rui-modal__close" data-modal-close aria-label="Close">×</button>' +
        '<div class="rui-modal__content">' + opener.getAttribute("data-modal-html") || "" + "</div>" +
      "</div>";
    body.appendChild(modal);
    modal.classList.add("open");
  });
  document.addEventListener("click", function (e) {
    var closer = e.target.closest("[data-modal-close]");
    if (!closer) return;
    var modal = closer.closest(".rui-modal");
    if (modal) modal.classList.remove("open");
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".rui-modal.open").forEach(function (m) { m.classList.remove("open"); });
    }
  });

  /* ---------------- HTMX guards ---------------- */
  document.body.addEventListener("htmx:confirm", function (e) {
    var btn = e.detail.elt;
    if (btn.hasAttribute("data-confirm")) {
      e.preventDefault();
      var msg = btn.getAttribute("data-confirm") || "Are you sure?";
      if (window.confirm(msg)) { e.detail.issueRequest(true); }
    }
  });
  document.body.addEventListener("htmx:beforeRequest", function (e) {
    var el = e.detail.elt;
    if (el.classList.contains("rui-htmx-guard")) {
      el.classList.add("rui-loading");
      el.setAttribute("aria-busy", "true");
    }
    var btn = el.closest("button");
    if (btn) { btn.disabled = true; btn.setAttribute("data-disabled-during", "1"); }
  });
  document.body.addEventListener("htmx:afterRequest", function (e) {
    var el = e.detail.elt;
    if (el.classList.contains("rui-htmx-guard")) {
      el.classList.remove("rui-loading");
      el.setAttribute("aria-busy", "false");
    }
    var btn = el.closest("button");
    if (btn) { btn.disabled = false; btn.removeAttribute("data-disabled-during"); }
  });
  document.body.addEventListener("htmx:responseError", function (e) {
    toast("Something went wrong. Please try again.", "error");
  });
  document.body.addEventListener("htmx:sendError", function (e) {
    toast("Network error. Please try again.", "error");
  });

  /* ---------------- Order status inline update ---------------- */
  document.addEventListener("change", function (e) {
    var select = e.target.closest(".rui-status-select");
    if (!select) return;
    var pk = select.getAttribute("data-pk");
    var action = select.getAttribute("data-action");
    var badge = document.getElementById("rui-status-badge-" + pk);
    var previous = badge ? badge.getAttribute("data-status") : null;

    select.disabled = true;
    fetch(action, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
      body: "status=" + encodeURIComponent(select.value),
    })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (data) {
        if (badge) {
          badge.textContent = data.label;
          badge.setAttribute("data-status", data.status);
          badge.className = "rui-badge rui-badge-" + statusTone(data.status);
        }
        toast("Order status updated to " + data.label + ".", "success");
      })
      .catch(function () {
        if (previous && badge) badge.setAttribute("data-status", previous);
        if (badge && badge.dataset && badge.dataset.label) badge.textContent = badge.dataset.label;
        toast("Update failed. Please try again.", "error");
      })
      .finally(function () { select.disabled = false; });
  });

  function statusTone(status) {
    var map = {
      paid: "green", completed: "green", ready: "blue", processing: "blue",
      pending: "amber", cancelled: "red", refunded: "red", failed: "red",
    };
    return map[status] || "slate";
  }
})();
