let lastSelectedFile = null;

function showFileName() {
  // `const` means a var that won't be reassign, their properties are still mutable!
  const input = document.getElementById('fileInput');
  const fileInfo = document.getElementById('fileInfo');
  const fileName = document.getElementById('fileName');
  const stringBoxCont = document.getElementById('stringBoxContainer');
  const stringProgressLine = document.getElementById('stringProgressLine');
  const stringNotice = document.getElementById('stringNotice');

  // Disable display of the `Enter String` option if choose `Choose File`
  stringBoxCont.style.display = "none"
  stringProgressLine.style.display = "none"
  stringNotice.style.display = "none"

  // Note that a file is chosen through <input type="file" ... onchange="showFileName()">
  // If a file is chosen
  if (input.files.length > 0) {
    lastSelectedFile = input.files[0]
    fileName.textContent = "📄 " + input.files[0].name; // update the span fileName to show the file name
    fileInfo.style.display = "flex";    // change display from 'none' to 'flex' to show the div box
  } else if (lastSelectedFile) {
    fileName.textContent = "📄 " + lastSelectedFile.name;
    fileInfo.style.display = "flex";
  } else {
    fileName.textContent = "";
    fileInfo.style.display = "none";
  }
}

document.getElementById("fileForm").addEventListener("submit", async function(e) {
  e.preventDefault(); // no page reload

  const input = document.getElementById('fileInput');
  const formData = new FormData(this);

  if (input.files.length === 0 && lastSelectedFile) {
    formData.set('submittedFilename', lastSelectedFile, lastSelectedFile.name);
  }
  handleFormSubmit(this, "fileNotice", "fileProgressLine", formData);
});



function showTextBox() {
  const stringBoxCont = document.getElementById('stringBoxContainer');
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

document.getElementById("stringForm").addEventListener("submit", async function(e) {
  e.preventDefault(); // no page reload
  handleFormSubmit(this, "stringNotice", "stringProgressLine", null);
});



async function handleFormSubmit(form, noticeId, progressId, formData) {
  // `form` (or `this` in function call), is a normal, contains the chosen file name
  // `formData` is manual created form that includes the chosen file name

  // Get the backend response from `main_ep.upload_file`
  if (!formData) {
    formData = new FormData(form);
  }

  const response = await fetch(form.action, { method: "POST", body: formData });
  const notice = document.getElementById(noticeId);
  const progressLine = document.getElementById(progressId);

  notice.style.display = "none";
  progressLine.style.display = "block";
  progressLine.textContent = "Starting...";

  const decoder = new TextDecoder();
  const reader = response.body.getReader(); // const resultText = await response.text();
  let finalText = "";

  while (true) {
    const {done, value} = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });
    chunk.split("\n\n").forEach(line => {
      if (line.startsWith("data: ")) {
        const msg = line.replace("data: ", "").trim();
        progressLine.textContent = msg;
      } else {
        finalText = line.trim()
      }
    });
  }
  progressLine.style.display = "none";

  // Use the `notice` earlier for notification popup
  notice.style.display = "block";
  if (finalText.toLowerCase().includes("error")) {
    notice.style.color = "red";
  } else {
    notice.style.color = "green";
  }
  notice.textContent = finalText;
}
