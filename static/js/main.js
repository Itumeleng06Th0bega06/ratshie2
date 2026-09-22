/* Ratshie - interactions. */
(function () {
  "use strict";

  /* Navbar scroll shadow */
  var nav = document.querySelector(".nav");
  function onScroll() {
    if (nav) nav.classList.toggle("scrolled", window.scrollY > 10);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* Mobile nav */
  var toggle = document.querySelector(".nav__toggle");
  var closeBtn = document.querySelector(".mobile-nav__close");
  var mobileNav = document.querySelector(".mobile-nav");
  function openNav() { if (mobileNav) mobileNav.classList.add("open"); document.body.style.overflow = "hidden"; }
  function closeNav() { if (mobileNav) mobileNav.classList.remove("open"); document.body.style.overflow = ""; }
  if (toggle) toggle.addEventListener("click", openNav);
  if (closeBtn) closeBtn.addEventListener("click", closeNav);
  if (mobileNav) mobileNav.addEventListener("click", function (e) { if (e.target === mobileNav) closeNav(); });
  document.querySelectorAll(".mobile-nav a").forEach(function (a) {
    a.addEventListener("click", closeNav);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeNav(); });

  /* FAQ accordion */
  document.querySelectorAll(".faq-item__q").forEach(function (q) {
    q.addEventListener("click", function () {
      var item = q.closest(".faq-item");
      var answer = item.querySelector(".faq-item__a");
      var isOpen = item.classList.contains("open");
      document.querySelectorAll(".faq-item.open").forEach(function (o) {
        if (o !== item) {
          o.classList.remove("open");
          o.querySelector(".faq-item__a").style.maxHeight = null;
        }
      });
      if (isOpen) {
        item.classList.remove("open");
        answer.style.maxHeight = null;
      } else {
        item.classList.add("open");
        answer.style.maxHeight = answer.scrollHeight + "px";
      }
    });
  });

  /* Quantity steppers */
  document.querySelectorAll(".qty").forEach(function (box) {
    var input = box.querySelector("input");
    var minus = box.querySelector("[data-dec]");
    var plus = box.querySelector("[data-inc]");
    function set(v) {
      if (!input) return;
      v = Math.max(parseInt(input.min || "1", 10) || 1, v);
      input.value = v;
    }
    if (minus) minus.addEventListener("click", function () { set((parseInt(input.value, 10) || 1) - 1); });
    if (plus) plus.addEventListener("click", function () { set((parseInt(input.value, 10) || 0) + 1); });
    if (input) input.addEventListener("change", function () { set(parseInt(input.value, 10) || 1); });
  });

  /* Scroll reveal */
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function reveal() {
    document.querySelectorAll(".reveal, [data-stagger]").forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.top < window.innerHeight - 60) el.classList.add("visible");
    });
  }
  if (reduce) {
    document.querySelectorAll(".reveal, [data-stagger]").forEach(function (el) { el.classList.add("visible"); });
  } else {
    reveal();
    window.addEventListener("scroll", reveal, { passive: true });
    window.addEventListener("load", reveal);
  }

  /* Filter form auto-submit on change */
  document.querySelectorAll("[data-autofilter]").forEach(function (sel) {
    sel.addEventListener("change", function () {
      var form = sel.closest("form");
      if (form) form.submit();
    });
  });

  /* Account menu (header dropdown) */
  var acctTrigger = document.querySelector(".account-menu__trigger");
  var acctDropdown = document.querySelector(".account-menu__dropdown");
  if (acctTrigger && acctDropdown) {
    acctTrigger.addEventListener("click", function () {
      var open = acctDropdown.classList.toggle("open");
      acctTrigger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".account-menu")) {
        acctDropdown.classList.remove("open");
        acctTrigger.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* Password visibility toggles */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-password-toggle]");
    if (!btn) return;
    var input = document.getElementById(btn.getAttribute("data-password-toggle"));
    if (!input) return;
    var isHidden = input.type === "password";
    input.type = isHidden ? "text" : "password";
    btn.textContent = isHidden ? "Hide" : "Show";
    btn.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
  });

  /* ARIA wiring: mark invalid fields + describe errors. Re-runs on htmx swaps. */
  function wireFormsAria() {
    document.querySelectorAll(".field--error").forEach(function (field) {
      var input = field.querySelector("input, select, textarea");
      if (!input) return;
      input.setAttribute("aria-invalid", "true");
      var err = field.querySelector(".field-error");
      if (err && err.id) input.setAttribute("aria-describedby", err.id);
    });
  }
  wireFormsAria();

  /* Focus first invalid field (useful after a failed login/register/checkout) */
  document.addEventListener("htmx:afterSwap", function () {
    wireFormsAria();
    document
      .querySelectorAll(".reveal, [data-stagger]")
      .forEach(function (el) { el.classList.add("visible"); });
    var invalid = document.querySelector('.field--error input[aria-invalid="true"], .field--error select, .field--error textarea');
    if (invalid) invalid.focus();
  });

  /* Member purchase prompt modal */
  function openMemberPrompt() {
    var prompt = document.getElementById("memberPrompt");
    if (!prompt) return;
    prompt.classList.add("open");
    document.body.style.overflow = "hidden";
    var closeBtn = prompt.querySelector(".member-modal__close");
    if (closeBtn) closeBtn.focus();
  }
  function closeMemberPrompt() {
    var prompt = document.getElementById("memberPrompt");
    if (prompt) prompt.classList.remove("open");
    var host = document.getElementById("memberPromptHost");
    if (host) host.innerHTML = "";
    document.body.style.overflow = "";
  }
  document.addEventListener("click", function (e) {
    var closer = e.target.closest("[data-member-close], .member-modal__backdrop");
    if (closer) closeMemberPrompt();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeMemberPrompt();
      if (acctDropdown) acctDropdown.classList.remove("open");
    }
  });
  /* Auto-open prompt when the modal is injected via htmx */
  document.addEventListener("htmx:afterSwap", function (e) {
    if (e.target && e.target.id === "memberPromptHost") openMemberPrompt();
  });
  document.addEventListener("htmx:responseError", function () {
    openMemberPrompt();
  });

  function updateCartBadge(count) {
    var badges = document.querySelectorAll(".js-cart-count");
    badges.forEach(function (b) {
      if (count > 0) { b.textContent = count; b.style.display = ""; }
      else { b.textContent = ""; b.style.display = "none"; }
    });
  }

  /* No-refresh add-to-cart (progressive enhancement; server still enforces rules).
     Handles member-only 403 -> opens prompt, else updates badge + button state. */
  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  document.addEventListener("submit", function (e) {
    var form = e.target.closest("[data-add-to-cart]");
    if (!form) return;
    // Buy-now submits to a different action than the form's: let the browser
    // do a normal POST so the server keeps full control (guest → member gate,
    // member → checkout).
    if (e.submitter && e.submitter.getAttribute("formaction")) return;
    e.preventDefault();
    var button = form.querySelector("button[type=submit]");
    var url = form.getAttribute("action");
    var labelEl = button.querySelector("span");
    var original = (labelEl && labelEl.innerHTML) || button.innerHTML;
    button.disabled = true;
    if (labelEl) labelEl.textContent = "ADDING...";
    var payload = new FormData(form);
    fetch(url, { method: "POST", headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": getCookie("csrftoken") }, body: payload, credentials: "same-origin" })
      .then(function (res) { return res.text().then(function (t) { return { ok: res.ok, status: res.status, text: t }; }); })
      .then(function (result) {
        var data = null;
        try { data = JSON.parse(result.text); } catch (err) { data = null; }
        // Server-directed navigation (anonymous visitor + sale product →
        // registration). Do NOT update the cart count or button state.
        if (data && data.redirect) {
          window.location.href = data.redirect;
          return;
        }
        if (result.status === 403) {
          // inject member prompt modal
          var host = document.getElementById("memberPromptHost");
          if (host) { host.innerHTML = result.text; openMemberPrompt(); }
        } else if (result.ok) {
          if (labelEl) { labelEl.innerHTML = "✓ ADDED"; }
          var match = result.text.match(/id="cartCount"[^>]*>(\d+)</);
          if (match) updateCartBadge(parseInt(match[1], 10));
        }
        setTimeout(function () {
          button.disabled = false;
          if (labelEl) labelEl.innerHTML = original;
        }, 1400);
      })
      .catch(function () {
        button.disabled = false;
        if (labelEl) labelEl.innerHTML = original;
        window.RUI && RUI.toast("Unable to add the item. Please try again.", "error");
      });
  });

  /* Logout forms submit via fetch so only the account area updates. */
  document.addEventListener("submit", function (e) {
    var form = e.target.closest("[data-logout]");
    if (!form) return;
    e.preventDefault();
    var btn = form.querySelector("button[type=submit]");
    if (btn) btn.disabled = true;
    fetch(form.getAttribute("action"), { method: "POST", headers: { "X-CSRFToken": getCookie("csrftoken") }, body: new FormData(form), credentials: "same-origin" })
      .then(function () {
        var area = document.getElementById("accountArea");
        if (area) {
          area.innerHTML = '<div class="account-area account-area--anon">' +
            '<a class="account-link" href="/account/login/">Sign In</a>' +
            '<a class="btn btn--gold btn--sm" href="/account/register/">Sign Up</a></div>';
        }
        window.location.href = form.querySelector("input[name=next]") ? form.querySelector("input[name=next]").value : "/";
      })
      .catch(function () { if (btn) btn.disabled = false; });
  });
})();
