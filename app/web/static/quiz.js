// ================= Quiz main menu ===========================================
// show filter options before quiz starts
const searchForm = document.getElementById("quizJP");
if (searchForm) {
  searchForm.addEventListener("submit", async function(e) {
    e.preventDefault();
    await handleQuizWordSubmit(this, "showQuizWordOptions", "quizWordNotice");
  });
}

function showQuizWordOptionBox() {
  const quizWordBoxCont = document.getElementById('quizWordOptionBoxContainer');
  const fileInfo = document.getElementById('fileInfo');  
  const fileProgressLine = document.getElementById('fileProgressLine');
  const fileNotice = document.getElementById('fileNotice');

  // Disable display of the `Choose File` option if choose `Enter String`
  fileInfo.style.display = "none"
  fileProgressLine.style.display = "none"
  fileNotice.style.display = "none"

  // Display string text box
  stringBoxCont.style.display = "block"
}

async function handleQuizWordSubmit(form, optionId, noticeId) {
  console.log("Handling view submit");
  const showQuizWordOptions = document.getElementById(optionId);
  const notice = document.getElementById(noticeId);

  // Clear previous results
  // TODO: maybe remove this
  notice.style.display = "none";
  showQuizWordOptions.style.display = "flex";

  try {
    // Build URL with query parameters for GET request
    const formData = new FormData(form);
    const params = new URLSearchParams(formData);
    const url = `${form.action}?${params.toString()}`;
    
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
    notice.style.display = "block";
    notice.style.color = "red";
    notice.textContent = "Network error occurred";
  }

}


// new
function openQuizOptions(actionUrl, mode) {
  const form = document.getElementById('quizOptionsForm');
  if (!form) return;

  // Set endpoint to action (can be quiz_jp, quiz_en or quiz_sentence)
  form.action = actionUrl;

  // ???? what is this
  // Optionally store mode (useful if backend needs to know)
  // let hiddenMode = form.querySelector('input[name="quiz_mode"]');
  // if (!hiddenMode) {
  //   hiddenMode = document.createElement('input');
  //   hiddenMode.type = 'hidden';
  //   hiddenMode.name = 'quiz_mode';
  //   form.appendChild(hiddenMode);
  // }
  // hiddenMode.value = mode;

  // Show/hide fields depending on mode
  const jlptSelect = document.getElementById('jlptFilter');
  const starSelect = document.getElementById('starFilter');
  const bookSelect = document.getElementById('bookFilter');
  if (mode === 'sentence') {
    if (jlptSelect) jlptSelect.style.display = 'none';
    if (starSelect) starSelect.style.display = 'none';
  } else {
    if (jlptSelect) jlptSelect.style.display = 'flex';
    if (starSelect) starSelect.style.display = 'flex';
  }
  if (bookSelect) bookSelect.style.display = 'flex';

  // Show the entire options box
  form.style.display = 'block';

  // optional: scroll into view
  // form.scrollIntoView({ behavior: 'smooth', block: 'center' });
}