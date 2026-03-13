const HOME_URL = document.documentElement.getAttribute('data-home-url');

document.getElementById('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const username = document.getElementById('username').value;
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const messageDiv = document.getElementById('message');
    
    try {
        messageDiv.className = '';
        messageDiv.textContent = 'Creating account...';
        
        await AUTH.register(username, email, password);
        
        messageDiv.className = 'success';
        messageDiv.textContent = 'Account created successfully! Logging in...';
        
        // Auto-login after registration
        setTimeout(async () => {
            await AUTH.login(username, password);
            window.location.href = HOME_URL;
        }, 1500);
    } catch (error) {
        messageDiv.className = 'error';
        messageDiv.textContent = `Registration failed: ${error.message}`;
    }
});