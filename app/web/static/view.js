document.getElementById("searchWordForm").addEventListener("submit", async function(e) {
  e.preventDefault(); // no page reload
  await handleViewSubmit(this, "searchWordNotice", "showRes");
});

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
            <a href="${bpPrefix}/view/word/${encodeURIComponent(w.word)}">
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

// View word set star
// document.addEventListener("DOMContentLoaded", () => {
//   const star = document.getElementById("starToggle");

//   star.addEventListener("click", async () => {
//     const isYellow = star.classList.contains("yellow");

//     // Toggle UI immediately
//     star.classList.toggle("yellow", !isYellow);
//     star.classList.toggle("white", isYellow);

//     // Send change to backend
//     // try {
//     //   const resp = await fetch("/v1/toggle_star", {
//     //     method: "POST",
//     //     headers: { "Content-Type": "application/json" },
//     //     body: JSON.stringify({ word: document.getElementById("wordSpelling").textContent })
//     //   });
//     //   const data = await resp.json();
//     //   console.log("Server response:", data);
//     // } catch (err) {
//     //   console.error("Failed to toggle star:", err);
//     // }
//   });
// });




document.addEventListener("DOMContentLoaded", () => {
  const playBtn = document.getElementById("playBtn");
  if (!playBtn) return;

  playBtn.addEventListener("click", async () => {
    for (const file of window.audioFiles || []) {
      const audio = new Audio(`/v1/audio/${file}`); // uses Flask route
      await new Promise(resolve => {
        audio.onended = resolve;
        audio.play();
      });
    }
  });
});