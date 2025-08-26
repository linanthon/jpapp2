function showFileName() {
  // Get element from HTML
  // `const` means a var that won't be reassign, their properties are still mutable!
  const input = document.getElementById('fileInput');
  const fileInfo = document.getElementById('fileInfo');
  const fileName = document.getElementById('fileName'); // <span id="fileName"></span>

  // Note that a file is chosen through <input type="file" ... onchange="showFileName()">
  // If a file is chosen
  if (input.files.length > 0) {
    fileName.textContent = "📄 " + input.files[0].name; // update the span fileName to show the file name
    fileInfo.style.display = "flex";    // change display from 'none' to 'flex' to show the div box
  }
}

document.getElementById("fileForm").addEventListener("submit", async function(e) {
  e.preventDefault(); // no page reload

  // Get the backend response from `main_ep.upload_file`
  const formData = new FormData(this);
  const response = await fetch(this.action, { method: "POST", body: formData });
  const notice = document.getElementById("fileNotice");
  const progressLine = document.getElementById("fileProgressLine");

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

        if (msg.includes()) {
          progressLine.textContent = "";
        } else {
          progressLine.textContent = msg;
        }
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
});



function showTextBox() {
  const stringBoxCont = document.getElementById('stringBoxContainer');
  stringBoxCont.style.display = "block"
}

document.getElementById("stringForm").addEventListener("submit", async function(e) {
  e.preventDefault();

  const formData = new FormData(this);
  const response = await fetch(this.action, {method: "POST", body: formData});
  const notice = document.getElementById("stringNotice");
  const resultText = await response.text();

  notice.style.display = "block";
  if (response.ok) {
    notice.style.color = "green";
  } else {
    notice.style.color = "red";
  }
  notice.textContent = resultText;
});
