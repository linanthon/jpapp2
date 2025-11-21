// ================= Quiz main menu ===========================================
// Select quiz mode, take chosen mode necessary params and pass to openQuizOptions
function openQuizOptionsFromButton(btn) {
  const actionUrl = btn.getAttribute('data-action');
  const mode = btn.getAttribute('data-mode');
  
  // Selected mode button color is different, we need to change it when select different button
  // Remove active class from all quiz buttons
  document.querySelectorAll('#quizSelect').forEach(b => b.classList.remove('active'));
  // Add active class to newly clicked button
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