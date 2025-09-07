document.getElementById("searchWordForm").addEventListener("submit", async function(e) {
  e.preventDefault(); // no page reload
  await handleViewSubmit(this, "searchWordNotice", "showRes");
});

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
    
    if (data.results && data.results.length > 0) {
      showResult.style.display = "block";
      showResult.innerHTML = "<h3>Search Results:</h3><ul>" +
        data.results.map(w => `<li><strong>${w.word}</strong> (${w.spelling}) — ${w.senses}</li>`).join("") +
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
