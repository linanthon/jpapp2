// =============================== Search word ===============================
const searchForm = document.getElementById("searchWordForm");
if (searchForm) {
  searchForm.addEventListener("submit", async function(e) {
    e.preventDefault(); // no page reload
    await handleViewSubmit(this, "searchWordNotice", "showRes");
  });
}

// Search word print and clickable results
async function handleViewSubmit(form, noticeId, showResId) {
  console.log("Handling view submit");
  const notice = document.getElementById(noticeId);
  const showResult = document.getElementById(showResId);

  // Clear previous results
  notice.style.display = "none";
  showResult.style.display = "none";
  
  try {
    // Build URL with query parameters for GET request
    const formData = new FormData(form);
    const params = new URLSearchParams(formData);
    const url = `${form.action}?${params.toString()}`;
    
    console.log("Fetching:", url);
    const response = await fetch(url, { method: "GET" });
    
    if (!response.ok) {
      // Handle error response
      notice.style.display = "block";
      notice.style.color = "red";

      const resp = await response.json();
      notice.textContent = `Error: ${resp.error}`;
      return;
    }
    
    // Parse JSON response
    const data = await response.json();
    console.log("Response data:", data);
    const bpPrefix = data.bpPrefix
    
    if (data.results && data.results.length > 0) {
      showResult.style.display = "block";
      showResult.innerHTML = "<h3>Search Results:</h3><ul>" +
        data.results.map(w => `<li>
            <a href="${bpPrefix}/view/word/${w.word_id}">
              <strong>${w.word}</strong>
            </a>
            (${w.spelling}) — ${w.senses}
          </li>`).join("") +
        "</ul>";
    } else {
      notice.style.display = "block";
      notice.style.color = "orange";
      notice.textContent = "No results found";
    }
    
  } catch (error) {
    console.error("Fetch error:", error);
    notice.style.display = "block";
    notice.style.color = "red";
    notice.textContent = "Network error occurred";
  }
}


// =============================== View specific word ===============================
// ----- Toggle known/un-known for the word. aka. call backend to edit `priority` to 0.0 or recaculate it -----
document.addEventListener("DOMContentLoaded", () => {
  const toggleBtn = document.getElementById('toggleKnown');
  if (!toggleBtn) return;

  function buildLabel(priority) {
    const p = parseFloat(priority) || 0;
    return p > 0 ? 'Mark as known' : 'Unmark known';
  }

  toggleBtn.addEventListener('click', async function () {
    const wordId = this.dataset.id;
    const url = this.dataset.toggleUrl;
    const curPriority = parseFloat(this.dataset.priority) || 0.0;
    // If curPriority > 0 -> need to update priority to <= 0.0, word will never appear in (normal) quiz (mode) again
    const updateToKnown = curPriority > 0.0;
    const quized = this.dataset.quized;
    const occurrence = this.dataset.occurrence;

    // Disable while requesting
    this.disabled = true;

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word_id: wordId, update_to_known: updateToKnown, quized: quized, occurrence: occurrence})
      });

      const data = await (res.ok ? res.json() : Promise.resolve({ success: false }));
      if (!res.ok || !data.success) {
        console.error('Toggle known failed', data);
        alert('Failed to change known status');
        return;
      }

      // Set priority (don't need to be real priority), just enough to change UI
      let newPriority = 1
      if (updateToKnown) {
        newPriority = -1
      }
      this.dataset.priority = newPriority;
      // Update button label only (tooltip is a separate element to the right)
      this.textContent = buildLabel(newPriority);
      
      // Update tooltip text in the adjacent .info-tooltip (if exists)
      const tooltipContainer = this.nextElementSibling;
      if (tooltipContainer && tooltipContainer.classList && tooltipContainer.classList.contains('info-tooltip')) {
        const tt = tooltipContainer.querySelector('.tooltip-text');
        if (tt) {
          tt.textContent = newPriority > 0 ? 'Make this word no longer appear in quiz' : 'Let this word appear in quiz again with your previous progress on this word. If your have progressed this word to a point where it no longer appears in normal quiz mode on its own, pressing this button does not change such behavior. Use the `Review known words` mode for it.';
        }
      }
    } catch (err) {
      console.error('Toggle known error', err);
      alert('Network error changing known status');
    } finally {
      this.disabled = false;
    }
  });
});

