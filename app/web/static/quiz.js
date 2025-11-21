// ================= Quiz main menu ===========================================
// show filter options before quiz starts
// const searchForm = document.getElementById("quizJP");
// if (searchForm) {
//   searchForm.addEventListener("submit", async function(e) {
//     e.preventDefault();
//     await handleQuizWordSubmit(this, "showQuizWordOptions", "quizWordNotice");
//   });
// }

// function showQuizWordOptionBox() {
//   const quizWordBoxCont = document.getElementById('quizWordOptionBoxContainer');
//   const fileInfo = document.getElementById('fileInfo');  
//   const fileProgressLine = document.getElementById('fileProgressLine');
//   const fileNotice = document.getElementById('fileNotice');

//   // Disable display of the `Choose File` option if choose `Enter String`
//   fileInfo.style.display = "none"
//   fileProgressLine.style.display = "none"
//   fileNotice.style.display = "none"

//   // Display string text box
//   stringBoxCont.style.display = "block"
// }

// async function handleQuizWordSubmit(form, optionId, noticeId) {
//   console.log("Handling view submit");
//   const showQuizWordOptions = document.getElementById(optionId);
//   const notice = document.getElementById(noticeId);

//   // Clear previous results
//   // TODO: maybe remove this
//   notice.style.display = "none";
//   showQuizWordOptions.style.display = "flex";

//   try {
//     // Build URL with query parameters for GET request
//     const formData = new FormData(form);
//     const params = new URLSearchParams(formData);
//     const url = `${form.action}?${params.toString()}`;
    
//     const response = await fetch(url, { method: "GET" });
    
//     if (!response.ok) {
//       // Handle error response
//       notice.style.display = "block";
//       notice.style.color = "red";

//       const resp = await response.json();
//       notice.textContent = `Error: ${resp.error}`;
//       return;
//     }
    
//     // Parse JSON response
//     const data = await response.json();
//     const bpPrefix = data.bpPrefix
    
//     if (data.results && data.results.length > 0) {
//       showResult.style.display = "block";
//       showResult.innerHTML = "<h3>Search Results:</h3><ul>" +
//         data.results.map(w => `<li>
//             <a href="${bpPrefix}/view/word/${w.word_id}">
//               <strong>${w.word}</strong>
//             </a>
//             (${w.spelling}) — ${w.senses}
//           </li>`).join("") +
//         "</ul>";
//     } else {
//       notice.style.display = "block";
//       notice.style.color = "orange";
//       notice.textContent = "No results found";
//     }
    
//   } catch (error) {
//     notice.style.display = "block";
//     notice.style.color = "red";
//     notice.textContent = "Network error occurred";
//   }

// }

// Select quiz mode, take chosen mode necessary params and pass to openQuizOptions
function openQuizOptionsFromButton(btn) {
  const actionUrl = btn.getAttribute('data-action');
  const mode = btn.getAttribute('data-mode');
  
  // Remove active class from all quiz buttons
  document.querySelectorAll('#quizSelect').forEach(b => b.classList.remove('active'));
  
  // Add active class to clicked button
  btn.classList.add('active');
  
  openQuizOptions(actionUrl, mode);
}

// Show a box below to allow select JLPT level, star and specific book only
// Press `Start` button after this will go to the quiz session
function openQuizOptions(actionUrl, mode) {
  const form = document.getElementById('quizOptionsForm');
  if (!form) return;

  // Set endpoint to action (can be quiz_jp, quiz_en or quiz_sentence)
  form.action = actionUrl;

  // Show/hide fields depending on mode
  const jlptSelect = document.getElementById('jlptFilter');
  const starSelect = document.getElementById('starFilter');
  const bookSelect = document.getElementById('bookFilter');
  
  if (mode === 'sentence') {
    if (jlptSelect) jlptSelect.style.display = 'none';
    if (starSelect) starSelect.style.display = 'none';
    
    // Clear JLPT level and star selection if choose sentence
    const jlptDropdown = document.getElementById('jlpt');
    const starCheckbox = document.getElementById('star');
    if (jlptDropdown) jlptDropdown.value = '';
    if (starCheckbox) starCheckbox.checked = false;
  } else {
    if (jlptSelect) jlptSelect.style.display = '';
    if (starSelect) starSelect.style.display = '';
  }
  if (bookSelect) bookSelect.style.display = '';

  // Show the entire options box
  form.style.display = 'block';
}