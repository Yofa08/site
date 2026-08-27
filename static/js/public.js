(function () {
  function writeClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }

    var textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    return Promise.resolve();
  }

  function setMessage(el, message, type) {
    if (!el) return;
    el.textContent = message;
    el.classList.remove("is-success", "is-error");
    if (type) el.classList.add("is-" + type);
  }

  function copyCode(el) {
    var code = el.dataset.copyCode || "";
    if (!code) return;

    writeClipboard(code).then(function () {
      el.textContent = code + " Copied";
      el.classList.add("copied");
      window.setTimeout(function () {
        el.textContent = code + " Copy";
        el.classList.remove("copied");
      }, 1800);
    });
  }

  function toggleInfluencerCopy(el) {
    var targetId = el.dataset.copyTarget || "";
    var box = document.getElementById(targetId);
    if (!box) return;

    var open = box.classList.toggle("open");
    el.setAttribute("aria-expanded", open ? "true" : "false");
    el.textContent = open ? "Hide Influencer Copy" : "Copy for Influencer";
  }

  function copyInfluencerText(el) {
    var textId = el.dataset.copyTextId || "";
    var textarea = document.getElementById(textId);
    if (!textarea) return;

    writeClipboard(textarea.value).then(function () {
      el.textContent = "Copied";
      el.classList.add("copied");
      window.setTimeout(function () {
        el.textContent = "Copy Text";
        el.classList.remove("copied");
      }, 1800);
    });
  }

  function openSubscribeModal() {
    var modal = document.getElementById("subscribeModal");
    var input = document.getElementById("subEmail");
    var message = document.getElementById("subMsg");
    if (!modal) return;
    if (input) input.value = "";
    setMessage(message, "", null);
    modal.classList.add("open");
    if (input) input.focus();
  }

  function closeSubscribeModal() {
    var modal = document.getElementById("subscribeModal");
    if (modal) modal.classList.remove("open");
  }

  function doSubscribe() {
    var input = document.getElementById("subEmail");
    var message = document.getElementById("subMsg");
    var email = input ? input.value.trim() : "";

    if (!email || !email.includes("@")) {
      setMessage(message, "Please enter a valid email", "error");
      return;
    }

    fetch("/api/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email })
    })
      .then(function (response) { return response.json(); })
      .then(function (result) {
        var ok = Boolean(result.success);
        setMessage(message, result.message || (ok ? "Subscribed!" : "Error"), ok ? "success" : "error");
        if (ok) {
          if (input) input.value = "";
          window.setTimeout(closeSubscribeModal, 1800);
        }
      })
      .catch(function () {
        setMessage(message, "Network error", "error");
      });
  }

  document.addEventListener("click", function (event) {
    var copyTarget = event.target.closest("[data-copy-code]");
    if (copyTarget) {
      copyCode(copyTarget);
      return;
    }

    var copyToggle = event.target.closest("[data-copy-toggle]");
    if (copyToggle) {
      toggleInfluencerCopy(copyToggle);
      return;
    }

    var textCopy = event.target.closest("[data-copy-text-id]");
    if (textCopy) {
      copyInfluencerText(textCopy);
      return;
    }

    if (event.target.closest("[data-subscribe-open]")) {
      openSubscribeModal();
      return;
    }

    if (event.target.closest("[data-subscribe-submit]")) {
      doSubscribe();
      return;
    }

    if (event.target.closest("[data-subscribe-close]")) {
      closeSubscribeModal();
      return;
    }

    var modal = document.getElementById("subscribeModal");
    if (modal && event.target === modal) {
      closeSubscribeModal();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeSubscribeModal();
    }
    if (event.key === "Enter" && event.target && event.target.id === "subEmail") {
      doSubscribe();
    }
  });

  window.doSubscribe = doSubscribe;
})();
