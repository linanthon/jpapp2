document.getElementById("searchWordForm").addEventListener("submit", async function(e) {
  console.log("Form submitted");
  e.preventDefault(); // no page reload
  await handleViewSubmit(this, "searchWordNotice", "showRes");
});

// async function handleViewSubmit(form, noticeId, showResId) {
//   console.log("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB");
//   const notice = document.getElementById(noticeId);
//   const showResult = document.getElementById(showResId);

//   // const params = new URLSearchParams(new FormData(form));
//   // const response = await fetch(form.action + "?" + params.toString());  
//   const formData = new FormData(form);
//   const response = await fetch(form.action, { method: "GET", body: formData });
//   // const data = await response.json();

//   const decoder = new TextDecoder();
//   const reader = response.body.getReader();
//   let finalText = "";
  
//   notice.style.display = "none";
//   showResult.style.display = "none";

  
//   const {_, value} = await reader.read();
//   const chunk = decoder.decode(value, { stream: true });
//   chunk.split("\n\n").forEach(line => {
//     finalText = line.trim();
//   });

//   if (!response.ok) {
//     notice.style.display = "block";
//     notice.style.color = "red";
//     notice.textContent = //data.error;
//   }
//   // } else {
//   //   showResult.style.display = "block";
//   //   showResult.innerHTML = "<ul>" +
//   //     data.results.map(w => `<li>${w.word} – ${w.senses}</li>`).join("") +
//   //     "</ul>";
//   // }
//   console.log("CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC");
// }

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
      const errorText = await response.text();
      notice.style.display = "block";
      notice.style.color = "red";
      notice.textContent = `Error: ${errorText}`;
      return;
    }
    
    // Parse JSON response
    const data = await response.json();
    console.log("Response data:", data);
    
    if (data.error) {
      notice.style.display = "block";
      notice.style.color = "red";
      notice.textContent = data.error;
    } else if (data.results && data.results.length > 0) {
      showResult.style.display = "block";
      showResult.innerHTML = "<h3>Search Results:</h3><ul>" +
        data.results.map(w => `<li><strong>${w.word}</strong> — ${w.senses}</li>`).join("") +
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
