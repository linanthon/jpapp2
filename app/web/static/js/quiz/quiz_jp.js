// Quiz state management
let currentIndex = 0;
let correctCount = 0;
let skippedCount = 0;
let quizCards = [];
let answered = false;
const quizBackendParams = document.getElementById("quiz-backend-params");
const quizData = JSON.parse(quizBackendParams.dataset.quizes);
const updatePrioUrl = quizBackendParams.dataset.updatePrioUrl;
const viewWordUrlTemplate = quizBackendParams.dataset.viewWordUrlTemplate;
const toggleStarUrl = quizBackendParams.dataset.toggleStarUrl;

// Initialize quiz on page load
document.addEventListener('DOMContentLoaded', () => {
  // `quizData` is the var that took in `quizes` from backend
  if (typeof quizData === 'undefined' || Object.keys(quizData).length === 0) {
    showNoQuizMessage();
    return;
  }
  
  initializeQuiz();
  displayCurrentCard();
  updateScoreBoard();
});

// Initialize quiz cards from backend data
function initializeQuiz() {
  const container = document.getElementById('quizContainer');
  const wordIds = Object.keys(quizData);
  
  wordIds.forEach((wordId, index) => {
    const data = quizData[wordId];
    const card = createQuizCard(wordId, data, index);
    container.appendChild(card);
    quizCards.push({ element: card, wordId: wordId, data: data });
  });
  
  document.getElementById('totalCount').textContent = wordIds.length;
}

// Create a quiz card element
function createQuizCard(wordId, data, index) {
  const card = document.createElement('div');
  card.className = 'quiz-card';
  card.dataset.index = index;
  card.dataset.wordId = wordId;
  
  // Question section
  const questionSection = document.createElement('div');
  questionSection.className = 'question-section';
  
  // Star toggle button (like wordStarToggle in view_specific_word)
  const starBtn = document.createElement('button');
  starBtn.type = 'button';
  starBtn.className = `quiz-star ${data.star ? 'yellow' : 'white'}`;
  starBtn.ariaPressed = data.star ? 'true' : 'false';
  starBtn.textContent = '★';
  starBtn.dataset.id = wordId;
  starBtn.dataset.star = data.star ? '1' : '0';
  starBtn.onclick = (e) => {
    e.stopPropagation();
    toggleQuizWordStar(starBtn, wordId, toggleStarUrl);
  };
  
  const jpWord = document.createElement('div');
  jpWord.className = 'jp-word';
  jpWord.textContent = data.question;
  
  // Container for star and JP word
  const jpWordContainer = document.createElement('div');
  jpWordContainer.className = 'jp-word-container';
  jpWordContainer.appendChild(starBtn);
  jpWordContainer.appendChild(jpWord);
  
  const spelling = document.createElement('div');
  spelling.className = 'spelling';
  spelling.textContent = data.spelling;
  
  // Link to word detail page
  const viewWordLink = document.createElement('a');
  viewWordLink.href = `${viewWordUrlTemplate}${wordId}`;
  viewWordLink.className = 'view-word-link';
  viewWordLink.textContent = 'Go to this word';
  
  const audioBtn = document.createElement('button');
  audioBtn.className = 'audio-btn';
  audioBtn.textContent = '🔊 Play Audio';
  audioBtn.onclick = () => playAudio(data.audio_mapping); // is list
  
  questionSection.appendChild(jpWordContainer);
  questionSection.appendChild(spelling);
  questionSection.appendChild(viewWordLink);
  questionSection.appendChild(audioBtn);
  
  // Choices section
  const choicesSection = document.createElement('div');
  choicesSection.className = 'choices-section';
  
  data.choices.forEach((choice) => {
    const choiceBtn = document.createElement('button');
    choiceBtn.className = 'choice-btn';
    choiceBtn.textContent = choice;
    choiceBtn.dataset.choice = choice;
    choiceBtn.onclick = () => handleChoiceClick(wordId, choice, data.correct, choiceBtn, data.quized, data.occurrence);
    choicesSection.appendChild(choiceBtn);
  });
  
  card.appendChild(questionSection);
  card.appendChild(choicesSection);
  
  return card;
}

// Display current card
function displayCurrentCard() {
  quizCards.forEach((card, index) => {
    if (index === currentIndex) {
      card.element.classList.add('active');
    } else {
      card.element.classList.remove('active');
    }
  });
  
  updateSkipNextButton();
}

