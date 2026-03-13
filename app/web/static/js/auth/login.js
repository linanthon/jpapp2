const HOME_URL = document.documentElement.getAttribute('data-home-url');

document.getElementById('login-form').addEventListener('submit', async (e) => {
	e.preventDefault();
	
	const username = document.getElementById('username').value;
	const password = document.getElementById('password').value;
	const messageDiv = document.getElementById('message');
	
	try {
		messageDiv.className = '';
		messageDiv.textContent = 'Logging in...';
		
		await AUTH.login(username, password);
		
		messageDiv.className = 'success';
		messageDiv.textContent = 'Login successful! Redirecting...';
		
		// Redirect to home after 1 second
		setTimeout(() => {
			window.location.href = HOME_URL;
		}, 1000);
	} catch (error) {
		messageDiv.className = 'error';
		messageDiv.textContent = `Login failed: ${error.message}`;
	}
});