// ----- set star / favorite -----
document.addEventListener("DOMContentLoaded", () => {
  const star = document.getElementById("wordStarToggle");
  if (!star) return;

  star.addEventListener("click", async () => {
    // Current star state
    const isYellow = star.classList.contains("yellow");

    // Toggle UI immediately
    star.classList.toggle("yellow", !isYellow);
    star.classList.toggle("white", isYellow);

    const wordID = star.dataset.id;
    const url = star.dataset.toggleUrl || "/v1/toggle-star";
    const starParam = (!isYellow).toString(); // reverse of current state

    // Send change to backend
    try {
      // Make the star change call
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: wordID, objType: "word", star: starParam })
      });
      const data = await resp.json();

      if (!resp.ok || !data.success) {
        // revert UI on failure
        star.classList.toggle("yellow", isYellow);
        star.classList.toggle("white", !isYellow);
        console.error("Toggle star failed:", data);
        return;
      }

      // Keep UI in sync with server response if provided
      if (typeof data.starred !== "undefined") {
        const serverStarred = data.starred === 1;
        star.classList.toggle("yellow", serverStarred);
        star.classList.toggle("white", !serverStarred);
      }
    } catch (err) {
      // revert on network error
      star.classList.toggle("yellow", isYellow);
      star.classList.toggle("white", !isYellow);
      console.error("Failed to toggle star:", err);
    }
  });
});

// ----- play audio -----
document.addEventListener("DOMContentLoaded", () => {
  const playBtn = document.getElementById("playBtn");
  if (!playBtn) return;

  playBtn.addEventListener("click", async () => {
    const audioMappingStr = playBtn.dataset.audioMapping;
    if (!audioMappingStr) {
      console.warn("No audio mapping found for " + playBtn.dataset.word)
      return;
    }

    let audioMapping;
    try {
      audioMapping = JSON.parse(audioMappingStr);
    } catch(e) {
      // Fallback: handle Python-like list "['to','zan']" or unquoted tokens
      try {
        const alt = audioMappingStr
          .replace(" ", "")             // space after comma
          .replace(/'/g, '"')           // single → double quotes
          .replace(/,\s*,/g, ',')       // remove accidental empty elems
        audioMapping = JSON.parse(alt);
      } catch (e2) {
        console.error("Failed to parse audio mapping:", audioMappingStr, e, e2);
        return;
      }
    }

    const urlPrefix = document.documentElement.getAttribute('data-url-prefix');

    for (const syllable of audioMapping || []) {
      const filename = `${urlPrefix}/audio/${syllable}.wav`
      const audio = new Audio(filename);
      await new Promise(resolve => {
        audio.onended = resolve;
        audio.onerror = () => {
          console.error(`Failed to load audio: ${filename}`);
          resolve();
        };
        audio.play().catch(err => {
          console.error(`Failed to play audio: ${filename}`, err);
          resolve();
        });
      });
    }
  });
});

// =============================== Book ===============================
// View 1 book: set star
document.addEventListener("DOMContentLoaded", () => {
  const stars = document.querySelectorAll(".book-star-toggle");
  if (!stars.length) return;

  stars.forEach(star => {
    star.addEventListener("click", async () => {
      // Current star state
      const isYellow = star.classList.contains("yellow");

      // Toggle UI immediately
      star.classList.toggle("yellow", !isYellow);
      star.classList.toggle("white", isYellow);

      const bookID = star.dataset.id || this.getAttribute('data-id');
      const url = star.dataset.toggleUrl || this.getAttribute('data-toggle-url') || "/v1/toggle-star";
      const starParam = (!isYellow).toString(); // reverse of current state

      // Send change to backend
      try {
        // Make the star change call
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: bookID, objType: "book", star: starParam })
        });
        const data = await resp.json();

        if (!resp.ok || !data.success) {
          // revert UI on failure
          star.classList.toggle("yellow", isYellow);
          star.classList.toggle("white", !isYellow);
          console.error("Toggle star failed:", data);
          return;
        }

        // Keep UI in sync with server response if provided
        if (typeof data.starred !== "undefined") {
          const serverStarred = data.starred === 1;
          star.classList.toggle("yellow", serverStarred);
          star.classList.toggle("white", !serverStarred);
        }
      } catch (err) {
        // revert on network error
        star.classList.toggle("yellow", isYellow);
        star.classList.toggle("white", !isYellow);
        console.error("Failed to toggle star:", err);
      }
    });
  });
});

// Delete book
document.addEventListener("DOMContentLoaded", () => {
  const deleteBtn = document.getElementById('deleteBook');
  if (!deleteBtn) return;

  deleteBtn.addEventListener('click', async function () {
    const bookId = this.dataset.id || this.getAttribute('data-id');
    const bookName = this.dataset.name || this.getAttribute('data-name') || '';
    const url = this.dataset.deleteUrl || this.getAttribute('data-delete-url') || '/del/book';

    const ok = confirm(`Are you sure to delete book ${bookName} along its words and sentences?`);
    if (!ok) return;

    this.disabled = true;
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: bookId, name: bookName })
      });

      if (res.ok) {
        // go back to previous page or root
        window.location = document.referrer || '/';
      } else {
        let text = '';
        try { text = await res.text(); } catch (e) {}
        alert('Delete failed: ' + (text || res.statusText || res.status));
      }
    } catch (err) {
      alert('Delete failed: ' + (err && err.message ? err.message : err));
    } finally {
      this.disabled = false;
    }
  });
})();