// Handle choice selection
function handleChoiceClick(wordId, selectedChoice, correctAnswer, clickedBtn, quized, occurrence) {
  // About `quized` and `occurrence`, just pass in the number got from querying DB, no change
  if (answered) return; // Prevent multiple answers
  
  answered = true;
  const currentCard = quizCards[currentIndex];
  const choiceBtns = currentCard.element.querySelectorAll('.choice-btn');
  
  // Add `answered` class, prevent further clicks by in CSS
  choiceBtns.forEach(btn => {
    btn.classList.add('answered');
  });
  
  // Check if answer is correct, add class accordingly
  // And call backend to update priority
  const isCorrect = selectedChoice === correctAnswer;
  
  if (isCorrect) {
    clickedBtn.classList.add('correct');
    correctCount++;
    updateWordPriority(wordId, true, quized, occurrence);
  } else {
    clickedBtn.classList.add('incorrect');
    // Highlight the correct answer
    choiceBtns.forEach(btn => {
      if (btn.dataset.choice === correctAnswer) {
        btn.classList.add('correct');
      }
    });
    updateWordPriority(wordId, false, quized, occurrence);
  }
  
  updateScoreBoard();
  updateSkipNextButton();
}

// Handle skip/next button
function handleSkipNext() {
  if (!answered) {
    // Skip current question
    skippedCount++;
    updateScoreBoard();
  }
  
  // Move to next question
  currentIndex++;
  answered = false;
  
  if (currentIndex >= quizCards.length) {
    showCompletionMessage();
  } else {
    displayCurrentCard();
  }
}

// Update skip/next button text
function updateSkipNextButton() {
  const btn = document.getElementById('skipNextBtn');
  if (answered) {
    btn.textContent = 'Next';
  } else {
    btn.textContent = 'Skip';
  }
}

// Update score board
function updateScoreBoard() {
  document.getElementById('correctCount').textContent = correctCount;
  document.getElementById('skippedCount').textContent = skippedCount;
  document.getElementById('progressCount').textContent = currentIndex + 1;
}

// Play audio for the word
async function playAudio(audioMapping) {
  if (!audioMapping || audioMapping.length === 0) {
    alert('No audio available for this word');
    return;
  }

  for (const syllable of audioMapping || []) {
      const filename = `/v1/audio/${syllable}.wav`
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
}

// Call backend to update word priority
async function updateWordPriority(wordId, isCorrect, quized, occurrence) {
  // About `quized` and `occurrence`, just pass in the number got from querying DB, no change
  try {
    const response = await fetch(updatePrioUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        word_id: parseInt(wordId),
        is_correct: isCorrect,
        quized: parseInt(quized),
        occurrence: parseInt(occurrence)
      })
    });
    
    if (!response.ok) {
      console.error('Failed to update word priority:', response.statusText);
    }
  } catch (error) {
    console.error('Error updating word priority:', error);
  }
}

// Toggle star for a quiz word
async function toggleQuizWordStar(starBtn, wordId, toggleStarUrl) {
  const isYellow = starBtn.classList.contains('yellow');
  
  // Toggle UI immediately
  starBtn.classList.toggle('yellow', !isYellow);
  starBtn.classList.toggle('white', isYellow);
  
  const starParam = (!isYellow).toString();
  
  try {
    const resp = await fetch(toggleStarUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: wordId, objType: 'word', star: starParam })
    });
    const data = await resp.json();
    
    if (!resp.ok || !data.success) {
      // Revert UI on failure
      starBtn.classList.toggle('yellow', isYellow);
      starBtn.classList.toggle('white', !isYellow);
      console.error('Toggle star failed:', data);
      return;
    }
    
    // Keep UI in sync with server response
    if (typeof data.starred !== 'undefined') {
      const serverStarred = data.starred === 1;
      starBtn.classList.toggle('yellow', serverStarred);
      starBtn.classList.toggle('white', !serverStarred);
    }
  } catch (err) {
    // Revert on network error
    starBtn.classList.toggle('yellow', isYellow);
    starBtn.classList.toggle('white', !isYellow);
    console.error('Failed to toggle star:', err);
  }
}

// Show completion message
function showCompletionMessage() {
  const container = document.getElementById('quizContainer');
  const navButtons = document.getElementById('navigationButtons');
  
  container.innerHTML = `
    <div id="completionMessage">
      <h2>🎉 Quiz Complete!</h2>
      <p><strong>Total Questions:</strong> ${quizCards.length}</p>
      <p><strong>Correct Answers:</strong> ${correctCount}</p>
      <p><strong>Skipped:</strong> ${skippedCount}</p>
      <p><strong>Accuracy:</strong> ${quizCards.length > 0 ? Math.round((correctCount / quizCards.length) * 100) : 0}%</p>
      <button onclick="goBack()">Back to Quiz Options</button>
    </div>
  `;
  
  navButtons.style.display = 'none';
}

// Show message when no quiz data available
function showNoQuizMessage() {
  const container = document.getElementById('quizContainer');
  const navButtons = document.getElementById('navigationButtons');
  
  container.innerHTML = `
    <div id="completionMessage">
      <h2>No Quiz Available</h2>
      <p>No questions found with the selected filters.</p>
      <button onclick="goBack()">Back to Quiz Options</button>
    </div>
  `;
  
  navButtons.style.display = 'none';
  document.getElementById('scoreBoard').style.display = 'none';
}
