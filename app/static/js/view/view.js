// =============================== View page navigation ===============================

// Only re-executes inline scripts (no src). External scripts are already loaded and
// running in memory — re-creating their <script src> elements would re-execute them
// but their DOMContentLoaded callbacks would never fire (event already fired).
function _reexecuteInlineScripts(container) {
	container.querySelectorAll('script:not([src])').forEach(inert => {
		const live = document.createElement('script');
		[...inert.attributes].forEach(a => live.setAttribute(a.name, a.value));
		live.textContent = inert.textContent;
		inert.replaceWith(live);
	});
}

async function navigateWithAuth(url) {
	const response = await AUTH.request(url, { method: 'GET' });
	if (!response) return; // AUTH already redirected to login

	if (!response.ok) {
		console.error('Navigation failed:', response.status, url);
		return;
	}

	const html = await response.text();
	const newDoc = new DOMParser().parseFromString(html, 'text/html');

	window.history.pushState({}, '', url);
	document.title = newDoc.title;
	// replaceChildren moves nodes from newDoc — Array.from snapshots the live NodeList first
	document.head.replaceChildren(...Array.from(newDoc.head.childNodes));
	document.body.replaceChildren(...Array.from(newDoc.body.childNodes));
	// Re-run inline body scripts (e.g. the auth-redirect check).
	// Then call initViewPage() directly — DOMContentLoaded won't fire again.
	_reexecuteInlineScripts(document.body);
	initViewPage();
}

function navigateWithAuthForm(form) {
	const params = new URLSearchParams(new FormData(form));
	navigateWithAuth(`${form.action}?${params.toString()}`);
}

// =============================== Search word ===============================
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
		const response = await AUTH.request(url, {
			method: 'GET',
			headers: {'Content-Type': 'application/json'},
		});
		
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
						<a href="${bpPrefix}/view/word/${w.word_id}" onclick="event.preventDefault(); navigateWithAuth(this.href)">
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

// =============================== Page init ===============================
// All DOM-dependent setup lives here so it runs both on initial page load
// (via DOMContentLoaded) and after navigateWithAuth swaps the DOM
// (DOMContentLoaded does not fire a second time).
function initViewPage() {
	// ----- View page navigation buttons (view.html) -----
	["btn-search-word", "btn-view-words", "btn-view-books"].forEach(id => {
		const btn = document.getElementById(id);
		if (btn) btn.addEventListener("click", () => navigateWithAuth(btn.dataset.url));
	});

	// ----- Search word form (search_word.html) -----
	const searchForm = document.getElementById("searchWordForm");
	if (searchForm) {
		searchForm.addEventListener("submit", async function(e) {
			e.preventDefault();
			await handleViewSubmit(this, "searchWordNotice", "showRes");
		});
	}

	// =============================== View specific word ===============================
	// ----- Toggle known/unknown -----
	const toggleBtn = document.getElementById('toggleKnown');
	if (toggleBtn) {
		const buildLabel = (priority) => (parseFloat(priority) || 0) > 0 ? 'Mark as known' : 'Unmark known';

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
				const res = await AUTH.request(url, {
					method: 'POST',
					headers: {'Content-Type': 'application/json'},
					body: JSON.stringify({ word_id: wordId, update_to_known: updateToKnown, quized: quized, occurrence: occurrence})
				});

				const data = await (res.ok ? res.json() : Promise.resolve({ success: false }));
				if (!res.ok || !data.success) {
					console.error('Toggle known failed', data);
					alert('Failed to change known status');
					return;
				}

				// Set priority (don't need to be real priority), just enough to change UI
				const newPriority = updateToKnown ? -1 : 1;
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
	}

	// ----- Word star toggle -----
	const wordStar = document.getElementById("wordStarToggle");
	if (wordStar) {
		wordStar.addEventListener("click", async () => {
			// Current star state
			const isYellow = wordStar.classList.contains("yellow");

			// Toggle UI immediately
			wordStar.classList.toggle("yellow", !isYellow);
			wordStar.classList.toggle("white", isYellow);

			const wordID = wordStar.dataset.id;
			const url = wordStar.dataset.toggleUrl || "/v1/toggle-star";
			const starParam = (!isYellow).toString(); // reverse of current state

			// Send change to backend
			try {
				const resp = await AUTH.request(url, {
					method: "POST",
					headers: {'Content-Type': 'application/json'},
					body: JSON.stringify({ id: wordID, objType: "word", star: starParam })
				});
				const data = await resp.json();

				if (!resp.ok || !data.success) {
					// revert UI on failure
					wordStar.classList.toggle("yellow", isYellow);
					wordStar.classList.toggle("white", !isYellow);
					console.error("Toggle star failed:", data);
					return;
				}

				// Keep UI in sync with server response if provided
				if (typeof data.starred !== "undefined") {
					const serverStarred = data.starred === 1;
					wordStar.classList.toggle("yellow", serverStarred);
					wordStar.classList.toggle("white", !serverStarred);
				}
			} catch (err) {
				// revert on network error
				wordStar.classList.toggle("yellow", isYellow);
				wordStar.classList.toggle("white", !isYellow);
				console.error("Failed to toggle star:", err);
			}
		});
	}

	// ----- Play audio -----
	const playBtn = document.getElementById("playBtn");
	if (playBtn) {
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
	}

	// =============================== Book ===============================
	// ----- Book star toggle -----
	document.querySelectorAll(".book-star-toggle").forEach(star => {
		star.addEventListener("click", async () => {
			// Current star state
			const isYellow = star.classList.contains("yellow");

			// Toggle UI immediately
			star.classList.toggle("yellow", !isYellow);
			star.classList.toggle("white", isYellow);

			const bookID = star.dataset.id;
			const url = star.dataset.toggleUrl || "/v1/toggle-star";
			const starParam = (!isYellow).toString(); // reverse of current state

			// Send change to backend
			try {
				const resp = await AUTH.request(url, {
					method: "POST",
					headers: {'Content-Type': 'application/json'},
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

	// ----- Delete book -----
	const deleteBtn = document.getElementById('deleteBook');
	if (deleteBtn) {
		deleteBtn.addEventListener('click', async function () {
			const bookId = this.dataset.id;
			const bookName = this.dataset.name || '';
			const url = this.dataset.deleteUrl || '/del/book';

			const ok = confirm(`Are you sure to delete book ${bookName} along its words and sentences?`);
			if (!ok) return;

			this.disabled = true;
			try {
				const res = await AUTH.request(url, {
					method: 'POST',
					headers: {'Content-Type': 'application/json'},
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
	}
}

document.addEventListener("DOMContentLoaded", initViewPage);